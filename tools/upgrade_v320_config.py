from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from upgrade_v310_config import upgrade_text as upgrade_v310_text


TEXT_DETECTION_FALLBACK_BLOCK = '''  # Last-resort spatial fallback for crop-only modes. EasyOCR/CRAFT is loaded
  # with recognizer=false, so it returns only text bounding boxes. No character
  # recognition model is loaded and no text is decoded.
  text_detection_fallback:
    enabled: true
    engine: easyocr
    minimum_boxes: 4
    structural_confidence: 0.60
'''

EASYOCR_DETECTION_BLOCK = '''  # Detection-only CRAFT settings used by visual_structure.text_detection_fallback.
  # This Reader is initialized with detector=true and recognizer=false.
  easyocr_detection:
    verbose: false
    min_size: 5
    text_threshold: 0.55
    low_text: 0.30
    link_threshold: 0.30
    canvas_size: 2560
    mag_ratio: 1.0
    slope_ths: 0.10
    ycenter_ths: 0.50
    height_ths: 0.50
    width_ths: 0.50
    add_margin: 0.10
    binary_threshold: 0.20
    bbox_min_score: 0.20
    bbox_min_size: 3
    max_candidates: 0
    structural_box_confidence: 0.60
'''


def _update_project_version(text: str) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    in_project = False
    for index, line in enumerate(lines):
        raw = line.rstrip("\r\n")
        if raw == "project:":
            in_project = True
            continue
        if in_project and raw and not raw.startswith((" ", "\t", "#")):
            break
        if in_project and raw.startswith("  version:"):
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            desired = "  version: 3.2.0-text-detection" + newline
            if line != desired:
                lines[index] = desired
                return "".join(lines), True
            return text, False
    return text, False


def _insert_after_visual_header(text: str) -> tuple[str, bool]:
    if "text_detection_fallback:" in text:
        return text, False
    lines = text.splitlines(keepends=True)
    in_visual = False
    for index, line in enumerate(lines):
        raw = line.rstrip("\r\n")
        if raw == "visual_structure:":
            in_visual = True
            continue
        if in_visual and raw.startswith("  shaded_preference_min_confidence:"):
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            block = ("\n" + TEXT_DETECTION_FALLBACK_BLOCK).replace("\n", newline)
            lines[index + 1:index + 1] = [block]
            return "".join(lines), True
        if in_visual and raw and not raw.startswith((" ", "\t", "#")):
            break
    raise RuntimeError("Could not locate visual_structure.shaded_preference_min_confidence")


def _insert_easyocr_detection(text: str) -> tuple[str, bool]:
    if "\n  easyocr_detection:\n" in text.replace("\r\n", "\n"):
        return text, False
    normalized = text.replace("\r\n", "\n")
    marker = "\n  paddleocr:\n"
    if marker not in normalized:
        raise RuntimeError("Could not locate ocr.paddleocr section")
    normalized = normalized.replace(marker, "\n" + EASYOCR_DETECTION_BLOCK + "\n  paddleocr:\n", 1)
    if "\r\n" in text:
        normalized = normalized.replace("\n", "\r\n")
    return normalized, True


def upgrade_text(text: str) -> tuple[str, list[str]]:
    # v3.2 is cumulative: a user can apply it directly to a v3.0.x YAML.
    # Avoid calling the v3.1 upgrader on an already-newer file because that
    # helper intentionally rewrites project.version to its own release value.
    needs_v310 = (
        "visual_structure:" not in text
        or "x_tolerance_word_height_ratio:" not in text
    )
    if needs_v310:
        text, changes = upgrade_v310_text(text)
    else:
        changes = []

    text, changed = _update_project_version(text)
    if changed:
        changes.append("updated project.version metadata to 3.2.0-text-detection")

    text, changed = _insert_after_visual_header(text)
    if changed:
        changes.append("added detection-only text-box fallback controls")

    text, changed = _insert_easyocr_detection(text)
    if changed:
        changes.append("added EasyOCR/CRAFT detection-only settings")

    return text, changes


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Upgrade an existing default.yaml to v3.2.0 structure detection "
            "without changing output.mode or existing tuning values."
        )
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--no-backup", action="store_true")
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
        backup = path.with_suffix(path.suffix + ".pre_v3_2_0.bak")
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")

    path.write_text(updated, encoding="utf-8")
    print(f"Updated: {path}")
    for change in changes:
        print(f"- {change}")
    print("Preserved: output.mode and all existing operational values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
