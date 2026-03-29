from __future__ import annotations

from pathlib import Path
from typing import Dict, Protocol, runtime_checkable

from common import ReaderConfig

READER_FIELDS = (
    "sys_mmhg",
    "dia_mmhg",
    "pulse_bpm",
    "lcd_time",
    "lcd_day",
    "lcd_month",
    "user_number",
    "blue_backlight_on",
)

GROUND_TRUTH_FIELD_MAP = {
    "systolic_mmhg": "sys_mmhg",
    "diastolic_mmhg": "dia_mmhg",
    "pulse_bpm": "pulse_bpm",
    "lcd_time": "lcd_time",
    "lcd_day": "lcd_day",
    "lcd_month": "lcd_month",
    "user_number": "user_number",
    "blue_backlight_on": "blue_backlight_on",
}


class BackendError(RuntimeError):
    pass


@runtime_checkable
class ReaderBackend(Protocol):
    name: str

    def build_context(self, config: ReaderConfig, exclude_basenames: set[str] | None = None) -> object:
        ...

    def read_image(self, image_path: Path, config: ReaderConfig, context: object, verbose: bool = False) -> Dict[str, object]:
        ...


def ensure_prediction_shape(prediction: Dict[str, object]) -> Dict[str, object]:
    missing = [field for field in READER_FIELDS if field not in prediction]
    if missing:
        raise BackendError(f"prediction missing fields: {', '.join(missing)}")
    return prediction
