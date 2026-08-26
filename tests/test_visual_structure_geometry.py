from __future__ import annotations

from pathlib import Path

import cv2
import fitz
import numpy as np
import yaml

from config import ConfigResolver
from pipeline.pipeline import UniversalPDFPipeline
from pipeline.visual_structure_detector import VisualStructureDetector


def _write_crop_config(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    config["output"]["mode"] = "cropped_rows_and_cells"
    config["debug"]["enabled"] = False
    destination = tmp_path / "crop_config.yaml"
    destination.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return destination


def test_visual_structure_detects_shaded_grid_without_ocr():
    image = np.full((600, 900, 3), 255, dtype=np.uint8)
    xs = [80, 200, 500, 650, 800]
    ys = [100, 160, 220, 280, 340]
    for row in range(4):
        for column in range(4):
            cv2.rectangle(
                image,
                (xs[column], ys[row]),
                (xs[column + 1] - 5, ys[row + 1] - 5),
                (225, 225, 225),
                -1,
            )
            cv2.putText(
                image,
                f"{row}{column}",
                (xs[column] + 10, ys[row] + 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 0),
                2,
            )

    result = VisualStructureDetector({}).detect(
        image,
        binary=None,
        file_name="shaded.pdf",
        page_number=1,
    )

    assert result.method == "opencv_shaded_grid"
    assert len(result.rows) == 4
    assert {len(row.cells) for row in result.rows} == {4}
    assert all(cell.engine == "opencv_geometry" for row in result.rows for cell in row.cells)


def test_visual_structure_detects_borderless_projection_without_ocr():
    image = np.full((600, 900, 3), 255, dtype=np.uint8)
    for row, y in enumerate([100, 170, 240, 310, 380]):
        cv2.putText(
            image,
            f"2026-08-{row + 1:02d}",
            (60, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            f"Description {row + 1}",
            (300, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            f"{100 + row}.00",
            (700, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )

    result = VisualStructureDetector({}).detect(
        image,
        binary=None,
        file_name="borderless.pdf",
        page_number=1,
    )

    assert result.method == "opencv_projection_grid"
    assert len(result.rows) == 5
    assert {len(row.cells) for row in result.rows} == {3}
    assert all(cell.raw_value == "" for row in result.rows for cell in row.cells)


def test_crop_only_pipeline_scanned_shaded_table_produces_crops_without_ocr(tmp_path):
    image = np.full((900, 1200, 3), 255, dtype=np.uint8)
    xs = [100, 280, 650, 850, 1080]
    ys = [150, 240, 330, 420, 510]
    for row in range(4):
        for column in range(4):
            cv2.rectangle(
                image,
                (xs[column], ys[row]),
                (xs[column + 1] - 8, ys[row + 1] - 8),
                (225, 225, 225),
                -1,
            )
            cv2.putText(
                image,
                f"R{row}C{column}",
                (xs[column] + 12, ys[row] + 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 0),
                2,
            )

    ok, png = cv2.imencode(".png", image)
    assert ok
    pdf_path = tmp_path / "scanned_shaded.pdf"
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=png.tobytes())
    document.save(pdf_path)
    document.close()

    config_path = _write_crop_config(tmp_path)
    output = tmp_path / "result.xlsx"
    pipeline = UniversalPDFPipeline(ConfigResolver(config_path), debug=False)
    results = pipeline.extract(pdf_path, output, pages=[1], debug_root=tmp_path / "debug")

    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert len(result.rows) >= 4
    assert sum(len(row.cells) for row in result.rows) >= 16
    assert "ocr_initialization_skipped" in result.fallback_chain
    assert "geometry_only_no_page_ocr" in result.fallback_chain
    assert not any(issue.code == "NO_STRUCTURE_DETECTED" for issue in result.issues)
    assert pipeline.last_output_summary["row_crops"] >= 4
    assert pipeline.last_output_summary["cell_crops"] >= 16
    assert pipeline.last_output_summary["excel_enabled"] is False


def test_crop_only_pipeline_digital_pdf_uses_native_geometry_without_ocr(tmp_path):
    pdf_path = tmp_path / "digital_borderless.pdf"
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    y_positions = [120, 160, 200, 240, 280]
    for row, y in enumerate(y_positions):
        page.insert_text((50, y), f"2026-08-{row + 1:02d}", fontsize=11)
        page.insert_text((210, y), f"Description {row + 1}", fontsize=11)
        page.insert_text((470, y), f"{100 + row}.00", fontsize=11)
    document.save(pdf_path)
    document.close()

    config_path = _write_crop_config(tmp_path)
    output = tmp_path / "digital_result.xlsx"
    pipeline = UniversalPDFPipeline(ConfigResolver(config_path), debug=False)
    results = pipeline.extract(pdf_path, output, pages=[1], debug_root=tmp_path / "debug")

    result = results[0]
    assert result.success is True
    assert len(result.rows) >= 5
    assert max((len(row.cells) for row in result.rows), default=0) >= 3
    assert "ocr_initialization_skipped" in result.fallback_chain
    assert "native_digital_word_geometry" in result.fallback_chain
    assert "native_digital_words_scaled_to_image" in result.fallback_chain
    assert pipeline.last_output_summary["cell_crops"] > 0


def test_crop_only_blank_page_reports_no_structure_warning(tmp_path):
    image = np.full((600, 800, 3), 255, dtype=np.uint8)
    ok, png = cv2.imencode(".png", image)
    assert ok
    pdf_path = tmp_path / "blank_scan.pdf"
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=png.tobytes())
    document.save(pdf_path)
    document.close()

    config_path = _write_crop_config(tmp_path)
    pipeline = UniversalPDFPipeline(ConfigResolver(config_path), debug=False)
    results = pipeline.extract(
        pdf_path,
        tmp_path / "blank_result.xlsx",
        pages=[1],
        debug_root=tmp_path / "debug",
    )

    result = results[0]
    assert result.success is True
    assert result.rows == []
    assert any(issue.code == "NO_STRUCTURE_DETECTED" for issue in result.issues)
    assert pipeline.last_output_summary["pages_without_rows"] == 1
    assert pipeline.last_output_summary["pages_completed_with_warnings"] == 1
