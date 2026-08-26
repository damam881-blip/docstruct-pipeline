from __future__ import annotations

from config import ConfigResolver, deep_merge, parse_cli_overrides
from models import BBox, TransformChain


def test_crop_coordinate_transform_roundtrip():
    chain = TransformChain(600, 800, 1200, 1600)
    pdf_box = BBox(100, 200, 300, 400)
    image_box = chain.pdf_to_image(pdf_box)
    roundtrip = chain.image_to_pdf(image_box)
    assert roundtrip.to_list() == pdf_box.to_list()


def test_configuration_priority_cli_over_page_over_default(tmp_path):
    default = tmp_path / "default.yaml"
    default.write_text(
        "render:\n"
        "  default_dpi: 400\n"
        "  minimum_dpi: 300\n"
        "page_overrides:\n"
        "  2:\n"
        "    render:\n"
        "      default_dpi: 500\n",
        encoding="utf-8",
    )
    resolver = ConfigResolver(
        default, parse_cli_overrides(["render.default_dpi=600"])
    )
    assert resolver.resolve(2).get("render.default_dpi") == 600
    assert resolver.resolve(2).get("render.minimum_dpi") == 300


def test_integer_yaml_page_override_applies_without_cli(tmp_path):
    default = tmp_path / "default.yaml"
    default.write_text(
        "render:\n"
        "  default_dpi: 400\n"
        "page_overrides:\n"
        "  2:\n"
        "    render:\n"
        "      default_dpi: 500\n",
        encoding="utf-8",
    )
    resolver = ConfigResolver(default)
    assert resolver.resolve(2).get("render.default_dpi") == 500
    assert resolver.resolve(1).get("render.default_dpi") == 400


def test_deep_merge_does_not_modify_inputs():
    base = {"a": {"b": 1}, "items": [1, 2]}
    override = {"a": {"c": 2}, "items": [3]}
    result = deep_merge(base, override)
    assert result == {"a": {"b": 1, "c": 2}, "items": [3]}
    assert base == {"a": {"b": 1}, "items": [1, 2]}


def test_json_run_config_overrides_yaml_and_cli_stays_highest(tmp_path):
    import json

    default = tmp_path / "default.yaml"
    default.write_text(
        "render:\n"
        "  default_dpi: 400\n"
        "borderless_table:\n"
        "  row_detection:\n"
        "    anchor_segmentation:\n"
        "      boundary_mode: midpoint\n",
        encoding="utf-8",
    )
    run_config = tmp_path / "document.run_config.json"
    run_config.write_text(
        json.dumps(
            {
                "format": "universal_pdf_pipeline_run_config",
                "version": 1,
                "config": {
                    "render": {"default_dpi": 500},
                    "borderless_table": {
                        "row_detection": {
                            "anchor_segmentation": {
                                "boundary_mode": "anchor_start"
                            }
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    resolver = ConfigResolver(
        default,
        parse_cli_overrides(["render.default_dpi=600"]),
        run_config,
    )
    assert resolver.resolve().get("render.default_dpi") == 600
    assert (
        resolver.resolve().get(
            "borderless_table.row_detection.anchor_segmentation.boundary_mode"
        )
        == "anchor_start"
    )


def test_page_report_json_can_be_reused_as_config(tmp_path):
    import json

    default = tmp_path / "default.yaml"
    default.write_text("render:\n  default_dpi: 400\n", encoding="utf-8")
    page_report = tmp_path / "page_report.json"
    page_report.write_text(
        json.dumps({"resolved_config": {"render": {"default_dpi": 550}}}),
        encoding="utf-8",
    )
    resolver = ConfigResolver(default, run_config_path=page_report)
    assert resolver.resolve().get("render.default_dpi") == 550


def test_generated_run_config_roundtrip(tmp_path):
    import json

    default = tmp_path / "default.yaml"
    default.write_text("render:\n  default_dpi: 400\n", encoding="utf-8")
    destination = tmp_path / "first.run_config.json"
    resolver = ConfigResolver(default)
    resolver.save_editable_run_config(
        destination,
        source_pdf="sample.pdf",
        output_file="sample.xlsx",
        selected_pages=[1],
        last_run={"rows_extracted": 3},
    )
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["config"]["render"]["default_dpi"] == 400
    payload["config"]["render"]["default_dpi"] = 500
    destination.write_text(json.dumps(payload), encoding="utf-8")
    reused = ConfigResolver(default, run_config_path=destination)
    assert reused.resolve().get("render.default_dpi") == 500
