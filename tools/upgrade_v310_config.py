from __future__ import annotations

import argparse
import shutil
from pathlib import Path


VISUAL_STRUCTURE_BLOCK = r'''
# Generic no-OCR structure detection used by crop-only modes and as a
# fallback when classic ruled-line geometry is incomplete. It relies only on
# page pixels/coordinates; it never matches filenames, companies, or templates.
visual_structure:
  enabled: true
  # Large pages are analyzed at a smaller internal scale for speed, then all
  # detected coordinates are mapped back to the original rendered page.
  maximum_analysis_dimension: 1800
  shaded_preference_min_confidence: 0.45

  # Detect repeated filled/shaded cell rectangles. Useful for statements and
  # forms that have gray cell fills or white separators rather than dark rules.
  shaded_grid:
    enabled: true
    background_percentile: 95.0
    contrast_deltas: [6, 8, 10, 12]
    blur_kernel_ratio: 0.006
    opening_kernel_ratio: 0.0025
    minimum_component_width_px: 40
    minimum_component_width_ratio: 0.02
    minimum_component_height_px: 25
    minimum_component_height_ratio: 0.01
    minimum_component_fill_ratio: 0.80
    maximum_component_width_ratio: 0.75
    maximum_component_height_ratio: 0.60
    edge_exclusion_px: 2
    row_start_tolerance_px: 10
    row_start_tolerance_ratio: 0.012
    minimum_columns: 2
    minimum_rows: 2
    maximum_columns: 16
    x_alignment_tolerance_px: 12
    x_alignment_tolerance_ratio: 0.012
    minimum_row_match_ratio: 0.35
    minimum_row_matches: 2
    table_split_gap_factor: 2.75
    table_split_gap_page_ratio: 0.18
    table_split_gap_height_factor: 4.0
    confidence_rows_target: 4
    outer_padding_px: 0
    minimum_column_width_px: 12

  # Borderless scanned fallback. Text is treated only as ink geometry; no OCR
  # recognition or language model is invoked.
  projection_grid:
    enabled: true
    remove_horizontal_line_ratio: 0.08
    remove_vertical_line_ratio: 0.08
    close_width_px: 4
    close_height_px: 1
    minimum_text_component_area_px: 8
    minimum_text_component_height_px: 3
    maximum_text_component_height_ratio: 0.08
    maximum_text_component_width_ratio: 0.55
    baseline_tolerance_px: 4
    baseline_tolerance_height_ratio: 0.8
    baseline_tolerance_page_ratio: 0.001
    intra_block_merge_gap_px: 10
    intra_block_merge_height_ratio: 1.5
    minimum_columns: 2
    minimum_rows: 2
    maximum_columns: 16
    x_alignment_tolerance_px: 12
    x_alignment_tolerance_ratio: 0.012
    minimum_row_match_ratio: 0.35
    minimum_row_matches: 2
    table_split_gap_factor: 2.75
    table_split_gap_page_ratio: 0.18
    table_split_gap_height_factor: 4.0
    confidence_rows_target: 4
    outer_padding_px: 0
    minimum_column_width_px: 12
'''.strip("\n")


def upgrade_text(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    # Project version is metadata, not a per-PDF tuning value. Keep the YAML
    # aligned with the installed code release while preserving output.mode and
    # every operational value the user has chosen.
    lines = text.splitlines(keepends=True)
    in_project = False
    version_updated = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if line.startswith("project:"):
            in_project = True
            continue
        if in_project and line and not line.startswith((" ", "\t", "#", "\n", "\r")):
            in_project = False
        if in_project and line.startswith("  version:"):
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            if stripped != "version: 3.1.0-visual-structure":
                lines[index] = "  version: 3.1.0-visual-structure" + newline
                version_updated = True
            break
    if version_updated:
        text = "".join(lines)
        changes.append("updated project.version metadata to 3.1.0-visual-structure")

    if "x_tolerance_word_height_ratio:" not in text:
        lines = text.splitlines(keepends=True)
        in_borderless = False
        in_column_detection = False
        inserted = False
        for index, line in enumerate(lines):
            raw = line.rstrip("\r\n")
            if raw == "borderless_table:":
                in_borderless = True
                in_column_detection = False
                continue
            if in_borderless and raw and not raw.startswith((" ", "\t", "#")):
                break
            if in_borderless and raw == "  column_detection:":
                in_column_detection = True
                continue
            if in_column_detection and raw.startswith("  ") and not raw.startswith("    ") and raw != "  column_detection:":
                in_column_detection = False
            if in_column_detection and raw.lstrip().startswith("x_tolerance_px:"):
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                insertion = [
                    "    # Scale the clustering tolerance with measured word height on high-DPI" + newline,
                    "    # digital/hybrid page renders, while limiting it by page width." + newline,
                    "    x_tolerance_word_height_ratio: 1.0" + newline,
                    "    maximum_x_tolerance_page_ratio: 0.05" + newline,
                ]
                lines[index + 1:index + 1] = insertion
                inserted = True
                break
        if not inserted:
            raise RuntimeError(
                "Could not locate borderless_table.column_detection.x_tolerance_px. "
                "Update this YAML manually or start from the v3.1.0 default.yaml."
            )
        text = "".join(lines)
        changes.append("added DPI-aware borderless X-tolerance controls")

    if "\nvisual_structure:\n" not in "\n" + text.replace("\r\n", "\n"):
        normalized = text.replace("\r\n", "\n")
        marker = "\ncropping:\n"
        if marker not in normalized:
            raise RuntimeError(
                "Could not locate the top-level cropping section. "
                "Update this YAML manually or start from the v3.1.0 default.yaml."
            )
        normalized = normalized.replace(
            marker,
            "\n" + VISUAL_STRUCTURE_BLOCK + "\n\ncropping:\n",
            1,
        )
        # Keep Windows CRLF if the original file used it predominantly.
        if "\r\n" in text:
            text = normalized.replace("\n", "\r\n")
        else:
            text = normalized
        changes.append("added generic visual_structure configuration")

    return text, changes


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Add v3.1.0 generic visual-structure defaults to an existing "
            "configs/default.yaml without changing output.mode or other user values."
        )
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create <config>.pre_v3_1_0.bak before editing.",
    )
    args = parser.parse_args()

    path = Path(args.config)
    if not path.exists():
        raise FileNotFoundError(path)

    original = path.read_text(encoding="utf-8")
    updated, changes = upgrade_text(original)

    if not changes:
        print(f"Already up to date: {path}")
        return 0

    if not args.no_backup:
        backup = path.with_suffix(path.suffix + ".pre_v3_1_0.bak")
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")

    path.write_text(updated, encoding="utf-8")
    print(f"Updated: {path}")
    for change in changes:
        print(f"- {change}")
    print("Preserved: output.mode and all existing YAML values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
