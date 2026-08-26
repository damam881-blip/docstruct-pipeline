from __future__ import annotations

from hashlib import sha1

from models import LayoutType, PageType, Strategy


class PageClassifier:
    def classify_page_type(
        self,
        text_char_count: int,
        word_count: int,
        image_coverage: float,
        image_count: int,
        digital_quality: float,
        config: dict,
    ) -> PageType:
        min_chars = int(config.get("classification", {}).get("digital_min_characters", 30))
        has_text = text_char_count >= min_chars and word_count > 3
        has_scan = image_coverage >= float(config.get("classification", {}).get("scan_image_coverage_threshold", 0.70))
        if has_text and has_scan:
            return PageType.HYBRID
        if has_text:
            return PageType.DIGITAL
        return PageType.SCANNED

    def classify_layout(
        self,
        horizontal_density: float,
        vertical_density: float,
        alignment_score: float,
        table_region_count: int,
        config: dict,
    ) -> LayoutType:
        c = config.get("classification", {})
        h_min = float(c.get("horizontal_line_density_min", 0.002))
        v_min = float(c.get("vertical_line_density_min", 0.001))
        aligned_min = float(c.get("alignment_score_min", 0.35))
        has_h = horizontal_density >= h_min
        has_v = vertical_density >= v_min
        if has_h and has_v:
            return LayoutType.MIXED if table_region_count > 1 else LayoutType.BORDERED_TABLE
        if has_h or has_v:
            return LayoutType.MIXED
        if alignment_score >= aligned_min:
            return LayoutType.BORDERLESS_TABLE
        return LayoutType.FREE_TEXT

    def choose_strategy(self, page_type: PageType, layout_type: LayoutType, digital_quality: float, config: dict) -> Strategy:
        digital_cfg = config.get("digital_text", {})
        quality_min = float(digital_cfg.get("quality_min", 0.72))
        fallback_to_ocr = bool(digital_cfg.get("fallback_to_ocr_when_garbled", True))

        if page_type in {PageType.DIGITAL, PageType.HYBRID}:
            # High-quality selectable text is always preferred because it is
            # lossless and avoids OCR. Low-quality/garbled text falls back to
            # OCR by default, but the behavior can be explicitly disabled for
            # debugging or exceptional PDFs.
            if digital_quality >= quality_min or not fallback_to_ocr:
                return Strategy.DIGITAL_TEXT

        if layout_type == LayoutType.BORDERED_TABLE:
            return Strategy.CELL_OCR
        if layout_type in {LayoutType.BORDERLESS_TABLE, LayoutType.MIXED}:
            return Strategy.ROW_OCR
        return Strategy.FULL_PAGE_OCR

    @staticmethod
    def signature(values: list[object]) -> str:
        payload = "|".join(str(v) for v in values)
        return sha1(payload.encode("utf-8")).hexdigest()[:12]
