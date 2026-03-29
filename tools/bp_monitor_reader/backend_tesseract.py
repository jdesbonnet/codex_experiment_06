from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

from backend_api import BackendError, ensure_prediction_shape
from common import (
    AUX_CELL_ORDER,
    CELL_BOXES,
    CELL_ORDER,
    PRESSURE_CELL_ORDER,
    ReaderConfig,
    aux_fields_from_digits,
    build_orb_reference,
    build_warnings,
    compute_alignment_homography,
    crop_digit_from_cell,
    detect_blue_backlight,
    field_text_from_digits,
    load_color_image,
    load_grayscale_image,
    REFERENCE_IMAGE_BASENAME,
    warp_to_reference,
)

CELL_WHITELIST = {name: "0123456789" for name in CELL_ORDER}


class TesseractBackend:
    name = "tesseract"

    def __init__(self) -> None:
        try:
            subprocess.run(
                ["tesseract", "--version"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:  # pragma: no cover
            raise BackendError("tesseract backend requires the 'tesseract' binary") from exc

    def build_context(self, config: ReaderConfig, exclude_basenames: set[str] | None = None) -> object:
        reference_path = config.calibration_root / REFERENCE_IMAGE_BASENAME
        if not reference_path.exists():
            raise FileNotFoundError(f"missing reference image: {reference_path}")
        reference_image = load_grayscale_image(reference_path)
        orb, reference_keypoints, reference_descriptors = build_orb_reference(reference_image, config.orb_size)
        return {
            "reference_image": reference_image,
            "orb": orb,
            "reference_keypoints": reference_keypoints,
            "reference_descriptors": reference_descriptors,
        }

    def read_image(self, image_path: Path, config: ReaderConfig, context: object, verbose: bool = False) -> Dict[str, object]:
        ctx = dict(context)
        reference_image = ctx["reference_image"]
        homography_full, good_match_count = compute_alignment_homography(
            load_grayscale_image(image_path),
            reference_image,
            ctx["orb"],
            ctx["reference_keypoints"],
            ctx["reference_descriptors"],
            config.orb_size,
        )
        aligned_gray = warp_to_reference(load_grayscale_image(image_path), homography_full, reference_image.shape)
        aligned_color = warp_to_reference(load_color_image(image_path), homography_full, reference_image.shape)

        digits: Dict[str, str] = {}
        cell_confidence: Dict[str, float] = {}
        for cell_name in CELL_ORDER:
            digit, confidence = self._extract_digit(aligned_gray, config, cell_name)
            digits[cell_name] = digit
            cell_confidence[cell_name] = confidence

        reading = field_text_from_digits(digits)
        reading.update(aux_fields_from_digits(digits))
        backlight_on, backlight_score = detect_blue_backlight(aligned_color)
        reading["blue_backlight_on"] = backlight_on
        reading["backlight_score"] = backlight_score
        warnings = build_warnings(reading, cell_confidence)

        prediction = {
            "source_image": str(image_path),
            "method": "tesseract_v2",
            "alignment_good_matches": good_match_count,
            "sys_mmhg": reading["sys_mmhg"],
            "dia_mmhg": reading["dia_mmhg"],
            "pulse_bpm": reading["pulse_bpm"],
            "lcd_time": reading["lcd_time"],
            "lcd_day": reading["lcd_day"],
            "lcd_month": reading["lcd_month"],
            "user_number": reading["user_number"],
            "blue_backlight_on": reading["blue_backlight_on"],
            "backlight_score": backlight_score,
            "confidence": min(cell_confidence[name] for name in PRESSURE_CELL_ORDER),
            "aux_confidence": min(cell_confidence[name] for name in AUX_CELL_ORDER),
            "cell_digits": digits,
            "cell_confidence": cell_confidence,
            "cell_scores": {},
            "warnings": warnings,
            "_aligned_image": aligned_gray,
        }
        return ensure_prediction_shape(prediction)

    def _extract_digit(self, aligned_gray: np.ndarray, config: ReaderConfig, cell_name: str) -> Tuple[str, float]:
        candidate = crop_digit_from_cell(aligned_gray, CELL_BOXES[cell_name], config.input_size)
        variants = self._variants(candidate)
        best_text = ""
        best_score = 0.0
        for image in variants:
            text = self._run_tesseract(image, CELL_WHITELIST[cell_name])
            cleaned = "".join(ch for ch in text if ch.isdigit())[:1]
            score = 1.0 if cleaned else 0.0
            if score > best_score:
                best_text = cleaned
                best_score = score
        return best_text or "0", best_score

    def _variants(self, image: np.ndarray) -> List[np.ndarray]:
        enlarged = cv2.resize(image, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
        _, th = cv2.threshold(enlarged, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, th_inv = cv2.threshold(enlarged, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return [enlarged, th, th_inv]

    def _run_tesseract(self, image: np.ndarray, whitelist: str) -> str:
        with tempfile.NamedTemporaryFile(suffix=".png") as handle:
            if not cv2.imwrite(handle.name, image):
                return ""
            result = subprocess.run(
                [
                    "tesseract",
                    handle.name,
                    "stdout",
                    "--psm",
                    "10",
                    "-c",
                    f"tessedit_char_whitelist={whitelist}",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return ""
            return result.stdout.strip()
