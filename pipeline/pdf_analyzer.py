from __future__ import annotations

from pathlib import Path
from typing import Iterator

import cv2
import pymupdf as fitz
import numpy as np

from models import BBox, LayoutType, PageAnalysis, PageType, Strategy, TableRegion
from pipeline.digital_extractor import DigitalTextExtractor
from pipeline.page_classifier import PageClassifier


class PDFAnalyzer:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.digital = DigitalTextExtractor()
        self.classifier = PageClassifier()

    def analyze_pdf(self, input_path: str | Path, pages: list[int] | None = None, render_layout: bool = True) -> Iterator[PageAnalysis]:
        doc = fitz.open(str(input_path))
        page_numbers = pages or list(range(1, len(doc) + 1))
        previous_signature: str | None = None
        for page_number in page_numbers:
            analysis = self.analyze_page(doc, page_number, render_layout=render_layout)
            analysis.measurements["similar_to_previous_page"] = (
                previous_signature is not None and analysis.layout_signature == previous_signature
            )
            previous_signature = analysis.layout_signature
            yield analysis

    def analyze_page(self, doc: fitz.Document, page_number: int, render_layout: bool = True) -> PageAnalysis:
        page = doc[page_number - 1]
        text = page.get_text("text") or ""
        words = self.digital.extract_words(page)
        images = page.get_images(full=True)
        drawings = page.get_drawings()
        page_area = page.rect.width * page.rect.height
        image_coverage = self._image_coverage(page, images, page_area)
        digital_quality = self.digital.text_quality(text)
        alignment = self.digital.alignment_score(words, page.rect.height)
        estimated_dpi = self._estimated_dpi(doc, page, images)

        h_density = v_density = 0.0
        table_regions: list[TableRegion] = []
        image_measurements: dict[str, float] = {
            "average_character_height": 0.0,
            "average_row_height": 0.0,
            "average_column_gap": 0.0,
            "line_intersection_density": 0.0,
            "image_alignment_score": 0.0,
        }
        if render_layout:
            thumb_dpi = float(self.config.get("analysis", {}).get("thumbnail_dpi", 96))
            scale = thumb_dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
            h_density, v_density, raw_regions, image_measurements = self._quick_lines(binary)
            # Scanned pages have no digital WordBoxes. Use connected-component
            # baseline alignment as a page-layout signal instead of forcing
            # their alignment score to zero.
            alignment = max(alignment, float(image_measurements.get("image_alignment_score", 0.0)))
            factor = 72.0 / thumb_dpi
            table_regions = [
                TableRegion(f"table_{i+1:02d}", BBox(x * factor, y * factor, (x+w) * factor, (y+h) * factor), LayoutType.BORDERED_TABLE, 0.55)
                for i, (x, y, w, h) in enumerate(raw_regions)
            ]

        page_type = self.classifier.classify_page_type(len(text.strip()), len(words), image_coverage, len(images), digital_quality, self.config)
        layout_type = self.classifier.classify_layout(h_density, v_density, alignment, len(table_regions), self.config)
        strategy = self.classifier.choose_strategy(page_type, layout_type, digital_quality, self.config)
        signature = self.classifier.signature(
            [round(page.rect.width), round(page.rect.height), page_type.value, layout_type.value, round(h_density, 4), round(v_density, 4), len(images), len(table_regions)]
        )
        warnings: list[str] = []
        if page_type in {PageType.DIGITAL, PageType.HYBRID} and digital_quality < self.config.get("digital_text", {}).get("quality_min", 0.72):
            warnings.append("Digital text exists but appears corrupted or garbled; OCR fallback is recommended.")
        return PageAnalysis(
            page_number,
            page_type,
            layout_type,
            h_density > 0.001,
            v_density > 0.001,
            table_regions,
            float(page.rotation),
            strategy,
            float(page.rect.width),
            float(page.rect.height),
            estimated_dpi,
            len(text.strip()),
            len(words),
            len(images),
            len(drawings),
            len(text.strip()) / page_area if page_area else 0.0,
            image_coverage,
            h_density,
            v_density,
            alignment,
            digital_quality,
            strategy != Strategy.DIGITAL_TEXT,
            signature,
            {
                "page_width_in": page.rect.width / 72.0,
                "page_height_in": page.rect.height / 72.0,
                "image_count": len(images),
                "drawing_count": len(drawings),
                "average_character_height": self._average_word_height(words) or image_measurements["average_character_height"],
                "average_row_height": image_measurements["average_row_height"],
                "average_column_gap": image_measurements["average_column_gap"],
                "line_intersection_density": image_measurements["line_intersection_density"],
                "numeric_text_percentage": self._numeric_text_percentage(words),
                "alignment_consistency": alignment,
                "image_alignment_score": image_measurements.get("image_alignment_score", 0.0),
                "table_region_count": len(table_regions),
            },
            warnings,
        )

    @staticmethod
    def _image_coverage(page: fitz.Page, images: list[tuple], page_area: float) -> float:
        coverages: list[float] = []
        for info in images:
            try:
                rects = page.get_image_rects(info[0])
            except Exception:
                rects = []
            coverages.extend((r.width * r.height) / page_area for r in rects if page_area)
        return min(1.0, max(coverages, default=0.0))

    @staticmethod
    def _estimated_dpi(doc: fitz.Document, page: fitz.Page, images: list[tuple]) -> float | None:
        values: list[float] = []
        for info in images:
            xref = int(info[0])
            try:
                pix = fitz.Pixmap(doc, xref)
                rects = page.get_image_rects(xref)
                for rect in rects:
                    if rect.width > 0:
                        values.append(pix.width / (rect.width / 72.0))
            except Exception:
                continue
        return max(values) if values else None

    def _quick_lines(self, binary: np.ndarray) -> tuple[float, float, list[tuple[int, int, int, int]], dict[str, float]]:
        h, w = binary.shape
        hk = max(5, int(w * 0.04))
        vk = max(5, int(h * 0.04))
        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (hk, 1)))
        vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, vk)))
        combined = cv2.bitwise_or(horizontal, vertical)
        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regions = []
        for contour in contours:
            x, y, rw, rh = cv2.boundingRect(contour)
            if rw * rh >= h * w * 0.015 and rw > w * 0.15 and rh > h * 0.04:
                regions.append((x, y, rw, rh))

        # Connected components supply transparent scan measurements before OCR.
        text_only = cv2.bitwise_and(binary, cv2.bitwise_not(combined))
        count, _, stats, centroids = cv2.connectedComponentsWithStats((text_only > 0).astype(np.uint8), 8)
        components: list[tuple[float, float, float, float]] = []
        for idx in range(1, count):
            x, y, cw, ch, area = stats[idx]
            if 2 <= area <= max(1500, int(h * w * 0.002)) and 1 <= ch <= h * 0.08 and 1 <= cw <= w * 0.15:
                components.append((float(x), float(y), float(cw), float(ch)))
        heights = [item[3] for item in components]
        centers_y = sorted(item[1] + item[3] / 2 for item in components)
        row_gaps = [b - a for a, b in zip(centers_y, centers_y[1:]) if 1 < b - a < h * 0.08]
        centers_x = sorted(item[0] + item[2] / 2 for item in components)
        col_gaps = [b - a for a, b in zip(centers_x, centers_x[1:]) if 1 < b - a < w * 0.20]
        # Estimate row alignment directly from connected components. This is a
        # lightweight scan-layout signal, not OCR: components sharing a similar
        # vertical center are treated as one visual text line.
        alignment_tolerance = max(2.0, h * 0.004)
        alignment_groups: list[list[float]] = []
        for center_y in centers_y:
            if not alignment_groups or abs(center_y - float(np.mean(alignment_groups[-1]))) > alignment_tolerance:
                alignment_groups.append([center_y])
            else:
                alignment_groups[-1].append(center_y)
        aligned_components = sum(len(group) for group in alignment_groups if len(group) >= 3)
        image_alignment_score = aligned_components / len(components) if components else 0.0

        metrics = {
            "average_character_height": float(np.median(heights)) if heights else 0.0,
            "average_row_height": float(np.median(row_gaps)) if row_gaps else 0.0,
            "average_column_gap": float(np.median(col_gaps)) if col_gaps else 0.0,
            "line_intersection_density": float(np.mean(cv2.bitwise_and(horizontal, vertical) > 0)),
            "image_alignment_score": float(image_alignment_score),
        }
        return (
            float(np.mean(horizontal > 0)),
            float(np.mean(vertical > 0)),
            sorted(regions, key=lambda r: (r[1], r[0])),
            metrics,
        )

    @staticmethod
    def _average_word_height(words) -> float:
        heights = [word.bbox.height for word in words if word.bbox.height > 0]
        return float(np.median(heights)) if heights else 0.0

    @staticmethod
    def _numeric_text_percentage(words) -> float:
        characters = "".join(word.text for word in words)
        if not characters:
            return 0.0
        return sum(char.isdigit() for char in characters) / len(characters)
