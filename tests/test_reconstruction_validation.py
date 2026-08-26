from __future__ import annotations

from decimal import Decimal

from models import BBox, ExtractedCell, ExtractedRow
from pipeline.data_reconstructor import DataReconstructor
from pipeline.validator import Validator


def make_row(index, values, confidence=0.9):
    cells = [ExtractedCell("f.pdf", 1, "table_01", index, i, BBox(i*10, index*10, i*10+9, index*10+9), None, "test", confidence, v, v) for i, v in enumerate(values)]
    return ExtractedRow("f.pdf", 1, "table_01", index, cells, BBox(0, index*10, 100, index*10+9), confidence)


def config():
    return {
        "schema": {"columns": [
            {"name": "date", "type": "date"},
            {"name": "description", "type": "text"},
            {"name": "debit", "type": "amount"},
            {"name": "credit", "type": "amount"},
            {"name": "balance", "type": "amount"},
        ]},
        "reconstruction": {"remove_repeated_headers": False, "header_keywords": ["date", "description"]},
        "validation": {
            "enabled": True,
            "confidence_threshold": 0.75,
            "expected_columns": 5,
            "required_columns": ["date", "description", "balance"],
            "date_check": {"allowed_formats": ["%d/%m/%Y", "%Y-%m-%d"]},
            "balance_check": {"enabled": True, "formula": "previous_balance + credit - debit", "tolerance": 0.01, "fields": {"debit": "debit", "credit": "credit", "balance": "balance"}},
        },
    }


def test_arabic_numeral_normalization():
    assert DataReconstructor.normalize_digits("١٢٣٤٥") == "12345"


def test_financial_amount_parsing():
    assert DataReconstructor.parse_amount("(١٬٢٣٤٫٥٠)".replace("٬", ",").replace("٫", ".")) == Decimal("-1234.50")
    assert DataReconstructor.parse_amount("1,234.50") == Decimal("1234.50")


def test_date_normalization():
    r = DataReconstructor(config())
    assert r.parse_date("٣٠/٠٦/٢٠٢٦") == "2026-06-30"


def test_balance_validation_success():
    rows = [
        make_row(0, ["2026-01-01", "Opening", "", "", "100.00"]),
        make_row(1, ["2026-01-02", "Sale", "", "50.00", "150.00"]),
        make_row(2, ["2026-01-03", "Expense", "20.00", "", "130.00"]),
    ]
    rows = DataReconstructor(config()).normalize_rows(rows)
    issues = Validator(config()).validate(rows)
    assert not [i for i in issues if i.code == "BALANCE_MISMATCH"]


def test_missing_cell_handling():
    row = make_row(0, ["", "", "", "", ""])
    rows = DataReconstructor(config()).normalize_rows([row])
    issues = Validator(config()).validate(rows)
    assert any(i.code == "MISSING_REQUIRED" for i in issues)


def test_invalid_date_and_numeric_are_flagged():
    row = make_row(0, ["31/99/2026", "Expense", "not-number", "", "100.00"])
    rows = DataReconstructor(config()).normalize_rows([row])
    issues = Validator(config()).validate(rows)
    codes = {issue.code for issue in issues}
    assert "INVALID_DATE" in codes
    assert "INVALID_NUMERIC" in codes
