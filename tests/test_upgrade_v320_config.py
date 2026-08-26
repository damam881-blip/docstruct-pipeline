from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import yaml


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("upgrade_v320_config", TOOLS / "upgrade_v320_config.py")
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_upgrade_v320_is_cumulative_and_preserves_output_mode():
    source = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    current = yaml.safe_load(source.read_text(encoding="utf-8"))
    current["project"]["version"] = "3.0.1"
    current["output"]["mode"] = "cropped_rows_and_cells"
    current.pop("visual_structure", None)
    current["ocr"].pop("easyocr_detection", None)
    text = yaml.safe_dump(current, allow_unicode=True, sort_keys=False)

    upgraded, changes = module.upgrade_text(text)
    parsed = yaml.safe_load(upgraded)

    assert changes
    assert parsed["output"]["mode"] == "cropped_rows_and_cells"
    assert parsed["project"]["version"] == "3.2.0-text-detection"
    assert parsed["visual_structure"]["text_detection_fallback"]["enabled"] is True
    assert parsed["ocr"]["easyocr_detection"]["verbose"] is False


def test_upgrade_v320_is_idempotent():
    source = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    text = source.read_text(encoding="utf-8")
    upgraded, changes = module.upgrade_text(text)
    assert upgraded == text
    assert changes == []
