from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from models import BBox, TransformChain


class CropGenerator:
    def __init__(self, config: dict) -> None:
        self.config = config.get("cropping", {})

    def crop(
        self,
        image: np.ndarray,
        bbox: BBox,
        name: str,
        output_dir: Path,
        chain: TransformChain | None = None,
        *,
        save: bool = True,
    ) -> tuple[np.ndarray, TransformChain | None, str | None]:
        h, w = image.shape[:2]
        padding = self.config.get("padding", {}) if self.config.get("add_padding", True) else {}
        expanded = bbox.expanded(
            float(padding.get("left", 0)),
            float(padding.get("top", 0)),
            float(padding.get("right", 0)),
            float(padding.get("bottom", 0)),
        )
        if self.config.get("clamp_to_page", True):
            expanded = expanded.clamped(w, h)
        x0, y0, x1, y1 = expanded.to_int()
        if x1 <= x0 or y1 <= y0:
            return np.empty((0, 0), dtype=image.dtype), chain, None
        cropped = image[y0:y1, x0:x1].copy()
        output_path: str | None = None
        if save:
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{name}.png"
            cv2.imwrite(str(path), cropped)
            output_path = str(path)
        if chain is None:
            return cropped, None, output_path
        crop_bbox = BBox(x0, y0, x1, y1)
        child = TransformChain(
            chain.pdf_width_pt,
            chain.pdf_height_pt,
            int(crop_bbox.width),
            int(crop_bbox.height),
            chain.deskew_angle_deg,
            (crop_bbox.x0, crop_bbox.y0),
        )
        return cropped, child, output_path
