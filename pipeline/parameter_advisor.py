from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ParameterAdvice:
    """Transparent tuning advice derived from page measurements."""

    observations: list[str] = field(default_factory=list)
    suggested_overrides: dict[str, Any] = field(default_factory=dict)
    inspect_debug_files: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)


class ParameterAdvisor:
    """Recommend generic parameter changes without identifying a PDF family.

    This component does not choose a saved profile and does not inspect a file
    name. It converts measurable symptoms into explicit, reviewable advice.
    The user remains in control of whether an override is applied.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def advise(self, analysis: dict[str, Any]) -> ParameterAdvice:
        advice = ParameterAdvice()
        page_type = str(analysis.get("page_type", ""))
        layout_type = str(analysis.get("layout_type", ""))
        estimated_dpi = analysis.get("estimated_dpi")
        quality = float(analysis.get("digital_text_quality", 0.0) or 0.0)
        h_density = float(analysis.get("horizontal_line_density", 0.0) or 0.0)
        v_density = float(analysis.get("vertical_line_density", 0.0) or 0.0)
        alignment = float(analysis.get("alignment_score", 0.0) or 0.0)
        measurements = analysis.get("measurements", {}) or {}
        char_height = float(measurements.get("average_character_height", 0.0) or 0.0)
        row_height = float(measurements.get("average_row_height", 0.0) or 0.0)
        region_count = int(measurements.get("table_region_count", 0) or 0)

        advice.observations.append(
            f"page_type={page_type}, layout_type={layout_type}, "
            f"digital_quality={quality:.3f}, alignment={alignment:.3f}"
        )

        if page_type in {"scanned", "hybrid"}:
            advice.inspect_debug_files.extend(
                ["01_original.png", "03_contrast.png", "06_threshold.png", "11_ocr_overlay.png"]
            )
            if estimated_dpi is not None and float(estimated_dpi) < 280:
                advice.observations.append(
                    f"Embedded scan resolution is low ({float(estimated_dpi):.0f} DPI)."
                )
                advice.suggested_overrides["render.default_dpi"] = 500
                advice.cautions.append(
                    "Rendering at a higher DPI enlarges the low-resolution scan; it cannot restore detail that is absent."
                )
            elif 0 < char_height < 9:
                advice.observations.append(
                    f"Average character height is small ({char_height:.1f} analysis pixels)."
                )
                advice.suggested_overrides["render.default_dpi"] = 500

        digital_cfg = self.config.get("digital_text", {})
        if page_type in {"digital", "hybrid"} and quality < float(
            digital_cfg.get("quality_min", 0.72)
        ):
            advice.observations.append("The selectable text layer appears garbled or incomplete.")
            if not bool(digital_cfg.get("fallback_to_ocr_when_garbled", True)):
                advice.suggested_overrides["digital_text.fallback_to_ocr_when_garbled"] = True
            else:
                advice.observations.append("OCR fallback for garbled digital text is already enabled.")

        if layout_type == "bordered_table":
            advice.inspect_debug_files.extend(
                ["05_horizontal_lines.png", "06_vertical_lines.png", "07_detected_regions.png", "10_detected_cells.png"]
            )
            if region_count == 0 or h_density < 0.001 or v_density < 0.0005:
                advice.observations.append("The page looks bordered, but the line evidence is weak.")
                advice.suggested_overrides[
                    "bordered_table.horizontal.kernel_width_ratio"
                ] = 0.02
                advice.suggested_overrides[
                    "bordered_table.vertical.kernel_height_ratio"
                ] = 0.02
                advice.suggested_overrides[
                    "bordered_table.horizontal.minimum_line_length_ratio"
                ] = 0.07
                advice.suggested_overrides[
                    "bordered_table.vertical.minimum_line_length_ratio"
                ] = 0.07

        if layout_type in {"borderless_table", "mixed"}:
            advice.inspect_debug_files.extend(
                ["08_detected_rows.png", "09_detected_columns.png", "10_detected_cells.png"]
            )
            if row_height > 0:
                # Use a conservative fraction of the measured inter-line distance.
                advice.suggested_overrides[
                    "borderless_table.row_detection.baseline_tolerance_px"
                ] = max(4, min(18, round(row_height * 0.35)))
            if alignment < 0.20:
                advice.cautions.append(
                    "Word alignment is weak. Borderless column inference may need explicit column boundaries after visual inspection."
                )

        # Remove duplicates while preserving order.
        advice.inspect_debug_files = list(dict.fromkeys(advice.inspect_debug_files))
        return advice
