from __future__ import annotations

import math
import unicodedata
from typing import Any

import pymupdf as fitz

from models import BBox, WordBox


class DigitalTextExtractor:
    def extract_words(self, page: fitz.Page) -> list[WordBox]:
        words = []
        for item in page.get_text("words", sort=False):
            x0, y0, x1, y1, text, block, line, word = item[:8]
            if not str(text).strip():
                continue
            words.append(
                WordBox(
                    text=str(text),
                    bbox=BBox(float(x0), float(y0), float(x1), float(y1)),
                    confidence=1.0,
                    source="digital",
                    block_no=int(block),
                    line_no=int(line),
                    word_no=int(word),
                )
            )
        return words

    def extract_spans(self, page: fitz.Page) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        raw = page.get_text("dict")
        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    result.append(
                        {
                            "text": span.get("text", ""),
                            "bbox": span.get("bbox"),
                            "font": span.get("font"),
                            "size": span.get("size"),
                            "flags": span.get("flags"),
                            "color": span.get("color"),
                        }
                    )
        return result

    @staticmethod
    def text_quality(text: str) -> float:
        text = text.strip()
        if not text:
            return 0.0
        printable = sum(ch.isprintable() for ch in text) / len(text)
        useful = sum(ch.isalnum() or ch.isspace() or ch in ".,/-():%" for ch in text) / len(text)
        control = sum(unicodedata.category(ch).startswith("C") for ch in text) / len(text)
        private_or_symbol = sum(
            unicodedata.category(ch) in {"Co", "Cs"} or (0x0100 <= ord(ch) <= 0x02FF and not ch.isalpha())
            for ch in text
        ) / len(text)
        replacement = text.count("�") / len(text)
        score = 0.45 * printable + 0.55 * useful - 0.8 * control - 0.5 * private_or_symbol - replacement
        return max(0.0, min(1.0, score))

    @staticmethod
    def alignment_score(words: list[WordBox], page_height: float) -> float:
        if len(words) < 5:
            return 0.0
        centers = sorted(w.bbox.center[1] for w in words)
        tolerance = max(1.5, page_height * 0.003)
        groups: list[list[float]] = []
        for y in centers:
            if not groups or abs(y - sum(groups[-1]) / len(groups[-1])) > tolerance:
                groups.append([y])
            else:
                groups[-1].append(y)
        aligned = sum(len(g) for g in groups if len(g) >= 3)
        return aligned / len(words)
