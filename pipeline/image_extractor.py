from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import pymupdf as fitz
import numpy as np


@dataclass(slots=True)
class PageImage:
    image: np.ndarray
    source: str
    dpi: float
    path: str | None = None


class ImageExtractor:
    def __init__(self, config: dict) -> None:
        self.config = config

    def extract_or_render(self, doc: fitz.Document, page: fitz.Page, output_path: str | Path | None = None) -> PageImage:
        render_cfg = self.config.get("render", {})
        requested_dpi = float(render_cfg.get("default_dpi", 400))
        minimum_dpi = float(render_cfg.get("minimum_dpi", 300))
        maximum_dpi = float(render_cfg.get("maximum_dpi", 600))
        dpi = max(minimum_dpi, min(maximum_dpi, requested_dpi))
        prefer_embedded = bool(render_cfg.get("use_embedded_image_when_possible", True))
        image: np.ndarray | None = None
        source = "rendered"

        if prefer_embedded:
            image = self._extract_full_page_image(doc, page)
            if image is not None:
                source = "embedded"
                page_width_in = page.rect.width / 72.0
                embedded_dpi = image.shape[1] / page_width_in if page_width_in else dpi
                minimum_useful_dpi = float(render_cfg.get("embedded_image_minimum_dpi", render_cfg.get("minimum_dpi", 300)))
                if embedded_dpi < minimum_useful_dpi and render_cfg.get("rerender_low_resolution_embedded_images", True):
                    image = None
                    source = "rendered_low_resolution_scan"
                else:
                    dpi = embedded_dpi

        if image is None:
            scale = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, colorspace=fitz.csRGB)
            image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
            else:
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        path_str = None
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(output_path), image)
            path_str = str(output_path)
        return PageImage(image=image, source=source, dpi=float(dpi), path=path_str)

    def _extract_full_page_image(self, doc: fitz.Document, page: fitz.Page) -> np.ndarray | None:
        page_area = page.rect.width * page.rect.height
        candidates: list[tuple[float, int]] = []
        for image_info in page.get_images(full=True):
            xref = int(image_info[0])
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            coverage = max((r.width * r.height / page_area for r in rects), default=0.0)
            candidates.append((coverage, xref))
        candidates.sort(reverse=True)
        for coverage, xref in candidates:
            if coverage < 0.80:
                continue
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.alpha:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                if pix.n == 1:
                    arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
                elif pix.n >= 3:
                    arr = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2BGR)
                return arr.copy()
            except Exception:
                continue
        return None
