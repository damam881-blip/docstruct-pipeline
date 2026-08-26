from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN

from models import BBox, ExtractedCell, ExtractedRow, LayoutType, TableRegion, WordBox, union_bbox


@dataclass(slots=True)
class BorderlessDetection:
    regions: list[TableRegion]
    rows_by_table: dict[str, list[ExtractedRow]]
    column_anchors: dict[str, list[float]]
    measurements: dict[str, Any] = field(default_factory=dict)


class BorderlessTableDetector:
    def __init__(self, config: dict) -> None:
        self.config = config.get("borderless_table", {})

    def detect(self, words: list[WordBox], file_name: str, page_number: int, page_bbox: BBox) -> BorderlessDetection:
        if not self.config.get("enabled", True):
            return BorderlessDetection([], {}, {}, {"disabled": True})
        if not words:
            return BorderlessDetection([], {}, {}, {})
        self._page_width = page_bbox.width
        row_cfg = self.config.get("row_detection", {})
        tolerance = float(row_cfg.get("baseline_tolerance_px", 8))
        # Keep physical OCR line clustering separate from logical row
        # reconstruction. Column topology must be inferred from the stable
        # physical evidence, otherwise changing multiline-row merging can
        # change the number of rows used by the column support threshold and
        # create/remove columns even though the OCR word geometry is identical.
        physical_rows = self._cluster_rows(words, tolerance)
        logical_rows = self._merge_continuations(physical_rows)
        anchors = self._infer_anchors(physical_rows, page_bbox.width)
        table_id = "table_01"
        extracted_rows = self._build_rows(
            logical_rows, anchors, file_name, page_number, table_id
        )
        bbox = union_bbox([w.bbox for w in words]) or page_bbox
        region = TableRegion(table_id, bbox, LayoutType.BORDERLESS_TABLE, self._consistency_score(extracted_rows), [], anchors)
        gaps = [anchors[i + 1] - anchors[i] for i in range(len(anchors) - 1)]
        return BorderlessDetection(
            [region],
            {table_id: extracted_rows},
            {table_id: anchors},
            {
                "physical_row_count": len(physical_rows),
                "logical_row_count": len(extracted_rows),
                # Backward-compatible alias used by existing reports/tests.
                "row_count": len(extracted_rows),
                "column_count": max(0, len(anchors) - 1),
                "column_inference_source": "physical_rows",
                "median_column_gap": float(median(gaps)) if gaps else 0.0,
            },
        )

    def _cluster_rows(self, words: list[WordBox], tolerance: float) -> list[list[WordBox]]:
        ordered = sorted(words, key=lambda w: (w.bbox.center[1], w.bbox.x0))
        groups: list[list[WordBox]] = []
        for word in ordered:
            cy = word.bbox.center[1]
            if not groups:
                groups.append([word])
                continue
            last_center = np.median([w.bbox.center[1] for w in groups[-1]])
            overlap = max(
                0.0,
                min(word.bbox.y1, max(w.bbox.y1 for w in groups[-1])) - max(word.bbox.y0, min(w.bbox.y0 for w in groups[-1])),
            )
            min_height = max(1.0, min(word.bbox.height, median([w.bbox.height for w in groups[-1]])))
            overlap_ratio = overlap / min_height
            if abs(cy - last_center) <= tolerance or overlap_ratio >= float(self.config.get("row_detection", {}).get("y_overlap_ratio", 0.50)):
                groups[-1].append(word)
            else:
                groups.append([word])
        return groups

    def _merge_continuations(self, rows: list[list[WordBox]]) -> list[list[WordBox]]:
        cfg = self.config.get("row_detection", {})
        if not cfg.get("merge_multiline_rows", True) or len(rows) < 2:
            return rows
        continuation_gap = float(cfg.get("continuation_line_gap_px", 18))
        # Work on copies so logical-row merging never mutates the physical
        # row groups. The physical groups are also used for column topology.
        result: list[list[WordBox]] = [list(rows[0])]
        for row in rows[1:]:
            previous = result[-1]
            prev_box, row_box = union_bbox([w.bbox for w in previous]), union_bbox([w.bbox for w in row])
            if prev_box is None or row_box is None:
                result.append(list(row))
                continue
            gap = row_box.y0 - prev_box.y1
            prev_has_anchor = self._has_row_anchor(previous)
            current_has_anchor = self._has_row_anchor(row)
            if gap <= continuation_gap and prev_has_anchor and not current_has_anchor:
                previous.extend(row)
            else:
                result.append(list(row))
        return result

    def _has_row_anchor(self, words: list[WordBox]) -> bool:
        cfg = self.config.get("row_detection", {})
        x_range = cfg.get("anchor_x_range_ratio")
        candidate_words = words
        if x_range and getattr(self, "_page_width", 0):
            x0 = float(x_range[0]) * self._page_width
            x1 = float(x_range[1]) * self._page_width
            candidate_words = [w for w in words if x0 <= w.bbox.center[0] <= x1]
        text = " ".join(w.text for w in candidate_words)
        digit_count = sum(ch.isdigit() for ch in text)
        anchor_type = cfg.get("anchor_type", "auto")
        has_date = any(sep in text for sep in ("/", "-")) and digit_count >= 4
        has_amount = digit_count >= 1 and (any(ch in text for ch in (".", ",", "٫", "٬")) or digit_count >= 3)
        if anchor_type == "date":
            return has_date
        if anchor_type == "amount":
            return has_amount
        return has_date or has_amount

    def _infer_anchors(self, rows: list[list[WordBox]], page_width: float) -> list[float]:
        """Infer stable column boundaries from repeated horizontal alignments.

        A raw DBSCAN over every word position usually creates too many columns,
        especially inside long descriptions. We therefore keep clusters that
        recur across several visual rows. Stable amount/date/reference columns
        receive high support, while arbitrary word positions inside prose are
        filtered out.
        """
        cfg = self.config.get("column_detection", {})
        expected = cfg.get("expected_columns")
        samples: list[tuple[int, float]] = [
            (row_index, word.bbox.center[0])
            for row_index, row in enumerate(rows)
            for word in row
        ]
        if not samples:
            return [0.0, page_width]

        x_values = np.array([[x] for _, x in samples], dtype=np.float32)
        eps = float(cfg.get("x_tolerance_px", 15))
        min_samples = int(self.config.get("clustering", {}).get("min_samples", 1))
        labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(x_values)

        minimum_support_rows = int(cfg.get("minimum_column_support_rows", 3))
        minimum_support_ratio = float(cfg.get("minimum_column_support_ratio", 0.20))
        required_support = max(
            1 if len(rows) < 4 else minimum_support_rows,
            int(np.ceil(len(rows) * minimum_support_ratio)),
        )

        supported_centers: list[tuple[float, int]] = []
        for label in sorted(set(labels)):
            if label == -1:
                continue
            member_indices = np.where(labels == label)[0]
            support_rows = {samples[index][0] for index in member_indices}
            center = float(np.median(x_values[member_indices]))
            if len(support_rows) >= required_support:
                supported_centers.append((center, len(support_rows)))

        centers = [center for center, _ in supported_centers]
        centers = self._merge_close(
            centers, float(cfg.get("minimum_column_gap_px", 20))
        )
        maximum_columns = int(cfg.get("maximum_columns", 20))

        if expected:
            centers = self._force_expected_centers(
                x_values[:, 0].tolist(), int(expected)
            )
        elif len(centers) > maximum_columns:
            # Prefer the most frequently repeated alignments before falling back
            # to quantiles. This keeps stable numeric columns and removes prose.
            supported_centers.sort(key=lambda item: (-item[1], item[0]))
            centers = sorted(center for center, _ in supported_centers[:maximum_columns])
            centers = self._merge_close(
                centers, float(cfg.get("minimum_column_gap_px", 20))
            )

        if len(centers) <= 1:
            # Insufficient repeated evidence: retain a conservative single-column
            # representation instead of inventing many unstable columns.
            return [0.0, page_width]

        boundaries = [0.0]
        boundaries.extend((left + right) / 2.0 for left, right in zip(centers, centers[1:]))
        boundaries.append(page_width)
        return sorted(set(float(value) for value in boundaries))

    @staticmethod
    def _force_expected_centers(values: list[float], expected: int) -> list[float]:
        if expected <= 1:
            return [float(np.median(values))]
        quantiles = np.linspace(0.0, 1.0, expected + 2)[1:-1]
        return [float(np.quantile(values, q)) for q in quantiles]

    @staticmethod
    def _merge_close(values: list[float], minimum_gap: float) -> list[float]:
        result: list[float] = []
        for value in sorted(values):
            if not result or value - result[-1] >= minimum_gap:
                result.append(value)
            else:
                result[-1] = (result[-1] + value) / 2.0
        return result

    def _build_rows(
        self,
        rows: list[list[WordBox]],
        boundaries: list[float],
        file_name: str,
        page_number: int,
        table_id: str,
    ) -> list[ExtractedRow]:
        output: list[ExtractedRow] = []
        for row_index, words in enumerate(rows):
            word_row_bbox = union_bbox([word.bbox for word in words])
            if word_row_bbox is None:
                continue
            buckets: dict[int, list[WordBox]] = defaultdict(list)
            for word in words:
                cx = word.bbox.center[0]
                col = max(0, min(len(boundaries) - 2, int(np.searchsorted(boundaries, cx, side="right") - 1)))
                buckets[col].append(word)
            cells: list[ExtractedCell] = []
            for col in range(len(boundaries) - 1):
                col_words = sorted(buckets.get(col, []), key=lambda w: (w.bbox.y0, w.bbox.x0))
                if self._arabic_ratio(" ".join(w.text for w in col_words)) > 0.5:
                    col_words = sorted(col_words, key=lambda w: (w.bbox.y0, -w.bbox.x0))
                text = " ".join(w.text for w in col_words).strip()
                bbox = BBox(
                    boundaries[col],
                    word_row_bbox.y0,
                    boundaries[col + 1],
                    word_row_bbox.y1,
                )
                confidence = float(np.mean([w.confidence for w in col_words])) if col_words else 0.0
                cells.append(
                    ExtractedCell(
                        file_name,
                        page_number,
                        table_id,
                        row_index,
                        col,
                        bbox,
                        None,
                        col_words[0].source if col_words else "none",
                        confidence,
                        text,
                        text,
                    )
                )
            row_bbox = BBox(
                boundaries[0],
                word_row_bbox.y0,
                boundaries[-1],
                word_row_bbox.y1,
            )
            output.append(
                ExtractedRow(
                    file_name,
                    page_number,
                    table_id,
                    row_index,
                    cells,
                    row_bbox,
                    float(np.mean([c.confidence for c in cells if c.raw_value])) if any(c.raw_value for c in cells) else 0.0,
                )
            )
        return output

    @staticmethod
    def _arabic_ratio(text: str) -> float:
        letters = [ch for ch in text if ch.isalpha()]
        if not letters:
            return 0.0
        return sum("\u0600" <= ch <= "\u06ff" for ch in letters) / len(letters)

    @staticmethod
    def _consistency_score(rows: list[ExtractedRow]) -> float:
        if not rows:
            return 0.0
        nonempty_counts = [sum(bool(c.raw_value) for c in row.cells) for row in rows]
        mode = max(set(nonempty_counts), key=nonempty_counts.count)
        return nonempty_counts.count(mode) / len(nonempty_counts)
