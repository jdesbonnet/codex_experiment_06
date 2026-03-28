from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps


CALIBRATION_READINGS: Dict[str, Dict[str, int]] = {
    "20260324_151209.jpg": {"sys_mmhg": 134, "dia_mmhg": 84, "pulse_bpm": 78},
    "20260324_200920.jpg": {"sys_mmhg": 127, "dia_mmhg": 80, "pulse_bpm": 69},
    "20260324_200932.jpg": {"sys_mmhg": 127, "dia_mmhg": 80, "pulse_bpm": 69},
    "20260327_173714.jpg": {"sys_mmhg": 146, "dia_mmhg": 92, "pulse_bpm": 76},
    "20260327_173727.jpg": {"sys_mmhg": 146, "dia_mmhg": 92, "pulse_bpm": 76},
}

REFERENCE_IMAGE_BASENAME = "20260324_200932.jpg"
GROUND_TRUTH_CSV_BASENAME = "bp_monitor_ground_truth.csv"
BLANK_LABEL = "_"

# Cell coordinates on the aligned reference image after EXIF correction.
PRESSURE_CELL_BOXES: Dict[str, Tuple[int, int, int, int]] = {
    "sys1": (1290, 1180, 1465, 1460),
    "sys2": (1490, 1170, 1765, 1470),
    "sys3": (1725, 1170, 1965, 1470),
    "dia1": (1440, 1450, 1765, 1845),
    "dia2": (1740, 1450, 1995, 1845),
    "pulse1": (1660, 1920, 1820, 2235),
    "pulse2": (1825, 1920, 1985, 2235),
}

AUX_CELL_BOXES: Dict[str, Tuple[int, int, int, int]] = {
    "time_h1": (760, 945, 865, 1110),
    "time_h2": (845, 945, 955, 1110),
    "time_m1": (975, 945, 1085, 1110),
    "time_m2": (1065, 945, 1175, 1110),
    "day1": (760, 1110, 860, 1280),
    "day2": (835, 1110, 940, 1280),
    "month1": (965, 1110, 1045, 1280),
    "month2": (1040, 1110, 1140, 1280),
    "user1": (780, 1410, 940, 1720),
}

DISPLAY_BOX = (770, 690, 2240, 2280)

CELL_BOXES: Dict[str, Tuple[int, int, int, int]] = {**PRESSURE_CELL_BOXES, **AUX_CELL_BOXES}
PRESSURE_CELL_ORDER = tuple(PRESSURE_CELL_BOXES.keys())
AUX_CELL_ORDER = tuple(AUX_CELL_BOXES.keys())
CELL_ORDER = PRESSURE_CELL_ORDER + AUX_CELL_ORDER


@dataclass(frozen=True)
class ReaderConfig:
    calibration_root: Path
    input_size: Tuple[int, int] = (64, 96)
    orb_size: Tuple[int, int] = (900, 1200)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_calibration_root(path: Path | None = None) -> Path:
    if path is not None:
        return path
    return repo_root() / "experiments"


def load_grayscale_image(path: Path) -> np.ndarray:
    image = ImageOps.exif_transpose(Image.open(path)).convert("L")
    return np.array(image)


def load_color_image(path: Path) -> np.ndarray:
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def resize_for_orb(image: np.ndarray, size: Tuple[int, int]) -> np.ndarray:
    return cv2.resize(image, size)


def cell_truths_for_reading(reading: Dict[str, int]) -> Dict[str, str]:
    sys_text = f"{reading['sys_mmhg']:03d}"
    dia_text = f"{reading['dia_mmhg']:02d}"
    pulse_text = f"{reading['pulse_bpm']:02d}"
    return {
        "sys1": sys_text[0],
        "sys2": sys_text[1],
        "sys3": sys_text[2],
        "dia1": dia_text[0],
        "dia2": dia_text[1],
        "pulse1": pulse_text[0],
        "pulse2": pulse_text[1],
    }


def load_ground_truth_rows(calibration_root: Path) -> List[Dict[str, str]]:
    csv_path = calibration_root / GROUND_TRUTH_CSV_BASENAME
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _left_padded_digits(value: str, width: int) -> List[str]:
    digits = [char for char in value if char.isdigit()]
    if not digits:
        return [BLANK_LABEL] * width
    trimmed = digits[-width:]
    return [BLANK_LABEL] * (width - len(trimmed)) + trimmed


def aux_cell_truths_from_ground_truth_row(row: Dict[str, str]) -> Dict[str, str]:
    truths: Dict[str, str] = {}

    lcd_time = (row.get("lcd_time") or "").strip()
    if lcd_time:
        hours, minutes = lcd_time.split(":", 1)
        hour_digits = _left_padded_digits(hours, 2)
        minute_digits = _left_padded_digits(minutes, 2)
        truths.update(
            {
                "time_h1": hour_digits[0],
                "time_h2": hour_digits[1],
                "time_m1": minute_digits[0],
                "time_m2": minute_digits[1],
            }
        )

    lcd_day = (row.get("lcd_day") or "").strip()
    if lcd_day:
        day_digits = _left_padded_digits(lcd_day, 2)
        truths.update({"day1": day_digits[0], "day2": day_digits[1]})

    lcd_month = (row.get("lcd_month") or "").strip()
    if lcd_month:
        month_digits = _left_padded_digits(lcd_month, 2)
        truths.update({"month1": month_digits[0], "month2": month_digits[1]})

    user_number = (row.get("user_number") or "").strip()
    if user_number:
        truths["user1"] = user_number[-1]

    return truths


def build_orb_reference(reference_image: np.ndarray, orb_size: Tuple[int, int]) -> Tuple[cv2.ORB, List[cv2.KeyPoint], np.ndarray]:
    orb = cv2.ORB_create(3000)
    small = resize_for_orb(reference_image, orb_size)
    keypoints, descriptors = orb.detectAndCompute(small, None)
    if descriptors is None or len(keypoints) < 10:
        raise RuntimeError("failed to build ORB reference descriptors")
    return orb, keypoints, descriptors


def compute_alignment_homography(
    image: np.ndarray,
    reference_image: np.ndarray,
    orb: cv2.ORB,
    reference_keypoints: List[cv2.KeyPoint],
    reference_descriptors: np.ndarray,
    orb_size: Tuple[int, int],
) -> Tuple[np.ndarray, int]:
    small = resize_for_orb(image, orb_size)
    keypoints, descriptors = orb.detectAndCompute(small, None)
    if descriptors is None or len(keypoints) < 10:
        raise RuntimeError("failed to extract enough ORB features from input")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = matcher.knnMatch(reference_descriptors, descriptors, k=2)
    good_matches = [m for m, n in matches if m.distance < 0.75 * n.distance]
    if len(good_matches) < 12:
        raise RuntimeError(f"not enough ORB matches for alignment: {len(good_matches)}")

    src = np.float32([reference_keypoints[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst = np.float32([keypoints[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    homography_small, _ = cv2.findHomography(dst, src, cv2.RANSAC, 5.0)
    if homography_small is None:
        raise RuntimeError("failed to compute input->reference homography")

    scale_x = reference_image.shape[1] / orb_size[0]
    scale_y = reference_image.shape[0] / orb_size[1]
    up = np.array([[scale_x, 0.0, 0.0], [0.0, scale_y, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    down = np.array([[1.0 / scale_x, 0.0, 0.0], [0.0, 1.0 / scale_y, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    homography_full = up @ homography_small @ down
    return homography_full, len(good_matches)


def warp_to_reference(image: np.ndarray, homography_full: np.ndarray, reference_shape: Tuple[int, int]) -> np.ndarray:
    height, width = reference_shape
    return cv2.warpPerspective(image, homography_full, (width, height))


def align_to_reference(
    image: np.ndarray,
    reference_image: np.ndarray,
    orb: cv2.ORB,
    reference_keypoints: List[cv2.KeyPoint],
    reference_descriptors: np.ndarray,
    orb_size: Tuple[int, int],
) -> Tuple[np.ndarray, int]:
    homography_full, good_match_count = compute_alignment_homography(
        image,
        reference_image,
        orb,
        reference_keypoints,
        reference_descriptors,
        orb_size,
    )
    aligned = warp_to_reference(image, homography_full, reference_image.shape)
    return aligned, good_match_count


def crop_digit_from_cell(image: np.ndarray, box: Tuple[int, int, int, int], output_size: Tuple[int, int]) -> np.ndarray:
    x0, y0, x1, y1 = box
    roi = image[y0:y1, x0:x1]
    blur = cv2.GaussianBlur(roi, (5, 5), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    keep = np.zeros_like(binary)
    min_area = max(20, roi.size // 5000)
    for index in range(1, component_count):
        _x, _y, _w, _h, area = stats[index]
        if area >= min_area:
            keep[labels == index] = 255

    ys, xs = np.where(keep > 0)
    if len(xs) == 0:
        return np.zeros((output_size[1], output_size[0]), dtype=np.uint8)

    x0b, x1b = xs.min(), xs.max() + 1
    y0b, y1b = ys.min(), ys.max() + 1
    crop = keep[y0b:y1b, x0b:x1b]

    target_w, target_h = output_size
    scale = min(target_w / crop.shape[1], target_h / crop.shape[0])
    resized = cv2.resize(
        crop,
        (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale))),
        interpolation=cv2.INTER_AREA,
    )
    canvas = np.zeros((target_h, target_w), dtype=np.uint8)
    offset_y = (target_h - resized.shape[0]) // 2
    offset_x = (target_w - resized.shape[1]) // 2
    canvas[offset_y : offset_y + resized.shape[0], offset_x : offset_x + resized.shape[1]] = resized
    return canvas


def combine_truth_maps(config: ReaderConfig) -> Dict[str, Dict[str, str]]:
    combined: Dict[str, Dict[str, str]] = {}
    for basename, reading in CALIBRATION_READINGS.items():
        combined.setdefault(basename, {}).update(cell_truths_for_reading(reading))
    for row in load_ground_truth_rows(config.calibration_root):
        basename = (row.get("filename") or "").strip()
        if not basename:
            continue
        combined.setdefault(basename, {}).update(aux_cell_truths_from_ground_truth_row(row))
    return combined


def build_template_bank(
    config: ReaderConfig,
    exclude_basenames: Iterable[str] = (),
) -> Tuple[np.ndarray, cv2.ORB, List[cv2.KeyPoint], np.ndarray, Dict[str, Dict[str, List[np.ndarray]]]]:
    reference_path = config.calibration_root / REFERENCE_IMAGE_BASENAME
    if not reference_path.exists():
        raise FileNotFoundError(f"missing reference image: {reference_path}")

    reference_image = load_grayscale_image(reference_path)
    orb, reference_keypoints, reference_descriptors = build_orb_reference(reference_image, config.orb_size)
    excluded = set(exclude_basenames)

    bank: Dict[str, Dict[str, List[np.ndarray]]] = {cell: {} for cell in CELL_ORDER}
    truth_map = combine_truth_maps(config)
    for basename, truths in truth_map.items():
        if basename in excluded:
            continue
        sample_path = config.calibration_root / basename
        if not sample_path.exists():
            continue
        aligned, _ = align_to_reference(
            load_grayscale_image(sample_path),
            reference_image,
            orb,
            reference_keypoints,
            reference_descriptors,
            config.orb_size,
        )
        for cell_name, digit in truths.items():
            template = crop_digit_from_cell(aligned, CELL_BOXES[cell_name], config.input_size)
            bank[cell_name].setdefault(digit, []).append(template)
    return reference_image, orb, reference_keypoints, reference_descriptors, bank


def classify_digit(template_bank: Dict[str, List[np.ndarray]], candidate: np.ndarray) -> Tuple[str, float, Dict[str, float]]:
    scores: Dict[str, float] = {}
    for digit, templates in template_bank.items():
        distances = [
            float(np.mean(np.abs(candidate.astype(np.int16) - template.astype(np.int16))))
            for template in templates
        ]
        scores[digit] = min(distances)

    ranked = sorted(scores.items(), key=lambda item: item[1])
    best_digit, best_score = ranked[0]
    if len(ranked) == 1:
        confidence = 1.0
    else:
        second_score = ranked[1][1]
        confidence = max(0.0, min(1.0, (second_score - best_score) / max(second_score, 1.0)))
    return best_digit, confidence, scores


def field_text_from_digits(digits: Dict[str, str]) -> Dict[str, int]:
    return {
        "sys_mmhg": int(digits["sys1"] + digits["sys2"] + digits["sys3"]),
        "dia_mmhg": int(digits["dia1"] + digits["dia2"]),
        "pulse_bpm": int(digits["pulse1"] + digits["pulse2"]),
    }


def _strip_blanks(digits: Iterable[str]) -> str:
    return "".join("" if digit == BLANK_LABEL else digit for digit in digits)


def aux_fields_from_digits(digits: Dict[str, str]) -> Dict[str, object]:
    time_hour = _strip_blanks([digits["time_h1"], digits["time_h2"]])
    time_minute = _strip_blanks([digits["time_m1"], digits["time_m2"]])
    lcd_time = ""
    if time_hour and len(time_minute) == 2:
        lcd_time = f"{int(time_hour)}:{time_minute}"

    lcd_day = _strip_blanks([digits["day1"], digits["day2"]])
    lcd_month = _strip_blanks([digits["month1"], digits["month2"]])
    user_number = _strip_blanks([digits["user1"]])

    return {
        "lcd_time": lcd_time,
        "lcd_day": str(int(lcd_day)) if lcd_day else "",
        "lcd_month": str(int(lcd_month)) if lcd_month else "",
        "user_number": user_number,
    }


def detect_blue_backlight(aligned_color: np.ndarray) -> Tuple[bool, float]:
    x0, y0, x1, y1 = DISPLAY_BOX
    roi = aligned_color[y0:y1, x0:x1]
    blue_mean = float(np.mean(roi[:, :, 0]))
    green_mean = float(np.mean(roi[:, :, 1]))
    red_mean = float(np.mean(roi[:, :, 2]))
    score = blue_mean - 0.5 * (green_mean + red_mean)
    return score >= 8.0, score


def build_warnings(reading: Dict[str, int], cell_confidence: Dict[str, float]) -> List[str]:
    warnings: List[str] = []
    if not (60 <= reading["sys_mmhg"] <= 260):
        warnings.append("sys_out_of_range")
    if not (30 <= reading["dia_mmhg"] <= 180):
        warnings.append("dia_out_of_range")
    if not (20 <= reading["pulse_bpm"] <= 240):
        warnings.append("pulse_out_of_range")
    if reading["sys_mmhg"] <= reading["dia_mmhg"]:
        warnings.append("sys_not_greater_than_dia")
    pressure_confidence = [cell_confidence[name] for name in PRESSURE_CELL_ORDER if name in cell_confidence]
    if pressure_confidence and min(pressure_confidence) < 0.05:
        warnings.append("low_confidence_digit")
    return warnings


def annotate_aligned_image(aligned: np.ndarray, reading: Dict[str, object], cell_confidence: Dict[str, float], warnings: List[str]) -> np.ndarray:
    annotated = cv2.cvtColor(aligned, cv2.COLOR_GRAY2BGR)
    for cell_name, (x0, y0, x1, y1) in CELL_BOXES.items():
        confidence = cell_confidence.get(cell_name, 0.0)
        color = (0, 180, 0) if confidence >= 0.2 else (0, 140, 255)
        thickness = 2 if cell_name in AUX_CELL_ORDER else 3
        cv2.rectangle(annotated, (x0, y0), (x1, y1), color, thickness)
        if cell_name in PRESSURE_CELL_ORDER:
            cv2.putText(
                annotated,
                f"{cell_name}:{confidence:.2f}",
                (x0, max(20, y0 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )

    title = (
        f"SYS {reading['sys_mmhg']}  DIA {reading['dia_mmhg']}  PUL {reading['pulse_bpm']}  "
        f"T {reading.get('lcd_time', '') or '-'}  D {reading.get('lcd_day', '') or '-'}" 
        f"/{reading.get('lcd_month', '') or '-'}  U {reading.get('user_number', '') or '-'}"
    )
    cv2.putText(annotated, title, (70, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 220, 255), 2, cv2.LINE_AA)
    if warnings:
        cv2.putText(
            annotated,
            "warnings: " + ", ".join(warnings),
            (70, 180),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 128, 255),
            2,
            cv2.LINE_AA,
        )
    return annotated
