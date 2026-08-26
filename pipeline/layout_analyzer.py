from __future__ import annotations

import cv2
import numpy as np

from models import BBox, TableRegion
from pipeline.bordered_table_detector import BorderedDetection, BorderedTableDetector


class LayoutAnalyzer:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.bordered = BorderedTableDetector(config)

    def analyze_image(self, binary: np.ndarray) -> BorderedDetection:
        return self.bordered.detect(binary)

    @staticmethod
    def draw_regions(image: np.ndarray, regions: list[TableRegion]) -> np.ndarray:
        overlay = image.copy()
        if overlay.ndim == 2:
            overlay = cv2.cvtColor(overlay, cv2.COLOR_GRAY2BGR)
        for region in regions:
            x0, y0, x1, y1 = region.bbox.to_int()
            cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 0, 255), 2)
            cv2.putText(overlay, region.table_id, (x0, max(15, y0 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
        return overlay

    @staticmethod
    def draw_grid(image: np.ndarray, region: TableRegion) -> np.ndarray:
        overlay = image.copy()
        if overlay.ndim == 2:
            overlay = cv2.cvtColor(overlay, cv2.COLOR_GRAY2BGR)
        for y in region.row_boundaries:
            cv2.line(overlay, (int(region.bbox.x0), int(y)), (int(region.bbox.x1), int(y)), (255, 0, 0), 1)
        for x in region.column_boundaries:
            cv2.line(overlay, (int(x), int(region.bbox.y0)), (int(x), int(region.bbox.y1)), (0, 128, 0), 1)
        return overlay
