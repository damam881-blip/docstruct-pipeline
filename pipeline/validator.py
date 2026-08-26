from __future__ import annotations

from collections import Counter
from decimal import Decimal
from statistics import median
from typing import Any

import numpy as np

from models import ExtractedRow, ValidationIssue


class Validator:
    """Configurable structural, semantic, geometry, and financial validation.

    Validation never overwrites OCR values. It only adds explicit issue codes and
    marks affected rows for review.
    """

    def __init__(self, config: dict) -> None:
        self.full_config = config
        self.config = config.get("validation", {})
        self.schema = config.get("schema", {}).get("columns", [])

    def validate(self, rows: list[ExtractedRow]) -> list[ValidationIssue]:
        if not self.config.get("enabled", True):
            return []
        issues: list[ValidationIssue] = []
        confidence_threshold = float(self.config.get("confidence_threshold", 0.75))
        required = self.config.get("required_columns", [])
        expected = self.config.get("expected_columns")
        seen: Counter[tuple[str, ...]] = Counter()

        heights = [row.bbox.height for row in rows if row.bbox and row.bbox.height > 0 and not row.is_header]
        gaps = self._row_gaps(rows)
        geometry_cfg = self.config.get("geometry_check", {})

        # Robust outlier statistics are unreliable on very small tables.
        # A short table can legitimately contain rows with very different heights
        # because descriptions wrap over multiple lines.  Do not manufacture a
        # huge z-score from a near-zero scale when there is not enough evidence.
        minimum_samples = max(3, int(geometry_cfg.get("minimum_samples_for_outlier_stats", 8)))
        height_center, height_scale = (
            self._robust_center_scale(heights) if len(heights) >= minimum_samples else (0.0, 0.0)
        )
        gap_center, gap_scale = (
            self._robust_center_scale(gaps) if len(gaps) >= minimum_samples else (0.0, 0.0)
        )

        for index, row in enumerate(rows):
            row_errors: list[str] = []
            if row.row_confidence < confidence_threshold and not row.is_header:
                self._add(row_errors, issues, "LOW_CONFIDENCE", f"Row OCR confidence {row.row_confidence:.3f} is below {confidence_threshold}", row)
            if expected is not None and len(row.cells) != int(expected):
                self._add(row_errors, issues, "UNEXPECTED_COLUMN_COUNT", f"Expected {expected} columns but found {len(row.cells)}", row)
            for name in required:
                if row.normalized.get(name) in (None, "") and not row.is_header:
                    self._add(row_errors, issues, "MISSING_REQUIRED", f"Required field '{name}' is empty", row, suffix=name)

            key = tuple(str(v) for v in row.raw_values())
            seen[key] += 1
            if seen[key] > 1 and any(key):
                self._add(row_errors, issues, "DUPLICATE_ROW", "Duplicate row content detected", row)

            self._validate_cell_types(row, row_errors, issues)
            if geometry_cfg.get("enabled", True):
                self._validate_geometry(row, row_errors, issues, geometry_cfg)
                if row.bbox and height_scale > 0:
                    z = abs(row.bbox.height - height_center) / height_scale
                    if z > float(geometry_cfg.get("unusual_height_zscore", 3.0)):
                        self._add(row_errors, issues, "UNUSUAL_ROW_HEIGHT", f"Row height z-score {z:.2f} is unusual; possible merge/split error", row)
                if index > 0 and index - 1 < len(gaps) and gap_scale > 0:
                    z = abs(gaps[index - 1] - gap_center) / gap_scale
                    if z > float(geometry_cfg.get("unusual_gap_zscore", 3.0)):
                        self._add(row_errors, issues, "UNUSUAL_ROW_GAP", f"Row gap z-score {z:.2f} is unusual; possible missing/split row", row)

            if expected is not None and not row.is_header:
                empty_count = sum(cell.raw_value.strip() == "" for cell in row.cells)
                if len(row.cells) and empty_count == len(row.cells):
                    self._add(row_errors, issues, "EMPTY_ROW", "All expected cells are empty", row)
                elif empty_count > len(row.cells) * 0.75:
                    self._add(row_errors, issues, "MISSING_CELLS", f"{empty_count} of {len(row.cells)} cells are empty", row)

            row.validation_errors = row_errors
            row.validation_status = "review" if row_errors else "valid"
            for cell in row.cells:
                cell.validation_status = row.validation_status
                cell.validation_errors = list(row_errors)

        balance_cfg = self.config.get("balance_check", {})
        if balance_cfg.get("enabled", False):
            self._validate_balance_sequence(rows, issues, balance_cfg)
        return issues

    def _validate_cell_types(self, row: ExtractedRow, errors: list[str], issues: list[ValidationIssue]) -> None:
        for index, spec in enumerate(self.schema):
            if index >= len(row.cells) or row.is_header:
                continue
            cell = row.cells[index]
            raw = cell.raw_value.strip()
            if not raw:
                continue
            kind = spec.get("type", "text")
            name = spec.get("name", f"column_{index+1}")
            if kind == "date" and self.config.get("date_check", {}).get("enabled", True) and cell.normalized_value is None:
                self._add(errors, issues, "INVALID_DATE", f"Field '{name}' is not a valid configured date: {raw!r}", row, index)
            elif kind in {"amount", "number"} and self.config.get("numeric_check", {}).get("enabled", True) and cell.normalized_value is None:
                self._add(errors, issues, "INVALID_NUMERIC", f"Field '{name}' is not a valid numeric value: {raw!r}", row, index)

    def _validate_geometry(self, row: ExtractedRow, errors: list[str], issues: list[ValidationIssue], cfg: dict) -> None:
        tolerance = float(cfg.get("out_of_page_tolerance_px", 3))
        for cell in row.cells:
            if cell.bbox.x1 < cell.bbox.x0 or cell.bbox.y1 < cell.bbox.y0:
                self._add(errors, issues, "INVALID_BBOX", "Cell bounding box is invalid", row, cell.column_index)
            if cell.bbox.x0 < -tolerance or cell.bbox.y0 < -tolerance:
                self._add(errors, issues, "OUT_OF_PAGE_BBOX", "Cell bounding box starts outside the page", row, cell.column_index)
        overlap_threshold = float(cfg.get("overlap_ratio_threshold", 0.20))
        nonempty = [cell for cell in row.cells if cell.raw_value.strip() and cell.bbox.area > 0]
        for left_index, left in enumerate(nonempty):
            for right in nonempty[left_index + 1 :]:
                overlap = left.bbox.intersection_ratio(right.bbox, denominator="self")
                reverse = right.bbox.intersection_ratio(left.bbox, denominator="self")
                if max(overlap, reverse) > overlap_threshold:
                    self._add(errors, issues, "OVERLAPPING_CELLS", f"Cells {left.column_index} and {right.column_index} overlap", row)
                    return

    def _validate_balance_sequence(self, rows: list[ExtractedRow], issues: list[ValidationIssue], cfg: dict) -> None:
        data_rows = [row for row in rows if not row.is_header]
        order = cfg.get("order", "chronological")
        if order == "reverse_chronological":
            iterable = list(reversed(data_rows))
        else:
            iterable = data_rows
        previous_balance: Decimal | None = None
        for row in iterable:
            previous_balance, error = self._validate_balance(row, previous_balance, cfg)
            if error:
                if error not in row.validation_errors:
                    row.validation_errors.append(error)
                row.validation_status = "review"
                for cell in row.cells:
                    cell.validation_status = "review"
                    cell.validation_errors = list(row.validation_errors)
                issues.append(self._issue("BALANCE_MISMATCH", error, row))

    def _validate_balance(self, row: ExtractedRow, previous_balance: Decimal | None, cfg: dict) -> tuple[Decimal | None, str | None]:
        fields = cfg.get("fields", {"debit": "debit", "credit": "credit", "balance": "balance"})
        balance = self._decimal(row.normalized.get(fields.get("balance", "balance")))
        if balance is None:
            return previous_balance, None
        if previous_balance is None:
            return balance, None
        debit = self._decimal(row.normalized.get(fields.get("debit", "debit"))) or Decimal("0")
        credit = self._decimal(row.normalized.get(fields.get("credit", "credit"))) or Decimal("0")
        if cfg.get("absolute_debit_credit", True):
            debit, credit = abs(debit), abs(credit)
        formula = cfg.get("formula", "previous_balance + credit - debit")
        if formula == "previous_balance + debit - credit":
            expected = previous_balance + debit - credit
        elif formula == "previous_balance - credit + debit":
            expected = previous_balance - credit + debit
        elif formula == "previous_balance - debit + credit":
            expected = previous_balance - debit + credit
        else:
            expected = previous_balance + credit - debit
        tolerance = Decimal(str(cfg.get("tolerance", 0.01)))
        if abs(expected - balance) > tolerance:
            return balance, f"balance_mismatch expected={expected} actual={balance} tolerance={tolerance}"
        return balance, None

    @staticmethod
    def _row_gaps(rows: list[ExtractedRow]) -> list[float]:
        ordered = [row for row in rows if row.bbox and not row.is_header]
        return [max(0.0, current.bbox.y0 - previous.bbox.y1) for previous, current in zip(ordered, ordered[1:])]

    @staticmethod
    def _robust_center_scale(values: list[float]) -> tuple[float, float]:
        """Return a stable center/scale pair for geometry outlier checks.

        MAD is preferred because it is robust to outliers.  When many values are
        identical, MAD can be zero; using an artificial epsilon such as 1e-9
        turns harmless pixel differences into enormous z-scores.  In that case
        fall back to IQR, then standard deviation.  If the distribution truly
        has no measurable spread, return scale=0 so the caller skips the z-test.
        """
        clean = [float(value) for value in values if np.isfinite(value)]
        if len(clean) < 3:
            return (float(median(clean)) if clean else 0.0, 0.0)

        center = float(median(clean))
        mad = float(median([abs(value - center) for value in clean]))
        mad_scale = 1.4826 * mad
        if mad_scale > 1e-6:
            return center, mad_scale

        q1, q3 = np.percentile(np.asarray(clean, dtype=float), [25.0, 75.0])
        iqr_scale = float(q3 - q1) / 1.349
        if iqr_scale > 1e-6:
            return center, iqr_scale

        std_scale = float(np.std(np.asarray(clean, dtype=float), ddof=1))
        if std_scale > 1e-6:
            return center, std_scale

        return center, 0.0

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _add(
        self,
        errors: list[str],
        issues: list[ValidationIssue],
        code: str,
        message: str,
        row: ExtractedRow,
        column: int | None = None,
        suffix: str | None = None,
    ) -> None:
        token = code.lower() + (f":{suffix}" if suffix else "")
        if token not in errors:
            errors.append(token)
            issues.append(self._issue(code, message, row, column))

    @staticmethod
    def _issue(code: str, message: str, row: ExtractedRow, column: int | None = None) -> ValidationIssue:
        return ValidationIssue(code, message, "warning", row.page_number, row.table_id, row.row_index, column)
