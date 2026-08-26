from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from models import BBox, LayoutType, TableRegion


@dataclass(slots=True)
class BorderedDetection:
    horizontal_mask: np.ndarray
    vertical_mask: np.ndarray
    combined_mask: np.ndarray
    regions: list[TableRegion] = field(default_factory=list)
    cells_by_table: dict[str, list[BBox]] = field(default_factory=dict)
    measurements: dict[str, Any] = field(default_factory=dict)


class BorderedTableDetector:
    def __init__(self, config: dict) -> None:
        self.config = config.get("bordered_table", {})

    def detect(self, binary: np.ndarray) -> BorderedDetection:
        if not self.config.get("enabled", True):
            shape = binary.shape[:2]
            empty = np.zeros(shape, dtype=np.uint8)
            return BorderedDetection(empty, empty.copy(), empty.copy(), [], {}, {"disabled": True})
        if binary.ndim == 3:
            gray = cv2.cvtColor(binary, cv2.COLOR_BGR2GRAY)
        else:
            gray = binary.copy()
        if np.mean(gray) > 127:
            work = cv2.bitwise_not(gray)
        else:
            work = gray
        h, w = work.shape[:2]
        hc = self.config.get("horizontal", {})
        vc = self.config.get("vertical", {})
        h_kernel_w = max(3, int(w * float(hc.get("kernel_width_ratio", 0.03))))
        v_kernel_h = max(3, int(h * float(vc.get("kernel_height_ratio", 0.03))))
        horizontal = cv2.morphologyEx(work, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_w, int(hc.get("kernel_height", 1)))))
        vertical = cv2.morphologyEx(work, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(vc.get("kernel_width", 1)), v_kernel_h)))
        horizontal = self._merge_fragments(horizontal, int(hc.get("merge_gap_px", 12)), horizontal_axis=True)
        vertical = self._merge_fragments(vertical, int(vc.get("merge_gap_px", 12)), horizontal_axis=False)
        horizontal = self._filter_short_lines(
            horizontal,
            minimum_length=max(2, int(w * float(hc.get("minimum_line_length_ratio", 0.10)))),
            horizontal_axis=True,
        )
        vertical = self._filter_short_lines(
            vertical,
            minimum_length=max(2, int(h * float(vc.get("minimum_line_length_ratio", 0.10)))),
            horizontal_axis=False,
        )
        combined = cv2.bitwise_or(horizontal, vertical)

        regions: list[TableRegion] = []
        cells_by_table: dict[str, list[BBox]] = {}
        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_region_area = float(self.config.get("minimum_region_area_ratio", 0.01)) * h * w
        contours = sorted(contours, key=lambda c: cv2.boundingRect(c)[1])
        for idx, contour in enumerate(contours, start=1):
            x, y, rw, rh = cv2.boundingRect(contour)
            if rw * rh < min_region_area or rw < w * 0.15 or rh < h * 0.04:
                continue
            bbox = BBox(float(x), float(y), float(x + rw), float(y + rh))
            xs = self._line_positions(vertical[y : y + rh, x : x + rw], axis=0, offset=x)
            ys = self._line_positions(horizontal[y : y + rh, x : x + rw], axis=1, offset=y)
            xs = self._merge_positions(xs, float(self.config.get("column_merge_tolerance_px", 8)))
            ys = self._merge_positions(ys, float(self.config.get("row_merge_tolerance_px", 8)))
            if len(xs) < 2 or len(ys) < 2:
                continue
            table_id = f"table_{idx:02d}"
            cells = self._grid_cells(xs, ys)
            cell_cfg = self.config.get("cells", {})
            cells = [
                c
                for c in cells
                if c.width >= float(cell_cfg.get("minimum_width_px", 15))
                and c.height >= float(cell_cfg.get("minimum_height_px", 10))
                and c.area >= float(cell_cfg.get("minimum_area_px", 150))
            ]
            intersection_mask = cv2.bitwise_and(horizontal[y:y+rh, x:x+rw], vertical[y:y+rh, x:x+rw])
            intersection_pixels = int(np.count_nonzero(intersection_mask))
            minimum_intersection_area = int(self.config.get("intersections", {}).get("minimum_area", 3))
            count, _, stats, _ = cv2.connectedComponentsWithStats((intersection_mask > 0).astype(np.uint8), 8)
            intersection_count = sum(int(stats[index, cv2.CC_STAT_AREA]) >= minimum_intersection_area for index in range(1, count))
            expected = len(xs) * len(ys)
            confidence = min(1.0, 0.45 + 0.25 * min(1.0, len(cells) / max(1, (len(xs) - 1) * (len(ys) - 1))) + 0.30 * min(1.0, intersection_count / max(1, expected)))
            region = TableRegion(table_id, bbox, LayoutType.BORDERED_TABLE, confidence, ys, xs, {"intersection_count": intersection_count, "intersection_pixels": intersection_pixels})
            regions.append(region)
            cells_by_table[table_id] = cells

        return BorderedDetection(
            horizontal,
            vertical,
            combined,
            regions,
            cells_by_table,
            {
                "horizontal_density": float(np.mean(horizontal > 0)),
                "vertical_density": float(np.mean(vertical > 0)),
                "region_count": len(regions),
            },
        )

    @staticmethod
    def _filter_short_lines(mask: np.ndarray, minimum_length: int, horizontal_axis: bool) -> np.ndarray:
        """Remove connected line fragments shorter than the configured length."""
        count, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
        filtered = np.zeros_like(mask)
        for index in range(1, count):
            width = int(stats[index, cv2.CC_STAT_WIDTH])
            height = int(stats[index, cv2.CC_STAT_HEIGHT])
            length = width if horizontal_axis else height
            if length >= minimum_length:
                filtered[labels == index] = 255
        return filtered

    @staticmethod
    def _merge_fragments(mask: np.ndarray, gap: int, horizontal_axis: bool) -> np.ndarray:
        if gap <= 0:
            return mask
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (gap, 1) if horizontal_axis else (1, gap))
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    @staticmethod
    def _line_positions(mask: np.ndarray, axis: int, offset: int) -> list[float]:
        projection = np.sum(mask > 0, axis=axis)
        threshold = max(2, int((mask.shape[1-axis]) * 0.15))
        indices = np.where(projection >= threshold)[0]
        if indices.size == 0:
            return []
        groups = np.split(indices, np.where(np.diff(indices) > 1)[0] + 1)
        return [float(offset + np.mean(group)) for group in groups if len(group)]

    @staticmethod
    def _merge_positions(values: list[float], tolerance: float) -> list[float]:
        values = sorted(values)
        groups: list[list[float]] = []
        for value in values:
            if not groups or value - np.mean(groups[-1]) > tolerance:
                groups.append([value])
            else:
                groups[-1].append(value)
        return [float(np.mean(g)) for g in groups]

    @staticmethod
    def _grid_cells(xs: list[float], ys: list[float]) -> list[BBox]:
        cells: list[BBox] = []
        for y0, y1 in zip(ys, ys[1:]):
            for x0, x1 in zip(xs, xs[1:]):
                cells.append(BBox(x0, y0, x1, y1))
        return cells
