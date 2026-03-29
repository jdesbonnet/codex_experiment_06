from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import cv2
import numpy as np

from backend_api import BackendError, ensure_prediction_shape
from common import (
    ReaderConfig,
    REFERENCE_IMAGE_BASENAME,
    build_orb_reference,
    compute_alignment_homography,
    detect_blue_backlight,
    load_color_image,
    load_grayscale_image,
    warp_to_reference,
)

# Coarse ROIs on the aligned reference image. This backend intentionally uses
# larger field regions than the calibrated template backend.
FIELD_ROIS: Dict[str, Tuple[int, int, int, int]] = {
    "sys": (1260, 1120, 1995, 1505),
    "dia": (1400, 1410, 2010, 1885),
    "pulse": (1600, 1865, 2010, 2275),
    "time": (745, 915, 1185, 1125),
    "date": (735, 1090, 1150, 1315),
    "user": (735, 1365, 985, 1755),
}


class PaddleOCRBackend:
    name = "paddleocr"

    def __init__(self) -> None:
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", "/tmp/paddlex_cache")
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency path
            raise BackendError(
                "paddleocr backend requires the 'paddleocr' package; see tools/bp_monitor_reader/README.md"
            ) from exc
        self._paddleocr_cls = PaddleOCR

    def build_context(self, config: ReaderConfig, exclude_basenames: set[str] | None = None) -> object:
        reference_path = config.calibration_root / REFERENCE_IMAGE_BASENAME
        if not reference_path.exists():
            raise FileNotFoundError(f"missing reference image: {reference_path}")
        reference_image = load_grayscale_image(reference_path)
        orb, reference_keypoints, reference_descriptors = build_orb_reference(reference_image, config.orb_size)
        ocr = self._paddleocr_cls(use_angle_cls=False, lang="en")
        return {
            "reference_image": reference_image,
            "orb": orb,
            "reference_keypoints": reference_keypoints,
            "reference_descriptors": reference_descriptors,
            "ocr": ocr,
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
        ocr = ctx["ocr"]

        sys_text, sys_conf = self._extract_field(ocr, aligned_gray, "sys")
        dia_text, dia_conf = self._extract_field(ocr, aligned_gray, "dia")
        pulse_text, pulse_conf = self._extract_field(ocr, aligned_gray, "pulse")
        time_text, time_conf = self._extract_field(ocr, aligned_gray, "time")
        date_text, date_conf = self._extract_field(ocr, aligned_gray, "date")
        user_text, user_conf = self._extract_field(ocr, aligned_gray, "user")

        sys_digits = self._parse_digits(sys_text, 3)
        dia_digits = self._parse_digits(dia_text, 2)
        pulse_digits = self._parse_digits(pulse_text, 2)
        lcd_time = self._parse_time(time_text)
        lcd_day, lcd_month = self._parse_date(date_text)
        user_number = self._parse_digits(user_text, 1)
        backlight_on, backlight_score = detect_blue_backlight(aligned_color)

        warnings: List[str] = []
        if sys_digits == "":
            warnings.append("missing_sys")
        if dia_digits == "":
            warnings.append("missing_dia")
        if pulse_digits == "":
            warnings.append("missing_pulse")
        if lcd_time == "":
            warnings.append("missing_time")
        if lcd_day == "" and lcd_month == "":
            warnings.append("missing_date")
        if user_number == "":
            warnings.append("missing_user")

        prediction = {
            "source_image": str(image_path),
            "method": "paddleocr_v1",
            "alignment_good_matches": good_match_count,
            "sys_mmhg": int(sys_digits) if sys_digits else -1,
            "dia_mmhg": int(dia_digits) if dia_digits else -1,
            "pulse_bpm": int(pulse_digits) if pulse_digits else -1,
            "lcd_time": lcd_time,
            "lcd_day": lcd_day,
            "lcd_month": lcd_month,
            "user_number": user_number,
            "blue_backlight_on": backlight_on,
            "backlight_score": backlight_score,
            "confidence": min(sys_conf, dia_conf, pulse_conf),
            "aux_confidence": min(time_conf, date_conf, user_conf),
            "cell_digits": {
                "sys": sys_text,
                "dia": dia_text,
                "pulse": pulse_text,
                "time": time_text,
                "date": date_text,
                "user": user_text,
            },
            "cell_confidence": {
                "sys": sys_conf,
                "dia": dia_conf,
                "pulse": pulse_conf,
                "time": time_conf,
                "date": date_conf,
                "user": user_conf,
            },
            "cell_scores": {},
            "warnings": warnings,
            "_aligned_image": aligned_gray,
        }
        return ensure_prediction_shape(prediction)

    def _extract_field(self, ocr: object, aligned_gray: np.ndarray, field_name: str) -> Tuple[str, float]:
        x0, y0, x1, y1 = FIELD_ROIS[field_name]
        roi = aligned_gray[y0:y1, x0:x1]
        variants = self._ocr_variants(roi)
        best_text = ""
        best_conf = 0.0
        for image in variants:
            result = ocr.ocr(image, cls=False)
            text, conf = self._collect_text(result)
            if conf > best_conf and text:
                best_text = text
                best_conf = conf
        return best_text, best_conf

    def _ocr_variants(self, roi: np.ndarray) -> List[np.ndarray]:
        enlarged = cv2.resize(roi, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        _, th_inv = cv2.threshold(enlarged, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        _, th = cv2.threshold(enlarged, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(enlarged)
        return [enlarged, th_inv, th, clahe]

    def _collect_text(self, result: object) -> Tuple[str, float]:
        if not result or not isinstance(result, list):
            return "", 0.0
        lines = result[0] if result and isinstance(result[0], list) else result
        if not lines:
            return "", 0.0
        tokens: List[Tuple[float, str, float]] = []
        for line in lines:
            if not isinstance(line, list) or len(line) < 2:
                continue
            box, rec = line[0], line[1]
            if not isinstance(rec, tuple) and not isinstance(rec, list):
                continue
            text = str(rec[0]).strip()
            conf = float(rec[1]) if len(rec) > 1 else 0.0
            if not text:
                continue
            x = float(box[0][0]) if box and box[0] else 0.0
            tokens.append((x, text, conf))
        if not tokens:
            return "", 0.0
        tokens.sort(key=lambda item: item[0])
        merged = "".join(text for _, text, _ in tokens)
        confidence = sum(conf for _, _, conf in tokens) / len(tokens)
        return merged, confidence

    def _parse_digits(self, text: str, width: int) -> str:
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return ""
        return digits[:width]

    def _parse_time(self, text: str) -> str:
        match = re.search(r"(\d{1,2})[:.]?(\d{2})", text)
        if not match:
            return ""
        hour = str(int(match.group(1)))
        minute = match.group(2)
        return f"{hour}:{minute}"

    def _parse_date(self, text: str) -> Tuple[str, str]:
        match = re.search(r"(\d{1,2})\D?(\d{1,2})", text)
        if not match:
            return "", ""
        return str(int(match.group(1))), str(int(match.group(2)))
