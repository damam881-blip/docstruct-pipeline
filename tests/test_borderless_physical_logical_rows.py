from __future__ import annotations

from models import BBox, WordBox
from pipeline.borderless_table_detector import BorderlessTableDetector


def _config() -> dict:
    return {
        "borderless_table": {
            "enabled": True,
            "row_detection": {
                "baseline_tolerance_px": 8,
                "y_overlap_ratio": 0.50,
                "continuation_line_gap_px": 18,
                "merge_multiline_rows": True,
                "anchor_type": "date",
                "anchor_x_range_ratio": [0.80, 1.00],
            },
            "column_detection": {
                "x_tolerance_px": 15,
                "x_tolerance_word_height_ratio": 1.0,
                "maximum_x_tolerance_page_ratio": 0.05,
                "minimum_column_gap_px": 20,
                "expected_columns": None,
                "minimum_column_support_rows": 3,
                "minimum_column_support_ratio": 0.20,
                "maximum_columns": 12,
            },
            "clustering": {"min_samples": 1},
        }
    }


def _word(text: str, x0: float, y0: float, x1: float, y1: float) -> WordBox:
    return WordBox(text=text, bbox=BBox(x0, y0, x1, y1), confidence=0.95, source="test")


def test_merge_continuations_does_not_mutate_physical_rows() -> None:
    detector = BorderlessTableDetector(_config())
    detector._page_width = 1000.0

    physical_rows = [
        [
            _word("Transaction", 300, 100, 430, 110),
            _word("2026/08/23", 850, 100, 950, 110),
        ],
        [
            _word("REF123456", 310, 115, 420, 125),
        ],
    ]

    original_lengths = [len(row) for row in physical_rows]
    original_texts = [[word.text for word in row] for row in physical_rows]

    logical_rows = detector._merge_continuations(physical_rows)

    assert len(logical_rows) == 1
    assert [word.text for word in logical_rows[0]] == [
        "Transaction",
        "2026/08/23",
        "REF123456",
    ]

    # The physical source geometry must remain unchanged.
    assert [len(row) for row in physical_rows] == original_lengths
    assert [[word.text for word in row] for row in physical_rows] == original_texts
    assert logical_rows[0] is not physical_rows[0]


def test_detect_records_physical_and_logical_rows_and_keeps_logical_column_source() -> None:
    detector = BorderlessTableDetector(_config())

    words = [
        _word("Transaction", 300, 100, 430, 110),
        _word("2026/08/23", 850, 100, 950, 110),
        _word("REF123456", 310, 115, 420, 125),
    ]

    detection = detector.detect(
        words=words,
        file_name="synthetic.pdf",
        page_number=1,
        page_bbox=BBox(0, 0, 1000, 1400),
    )

    assert detection.measurements["physical_row_count"] == 2
    assert detection.measurements["logical_row_count"] == 1
    assert detection.measurements["row_count"] == 1
    assert detection.measurements["column_inference_source"] == "logical_rows"
