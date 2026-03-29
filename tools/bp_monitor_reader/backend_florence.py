from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
from PIL import Image

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

MODEL_ID = "microsoft/Florence-2-base-ft"


def _resolve_model_source() -> tuple[str, bool]:
    hf_home = Path(os.environ.get("HF_HOME", "/tmp/hf_cache"))
    refs_main = hf_home / "hub" / "models--microsoft--Florence-2-base-ft" / "refs" / "main"
    if refs_main.exists():
        revision = refs_main.read_text().strip()
        snapshot = hf_home / "hub" / "models--microsoft--Florence-2-base-ft" / "snapshots" / revision
        if snapshot.exists():
            return str(snapshot), True
    return MODEL_ID, False
FIELD_ROIS: Dict[str, Tuple[int, int, int, int]] = {
    "sys": (1260, 1120, 1995, 1505),
    "dia": (1400, 1410, 2010, 1885),
    "pulse": (1600, 1865, 2010, 2275),
    "time": (745, 915, 1185, 1125),
    "date": (735, 1090, 1150, 1315),
    "user": (735, 1365, 985, 1755),
}


class FlorenceBackend:
    name = "florence"

    def __init__(self) -> None:
        os.environ.setdefault("HF_HOME", "/tmp/hf_cache")
        os.environ.setdefault("TRANSFORMERS_CACHE", "/tmp/hf_cache/transformers")
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoProcessor
        except ImportError as exc:  # pragma: no cover
            raise BackendError(
                "florence backend requires 'torch' and 'transformers'; see tools/bp_monitor_reader/README.md"
            ) from exc
        self._torch = torch
        self._auto_model = AutoModelForCausalLM
        self._auto_processor = AutoProcessor

    def build_context(self, config: ReaderConfig, exclude_basenames: set[str] | None = None) -> object:
        reference_path = config.calibration_root / REFERENCE_IMAGE_BASENAME
        if not reference_path.exists():
            raise FileNotFoundError(f"missing reference image: {reference_path}")
        reference_image = load_grayscale_image(reference_path)
        orb, reference_keypoints, reference_descriptors = build_orb_reference(reference_image, config.orb_size)
        model_source, local_only = _resolve_model_source()
        processor = self._auto_processor.from_pretrained(
            model_source,
            trust_remote_code=True,
            local_files_only=local_only,
        )
        model = self._auto_model.from_pretrained(
            model_source,
            trust_remote_code=True,
            local_files_only=local_only,
            low_cpu_mem_usage=False,
        )
        model = model.float()
        model.eval()
        self._torch.set_num_threads(max(1, min(4, self._torch.get_num_threads())))
        return {
            "reference_image": reference_image,
            "orb": orb,
            "reference_keypoints": reference_keypoints,
            "reference_descriptors": reference_descriptors,
            "processor": processor,
            "model": model,
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

        processor = ctx["processor"]
        model = ctx["model"]

        sys_text, sys_conf = self._extract_field(processor, model, aligned_gray, "sys")
        dia_text, dia_conf = self._extract_field(processor, model, aligned_gray, "dia")
        pulse_text, pulse_conf = self._extract_field(processor, model, aligned_gray, "pulse")
        time_text, time_conf = self._extract_field(processor, model, aligned_gray, "time")
        date_text, date_conf = self._extract_field(processor, model, aligned_gray, "date")
        user_text, user_conf = self._extract_field(processor, model, aligned_gray, "user")

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
            "method": "florence_v1",
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

    def _extract_field(self, processor: object, model: object, aligned_gray, field_name: str) -> Tuple[str, float]:
        x0, y0, x1, y1 = FIELD_ROIS[field_name]
        roi = aligned_gray[y0:y1, x0:x1]
        rgb = cv2.cvtColor(roi, cv2.COLOR_GRAY2RGB)
        pil = Image.fromarray(rgb)
        prompt = "<OCR>"
        inputs = processor(text=prompt, images=pil, return_tensors="pt")
        with self._torch.no_grad():
            generated_ids = model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=8,
                num_beams=1,
                do_sample=False,
            )
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed = processor.post_process_generation(generated_text, task=prompt, image_size=pil.size)
        text = self._flatten_parsed(parsed)
        confidence = 1.0 if text else 0.0
        return text, confidence

    def _flatten_parsed(self, parsed: object) -> str:
        if isinstance(parsed, dict):
            if "<OCR>" in parsed:
                value = parsed["<OCR>"]
                if isinstance(value, str):
                    return value.strip()
            values = []
            for value in parsed.values():
                if isinstance(value, str):
                    values.append(value)
                elif isinstance(value, list):
                    values.extend(str(item) for item in value)
            return " ".join(values).strip()
        return str(parsed).strip()

    def _parse_digits(self, text: str, width: int) -> str:
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return ""
        return digits[:width]

    def _parse_time(self, text: str) -> str:
        match = re.search(r"(\d{1,2})[:.]?(\d{2})", text)
        if not match:
            return ""
        return f"{int(match.group(1))}:{match.group(2)}"

    def _parse_date(self, text: str) -> Tuple[str, str]:
        match = re.search(r"(\d{1,2})\D+(\d{1,2})", text)
        if not match:
            digits = "".join(ch for ch in text if ch.isdigit())
            if len(digits) >= 2:
                if len(digits) == 2:
                    return str(int(digits[0])), str(int(digits[1]))
                return str(int(digits[:2])), str(int(digits[2:4])) if len(digits) >= 4 else ""
            return "", ""
        return str(int(match.group(1))), str(int(match.group(2)))
