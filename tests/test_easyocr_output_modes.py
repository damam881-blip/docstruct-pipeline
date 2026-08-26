from __future__ import annotations

import csv
import sys
import types
from pathlib import Path

import numpy as np

from models import BBox, ExtractedCell, ExtractedRow
from pipeline.ocr_engine import EasyOCREngine
from pipeline.output_manager import OutputManager


class _FakeReader:
    created_kwargs: dict = {}
    read_kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).created_kwargs = kwargs

    def readtext(
        self,
        image,
        decoder="greedy",
        beamWidth=5,
        batch_size=1,
        workers=0,
        allowlist=None,
        blocklist=None,
        detail=1,
        paragraph=False,
        min_size=5,
        rotation_info=None,
        contrast_ths=0.1,
        adjust_contrast=0.5,
        filter_ths=0.003,
        text_threshold=0.7,
        low_text=0.4,
        link_threshold=0.4,
        canvas_size=2560,
        mag_ratio=1.0,
        slope_ths=0.1,
        ycenter_ths=0.5,
        height_ths=0.5,
        width_ths=0.5,
        add_margin=0.1,
        x_ths=1.0,
        y_ths=0.5,
        threshold=0.2,
    ):
        type(self).read_kwargs = locals().copy()
        return [([[1, 2], [20, 2], [20, 12], [1, 12]], "١٢٣.٤٥", 0.92)]


def test_easyocr_adapter_and_numeric_allowlist(monkeypatch):
    fake_module = types.SimpleNamespace(Reader=_FakeReader)
    monkeypatch.setitem(sys.modules, "easyocr", fake_module)
    EasyOCREngine._reader_cache.clear()
    config = {
        "ocr": {
            "languages": ["ar", "en"],
            "use_gpu": False,
            "numeric_columns": {"allowlist": "0123456789٠١٢٣٤٥٦٧٨٩."},
            "easyocr": {
                "download_enabled": False,
                "model_storage_directory": "models/model",
                "user_network_directory": "models/user_network",
                "recog_network": "standard",
                "modes": {"single_line": {"width_ths": 10.0}},
            },
        }
    }
    engine = EasyOCREngine(config)
    result = engine.recognize(np.zeros((30, 60), dtype=np.uint8), mode="single_line", numeric=True)
    assert result.engine == "easyocr"
    assert result.text == "١٢٣.٤٥"
    assert result.words[0].bbox.to_list() == [1.0, 2.0, 20.0, 12.0]
    assert _FakeReader.created_kwargs["lang_list"] == ["ar", "en"]
    assert _FakeReader.read_kwargs["allowlist"] == "0123456789٠١٢٣٤٥٦٧٨٩."
    assert _FakeReader.read_kwargs["width_ths"] == 10.0


def _sample_row() -> ExtractedRow:
    cell = ExtractedCell(
        file_name="sample.pdf",
        page_number=1,
        table_id="table_01",
        row_index=0,
        column_index=0,
        bbox=BBox(10, 10, 70, 40),
        crop_path=None,
        engine="easyocr",
        confidence=0.88,
        raw_value="نص 123",
        normalized_value="نص 123",
        validation_status="valid",
    )
    return ExtractedRow(
        file_name="sample.pdf",
        page_number=1,
        table_id="table_01",
        row_index=0,
        cells=[cell],
        bbox=BBox(5, 5, 95, 45),
        row_confidence=0.88,
        normalized={"column_1": "نص 123"},
        validation_status="valid",
    )


def test_cropped_cells_only_writes_no_excel_plan_and_manifests(tmp_path):
    config = {
        "cropping": {
            "add_padding": False,
            "clamp_to_page": True,
        },
        "output": {
            "mode": "cropped_cells_only",
            "crops": {
                "image_format": "png",
                "manifest_csv": True,
                "manifest_json": True,
                "include_empty_cells": True,
            },
        },
    }
    manager = OutputManager(config, tmp_path / "result.xlsx")
    assert manager.plan.excel_enabled is False
    assert manager.plan.save_cells is True
    assert manager.plan.save_rows is False

    row = _sample_row()
    image = np.full((60, 110, 3), 255, dtype=np.uint8)
    manager.save_page_crops(image, [row], 1)
    summary = manager.finalize([types.SimpleNamespace(success=True)])

    assert row.cells[0].crop_path is not None
    assert Path(row.cells[0].crop_path).exists()
    assert summary["cell_crops"] == 1
    assert summary["row_crops"] == 0
    assert (manager.plan.artifact_root / "crop_manifest.csv").exists()
    assert (manager.plan.artifact_root / "crop_manifest.json").exists()


def test_training_dataset_creates_editable_labels(tmp_path):
    config = {
        "cropping": {"add_padding": False, "clamp_to_page": True},
        "output": {
            "mode": "training_dataset",
            "crops": {"image_format": "png"},
        },
    }
    manager = OutputManager(config, tmp_path / "training.xlsx")
    row = _sample_row()
    manager.save_page_crops(np.full((60, 110, 3), 255, dtype=np.uint8), [row], 1)
    manager.finalize([types.SimpleNamespace(success=True)])

    labels = manager.plan.artifact_root / "training_labels.csv"
    assert labels.exists()
    with labels.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    assert records[0]["ocr_draft_label"] == "نص 123"
    assert records[0]["corrected_label"] == ""


def test_training_dataset_label_source_normalized(tmp_path):
    config = {
        "cropping": {"add_padding": False, "clamp_to_page": True},
        "output": {
            "mode": "training_dataset",
            "crops": {"image_format": "png"},
            "training_dataset": {"label_source": "normalized"},
        },
    }
    manager = OutputManager(config, tmp_path / "normalized_training.xlsx")
    row = _sample_row()
    row.cells[0].normalized_value = 123.45
    manager.save_page_crops(np.full((60, 110, 3), 255, dtype=np.uint8), [row], 1)
    summary = manager.finalize([types.SimpleNamespace(success=True)])

    with (manager.plan.artifact_root / "training_labels.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        records = list(csv.DictReader(handle))
    assert records[0]["ocr_draft_label"] == "123.45"
    assert summary["training_label_source"] == "normalized"


def test_training_dataset_label_source_blank_preserves_empty_ocr_crops(tmp_path):
    config = {
        "cropping": {"add_padding": False, "clamp_to_page": True},
        "output": {
            "mode": "training_dataset",
            "crops": {"image_format": "png", "include_empty_cells": True},
            "training_dataset": {"label_source": "blank"},
        },
    }
    manager = OutputManager(config, tmp_path / "manual_training.xlsx")
    row = _sample_row()
    row.cells[0].raw_value = ""
    row.cells[0].normalized_value = None
    row.cells[0].confidence = 0.0
    manager.save_page_crops(np.full((60, 110, 3), 255, dtype=np.uint8), [row], 1)
    manager.finalize([types.SimpleNamespace(success=True)])

    with (manager.plan.artifact_root / "training_labels.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        records = list(csv.DictReader(handle))
    assert len(records) == 1
    assert records[0]["ocr_draft_label"] == ""
    assert records[0]["needs_manual_review"] == "True"


def test_training_dataset_rejects_unknown_label_source(tmp_path):
    config = {
        "output": {
            "mode": "training_dataset",
            "training_dataset": {"label_source": "unknown"},
        }
    }
    import pytest

    with pytest.raises(ValueError, match="label_source"):
        OutputManager(config, tmp_path / "invalid.xlsx")
