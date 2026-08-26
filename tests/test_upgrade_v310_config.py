from __future__ import annotations

from tools.upgrade_v310_config import upgrade_text


def test_upgrade_adds_visual_structure_without_changing_output_mode():
    original = """
project:
  version: 3.0.1-easyocr-json-output

borderless_table:
  enabled: true
  column_detection:
    x_tolerance_px: 27
    minimum_column_gap_px: 20

cropping:
  add_padding: true

output:
  mode: cropped_rows_and_cells
""".lstrip()

    updated, changes = upgrade_text(original)

    assert "visual_structure:" in updated
    assert "x_tolerance_word_height_ratio: 1.0" in updated
    assert "maximum_x_tolerance_page_ratio: 0.05" in updated
    assert "mode: cropped_rows_and_cells" in updated
    assert "x_tolerance_px: 27" in updated
    assert "version: 3.1.0-visual-structure" in updated
    assert len(changes) == 3


def test_upgrade_is_idempotent():
    original = """
project:
  version: 3.1.0-visual-structure

borderless_table:
  enabled: true
  column_detection:
    x_tolerance_px: 15
    x_tolerance_word_height_ratio: 1.0
    maximum_x_tolerance_page_ratio: 0.05

visual_structure:
  enabled: true

cropping:
  add_padding: true
""".lstrip()

    updated, changes = upgrade_text(original)
    assert updated == original
    assert changes == []
