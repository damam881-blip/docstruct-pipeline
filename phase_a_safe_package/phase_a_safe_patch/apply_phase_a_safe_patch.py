from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import sys

ROOT = Path.cwd()
TARGET = ROOT / "pipeline" / "borderless_table_detector.py"
TEST_TARGET = ROOT / "tests" / "test_borderless_physical_logical_rows.py"
BACKUP = ROOT / "pipeline" / "borderless_table_detector.py.pre_phase_a_safe.bak"
CONFIG = ROOT / "configs" / "default.yaml"

OLD_DETECT = '''    def detect(self, words: list[WordBox], file_name: str, page_number: int, page_bbox: BBox) -> BorderlessDetection:\n        if not self.config.get("enabled", True):\n            return BorderlessDetection([], {}, {}, {"disabled": True})\n        if not words:\n            return BorderlessDetection([], {}, {}, {})\n        self._page_width = page_bbox.width\n        row_cfg = self.config.get("row_detection", {})\n        tolerance = float(row_cfg.get("baseline_tolerance_px", 8))\n        rows = self._cluster_rows(words, tolerance)\n        rows = self._merge_continuations(rows)\n        anchors = self._infer_anchors(rows, page_bbox.width)\n        table_id = "table_01"\n        extracted_rows = self._build_rows(rows, anchors, file_name, page_number, table_id)\n        bbox = union_bbox([w.bbox for w in words]) or page_bbox\n        region = TableRegion(table_id, bbox, LayoutType.BORDERLESS_TABLE, self._consistency_score(extracted_rows), [], anchors)\n        gaps = [anchors[i + 1] - anchors[i] for i in range(len(anchors) - 1)]\n        return BorderlessDetection(\n            [region],\n            {table_id: extracted_rows},\n            {table_id: anchors},\n            {\n                "row_count": len(extracted_rows),\n                "column_count": max(0, len(anchors) - 1),\n                "median_column_gap": float(median(gaps)) if gaps else 0.0,\n            },\n        )\n'''

NEW_DETECT = '''    def detect(self, words: list[WordBox], file_name: str, page_number: int, page_bbox: BBox) -> BorderlessDetection:\n        if not self.config.get("enabled", True):\n            return BorderlessDetection([], {}, {}, {"disabled": True})\n        if not words:\n            return BorderlessDetection([], {}, {}, {})\n        self._page_width = page_bbox.width\n        row_cfg = self.config.get("row_detection", {})\n        tolerance = float(row_cfg.get("baseline_tolerance_px", 8))\n\n        # Keep the raw visual row grouping intact. Logical multiline merging must\n        # never mutate this source geometry because later phases may need the\n        # original physical rows for diagnostics or alternative reconstruction.\n        physical_rows = self._cluster_rows(words, tolerance)\n        logical_rows = self._merge_continuations(physical_rows)\n\n        # Phase A is intentionally behavior-preserving: column inference remains\n        # based on logical rows. A later phase can change the column-topology\n        # algorithm independently, with its own regression coverage.\n        anchors = self._infer_anchors(logical_rows, page_bbox.width)\n        table_id = "table_01"\n        extracted_rows = self._build_rows(logical_rows, anchors, file_name, page_number, table_id)\n        bbox = union_bbox([w.bbox for w in words]) or page_bbox\n        region = TableRegion(table_id, bbox, LayoutType.BORDERLESS_TABLE, self._consistency_score(extracted_rows), [], anchors)\n        gaps = [anchors[i + 1] - anchors[i] for i in range(len(anchors) - 1)]\n        return BorderlessDetection(\n            [region],\n            {table_id: extracted_rows},\n            {table_id: anchors},\n            {\n                "row_count": len(extracted_rows),\n                "physical_row_count": len(physical_rows),\n                "logical_row_count": len(logical_rows),\n                "column_inference_source": "logical_rows",\n                "column_count": max(0, len(anchors) - 1),\n                "median_column_gap": float(median(gaps)) if gaps else 0.0,\n            },\n        )\n'''

OLD_MERGE = '''    def _merge_continuations(self, rows: list[list[WordBox]]) -> list[list[WordBox]]:\n        cfg = self.config.get("row_detection", {})\n        if not cfg.get("merge_multiline_rows", True) or len(rows) < 2:\n            return rows\n        continuation_gap = float(cfg.get("continuation_line_gap_px", 18))\n        result: list[list[WordBox]] = [rows[0]]\n        for row in rows[1:]:\n            previous = result[-1]\n            prev_box, row_box = union_bbox([w.bbox for w in previous]), union_bbox([w.bbox for w in row])\n            if prev_box is None or row_box is None:\n                result.append(row)\n                continue\n            gap = row_box.y0 - prev_box.y1\n            prev_has_anchor = self._has_row_anchor(previous)\n            current_has_anchor = self._has_row_anchor(row)\n            if gap <= continuation_gap and prev_has_anchor and not current_has_anchor:\n                previous.extend(row)\n            else:\n                result.append(row)\n        return result\n'''

NEW_MERGE = '''    def _merge_continuations(self, rows: list[list[WordBox]]) -> list[list[WordBox]]:\n        cfg = self.config.get("row_detection", {})\n\n        # Return independent row lists even when merging is disabled. This keeps\n        # callers from accidentally aliasing and mutating the physical rows.\n        if not cfg.get("merge_multiline_rows", True) or len(rows) < 2:\n            return [list(row) for row in rows]\n\n        continuation_gap = float(cfg.get("continuation_line_gap_px", 18))\n        result: list[list[WordBox]] = [list(rows[0])]\n        for row in rows[1:]:\n            current = list(row)\n            previous = result[-1]\n            prev_box, row_box = union_bbox([w.bbox for w in previous]), union_bbox([w.bbox for w in current])\n            if prev_box is None or row_box is None:\n                result.append(current)\n                continue\n            gap = row_box.y0 - prev_box.y1\n            prev_has_anchor = self._has_row_anchor(previous)\n            current_has_anchor = self._has_row_anchor(current)\n            if gap <= continuation_gap and prev_has_anchor and not current_has_anchor:\n                previous.extend(current)\n            else:\n                result.append(current)\n        return result\n'''

TEST_CONTENT = r'''from __future__ import annotations

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
'''


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


if not TARGET.exists():
    fail(f"Target file not found: {TARGET}")
if not CONFIG.exists():
    fail(f"Config file not found: {CONFIG}")

config_hash_before = sha256(CONFIG)
source = TARGET.read_text(encoding="utf-8")

if NEW_DETECT in source and NEW_MERGE in source:
    print("Phase A safe patch already appears to be applied; source patch skipped.")
elif OLD_DETECT not in source or OLD_MERGE not in source:
    fail(
        "Live source does not match the validated methods used to build this patch. "
        "No files were changed. Re-extract phase_a_live_methods.txt before proceeding."
    )
else:
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
        print(f"Backup created: {BACKUP}")
    else:
        print(f"Backup already exists: {BACKUP}")

    patched = source.replace(OLD_DETECT, NEW_DETECT, 1)
    patched = patched.replace(OLD_MERGE, NEW_MERGE, 1)
    TARGET.write_text(patched, encoding="utf-8")
    print(f"Patched: {TARGET}")

TEST_TARGET.write_text(TEST_CONTENT, encoding="utf-8")
print(f"Regression test written: {TEST_TARGET}")

config_hash_after = sha256(CONFIG)
print(f"default.yaml SHA256 before: {config_hash_before}")
print(f"default.yaml SHA256 after : {config_hash_after}")
if config_hash_before != config_hash_after:
    fail("default.yaml changed unexpectedly. Restore it before continuing.")

print("\nPhase A safe patch applied successfully.")
print("Next: python -m pytest -q")
