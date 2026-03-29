from __future__ import annotations

from pathlib import Path
from typing import Dict

from backend_api import ReaderBackend, ensure_prediction_shape
from common import ReaderConfig
from template_reader import build_reader_context, read_one_image_with_context


class TemplateBackend:
    name = "template"

    def build_context(self, config: ReaderConfig, exclude_basenames: set[str] | None = None) -> object:
        return build_reader_context(config, exclude_basenames=exclude_basenames)

    def read_image(self, image_path: Path, config: ReaderConfig, context: object, verbose: bool = False) -> Dict[str, object]:
        prediction = read_one_image_with_context(image_path=image_path, config=config, context=context, verbose=verbose)
        return ensure_prediction_shape(prediction)
