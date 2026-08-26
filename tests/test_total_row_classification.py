from __future__ import annotations

from models import BBox, ExtractedCell, ExtractedRow
from pipeline.data_reconstructor import DataReconstructor


def _make_row(values: list[str]) -> ExtractedRow:
    cells = [
        ExtractedCell(
            "f.pdf",
            1,
            "table_01",
            0,
            index,
            BBox(index * 10, 0, index * 10 + 9, 9),
            None,
            "test",
            0.9,
            value,
            value,
        )
        for index, value in enumerate(values)
    ]
    return ExtractedRow(
        "f.pdf",
        1,
        "table_01",
        0,
        cells,
        BBox(0, 0, max(10, len(values) * 10), 9),
        0.9,
    )


def _reconstructor() -> DataReconstructor:
    return DataReconstructor(
        {
            "schema": {"columns": []},
            "reconstruction": {"remove_repeated_headers": False},
        }
    )


def test_total_inside_transaction_description_is_not_total_row() -> None:
    row = _make_row(
        [
            "897.25",
            "20.01",
            "",
            "Total POS Purchase for MADA Net SPANMRC for Machine 111TS993IT8SOT68 Value Dated 20260625",
            "ATMTOT2O 2606256711 30000000 0005587",
            "06/25/2026",
            "18:53:00",
        ]
    )

    [normalized] = _reconstructor().normalize_rows([row])
    assert normalized.is_total is False


def test_fees_for_total_inside_transaction_description_is_not_total_row() -> None:
    row = _make_row(
        [
            "897.17",
            "",
            "-0.07",
            "Fees for Total POS Purchase for SFEEMRC MADA Net for Machine 111TS9931I8SOT68 Value Dated 20260625",
            "ATMT0T202606256711300000000005588",
            "06/25/2026",
            "18:53:00",
        ]
    )

    [normalized] = _reconstructor().normalize_rows([row])
    assert normalized.is_total is False


def test_short_total_label_is_total_row() -> None:
    row = _make_row(["", "", "", "Total Amount", "", "", ""])

    [normalized] = _reconstructor().normalize_rows([row])
    assert normalized.is_total is True


def test_strong_summary_labels_are_total_rows() -> None:
    reconstructor = _reconstructor()
    for label in ("Grand Total", "Subtotal", "الإجمالي", "المجموع", "الرصيد الختامي"):
        row = _make_row(["", "", "", label, "", "", ""])
        [normalized] = reconstructor.normalize_rows([row])
        assert normalized.is_total is True
