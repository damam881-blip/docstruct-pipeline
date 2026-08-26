from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from models import ExtractedRow


ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


class DataReconstructor:
    def __init__(self, config: dict) -> None:
        self.config = config

    @staticmethod
    def normalize_digits(value: str) -> str:
        return value.translate(ARABIC_DIGITS)

    @classmethod
    def parse_amount(cls, value: str) -> Decimal | None:
        raw = cls.normalize_digits(value).strip()
        if not raw:
            return None
        negative = raw.startswith("(") and raw.endswith(")")
        raw = raw.strip("() ")
        raw = raw.replace("−", "-").replace("–", "-")
        raw = re.sub(r"[^0-9,\.\-+]", "", raw)
        if not raw or raw in {"-", "+", ".", ","}:
            return None
        if "," in raw and "." in raw:
            if raw.rfind(",") > raw.rfind("."):
                raw = raw.replace(".", "").replace(",", ".")
            else:
                raw = raw.replace(",", "")
        elif "," in raw:
            parts = raw.split(",")
            if len(parts[-1]) in {1, 2, 3}:
                raw = "".join(parts[:-1]) + "." + parts[-1]
            else:
                raw = raw.replace(",", "")
        try:
            number = Decimal(raw)
            return -abs(number) if negative else number
        except InvalidOperation:
            return None

    def parse_date(self, value: str) -> str | None:
        raw = self.normalize_digits(value).strip()
        formats = self.config.get("validation", {}).get("date_check", {}).get("allowed_formats", ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"])
        raw = re.sub(r"\s+", "", raw)
        for fmt in formats:
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue
        match = re.search(r"(20\d{2})[/-]?(\d{2})[/-]?(\d{2})", raw)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date().isoformat()
            except ValueError:
                return None
        return None

    def normalize_rows(self, rows: list[ExtractedRow]) -> list[ExtractedRow]:
        schema = self.config.get("schema", {})
        columns: list[dict[str, Any]] = schema.get("columns", [])
        for row in rows:
            row.normalized = {}
            for idx, cell in enumerate(row.cells):
                spec = columns[idx] if idx < len(columns) else {"name": f"column_{idx+1}", "type": "text"}
                name = spec.get("name", f"column_{idx+1}")
                kind = spec.get("type", "text")
                raw = cell.raw_value.strip()
                if kind in {"amount", "number"}:
                    value = self.parse_amount(raw)
                    normalized = float(value) if value is not None else None
                elif kind == "date":
                    normalized = self.parse_date(raw)
                else:
                    normalized = re.sub(r"\s+", " ", self.normalize_digits(raw)).strip()
                cell.normalized_value = normalized
                row.normalized[name] = normalized
            row.is_header = self._looks_like_header(row)
            row.is_total = self._looks_like_total(row)
        return self._drop_repeated_headers(rows)

    def _looks_like_header(self, row: ExtractedRow) -> bool:
        raw = " ".join(row.raw_values()).lower()
        # Transaction descriptions often contain words such as "Total" and
        # "Dated". A row with multiple financial values is therefore data,
        # not a repeated table header.
        parseable_amounts = sum(self.parse_amount(value) is not None for value in row.raw_values())
        if parseable_amounts >= 2:
            return False
        keywords = self.config.get("reconstruction", {}).get("header_keywords", ["date", "description", "debit", "credit", "balance", "التاريخ", "البيان", "مدين", "دائن", "الرصيد"])
        return sum(keyword.lower() in raw for keyword in keywords) >= 2

    def _looks_like_total(self, row: ExtractedRow) -> bool:
        """Return True only when a row looks like an actual summary/total row.

        A plain occurrence of the word ``total`` inside a long transaction
        description is not enough.  This avoids false positives such as
        ``Total POS Purchase ...`` while still recognizing label-like summary
        rows such as ``Total``, ``Total Amount``, ``Subtotal`` and
        ``Grand Total``.
        """
        values = [re.sub(r"\s+", " ", value).strip().lower() for value in row.raw_values()]
        nonempty = [value for value in values if value]
        if not nonempty:
            return False

        # Strong summary phrases are sufficiently specific on their own.
        strong_phrases = (
            "grand total",
            "subtotal",
            "sub total",
            "الإجمالي",
            "الاجمالي",
            "المجموع",
            "الرصيد الختامي",
        )
        if any(phrase in value for value in nonempty for phrase in strong_phrases):
            return True

        # Treat plain English "total" as a summary marker only when it appears
        # in a short, label-like cell.  Long narrative cells are transaction
        # descriptions and must not turn the whole row into a total row.
        for value in nonempty:
            if not re.search(r"\btotal\b", value):
                continue
            words = re.findall(r"[a-z]+", value)
            if len(words) <= 4:
                return True

        return False

    def _drop_repeated_headers(self, rows: list[ExtractedRow]) -> list[ExtractedRow]:
        if not self.config.get("reconstruction", {}).get("remove_repeated_headers", True):
            return rows
        keep_first = True
        output: list[ExtractedRow] = []
        for row in rows:
            if row.is_header:
                if keep_first:
                    output.append(row)
                    keep_first = False
                continue
            output.append(row)
        return output
