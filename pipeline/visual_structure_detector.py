from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any

import cv2
import numpy as np

from models import BBox, ExtractedCell, ExtractedRow, LayoutType, TableRegion


@dataclass(slots=True)
class VisualStructureDetection:
    """Geometry-only table structure inferred from page pixels.

    This detector deliberately performs no OCR/recognition.  It is used as a
    generic fallback for crop-only output modes when normal ruled-line geometry
    is absent or incomplete.  The implementation prefers strong visual evidence
    (repeated shaded/filled cell rectangles) and then falls back to text-ink
    projection/alignment when the page has no visible cell fill.
    """

    rows: list[ExtractedRow] = field(default_factory=list)
    regions: list[TableRegion] = field(default_factory=list)
    method: str = "none"
    confidence: float = 0.0
    measurements: dict[str, Any] = field(default_factory=dict)
    debug_masks: dict[str, np.ndarray] = field(default_factory=dict)


@dataclass(slots=True)
class _Box:
    x0: float
    y0: float
    x1: float
    y1: float
    area: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2.0


class VisualStructureDetector:
    """Generic no-OCR structure detector for scanned/image-only pages.

    Fallback order inside this component:

    1. Shaded/filled cell rectangles (very common in statements/invoices where
       separators are white/light and a classical black-line detector fails).
    2. Text-ink projection/alignment (borderless pages with no cell fill).

    No filename, company, bank, or template identity is used anywhere in this
    detector.  All decisions are based on measured page geometry.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.root = config
        self.config = config.get("visual_structure", {})

    def detect(
        self,
        image: np.ndarray,
        binary: np.ndarray | None,
        file_name: str,
        page_number: int,
    ) -> VisualStructureDetection:
        if not self.config.get("enabled", True):
            return VisualStructureDetection(method="disabled", measurements={"disabled": True})
        if image is None or image.size == 0:
            return VisualStructureDetection(method="none", measurements={"reason": "empty_image"})

        gray_full = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        full_h, full_w = gray_full.shape[:2]
        max_dimension = max(600, int(self.config.get("maximum_analysis_dimension", 1800)))
        analysis_scale = min(1.0, max_dimension / max(full_h, full_w))
        if analysis_scale < 1.0:
            analysis_w = max(1, int(round(full_w * analysis_scale)))
            analysis_h = max(1, int(round(full_h * analysis_scale)))
            gray = cv2.resize(
                gray_full,
                (analysis_w, analysis_h),
                interpolation=cv2.INTER_AREA,
            )
            binary_small = (
                cv2.resize(binary, (analysis_w, analysis_h), interpolation=cv2.INTER_NEAREST)
                if binary is not None and binary.size
                else None
            )
        else:
            gray = gray_full
            binary_small = binary

        shaded = self._detect_shaded_grid(gray, file_name, page_number)
        projection = self._detect_projection_grid(gray, binary_small, file_name, page_number)

        if analysis_scale < 1.0:
            self._scale_detection(shaded, 1.0 / analysis_scale)
            self._scale_detection(projection, 1.0 / analysis_scale)
        shaded.measurements["analysis_scale"] = analysis_scale
        projection.measurements["analysis_scale"] = analysis_scale

        candidates = [candidate for candidate in (shaded, projection) if candidate.rows]
        if not candidates:
            measurements = {
                "shaded": shaded.measurements,
                "projection": projection.measurements,
            }
            debug_masks = {}
            debug_masks.update({f"shaded_{k}": v for k, v in shaded.debug_masks.items()})
            debug_masks.update({f"projection_{k}": v for k, v in projection.debug_masks.items()})
            return VisualStructureDetection(
                method="none",
                confidence=0.0,
                measurements=measurements,
                debug_masks=debug_masks,
            )

        shaded_min_confidence = float(
            self.config.get("shaded_preference_min_confidence", 0.45)
        )
        if shaded.rows and shaded.confidence >= shaded_min_confidence:
            # Repeated filled/shaded rectangles are stronger cell-boundary
            # evidence than raw text projections, which can easily over-segment
            # every physical text line.  Projection remains the fallback when
            # no convincing shaded grid exists.
            best = shaded
        else:
            best = max(candidates, key=self._coverage_score)
        best.measurements = {
            **best.measurements,
            "candidate_scores": {
                "shaded_grid": shaded.confidence,
                "projection_grid": projection.confidence,
            },
        }
        best.debug_masks = {
            **{f"shaded_{k}": v for k, v in shaded.debug_masks.items()},
            **{f"projection_{k}": v for k, v in projection.debug_masks.items()},
        }
        return best

    # ------------------------------------------------------------------
    # Shaded / filled cell grid detector
    # ------------------------------------------------------------------

    def _detect_shaded_grid(
        self,
        gray: np.ndarray,
        file_name: str,
        page_number: int,
    ) -> VisualStructureDetection:
        cfg = self.config.get("shaded_grid", {})
        if not cfg.get("enabled", True):
            return VisualStructureDetection(method="shaded_grid_disabled")

        h, w = gray.shape[:2]
        blur_ratio = float(cfg.get("blur_kernel_ratio", 0.006))
        blur_k = self._odd(max(5, int(min(h, w) * blur_ratio)))
        blurred = cv2.GaussianBlur(gray, (blur_k, blur_k), 0)
        background_level = float(np.percentile(gray, float(cfg.get("background_percentile", 95.0))))

        deltas = cfg.get("contrast_deltas", [6, 8, 10, 12])
        if not isinstance(deltas, list) or not deltas:
            deltas = [8]

        best: VisualStructureDetection | None = None
        best_mask: np.ndarray | None = None
        trial_measurements: list[dict[str, Any]] = []

        for raw_delta in deltas:
            delta = float(raw_delta)
            threshold = background_level - delta
            mask = (blurred < threshold).astype(np.uint8) * 255

            opening_ratio = float(cfg.get("opening_kernel_ratio", 0.0025))
            opening_k = self._odd(max(3, int(min(h, w) * opening_ratio)))
            mask = cv2.morphologyEx(
                mask,
                cv2.MORPH_OPEN,
                cv2.getStructuringElement(cv2.MORPH_RECT, (opening_k, opening_k)),
            )

            boxes = self._background_boxes(mask, h, w, cfg)
            row_groups = self._group_boxes_by_y_start(boxes, h, cfg)
            candidate = self._grid_from_row_groups(
                row_groups=row_groups,
                page_width=w,
                page_height=h,
                file_name=file_name,
                page_number=page_number,
                method="opencv_shaded_grid",
                cfg=cfg,
            )
            candidate.measurements.update(
                {
                    "background_level": background_level,
                    "contrast_delta": delta,
                    "component_boxes": len(boxes),
                    "row_groups": len(row_groups),
                    "blur_kernel": blur_k,
                    "opening_kernel": opening_k,
                }
            )
            trial_measurements.append(
                {
                    "delta": delta,
                    "rows": len(candidate.rows),
                    "confidence": candidate.confidence,
                    "component_boxes": len(boxes),
                }
            )
            if best is None or self._coverage_score(candidate) > self._coverage_score(best):
                best = candidate
                best_mask = mask

        if best is None:
            best = VisualStructureDetection(method="shaded_grid")
        best.measurements["trials"] = trial_measurements
        if best_mask is not None:
            best.debug_masks["mask"] = best_mask
        return best

    def _background_boxes(
        self,
        mask: np.ndarray,
        h: int,
        w: int,
        cfg: dict[str, Any],
    ) -> list[_Box]:
        count, _, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
        min_width = max(int(cfg.get("minimum_component_width_px", 40)), int(w * float(cfg.get("minimum_component_width_ratio", 0.02))))
        min_height = max(int(cfg.get("minimum_component_height_px", 25)), int(h * float(cfg.get("minimum_component_height_ratio", 0.01))))
        min_fill = float(cfg.get("minimum_component_fill_ratio", 0.80))
        max_width = w * float(cfg.get("maximum_component_width_ratio", 0.75))
        max_height = h * float(cfg.get("maximum_component_height_ratio", 0.60))
        edge_margin = int(cfg.get("edge_exclusion_px", 2))

        boxes: list[_Box] = []
        for index in range(1, count):
            x, y, rw, rh, area = (int(value) for value in stats[index])
            if rw < min_width or rh < min_height:
                continue
            if rw > max_width or rh > max_height:
                continue
            if area / max(1.0, float(rw * rh)) < min_fill:
                continue
            if (
                x <= edge_margin
                or y <= edge_margin
                or x + rw >= w - edge_margin
                or y + rh >= h - edge_margin
            ):
                continue
            boxes.append(_Box(float(x), float(y), float(x + rw), float(y + rh), float(area)))
        return boxes

    def _group_boxes_by_y_start(
        self,
        boxes: list[_Box],
        page_height: int,
        cfg: dict[str, Any],
    ) -> list[list[_Box]]:
        tolerance = max(
            float(cfg.get("row_start_tolerance_px", 10)),
            page_height * float(cfg.get("row_start_tolerance_ratio", 0.012)),
        )
        groups: list[list[_Box]] = []
        for box in sorted(boxes, key=lambda item: item.y0):
            chosen: list[_Box] | None = None
            for group in groups:
                center = float(np.median([item.y0 for item in group]))
                if abs(box.y0 - center) <= tolerance:
                    chosen = group
                    break
            if chosen is None:
                groups.append([box])
            else:
                chosen.append(box)
        return groups

    # ------------------------------------------------------------------
    # Text-ink / projection fallback
    # ------------------------------------------------------------------

    def _detect_projection_grid(
        self,
        gray: np.ndarray,
        binary: np.ndarray | None,
        file_name: str,
        page_number: int,
    ) -> VisualStructureDetection:
        cfg = self.config.get("projection_grid", {})
        if not cfg.get("enabled", True):
            return VisualStructureDetection(method="projection_grid_disabled")

        h, w = gray.shape[:2]
        foreground = self._foreground_mask(gray, binary)

        # Remove long rules so they do not become giant text blocks.
        h_len = max(15, int(w * float(cfg.get("remove_horizontal_line_ratio", 0.08))))
        v_len = max(15, int(h * float(cfg.get("remove_vertical_line_ratio", 0.08))))
        horizontal = cv2.morphologyEx(
            foreground,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)),
        )
        vertical = cv2.morphologyEx(
            foreground,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)),
        )
        text_mask = cv2.subtract(foreground, cv2.bitwise_or(horizontal, vertical))

        close_w = max(2, int(cfg.get("close_width_px", max(4, w * 0.003))))
        close_h = max(1, int(cfg.get("close_height_px", max(1, h * 0.0008))))
        text_mask = cv2.morphologyEx(
            text_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (close_w, close_h)),
        )

        boxes = self._text_boxes(text_mask, h, w, cfg)
        row_groups = self._group_text_boxes(boxes, h, cfg)
        candidate = self._grid_from_row_groups(
            row_groups=row_groups,
            page_width=w,
            page_height=h,
            file_name=file_name,
            page_number=page_number,
            method="opencv_projection_grid",
            cfg=cfg,
        )
        candidate.measurements.update(
            {
                "component_boxes": len(boxes),
                "row_groups": len(row_groups),
                "remove_horizontal_length": h_len,
                "remove_vertical_length": v_len,
                "close_width": close_w,
                "close_height": close_h,
            }
        )
        candidate.debug_masks.update(
            {
                "foreground": foreground,
                "text_mask": text_mask,
            }
        )
        return candidate

    @staticmethod
    def _foreground_mask(gray: np.ndarray, binary: np.ndarray | None) -> np.ndarray:
        if binary is not None and binary.size:
            source = cv2.cvtColor(binary, cv2.COLOR_BGR2GRAY) if binary.ndim == 3 else binary.copy()
            # Prefer the representation with sparse white foreground.
            white_ratio = float(np.mean(source > 127))
            if white_ratio <= 0.50:
                return ((source > 127).astype(np.uint8) * 255)
            return ((source < 128).astype(np.uint8) * 255)
        _, foreground = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        return foreground

    def _text_boxes(
        self,
        mask: np.ndarray,
        h: int,
        w: int,
        cfg: dict[str, Any],
    ) -> list[_Box]:
        count, _, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
        min_area = max(3, int(cfg.get("minimum_text_component_area_px", 8)))
        min_height = max(2, int(cfg.get("minimum_text_component_height_px", 3)))
        max_height = h * float(cfg.get("maximum_text_component_height_ratio", 0.08))
        max_width = w * float(cfg.get("maximum_text_component_width_ratio", 0.55))

        boxes: list[_Box] = []
        for index in range(1, count):
            x, y, rw, rh, area = (int(value) for value in stats[index])
            if area < min_area or rh < min_height:
                continue
            if rh > max_height or rw > max_width:
                continue
            boxes.append(_Box(float(x), float(y), float(x + rw), float(y + rh), float(area)))
        return boxes

    def _group_text_boxes(
        self,
        boxes: list[_Box],
        page_height: int,
        cfg: dict[str, Any],
    ) -> list[list[_Box]]:
        if not boxes:
            return []
        heights = [box.height for box in boxes if box.height > 0]
        typical_height = float(median(heights)) if heights else 8.0
        tolerance = max(
            float(cfg.get("baseline_tolerance_px", 4)),
            typical_height * float(cfg.get("baseline_tolerance_height_ratio", 0.8)),
            page_height * float(cfg.get("baseline_tolerance_page_ratio", 0.001)),
        )

        groups: list[list[_Box]] = []
        for box in sorted(boxes, key=lambda item: item.center_y):
            chosen: list[_Box] | None = None
            best_distance = float("inf")
            for group in groups:
                center = float(np.median([item.center_y for item in group]))
                distance = abs(box.center_y - center)
                if distance <= tolerance and distance < best_distance:
                    best_distance = distance
                    chosen = group
            if chosen is None:
                groups.append([box])
            else:
                chosen.append(box)

        # Merge components that are separated only by normal intra-cell word gaps.
        merged_groups: list[list[_Box]] = []
        merge_gap = max(
            float(cfg.get("intra_block_merge_gap_px", 10)),
            typical_height * float(cfg.get("intra_block_merge_height_ratio", 1.5)),
            0.004 * float(self._page_width(boxes)),
        )
        for group in groups:
            ordered = sorted(group, key=lambda item: item.x0)
            merged: list[_Box] = []
            for box in ordered:
                if not merged or box.x0 - merged[-1].x1 > merge_gap:
                    merged.append(box)
                else:
                    previous = merged[-1]
                    merged[-1] = _Box(
                        previous.x0,
                        min(previous.y0, box.y0),
                        max(previous.x1, box.x1),
                        max(previous.y1, box.y1),
                        previous.area + box.area,
                    )
            merged_groups.append(merged)
        return merged_groups

    @staticmethod
    def _page_width(boxes: list[_Box]) -> float:
        return max((box.x1 for box in boxes), default=1.0)

    # ------------------------------------------------------------------
    # Shared repeated-alignment grid inference
    # ------------------------------------------------------------------

    def _grid_from_row_groups(
        self,
        *,
        row_groups: list[list[_Box]],
        page_width: int,
        page_height: int,
        file_name: str,
        page_number: int,
        method: str,
        cfg: dict[str, Any],
    ) -> VisualStructureDetection:
        minimum_columns = max(2, int(cfg.get("minimum_columns", 2)))
        groups = [group for group in row_groups if len(group) >= minimum_columns]
        if not groups:
            return VisualStructureDetection(method=method, measurements={"reason": "no_multi_column_rows"})

        # The row with the largest number of aligned blocks becomes a purely
        # geometric seed.  No template identity or semantic value is involved.
        seed = max(groups, key=lambda group: (len(group), self._row_span(group)))
        seed_boxes = sorted(seed, key=lambda item: item.x0)
        maximum_columns = int(cfg.get("maximum_columns", 16))
        if len(seed_boxes) > maximum_columns:
            # Excess blocks usually indicate text fragments rather than columns.
            seed_boxes = self._reduce_seed_by_largest_gaps(seed_boxes, maximum_columns)
        if len(seed_boxes) < minimum_columns:
            return VisualStructureDetection(method=method, measurements={"reason": "insufficient_seed_columns"})

        seed_x = [box.x0 for box in seed_boxes]
        x_tolerance = max(
            float(cfg.get("x_alignment_tolerance_px", 12)),
            page_width * float(cfg.get("x_alignment_tolerance_ratio", 0.012)),
        )
        minimum_match_ratio = float(cfg.get("minimum_row_match_ratio", 0.35))
        minimum_matches = max(
            int(cfg.get("minimum_row_matches", 2)),
            int(np.ceil(len(seed_x) * minimum_match_ratio)),
        )

        selected: list[tuple[list[_Box], dict[int, _Box]]] = []
        for group in groups:
            matches = self._match_group_to_seed(group, seed_x, x_tolerance)
            if len(matches) >= minimum_matches:
                selected.append((group, matches))

        minimum_rows = max(2, int(cfg.get("minimum_rows", 2)))
        if len(selected) < minimum_rows:
            return VisualStructureDetection(
                method=method,
                measurements={
                    "reason": "insufficient_aligned_rows",
                    "seed_columns": len(seed_x),
                    "aligned_rows": len(selected),
                },
            )

        # Sort and split into vertically coherent blocks.  This prevents two
        # separate tables with similar column geometry from being fused.
        selected.sort(key=lambda item: float(np.median([box.y0 for box in item[0]])))
        blocks = self._split_selected_rows(selected, page_height, cfg)

        all_rows: list[ExtractedRow] = []
        all_regions: list[TableRegion] = []
        table_metrics: list[dict[str, Any]] = []
        table_counter = 1

        for block in blocks:
            if len(block) < minimum_rows:
                continue
            column_boundaries = self._column_boundaries(block, seed_boxes, page_width, cfg)
            if len(column_boundaries) < minimum_columns + 1:
                continue
            row_boundaries = self._row_boundaries(block, page_height, cfg)
            if len(row_boundaries) < len(block) + 1:
                continue

            table_id = f"visual_table_{table_counter:02d}"
            table_counter += 1
            row_confidences = [len(matches) / max(1, len(seed_boxes)) for _, matches in block]
            confidence = float(np.mean(row_confidences)) if row_confidences else 0.0
            confidence *= min(1.0, len(block) / max(2.0, float(cfg.get("confidence_rows_target", 4))))

            rows = self._build_rows_from_boundaries(
                column_boundaries,
                row_boundaries,
                file_name,
                page_number,
                table_id,
                confidence,
            )
            all_rows.extend(rows)
            region_bbox = BBox(
                column_boundaries[0],
                row_boundaries[0],
                column_boundaries[-1],
                row_boundaries[-1],
            )
            all_regions.append(
                TableRegion(
                    table_id=table_id,
                    bbox=region_bbox,
                    layout_type=LayoutType.BORDERLESS_TABLE,
                    confidence=confidence,
                    row_boundaries=list(row_boundaries),
                    column_boundaries=list(column_boundaries),
                    metadata={"method": method, "seed_columns": len(seed_boxes)},
                )
            )
            table_metrics.append(
                {
                    "table_id": table_id,
                    "rows": len(rows),
                    "columns": len(column_boundaries) - 1,
                    "confidence": confidence,
                }
            )

        overall_confidence = max((region.confidence for region in all_regions), default=0.0)
        return VisualStructureDetection(
            rows=all_rows,
            regions=all_regions,
            method=method,
            confidence=overall_confidence,
            measurements={
                "seed_columns": len(seed_boxes),
                "candidate_rows": len(groups),
                "aligned_rows": len(selected),
                "table_count": len(all_regions),
                "tables": table_metrics,
            },
        )

    @staticmethod
    def _row_span(group: list[_Box]) -> float:
        if not group:
            return 0.0
        return max(box.x1 for box in group) - min(box.x0 for box in group)

    @staticmethod
    def _reduce_seed_by_largest_gaps(seed: list[_Box], maximum_columns: int) -> list[_Box]:
        if len(seed) <= maximum_columns:
            return seed
        # Keep the widest blocks first, then restore X order.  This suppresses
        # small word fragments when projection mode has fragmented a text line.
        retained = sorted(seed, key=lambda box: box.width, reverse=True)[:maximum_columns]
        return sorted(retained, key=lambda box: box.x0)

    @staticmethod
    def _match_group_to_seed(
        group: list[_Box],
        seed_x: list[float],
        tolerance: float,
    ) -> dict[int, _Box]:
        available = set(range(len(group)))
        ordered_group = sorted(group, key=lambda item: item.x0)
        matches: dict[int, _Box] = {}
        for seed_index, seed_value in enumerate(seed_x):
            candidates = [
                (abs(ordered_group[index].x0 - seed_value), index)
                for index in available
                if abs(ordered_group[index].x0 - seed_value) <= tolerance
            ]
            if not candidates:
                continue
            _, chosen_index = min(candidates)
            matches[seed_index] = ordered_group[chosen_index]
            available.remove(chosen_index)
        return matches

    def _split_selected_rows(
        self,
        selected: list[tuple[list[_Box], dict[int, _Box]]],
        page_height: int,
        cfg: dict[str, Any],
    ) -> list[list[tuple[list[_Box], dict[int, _Box]]]]:
        if not selected:
            return []
        starts = [float(np.median([box.y0 for box in group])) for group, _ in selected]
        heights = [float(median([box.height for box in group])) for group, _ in selected]
        blocks: list[list[tuple[list[_Box], dict[int, _Box]]]] = [[selected[0]]]
        gaps = [right - left for left, right in zip(starts, starts[1:]) if right > left]
        typical_gap = float(median(gaps)) if gaps else 0.0
        gap_factor = float(cfg.get("table_split_gap_factor", 2.75))
        absolute_ratio = float(cfg.get("table_split_gap_page_ratio", 0.18))
        for index in range(1, len(selected)):
            gap = starts[index] - starts[index - 1]
            local_height = max(heights[index - 1], heights[index], 1.0)
            # A normal table may have very large row heights (wrapped text) or
            # generous whitespace.  Split only when the gap is an outlier both
            # relative to the page and to the observed row cadence.
            cadence_limit = typical_gap * gap_factor if typical_gap > 0 else 0.0
            split_threshold = max(
                page_height * absolute_ratio,
                cadence_limit,
                local_height * float(cfg.get("table_split_gap_height_factor", 4.0)),
            )
            split = gap > split_threshold
            if split:
                blocks.append([selected[index]])
            else:
                blocks[-1].append(selected[index])
        return blocks

    def _column_boundaries(
        self,
        block: list[tuple[list[_Box], dict[int, _Box]]],
        seed_boxes: list[_Box],
        page_width: int,
        cfg: dict[str, Any],
    ) -> list[float]:
        lefts: list[float] = []
        rights: list[float] = []
        for index, seed in enumerate(seed_boxes):
            matched = [matches[index] for _, matches in block if index in matches]
            lefts.append(float(np.median([box.x0 for box in matched])) if matched else seed.x0)
            rights.append(float(np.median([box.x1 for box in matched])) if matched else seed.x1)

        # Left edges of repeated cells are more stable than text centers.  The
        # final right boundary comes from the last column's repeated right edge.
        boundaries = list(lefts) + [rights[-1]]
        padding = float(cfg.get("outer_padding_px", 0))
        boundaries[0] = max(0.0, boundaries[0] - padding)
        boundaries[-1] = min(float(page_width), boundaries[-1] + padding)

        minimum_gap = max(2.0, float(cfg.get("minimum_column_width_px", 12)))
        cleaned = [boundaries[0]]
        for value in boundaries[1:]:
            if value - cleaned[-1] >= minimum_gap:
                cleaned.append(value)
        return cleaned

    def _row_boundaries(
        self,
        block: list[tuple[list[_Box], dict[int, _Box]]],
        page_height: int,
        cfg: dict[str, Any],
    ) -> list[float]:
        starts = [float(np.median([box.y0 for box in group])) for group, _ in block]
        last_group = block[-1][0]
        last_bottom = float(np.median([box.y1 for box in last_group]))
        if last_bottom <= starts[-1]:
            last_bottom = starts[-1] + float(median([box.height for box in last_group]))
        padding = float(cfg.get("outer_padding_px", 0))
        starts[0] = max(0.0, starts[0] - padding)
        last_bottom = min(float(page_height), last_bottom + padding)
        return starts + [last_bottom]

    @staticmethod
    def _build_rows_from_boundaries(
        xs: list[float],
        ys: list[float],
        file_name: str,
        page_number: int,
        table_id: str,
        confidence: float,
    ) -> list[ExtractedRow]:
        rows: list[ExtractedRow] = []
        for row_index, (y0, y1) in enumerate(zip(ys, ys[1:])):
            if y1 <= y0:
                continue
            cells: list[ExtractedCell] = []
            for column_index, (x0, x1) in enumerate(zip(xs, xs[1:])):
                if x1 <= x0:
                    continue
                cells.append(
                    ExtractedCell(
                        file_name=file_name,
                        page_number=page_number,
                        table_id=table_id,
                        row_index=row_index,
                        column_index=column_index,
                        bbox=BBox(x0, y0, x1, y1),
                        crop_path=None,
                        engine="opencv_geometry",
                        confidence=confidence,
                        raw_value="",
                        normalized_value=None,
                    )
                )
            if not cells:
                continue
            row_bbox = BBox(xs[0], y0, xs[-1], y1)
            rows.append(
                ExtractedRow(
                    file_name=file_name,
                    page_number=page_number,
                    table_id=table_id,
                    row_index=row_index,
                    cells=cells,
                    bbox=row_bbox,
                    row_confidence=confidence,
                )
            )
        return rows

    @staticmethod
    def _coverage_score(detection: VisualStructureDetection) -> float:
        if not detection.rows:
            return 0.0
        counts = [len(row.cells) for row in detection.rows if row.cells]
        median_columns = float(np.median(counts)) if counts else 1.0
        return len(detection.rows) * max(1.0, median_columns) * max(0.20, detection.confidence)

    @staticmethod
    def _scale_detection(detection: VisualStructureDetection, factor: float) -> None:
        if factor == 1.0:
            return
        for row in detection.rows:
            if row.bbox is not None:
                row.bbox = BBox(
                    row.bbox.x0 * factor,
                    row.bbox.y0 * factor,
                    row.bbox.x1 * factor,
                    row.bbox.y1 * factor,
                )
            for cell in row.cells:
                cell.bbox = BBox(
                    cell.bbox.x0 * factor,
                    cell.bbox.y0 * factor,
                    cell.bbox.x1 * factor,
                    cell.bbox.y1 * factor,
                )
        for region in detection.regions:
            region.bbox = BBox(
                region.bbox.x0 * factor,
                region.bbox.y0 * factor,
                region.bbox.x1 * factor,
                region.bbox.y1 * factor,
            )
            region.row_boundaries = [value * factor for value in region.row_boundaries]
            region.column_boundaries = [value * factor for value in region.column_boundaries]

    @staticmethod
    def _odd(value: int) -> int:
        value = max(1, int(value))
        return value if value % 2 else value + 1
