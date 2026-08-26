from __future__ import annotations

import cv2
import numpy as np

from models import BBox, WordBox
from pipeline.bordered_table_detector import BorderedTableDetector
from pipeline.borderless_table_detector import BorderlessTableDetector
from pipeline.column_detector import detect_column_anchors


def config():
    return {
        "bordered_table": {
            "minimum_region_area_ratio": 0.002,
            "horizontal": {"kernel_width_ratio": 0.04, "kernel_height": 1, "merge_gap_px": 3},
            "vertical": {"kernel_height_ratio": 0.04, "kernel_width": 1, "merge_gap_px": 3},
            "cells": {"minimum_width_px": 10, "minimum_height_px": 10, "minimum_area_px": 100},
            "row_merge_tolerance_px": 3,
            "column_merge_tolerance_px": 3,
        },
        "borderless_table": {
            "row_detection": {"baseline_tolerance_px": 5, "y_overlap_ratio": 0.4, "continuation_line_gap_px": 10, "merge_multiline_rows": True},
            "column_detection": {"x_tolerance_px": 12, "minimum_column_gap_px": 20, "expected_columns": 3},
            "clustering": {"min_samples": 1},
        },
    }


def test_bordered_table_detection():
    image = np.zeros((400, 600), dtype=np.uint8)
    for x in [50, 200, 400, 550]:
        cv2.line(image, (x, 50), (x, 350), 255, 2)
    for y in [50, 120, 200, 280, 350]:
        cv2.line(image, (50, y), (550, y), 255, 2)
    detection = BorderedTableDetector(config()).detect(image)
    assert detection.regions
    assert len(detection.regions[0].column_boundaries) >= 4
    assert len(detection.cells_by_table[detection.regions[0].table_id]) >= 8


def test_multiple_table_detection():
    image = np.zeros((500, 600), dtype=np.uint8)
    for offset in [30, 280]:
        cv2.rectangle(image, (50, offset), (550, offset + 160), 255, 2)
        cv2.line(image, (300, offset), (300, offset + 160), 255, 2)
        cv2.line(image, (50, offset + 80), (550, offset + 80), 255, 2)
    detection = BorderedTableDetector(config()).detect(image)
    assert len(detection.regions) >= 2


def test_borderless_row_and_column_detection():
    words = [
        WordBox("2026-01-01", BBox(10, 10, 80, 20)), WordBox("Coffee", BBox(150, 10, 220, 20)), WordBox("10.00", BBox(400, 10, 450, 20)),
        WordBox("2026-01-02", BBox(10, 40, 80, 50)), WordBox("Taxi", BBox(150, 40, 220, 50)), WordBox("20.00", BBox(400, 40, 450, 50)),
    ]
    detection = BorderlessTableDetector(config()).detect(words, "x.pdf", 1, BBox(0, 0, 500, 100))
    rows = detection.rows_by_table["table_01"]
    assert len(rows) == 2
    assert len(rows[0].cells) == 3
    assert rows[0].cells[1].raw_value == "Coffee"


def test_column_clustering():
    words = [WordBox("a", BBox(10, 0, 20, 10)), WordBox("b", BBox(12, 20, 22, 30)), WordBox("c", BBox(200, 0, 210, 10))]
    anchors = detect_column_anchors(words, 15)
    assert len(anchors) == 2


def test_multiline_description_merging():
    cfg = config()
    cfg["borderless_table"]["row_detection"].update({
        "anchor_type": "date",
        "anchor_x_range_ratio": [0.0, 0.25],
        "continuation_line_gap_px": 12,
    })
    words = [
        WordBox("2026-01-01", BBox(10, 10, 90, 20)),
        WordBox("Long", BBox(150, 10, 190, 20)),
        WordBox("description", BBox(200, 10, 280, 20)),
        WordBox("continued", BBox(150, 25, 220, 35)),
        WordBox("text", BBox(230, 25, 260, 35)),
        WordBox("2026-01-02", BBox(10, 55, 90, 65)),
        WordBox("Next", BBox(150, 55, 190, 65)),
    ]
    detection = BorderlessTableDetector(cfg).detect(words, "x.pdf", 1, BBox(0, 0, 500, 100))
    rows = detection.rows_by_table["table_01"]
    assert len(rows) == 2
    assert "continued" in " ".join(cell.raw_value for cell in rows[0].cells)
