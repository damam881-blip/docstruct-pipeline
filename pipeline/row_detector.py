from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from statistics import median
from typing import Any

import cv2
import numpy as np

from models import BBox, ExtractedCell, ExtractedRow, WordBox, union_bbox
from pipeline.data_reconstructor import DataReconstructor


def detect_rows_by_baseline(words: list[WordBox], tolerance: float = 8.0) -> list[BBox]:
    groups: list[list[WordBox]] = []
    for word in sorted(words, key=lambda w: w.bbox.center[1]):
        if not groups:
            groups.append([word])
            continue
        last_y = sum(w.bbox.center[1] for w in groups[-1]) / len(groups[-1])
        if abs(word.bbox.center[1] - last_y) <= tolerance:
            groups[-1].append(word)
        else:
            groups.append([word])
    return [box for group in groups if (box := union_bbox([w.bbox for w in group])) is not None]


@dataclass(slots=True)
class AnchorSegmentationResult:
    rows: list[ExtractedRow]
    anchors_y: list[float]
    roi_bbox: BBox
    confidence: float
    reason: str


class AnchorRowSegmenter:
    """Configurable row segmentation using a reliable numeric/date anchor column.

    The generic configuration may supply a relative ROI and relative column
    boundaries. It is useful for bank statements where each transaction has
    a balance/date anchor, while descriptions may span several physical text lines.
    """

    def __init__(self, config: dict, ocr_engine: Any) -> None:
        self.config = config.get("borderless_table", {}).get("row_detection", {}).get("anchor_segmentation", {})
        self.ocr_engine = ocr_engine

    def segment(
        self,
        image: np.ndarray,
        full_page_words: list[WordBox],
        file_name: str,
        page_number: int,
        table_id: str = "table_01",
        crop_dir: Path | None = None,
    ) -> AnchorSegmentationResult:
        if not self.config.get("enabled", False):
            return AnchorSegmentationResult([], [], BBox(0, 0, 0, 0), 0.0, "disabled")
        h, w = image.shape[:2]
        roi_ratio = self.config.get("roi_ratio", [0.0, 0.25, 0.20, 0.90])
        x0, x1 = int(float(roi_ratio[0]) * w), int(float(roi_ratio[1]) * w)
        y0, y1 = int(float(roi_ratio[2]) * h), int(float(roi_ratio[3]) * h)
        roi_bbox = BBox(x0, y0, x1, y1).clamped(w, h)
        rx0, ry0, rx1, ry1 = roi_bbox.to_int()
        roi = image[ry0:ry1, rx0:rx1]
        if roi.size == 0:
            return AnchorSegmentationResult([], [], roi_bbox, 0.0, "empty_roi")

        mode = self.config.get("ocr_mode", "sparse")
        anchor_type = self.config.get("anchor_type", "amount")
        candidate_source = self.config.get("candidate_source", "roi_ocr")
        projection_anchor_y: list[float] | None = None
        if candidate_source == "projection":
            projection_anchor_y = self._projection_anchors(roi, ry0)
            candidate_words = []
            result_confidence = float(self.config.get("projection_confidence", 0.70))
            result_engine = "opencv_projection"
        elif candidate_source == "full_page_words":
            candidate_words = [
                word for word in full_page_words
                if roi_bbox.x0 <= word.bbox.center[0] <= roi_bbox.x1
                and roi_bbox.y0 <= word.bbox.center[1] <= roi_bbox.y1
            ]
            result_confidence = float(np.mean([word.confidence for word in candidate_words])) if candidate_words else 0.0
            result_engine = candidate_words[0].source if candidate_words else "none"
        else:
            result = self.ocr_engine.recognize(roi, mode=mode, numeric=anchor_type == "amount")
            candidate_words = [
                WordBox(
                    word.text,
                    BBox(word.bbox.x0 + rx0, word.bbox.y0 + ry0, word.bbox.x1 + rx0, word.bbox.y1 + ry0),
                    word.confidence,
                    word.source,
                    word.block_no,
                    word.line_no,
                    word.word_no,
                    word.language,
                )
                for word in result.words
            ]
            result_confidence = result.confidence
            result_engine = result.engine

        candidates: list[tuple[float, float, str]] = []
        minimum_confidence = float(self.config.get("minimum_confidence", 0.15))
        minimum_digits = int(self.config.get("minimum_digits", 1))
        for word in candidate_words:
            text = word.text.strip()
            if word.confidence < minimum_confidence:
                continue
            normalized = DataReconstructor.normalize_digits(text)
            digit_count = sum(ch.isdigit() for ch in normalized)
            valid = False
            if anchor_type == "amount":
                valid = DataReconstructor.parse_amount(text) is not None and digit_count >= minimum_digits
            elif anchor_type == "date":
                valid = digit_count >= max(4, minimum_digits) and any(sep in normalized for sep in ("/", "-"))
            elif anchor_type == "digit_line":
                # Useful when OCR preserves the numeric line position but confuses
                # Arabic-Indic digits with Latin letters or drops date separators.
                valid = digit_count >= minimum_digits
            if valid:
                candidates.append((word.bbox.center[1], word.confidence, text))

        minimum_gap = float(self.config.get("minimum_anchor_gap_px", max(12, h * 0.008)))
        if projection_anchor_y is not None:
            anchor_y = projection_anchor_y
        else:
            anchors: list[list[tuple[float, float, str]]] = []
            for candidate in sorted(candidates):
                if not anchors or candidate[0] - np.mean([c[0] for c in anchors[-1]]) > minimum_gap:
                    anchors.append([candidate])
                else:
                    anchors[-1].append(candidate)
            anchor_y = [float(np.mean([c[0] for c in group])) for group in anchors]
        min_anchors = int(self.config.get("minimum_anchors", 3))
        if len(anchor_y) < min_anchors:
            return AnchorSegmentationResult([], anchor_y, roi_bbox, result_confidence, f"only_{len(anchor_y)}_anchors")

        gaps = [
            next_anchor - current_anchor
            for current_anchor, next_anchor in zip(
                anchor_y,
                anchor_y[1:],
            )
        ]
        typical_gap = (
            float(median(gaps))
            if gaps
            else float(self.config.get("default_row_height_px", 80))
        )

        # Controls how detected anchors are converted into row boundaries.
        boundary_mode = str(
            self.config.get("boundary_mode", "midpoint")
        ).strip().lower()

        if boundary_mode == "midpoint":
            # Use this mode when each anchor is approximately in the middle
            # of its logical row.
            top = max(float(ry0), anchor_y[0] - typical_gap / 2.0)
            bottom = min(float(ry1), anchor_y[-1] + typical_gap / 2.0)
            boundaries = [top] + [
                (current_anchor + next_anchor) / 2.0
                for current_anchor, next_anchor in zip(anchor_y, anchor_y[1:])
            ] + [bottom]
        elif boundary_mode == "anchor_start":
            # Use this mode when every anchor represents the beginning
            # of a new logical row.
            top = float(ry0)
            bottom = float(ry1)

            # Optional adjustment between the detected anchor center
            # and the actual beginning of the logical row.
            boundary_offset_px = float(self.config.get("boundary_offset_px", 0.0))

            internal_boundaries = [
                min(max(float(anchor) + boundary_offset_px, top), bottom)
                for anchor in anchor_y[1:]
            ]
            boundaries = [top] + internal_boundaries + [bottom]
        else:
            raise ValueError(
                "Unsupported anchor boundary_mode: "
                f"{boundary_mode!r}. "
                "Allowed values are 'midpoint' and 'anchor_start'."
            )

        column_ratios = self.config.get("column_boundaries_ratio")
        if not column_ratios:
            expected = int(self.config.get("expected_columns", 1))
            table_x0 = float(self.config.get("table_x0_ratio", 0.0))
            table_x1 = float(self.config.get("table_x1_ratio", 1.0))
            column_ratios = [table_x0 + (table_x1 - table_x0) * i / expected for i in range(expected + 1)]
        column_boundaries = [min(float(w), max(0.0, float(r) * w)) for r in column_ratios]
        column_boundaries = sorted(set(column_boundaries))

        rows: list[ExtractedRow] = []
        for row_index, (band_top, band_bottom) in enumerate(zip(boundaries, boundaries[1:])):
            row_words = [
                word for word in full_page_words
                if band_top <= word.bbox.center[1] < band_bottom
                and float(self.config.get("table_x0_ratio", 0.0)) * w <= word.bbox.center[0] <= float(self.config.get("table_x1_ratio", 1.0)) * w
            ]
            cells: list[ExtractedCell] = []
            for col_index, (col_left, col_right) in enumerate(zip(column_boundaries, column_boundaries[1:])):
                cell_words = [word for word in row_words if col_left <= word.bbox.center[0] < col_right]
                cell_words = self._sort_words(cell_words)
                text = " ".join(word.text for word in cell_words).strip()
                # A cell crop must represent the configured logical column, not
                # only the tight union of OCR words. This keeps empty space,
                # punctuation, and weakly recognized digits inside the crop.
                bbox = BBox(col_left, band_top, col_right, band_bottom).clamped(w, h)
                confidence = float(np.mean([word.confidence for word in cell_words])) if cell_words else 0.0
                engine = cell_words[0].source if cell_words else result_engine
                crop_path: str | None = None
                refined = self._refine_cell_with_crop_ocr(
                    image=image,
                    col_index=col_index,
                    col_left=col_left,
                    col_right=col_right,
                    band_top=band_top,
                    band_bottom=band_bottom,
                    existing_text=text,
                    existing_confidence=confidence,
                    row_index=row_index,
                    page_number=page_number,
                    table_id=table_id,
                    crop_dir=crop_dir,
                )
                if refined is not None:
                    text, confidence, engine, crop_path = refined
                    bbox = BBox(col_left, band_top, col_right, band_bottom).clamped(w, h)
                cells.append(
                    ExtractedCell(
                        file_name=file_name,
                        page_number=page_number,
                        table_id=table_id,
                        row_index=row_index,
                        column_index=col_index,
                        bbox=bbox,
                        crop_path=crop_path,
                        engine=engine,
                        confidence=confidence,
                        raw_value=text,
                        normalized_value=text,
                    )
                )
            if any(cell.raw_value for cell in cells):
                row_bbox = BBox(
                    column_boundaries[0], band_top, column_boundaries[-1], band_bottom
                ).clamped(w, h)
                nonempty_conf = [cell.confidence for cell in cells if cell.raw_value]
                rows.append(
                    ExtractedRow(
                        file_name=file_name,
                        page_number=page_number,
                        table_id=table_id,
                        row_index=row_index,
                        cells=cells,
                        bbox=row_bbox,
                        row_confidence=float(np.mean(nonempty_conf)) if nonempty_conf else 0.0,
                    )
                )
        return AnchorSegmentationResult(rows, anchor_y, roi_bbox, result_confidence, "ok")

    def _refine_cell_with_crop_ocr(
        self,
        image: np.ndarray,
        col_index: int,
        col_left: float,
        col_right: float,
        band_top: float,
        band_bottom: float,
        existing_text: str,
        existing_confidence: float,
        row_index: int,
        page_number: int,
        table_id: str,
        crop_dir: Path | None,
    ) -> tuple[str, float, str, str | None] | None:
        """Re-OCR configured semantic cells from their own crop.

        Full-page layout OCR is excellent for locating words, but small dates and
        financial amounts often need a single-line, character-constrained pass.
        This method is parameter-driven and therefore does not hardcode a document.
        """
        cfg = self.config.get("cell_ocr", {})
        if not cfg.get("enabled", False):
            return None
        schema = cfg.get("column_types", [])
        if not schema:
            schema = self.config.get("column_types", [])
        if col_index >= len(schema):
            return None
        field_type = str(schema[col_index]).lower()
        selected_types = {str(v).lower() for v in cfg.get("types", ["amount", "date", "time"])}
        if field_type not in selected_types:
            return None

        retry_empty = bool(cfg.get("retry_empty", True))
        threshold = float(cfg.get("existing_confidence_threshold", 0.90))
        existing_valid = self._cell_value_is_valid(existing_text, field_type)
        if existing_text and existing_valid and existing_confidence >= threshold and not cfg.get("always", False):
            return None
        if not existing_text and not retry_empty:
            return None

        h, w = image.shape[:2]
        pad = cfg.get("padding_px", {})
        x0 = max(0, int(round(col_left)) - int(pad.get("left", 8)))
        x1 = min(w, int(round(col_right)) + int(pad.get("right", 8)))
        y0 = max(0, int(round(band_top)) - int(pad.get("top", 3)))
        y1 = min(h, int(round(band_bottom)) + int(pad.get("bottom", 3)))
        crop = image[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        scale = float(cfg.get("scale_factor", 1.5))
        if scale != 1.0:
            crop_for_ocr = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        else:
            crop_for_ocr = crop
        if bool(cfg.get("grayscale", True)) and crop_for_ocr.ndim == 3:
            crop_for_ocr = cv2.cvtColor(crop_for_ocr, cv2.COLOR_BGR2GRAY)
        threshold_method = str(cfg.get("threshold", "none")).lower()
        if threshold_method == "otsu":
            _, crop_for_ocr = cv2.threshold(crop_for_ocr, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        elif threshold_method == "adaptive":
            block = int(cfg.get("adaptive_block_size", 31))
            block += 1 - block % 2
            crop_for_ocr = cv2.adaptiveThreshold(
                crop_for_ocr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, float(cfg.get("adaptive_c", 11))
            )

        mode_map = cfg.get("modes", {})
        mode = str(mode_map.get(field_type, "single_line"))
        numeric = field_type in {"amount", "date", "time", "number", "integer"}
        result = self.ocr_engine.recognize(crop_for_ocr, mode=mode, numeric=numeric)
        candidate = self._join_crop_words(result.words, field_type).strip()
        candidate_valid = self._cell_value_is_valid(candidate, field_type)
        minimum_confidence = float(cfg.get("minimum_confidence", 0.20))
        prefer_valid = bool(cfg.get("prefer_valid_candidate", True))
        use_candidate = bool(candidate) and result.confidence >= minimum_confidence and (
            (prefer_valid and candidate_valid and not existing_valid)
            or (candidate_valid == existing_valid and result.confidence > existing_confidence)
            or (not existing_text and candidate_valid)
        )
        if not use_candidate:
            return None

        saved_path: str | None = None
        if crop_dir is not None and bool(cfg.get("save_crops", True)):
            crop_dir.mkdir(parents=True, exist_ok=True)
            path = crop_dir / f"p{page_number:04d}_t{table_id}_r{row_index:03d}_c{col_index:02d}_refined.png"
            cv2.imwrite(str(path), crop)
            saved_path = str(path)
        return candidate, result.confidence, f"{result.engine}_cell_refine", saved_path

    @staticmethod
    def _join_crop_words(words: list[WordBox], field_type: str) -> str:
        ordered = sorted(words, key=lambda word: (word.bbox.y0, word.bbox.x0))
        if field_type in {"amount", "date", "time", "number", "integer"}:
            return "".join(word.text for word in ordered)
        return " ".join(word.text for word in ordered)

    @staticmethod
    def _cell_value_is_valid(text: str, field_type: str) -> bool:
        value = text.strip()
        if not value:
            return False
        if field_type == "amount":
            return DataReconstructor.parse_amount(value) is not None
        normalized = DataReconstructor.normalize_digits(value)
        if field_type == "date":
            return bool(
        re.fullmatch(
            r"(?:"
            r"\d{4}[/.-]\d{1,2}[/.-]\d{1,2}"
            r"|"
            r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
            r"|"
            r"\d{8}"
            r")",
            normalized,
        )
    )
        if field_type == "time":
            return bool(re.search(r"\d{1,2}:\d{2}(?::\d{2})?", normalized))
        if field_type in {"number", "integer"}:
            return any(char.isdigit() for char in normalized)
        return bool(value)

    def _projection_anchors(self, roi: np.ndarray, y_offset: int) -> list[float]:
        """Detect one anchor per text line from a narrow date/amount column.

        Long vertical rules are removed before computing the horizontal ink
        projection. Nearby bands are merged so a two-line date/time cell still
        represents one transaction row.
        """
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi.copy()
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        vertical_length = max(20, int(binary.shape[0] * float(self.config.get("projection_vertical_kernel_ratio", 0.05))))
        vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertical_length)))
        clean = cv2.subtract(binary, vertical)
        close_width = max(1, int(self.config.get("projection_close_width_px", 5)))
        close_height = max(1, int(self.config.get("projection_close_height_px", 2)))
        clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (close_width, close_height)))
        projection = np.count_nonzero(clean, axis=1)
        threshold_ratio = float(self.config.get("projection_ink_threshold_ratio", 0.02))
        threshold = max(int(self.config.get("projection_min_ink_px", 2)), int(clean.shape[1] * threshold_ratio))
        active = projection > threshold
        minimum_band_height = int(self.config.get("projection_min_band_height_px", 3))
        bands: list[tuple[int, int]] = []
        start: int | None = None
        for index, is_active in enumerate(active):
            if is_active and start is None:
                start = index
            elif not is_active and start is not None:
                if index - start >= minimum_band_height:
                    bands.append((start, index - 1))
                start = None
        if start is not None and len(active) - start >= minimum_band_height:
            bands.append((start, len(active) - 1))

        merge_gap = int(self.config.get("projection_merge_gap_px", self.config.get("minimum_anchor_gap_px", 40)))
        merged: list[tuple[int, int]] = []
        for band in bands:
            if merged and band[0] - merged[-1][1] <= merge_gap:
                merged[-1] = (merged[-1][0], band[1])
            else:
                merged.append(band)
        return [float(y_offset + (start + end) / 2.0) for start, end in merged]

    @staticmethod
    def _sort_words(words: list[WordBox]) -> list[WordBox]:
        text = " ".join(w.text for w in words)
        letters = [ch for ch in text if ch.isalpha()]
        arabic = bool(letters) and sum("\u0600" <= ch <= "\u06ff" for ch in letters) / len(letters) > 0.5
        return sorted(words, key=lambda word: (word.bbox.y0, -word.bbox.x0 if arabic else word.bbox.x0))
