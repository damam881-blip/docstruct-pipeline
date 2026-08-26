from __future__ import annotations

import sys
import types
from pathlib import Path

import cv2
import fitz
import numpy as np
import yaml

from config import ConfigResolver
from models import BBox, WordBox
from pipeline.ocr_engine import EasyOCRTextDetector, OCRResult, TextDetectionResult
from pipeline.pipeline import UniversalPDFPipeline
import pipeline.pipeline as pipeline_module


class _DetectionOnlyReader:
    created_kwargs: dict = {}
    detect_kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).created_kwargs = kwargs

    def detect(
        self,
        image,
        min_size=5,
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
        threshold=0.2,
        bbox_min_score=0.2,
        bbox_min_size=3,
        max_candidates=0,
    ):
        type(self).detect_kwargs = locals().copy()
        horizontal = [
            [10, 60, 20, 40],
            [100, 180, 20, 40],
            [220, 280, 20, 40],
        ]
        free = [
            [[20, 60], [80, 58], [82, 80], [18, 82]],
        ]
        # EasyOCR detect() returns one list per input image.
        return [horizontal], [free]


def test_easyocr_text_detector_loads_detector_without_recognizer(monkeypatch):
    monkeypatch.setitem(sys.modules, "easyocr", types.SimpleNamespace(Reader=_DetectionOnlyReader))
    EasyOCRTextDetector._reader_cache.clear()
    config = {
        "project": {"deterministic": True},
        "ocr": {
            "languages": ["ar", "en"],
            "use_gpu": False,
            "easyocr": {
                "download_enabled": False,
                "model_storage_directory": "models/easyocr/model",
                "user_network_directory": "models/easyocr/user_network",
                "detect_network": "craft",
                "quantize": True,
            },
            "easyocr_detection": {
                "verbose": False,
                "text_threshold": 0.55,
                "structural_box_confidence": 0.6,
            },
        },
    }

    detector = EasyOCRTextDetector(config)
    result = detector.detect(np.zeros((120, 320, 3), dtype=np.uint8))

    assert _DetectionOnlyReader.created_kwargs["detector"] is True
    assert _DetectionOnlyReader.created_kwargs["recognizer"] is False
    assert _DetectionOnlyReader.created_kwargs["gpu"] is False
    assert _DetectionOnlyReader.detect_kwargs["text_threshold"] == 0.55
    assert len(result.boxes) == 4
    assert all(box.text == "" for box in result.boxes)
    assert all(box.source == "easyocr_detection" for box in result.boxes)
    assert result.measurements["recognizer_loaded"] is False
    assert result.device == "cpu"


def _write_scanned_pdf(path: Path) -> None:
    image = np.full((800, 1100, 3), 255, dtype=np.uint8)
    # A few visible marks keep this a realistic scan, but the test deliberately
    # disables visual_structure so the mocked detection-only boxes are required.
    cv2.putText(image, "scan", (60, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    ok, png = cv2.imencode(".png", image)
    assert ok
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=png.tobytes())
    doc.save(path)
    doc.close()


def _config_for_mode(tmp_path: Path, mode: str) -> Path:
    source = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    config["output"]["mode"] = mode
    config["debug"]["enabled"] = False
    config["visual_structure"]["enabled"] = False
    config["bordered_table"]["enabled"] = False
    config["borderless_table"]["row_detection"]["anchor_segmentation"]["enabled"] = False
    # visual_structure.enabled controls OpenCV visual detectors, while this
    # explicit fallback flag remains enabled for the pipeline-level CRAFT path.
    config["visual_structure"]["text_detection_fallback"]["enabled"] = True
    destination = tmp_path / f"{mode}.yaml"
    destination.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return destination


class _FakeDetector:
    def detect(self, image: np.ndarray) -> TextDetectionResult:
        h, w = image.shape[:2]
        boxes: list[WordBox] = []
        for row_index in range(5):
            y0 = h * (0.18 + row_index * 0.11)
            y1 = y0 + h * 0.025
            for x_ratio in (0.12, 0.48, 0.82):
                x0 = w * x_ratio
                x1 = x0 + w * 0.08
                boxes.append(
                    WordBox("", BBox(x0, y0, x1, y1), 0.6, "easyocr_detection")
                )
        return TextDetectionResult(
            boxes=boxes,
            engine="easyocr_detection",
            device="cpu",
            measurements={"box_count": len(boxes), "recognizer_loaded": False},
        )


def test_crop_only_recovers_cells_from_detection_only_boxes(monkeypatch, tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    _write_scanned_pdf(pdf_path)
    config_path = _config_for_mode(tmp_path, "cropped_rows_and_cells")

    monkeypatch.setattr(pipeline_module, "create_text_detector", lambda config: _FakeDetector())

    pipeline = UniversalPDFPipeline(ConfigResolver(config_path), debug=False)
    results = pipeline.extract(
        pdf_path,
        tmp_path / "crop_result.xlsx",
        pages=[1],
        debug_root=tmp_path / "debug",
    )

    result = results[0]
    assert result.success is True
    assert len(result.rows) == 5
    assert {len(row.cells) for row in result.rows} == {3}
    assert all(cell.raw_value == "" for row in result.rows for cell in row.cells)
    assert all(
        cell.engine == "easyocr_detection_geometry"
        for row in result.rows
        for cell in row.cells
    )
    assert "structure_recovered_by_text_detection" in result.fallback_chain
    assert pipeline.last_output_summary["ocr_recognition_enabled"] is False
    assert pipeline.last_output_summary["text_detection_fallback_enabled"] is True
    assert pipeline.last_output_summary["cell_crops"] == 15
    import csv
    manifest = Path(pipeline.last_output_summary["crop_manifest_csv"])
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    detection_records = [record for record in records if record["level"] == "cell"]
    assert detection_records
    assert all(record["confidence_type"] == "geometry" for record in detection_records)
    assert all(record["ocr_engine"] == "none" for record in detection_records)


class _FakeFullOCR:
    def recognize(self, image: np.ndarray, mode: str = "block", numeric: bool = False) -> OCRResult:
        h, w = image.shape[:2]
        words: list[WordBox] = []
        for row_index in range(5):
            y0 = h * (0.18 + row_index * 0.11)
            y1 = y0 + h * 0.025
            for column_index, x_ratio in enumerate((0.12, 0.48, 0.82)):
                x0 = w * x_ratio
                x1 = x0 + w * 0.08
                words.append(
                    WordBox(
                        f"R{row_index}C{column_index}",
                        BBox(x0, y0, x1, y1),
                        0.9,
                        "fake_full_ocr",
                    )
                )
        return OCRResult(
            text=" ".join(word.text for word in words),
            confidence=0.9,
            words=words,
            language="ar+en",
            engine="fake_full_ocr",
        )


def test_full_mode_uses_recognized_positions_to_build_cells(monkeypatch, tmp_path):
    pdf_path = tmp_path / "scan_full.pdf"
    _write_scanned_pdf(pdf_path)
    config_path = _config_for_mode(tmp_path, "full")

    monkeypatch.setattr(pipeline_module, "create_ocr_engine", lambda config: _FakeFullOCR())

    pipeline = UniversalPDFPipeline(ConfigResolver(config_path), debug=False)
    results = pipeline.extract(
        pdf_path,
        tmp_path / "full_result.xlsx",
        pages=[1],
        debug_root=tmp_path / "debug",
    )

    result = results[0]
    assert result.success is True
    assert len(result.rows) == 5
    assert {len(row.cells) for row in result.rows} == {3}
    assert any(cell.raw_value for row in result.rows for cell in row.cells)
    assert pipeline.last_output_summary["ocr_recognition_enabled"] is True
    assert pipeline.last_output_summary["excel_enabled"] is True
