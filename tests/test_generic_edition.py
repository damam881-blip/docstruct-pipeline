from __future__ import annotations

from pathlib import Path

from config import ConfigResolver
from pipeline.parameter_advisor import ParameterAdvisor


def test_no_pdf_specific_profiles_exist():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "profiles").exists()
    assert not list((root / "configs").glob("file_*_profile.yaml"))
    source = (root / "main.py").read_text(encoding="utf-8")
    assert "--profile" not in source
    assert "recommend-profile" not in source


def test_default_config_resolves_without_file_identity():
    root = Path(__file__).resolve().parents[1]
    resolved = ConfigResolver(root / "configs/default.yaml").resolve(1)
    assert resolved.get("project.name") == "universal_pdf_extraction_pipeline"
    assert resolved.config_path.endswith("default.yaml")


def test_parameter_advisor_is_measurement_driven():
    advice = ParameterAdvisor({"digital_text": {"quality_min": 0.72}}).advise(
        {
            "page_type": "scanned",
            "layout_type": "borderless_table",
            "estimated_dpi": 200,
            "digital_text_quality": 0.0,
            "horizontal_line_density": 0.0,
            "vertical_line_density": 0.0,
            "alignment_score": 0.4,
            "measurements": {
                "average_character_height": 7,
                "average_row_height": 24,
                "table_region_count": 0,
            },
        }
    )
    assert advice.suggested_overrides["render.default_dpi"] == 500
    assert advice.suggested_overrides["borderless_table.row_detection.baseline_tolerance_px"] == 8


def test_default_output_mode_is_supported_and_user_configurable():
    root = Path(__file__).resolve().parents[1]
    resolved = ConfigResolver(root / "configs/default.yaml").resolve()
    assert resolved.get("output.mode") in {
        "full",
        "data_only",
        "cropped_cells_only",
        "cropped_rows_only",
        "cropped_rows_and_cells",
        "training_dataset",
        "custom",
    }


def test_garbled_digital_text_fallback_can_be_controlled():
    from models import LayoutType, PageType, Strategy
    from pipeline.page_classifier import PageClassifier

    classifier = PageClassifier()
    base = {
        "digital_text": {
            "quality_min": 0.72,
            "fallback_to_ocr_when_garbled": True,
        }
    }
    assert (
        classifier.choose_strategy(
            PageType.DIGITAL,
            LayoutType.BORDERLESS_TABLE,
            0.20,
            base,
        )
        == Strategy.ROW_OCR
    )

    base["digital_text"]["fallback_to_ocr_when_garbled"] = False
    assert (
        classifier.choose_strategy(
            PageType.DIGITAL,
            LayoutType.BORDERLESS_TABLE,
            0.20,
            base,
        )
        == Strategy.DIGITAL_TEXT
    )


def test_parameter_advisor_only_suggests_digital_fallback_when_disabled():
    analysis = {
        "page_type": "digital",
        "layout_type": "borderless_table",
        "estimated_dpi": None,
        "digital_text_quality": 0.20,
        "horizontal_line_density": 0.0,
        "vertical_line_density": 0.0,
        "alignment_score": 0.4,
        "measurements": {},
    }
    enabled = ParameterAdvisor(
        {"digital_text": {"quality_min": 0.72, "fallback_to_ocr_when_garbled": True}}
    ).advise(analysis)
    assert "digital_text.fallback_to_ocr_when_garbled" not in enabled.suggested_overrides

    disabled = ParameterAdvisor(
        {"digital_text": {"quality_min": 0.72, "fallback_to_ocr_when_garbled": False}}
    ).advise(analysis)
    assert disabled.suggested_overrides["digital_text.fallback_to_ocr_when_garbled"] is True
