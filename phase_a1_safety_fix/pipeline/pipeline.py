from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pymupdf as fitz

from config import ConfigResolver, ResolvedConfig
from models import (
    BBox,
    ExtractedCell,
    ExtractedRow,
    LayoutType,
    PageExtractionResult,
    Strategy,
    TransformChain,
    dataclass_to_dict,
    union_bbox,
)
from pipeline.bordered_table_detector import BorderedTableDetector
from pipeline.borderless_table_detector import BorderlessTableDetector
from pipeline.crop_generator import CropGenerator
from pipeline.data_reconstructor import DataReconstructor
from pipeline.digital_extractor import DigitalTextExtractor
from pipeline.exporter import Exporter
from pipeline.image_extractor import ImageExtractor
from pipeline.image_preprocessor import ImagePreprocessor
from pipeline.layout_analyzer import LayoutAnalyzer
from pipeline.logging_utils import configure_logging, log
from pipeline.ocr_engine import create_ocr_engine
from pipeline.output_manager import OutputManager
from pipeline.pdf_analyzer import PDFAnalyzer
from pipeline.row_detector import AnchorRowSegmenter
from pipeline.validator import Validator


class UniversalPDFPipeline:
    def __init__(
        self,
        resolver: ConfigResolver,
        debug: bool = False,
    ) -> None:
        self.resolver = resolver
        self.debug = debug

        base = resolver.resolve().values

        self.logger = configure_logging(
            base.get("logging", {}).get(
                "level",
                "INFO",
            )
        )

        self.last_output_summary: dict[str, Any] = {}

    def extract(
        self,
        input_path: str | Path,
        output_path: str | Path,
        pages: list[int] | None = None,
        debug_root: str | Path | None = None,
    ) -> list[PageExtractionResult]:
        input_path = Path(input_path)
        output_path = Path(output_path)

        base_config = self.resolver.resolve().values

        output_manager = OutputManager(
            base_config,
            output_path,
        )

        doc = fitz.open(str(input_path))

        selected_pages = (
            pages
            or list(
                range(
                    1,
                    len(doc) + 1,
                )
            )
        )

        debug_root = (
            Path(
                debug_root
                or self.resolver.resolve().get(
                    "debug.output_dir",
                    "debug_output",
                )
            )
            / input_path.stem
        )

        state_path = (
            debug_root
            / "resume_state.json"
        )

        completed = (
            self._load_completed(state_path)
            if self.resolver.resolve().get(
                "resume.enabled",
                True,
            )
            else set()
        )

        results: list[PageExtractionResult] = []

        for page_number in selected_pages:
            if (
                page_number in completed
                and self.resolver.resolve().get(
                    "resume.skip_completed_pages",
                    False,
                )
            ):
                continue

            resolved = self.resolver.resolve(
                page_number
            )

            result = self._process_page(
                doc,
                input_path,
                page_number,
                resolved,
                debug_root,
                output_manager,
            )

            results.append(result)

            if result.success:
                completed.add(page_number)

                self._save_completed(
                    state_path,
                    completed,
                )

        configuration_source = (
            self.resolver.run_config_path
            or self.resolver.config_path
        )

        if output_manager.plan.excel_enabled:
            Exporter(
                self.resolver.resolve().values
            ).export(
                output_path,
                results,
                self.resolver.resolve().values,
                input_path.name,
                configuration_source,
            )

        self.last_output_summary = (
            output_manager.finalize(results)
        )

        self.last_output_summary[
            "excel_file"
        ] = (
            str(output_path.resolve())
            if output_manager.plan.excel_enabled
            else None
        )

        return results

    def analyze(
        self,
        input_path: str | Path,
        pages: list[int] | None = None,
        render_layout: bool = True,
    ) -> list[dict[str, Any]]:
        analyzer = PDFAnalyzer(
            self.resolver.resolve().values
        )

        return [
            dataclass_to_dict(a)
            for a in analyzer.analyze_pdf(
                input_path,
                pages=pages,
                render_layout=render_layout,
            )
        ]

    def _process_page(
        self,
        doc: fitz.Document,
        input_path: Path,
        page_number: int,
        resolved: ResolvedConfig,
        debug_root: Path,
        output_manager: OutputManager,
    ) -> PageExtractionResult:
        started = time.perf_counter()

        config = resolved.values

        page_debug = (
            debug_root
            / f"page_{page_number:04d}"
        )

        if (
            self.debug
            or config.get(
                "debug",
                {},
            ).get(
                "enabled",
                False,
            )
        ):
            page_debug.mkdir(
                parents=True,
                exist_ok=True,
            )

        analyzer = PDFAnalyzer(config)

        analysis = analyzer.analyze_page(
            doc,
            page_number,
            render_layout=True,
        )

        page = doc[page_number - 1]

        rows: list[ExtractedRow] = []
        issues = []
        fallback: list[str] = []
        free_text = ""
        structure_diagnostics: dict[str, Any] = {}

        try:
            words = []
            image = None
            preprocessed = None

            # =====================================================
            # OUTPUT / PROCESSING MODE
            # =====================================================

            output_mode = str(
                config.get(
                    "output",
                    {},
                ).get(
                    "mode",
                    "full",
                )
            ).strip().lower()

            crop_only_modes = {
                "cropped_cells_only",
                "cropped_rows_only",
                "cropped_rows_and_cells",
            }

            crop_only = (
                output_mode
                in crop_only_modes
            )

            # =====================================================
            # OCR INITIALIZATION
            #
            # IMPORTANT:
            # In crop-only modes OCR is NEVER initialized.
            # Therefore EasyOCR / Torch models are not loaded.
            # =====================================================

            if crop_only:
                ocr = None

                fallback.append(
                    "ocr_initialization_skipped"
                )

            else:
                ocr = create_ocr_engine(
                    config
                )

            strategy = (
                analysis.recommended_strategy
            )

            digital = DigitalTextExtractor()

            # =====================================================
            # PAGE ACQUISITION
            # =====================================================

            if (
                strategy
                == Strategy.DIGITAL_TEXT
                and not crop_only
            ):
                # Normal digital PDF extraction.
                words = digital.extract_words(
                    page
                )

                fallback.append(
                    "digital_word_coordinates"
                )

            else:
                # Crop-only always uses image coordinates.
                extractor = ImageExtractor(
                    config
                )

                page_image = (
                    extractor.extract_or_render(
                        doc,
                        page,
                        (
                            page_debug
                            / "01_original.png"
                            if page_debug.exists()
                            else None
                        ),
                    )
                )

                image = page_image.image

                preprocessor = (
                    ImagePreprocessor(
                        config
                    )
                )

                preprocessed = (
                    preprocessor.process(
                        image,
                        (
                            page_debug
                            if page_debug.exists()
                            else None
                        ),
                    )
                )

                fallback.append(
                    f"{page_image.source}_page_image"
                )

                if crop_only:
                    # ---------------------------------------------
                    # TRUE GEOMETRY-ONLY MODE
                    #
                    # No OCR of the full page.
                    # ---------------------------------------------
                    words = []

                    fallback.append(
                        "geometry_only_no_page_ocr"
                    )

                else:
                    ocr_image = (
                        preprocessed
                        .variants
                        .get(
                            "08_deskewed_gray",
                            preprocessed.selected,
                        )
                    )

                    if ocr is None:
                        raise RuntimeError(
                            "OCR engine unexpectedly "
                            "missing in full extraction mode."
                        )

                    ocr_result = (
                        ocr.recognize(
                            ocr_image,
                            mode=config.get(
                                "ocr",
                                {},
                            ).get(
                                "page_mode",
                                "sparse",
                            ),
                        )
                    )

                    words = (
                        ocr_result.words
                    )

                    fallback.append(
                        f"{ocr_result.engine}_layout_ocr"
                    )

            # =====================================================
            # ENSURE AN IMAGE EXISTS
            # =====================================================

            if image is None:
                scale = (
                    float(
                        config.get(
                            "analysis",
                            {},
                        ).get(
                            "digital_layout_dpi",
                            144,
                        )
                    )
                    / 72.0
                )

                pix = page.get_pixmap(
                    matrix=fitz.Matrix(
                        scale,
                        scale,
                    ),
                    alpha=False,
                )

                image = np.frombuffer(
                    pix.samples,
                    dtype=np.uint8,
                ).reshape(
                    pix.height,
                    pix.width,
                    pix.n,
                )

                image = cv2.cvtColor(
                    image[:, :, :3],
                    cv2.COLOR_RGB2BGR,
                )

                # Digital PDF words use PDF coordinates.
                # Convert them to rendered image coordinates.
                sx = (
                    image.shape[1]
                    / page.rect.width
                )

                sy = (
                    image.shape[0]
                    / page.rect.height
                )

                words = [
                    type(w)(
                        w.text,
                        BBox(
                            w.bbox.x0 * sx,
                            w.bbox.y0 * sy,
                            w.bbox.x1 * sx,
                            w.bbox.y1 * sy,
                        ),
                        w.confidence,
                        w.source,
                        w.block_no,
                        w.line_no,
                        w.word_no,
                        w.language,
                    )
                    for w in words
                ]

            page_bbox = BBox(
                0.0,
                0.0,
                float(image.shape[1]),
                float(image.shape[0]),
            )

            # =====================================================
            # BINARY IMAGE FOR STRUCTURE DETECTION
            # =====================================================

            if preprocessed is not None:
                binary = (
                    preprocessed.selected
                )

            else:
                gray = cv2.cvtColor(
                    image,
                    cv2.COLOR_BGR2GRAY,
                )

                _, binary = cv2.threshold(
                    gray,
                    0,
                    255,
                    cv2.THRESH_BINARY_INV
                    | cv2.THRESH_OTSU,
                )

            # =====================================================
            # ANCHOR SEGMENTATION CONFIG
            #
            # Crop-only:
            #   - force OpenCV projection
            #   - disable cell OCR
            #
            # We use a COPY so normal extraction config
            # is not changed.
            # =====================================================

            anchor_config = config

            if crop_only:
                anchor_config = (
                    copy.deepcopy(config)
                )

                anchor_cfg = (
                    anchor_config
                    .setdefault(
                        "borderless_table",
                        {},
                    )
                    .setdefault(
                        "row_detection",
                        {},
                    )
                    .setdefault(
                        "anchor_segmentation",
                        {},
                    )
                )

                anchor_cfg[
                    "candidate_source"
                ] = "projection"

                anchor_cfg.setdefault(
                    "cell_ocr",
                    {},
                )["enabled"] = False

            anchor_result = (
                AnchorRowSegmenter(
                    anchor_config,
                    ocr,
                ).segment(
                    image,
                    words,
                    input_path.name,
                    page_number,
                    crop_dir=(
                        page_debug
                        / "crops"
                        if page_debug.exists()
                        else None
                    ),
                )
            )

            # =====================================================
            # BUILD ROWS
            # =====================================================

            if crop_only:
                # AnchorRowSegmenter normally creates rows from OCR
                # words. In crop-only there are intentionally no
                # words, so build rows/cells from geometry.
                if anchor_result.anchors_y:
                    rows = (
                        self._rows_from_anchor_geometry(
                            image=image,
                            anchors_y=(
                                anchor_result
                                .anchors_y
                            ),
                            config=config,
                            file_name=(
                                input_path.name
                            ),
                            page_number=(
                                page_number
                            ),
                        )
                    )

                    if rows:
                        fallback.append(
                            "anchor_geometry_"
                            f"{len(anchor_result.anchors_y)}"
                            "_anchors"
                        )

            elif anchor_result.rows:
                rows = (
                    anchor_result.rows
                )

                fallback.append(
                    "anchor_row_segmentation_"
                    f"{len(anchor_result.anchors_y)}"
                    "_anchors"
                )

            # =====================================================
            # BORDERED STRUCTURE DETECTION
            # =====================================================

            bordered = (
                BorderedTableDetector(
                    config
                ).detect(
                    binary
                )
            )

            if page_debug.exists():
                cv2.imwrite(
                    str(
                        page_debug
                        / "05_horizontal_lines.png"
                    ),
                    bordered.horizontal_mask,
                )

                cv2.imwrite(
                    str(
                        page_debug
                        / "06_vertical_lines.png"
                    ),
                    bordered.vertical_mask,
                )

                region_overlay = (
                    LayoutAnalyzer.draw_regions(
                        image,
                        bordered.regions,
                    )
                )

                cv2.imwrite(
                    str(
                        page_debug
                        / "07_detected_regions.png"
                    ),
                    region_overlay,
                )

            # =====================================================
            # FALLBACK STRUCTURE DETECTION
            # =====================================================

            if not rows:
                use_bordered = (
                    analysis.layout_type
                    in {
                        LayoutType.BORDERED_TABLE,
                        LayoutType.MIXED,
                    }
                    and bool(
                        bordered.regions
                    )
                )

                bordered_rows: list[
                    ExtractedRow
                ] = []

                if use_bordered:
                    bordered_rows = (
                        self._rows_from_bordered(
                            words,
                            bordered,
                            input_path.name,
                            page_number,
                            config,
                            image,
                            page_debug,
                            geometry_only=crop_only,
                        )
                    )

                # ---------------------------------------------
                # Crop-only mode:
                #
                # BorderlessTableDetector depends on words.
                # No OCR words exist here.
                # ---------------------------------------------

                if crop_only:
                    if bordered_rows:
                        rows = bordered_rows

                        fallback.append(
                            "geometry_only_"
                            "bordered_grid"
                        )

                else:
                    borderless = (
                        BorderlessTableDetector(
                            config
                        ).detect(
                            words,
                            input_path.name,
                            page_number,
                            page_bbox,
                        )
                    )

                    structure_diagnostics["borderless"] = dict(
                        borderless.measurements
                    )

                    borderless_rows = [
                        row
                        for table_rows
                        in (
                            borderless
                            .rows_by_table
                            .values()
                        )
                        for row in table_rows
                    ]

                    minimum_bordered_rows = int(
                        config.get(
                            "fallback",
                            {},
                        ).get(
                            "minimum_rows_for_bordered",
                            4,
                        )
                    )

                    bordered_score = (
                        self._structural_row_score(
                            bordered_rows
                        )
                    )

                    borderless_score = (
                        self._structural_row_score(
                            borderless_rows
                        )
                    )

                    prefer_bordered = bool(
                        config.get(
                            "fallback",
                            {},
                        ).get(
                            "prefer_bordered_when_detected",
                            False,
                        )
                    )

                    if (
                        bordered_rows
                        and len(
                            bordered_rows
                        )
                        >= minimum_bordered_rows
                        and (
                            prefer_bordered
                            or bordered_score
                            >= borderless_score
                            * float(
                                config.get(
                                    "fallback",
                                    {},
                                ).get(
                                    "bordered_score_ratio",
                                    0.75,
                                )
                            )
                        )
                    ):
                        rows = bordered_rows

                        fallback.append(
                            (
                                "bordered_grid_"
                                "assignment_preferred"
                            )
                            if prefer_bordered
                            else (
                                "bordered_grid_"
                                "assignment"
                            )
                        )

                    else:
                        if bordered_rows:
                            fallback.append(
                                "bordered_rejected_"
                                f"score="
                                f"{bordered_score:.2f}_"
                                f"rows="
                                f"{len(bordered_rows)}"
                            )

                        rows = (
                            borderless_rows
                        )

                        fallback.append(
                            "borderless_spatial_"
                            "reconstruction"
                        )

            # =====================================================
            # FREE TEXT FALLBACK
            # =====================================================

            if not rows:
                if crop_only:
                    # Do not create an artificial empty OCR row.
                    fallback.append(
                        "geometry_only_"
                        "no_rows_detected"
                    )

                else:
                    free_text = " ".join(
                        w.text
                        for w in words
                    )

                    rows = (
                        self._free_text_row(
                            words,
                            input_path.name,
                            page_number,
                        )
                    )

                    fallback.append(
                        "full_page_text_review"
                    )

            # =====================================================
            # NORMALIZATION / VALIDATION
            # =====================================================

            if crop_only:
                # No extracted semantic text exists.
                issues = []

            else:
                reconstructor = (
                    DataReconstructor(
                        config
                    )
                )

                rows = (
                    reconstructor
                    .normalize_rows(
                        rows
                    )
                )

                validator = (
                    Validator(
                        config
                    )
                )

                issues = (
                    validator.validate(
                        rows
                    )
                )

            # =====================================================
            # SAVE CROPS
            # =====================================================

            crop_image = image

            if preprocessed is not None:
                crop_image = (
                    preprocessed
                    .variants
                    .get(
                        "08_deskewed_gray",
                        image,
                    )
                )

            output_manager.save_page_crops(
                crop_image,
                rows,
                page_number,
            )

            processing_seconds = (
                time.perf_counter()
                - started
            )

            # =====================================================
            # DEBUG OUTPUTS
            # =====================================================

            if page_debug.exists():
                self._save_structure_overlays(
                    image,
                    rows,
                    issues,
                    page_debug,
                )

                # No meaningless OCR overlay in crop-only.
                if not crop_only:
                    self._save_ocr_overlay(
                        image,
                        words,
                        page_debug
                        / "11_ocr_overlay.png",
                    )

                page_report = {
                    "analysis": (
                        dataclass_to_dict(
                            analysis
                        )
                    ),
                    "processing_mode": (
                        "geometry_only"
                        if crop_only
                        else "full_extraction"
                    ),
                    "ocr_enabled": (
                        not crop_only
                    ),
                    "output_mode": (
                        output_mode
                    ),
                    "structure_diagnostics": structure_diagnostics,
                    "anchor_segmentation": {
                        "reason": (
                            anchor_result.reason
                        ),
                        "anchor_count": (
                            len(
                                anchor_result
                                .anchors_y
                            )
                        ),
                        "anchor_y": (
                            anchor_result
                            .anchors_y
                        ),
                        "roi_bbox": (
                            anchor_result
                            .roi_bbox
                            .to_list()
                        ),
                        "confidence": (
                            anchor_result
                            .confidence
                        ),
                    },
                    "rows": [
                        dataclass_to_dict(r)
                        for r in rows
                    ],
                    "issues": [
                        dataclass_to_dict(i)
                        for i in issues
                    ],
                    "fallback_chain": (
                        fallback
                    ),
                    "processing_seconds": (
                        processing_seconds
                    ),
                    "configuration_source": {
                        "base_yaml": (
                            resolved.config_path
                        ),
                        "run_config_json": (
                            resolved.run_config_path
                        ),
                        "page_number": (
                            resolved.page_number
                        ),
                        "page_overrides": (
                            resolved.page_overrides
                        ),
                        "cli_overrides": (
                            resolved.cli_overrides
                        ),
                    },
                    "resolved_config": (
                        resolved.values
                    ),
                }

                (
                    page_debug
                    / "page_report.json"
                ).write_text(
                    json.dumps(
                        page_report,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                    encoding="utf-8",
                )

            result = PageExtractionResult(
                analysis,
                rows,
                free_text,
                issues,
                (
                    str(page_debug)
                    if page_debug.exists()
                    else None
                ),
                processing_seconds,
                fallback,
                True,
                None,
            )

            log(
                self.logger,
                "page_processed",
                stage="extract",
                file_name=(
                    input_path.name
                ),
                page_number=(
                    page_number
                ),
                page_type=(
                    analysis.page_type.value
                ),
                layout_type=(
                    analysis.layout_type.value
                ),
                strategy=(
                    analysis
                    .recommended_strategy
                    .value
                ),
                rows_detected=(
                    len(rows)
                ),
                columns_detected=max(
                    (
                        len(r.cells)
                        for r in rows
                    ),
                    default=0,
                ),
                ocr_confidence=(
                    (
                        sum(
                            r.row_confidence
                            for r in rows
                        )
                        / len(rows)
                    )
                    if rows
                    else 0
                ),
                duration_seconds=(
                    result
                    .processing_seconds
                ),
                fallback=" -> ".join(
                    fallback
                ),
            )

            return result

        except Exception as exc:
            result = PageExtractionResult(
                analysis,
                [],
                "",
                [],
                (
                    str(page_debug)
                    if page_debug.exists()
                    else None
                ),
                (
                    time.perf_counter()
                    - started
                ),
                fallback,
                False,
                str(exc),
            )

            log(
                self.logger,
                "page_failed",
                stage="extract",
                file_name=(
                    input_path.name
                ),
                page_number=(
                    page_number
                ),
                duration_seconds=(
                    result
                    .processing_seconds
                ),
                fallback=" -> ".join(
                    fallback
                ),
            )

            return result

    def _rows_from_anchor_geometry(
        self,
        image: np.ndarray,
        anchors_y: list[float],
        config: dict[str, Any],
        file_name: str,
        page_number: int,
        table_id: str = "table_01",
    ) -> list[ExtractedRow]:
        """
        Build rows and cells entirely from geometry.

        This method is used by crop-only modes and therefore
        does not require OCR words or an OCR engine.
        """

        if not anchors_y:
            return []

        h, w = image.shape[:2]

        anchor_cfg = (
            config.get(
                "borderless_table",
                {},
            )
            .get(
                "row_detection",
                {},
            )
            .get(
                "anchor_segmentation",
                {},
            )
        )

        roi_ratio = anchor_cfg.get(
            "roi_ratio",
            [
                0.0,
                0.25,
                0.20,
                0.90,
            ],
        )

        ry0 = int(
            float(roi_ratio[2])
            * h
        )

        ry1 = int(
            float(roi_ratio[3])
            * h
        )

        anchor_y = sorted(
            float(v)
            for v in anchors_y
        )

        gaps = [
            b - a
            for a, b
            in zip(
                anchor_y,
                anchor_y[1:],
            )
        ]

        typical_gap = (
            float(
                np.median(gaps)
            )
            if gaps
            else float(
                anchor_cfg.get(
                    "default_row_height_px",
                    80,
                )
            )
        )

        boundary_mode = str(
            anchor_cfg.get(
                "boundary_mode",
                "midpoint",
            )
        ).strip().lower()

        if boundary_mode == "midpoint":
            top = max(
                float(ry0),
                anchor_y[0]
                - typical_gap / 2.0,
            )

            bottom = min(
                float(ry1),
                anchor_y[-1]
                + typical_gap / 2.0,
            )

            boundaries = (
                [top]
                + [
                    (
                        current_anchor
                        + next_anchor
                    )
                    / 2.0
                    for (
                        current_anchor,
                        next_anchor,
                    )
                    in zip(
                        anchor_y,
                        anchor_y[1:],
                    )
                ]
                + [bottom]
            )

        elif boundary_mode == "anchor_start":
            top = float(ry0)
            bottom = float(ry1)

            boundary_offset_px = float(
                anchor_cfg.get(
                    "boundary_offset_px",
                    0.0,
                )
            )

            internal_boundaries = [
                min(
                    max(
                        float(anchor)
                        + boundary_offset_px,
                        top,
                    ),
                    bottom,
                )
                for anchor
                in anchor_y[1:]
            ]

            boundaries = (
                [top]
                + internal_boundaries
                + [bottom]
            )

        else:
            raise ValueError(
                "Unsupported anchor "
                "boundary_mode: "
                f"{boundary_mode!r}. "
                "Allowed values are "
                "'midpoint' and "
                "'anchor_start'."
            )

        column_ratios = (
            anchor_cfg.get(
                "column_boundaries_ratio"
            )
        )

        if not column_ratios:
            expected = max(
                1,
                int(
                    anchor_cfg.get(
                        "expected_columns",
                        1,
                    )
                ),
            )

            table_x0 = float(
                anchor_cfg.get(
                    "table_x0_ratio",
                    0.0,
                )
            )

            table_x1 = float(
                anchor_cfg.get(
                    "table_x1_ratio",
                    1.0,
                )
            )

            column_ratios = [
                table_x0
                + (
                    table_x1
                    - table_x0
                )
                * i
                / expected
                for i
                in range(
                    expected + 1
                )
            ]

        column_boundaries = [
            min(
                float(w),
                max(
                    0.0,
                    float(ratio)
                    * w,
                ),
            )
            for ratio
            in column_ratios
        ]

        column_boundaries = (
            sorted(
                set(
                    column_boundaries
                )
            )
        )

        if len(
            column_boundaries
        ) < 2:
            return []

        rows: list[
            ExtractedRow
        ] = []

        for (
            row_index,
            (
                band_top,
                band_bottom,
            ),
        ) in enumerate(
            zip(
                boundaries,
                boundaries[1:],
            )
        ):
            if (
                band_bottom
                <= band_top
            ):
                continue

            cells: list[
                ExtractedCell
            ] = []

            for (
                col_index,
                (
                    col_left,
                    col_right,
                ),
            ) in enumerate(
                zip(
                    column_boundaries,
                    column_boundaries[1:],
                )
            ):
                if (
                    col_right
                    <= col_left
                ):
                    continue

                cell_bbox = BBox(
                    col_left,
                    band_top,
                    col_right,
                    band_bottom,
                ).clamped(
                    w,
                    h,
                )

                cells.append(
                    ExtractedCell(
                        file_name=(
                            file_name
                        ),
                        page_number=(
                            page_number
                        ),
                        table_id=(
                            table_id
                        ),
                        row_index=(
                            row_index
                        ),
                        column_index=(
                            col_index
                        ),
                        bbox=(
                            cell_bbox
                        ),
                        crop_path=None,
                        engine="none",
                        confidence=0.0,
                        raw_value="",
                        normalized_value="",
                    )
                )

            if not cells:
                continue

            row_bbox = BBox(
                column_boundaries[0],
                band_top,
                column_boundaries[-1],
                band_bottom,
            ).clamped(
                w,
                h,
            )

            rows.append(
                ExtractedRow(
                    file_name=(
                        file_name
                    ),
                    page_number=(
                        page_number
                    ),
                    table_id=(
                        table_id
                    ),
                    row_index=(
                        row_index
                    ),
                    cells=cells,
                    bbox=row_bbox,
                    row_confidence=0.0,
                )
            )

        return rows

    def _rows_from_bordered(
        self,
        words,
        detection,
        file_name,
        page_number,
        config,
        image,
        page_debug,
        geometry_only: bool = False,
    ) -> list[ExtractedRow]:
        output: list[
            ExtractedRow
        ] = []

        cropper = CropGenerator(
            config
        )

        for region in detection.regions:
            xs = (
                region.column_boundaries
            )

            ys = (
                region.row_boundaries
            )

            if (
                len(xs) < 2
                or len(ys) < 2
            ):
                continue

            for (
                row_index,
                (
                    y0,
                    y1,
                ),
            ) in enumerate(
                zip(
                    ys,
                    ys[1:],
                )
            ):
                cells: list[
                    ExtractedCell
                ] = []

                for (
                    col_index,
                    (
                        x0,
                        x1,
                    ),
                ) in enumerate(
                    zip(
                        xs,
                        xs[1:],
                    )
                ):
                    cell_box = BBox(
                        x0,
                        y0,
                        x1,
                        y1,
                    )

                    assigned = [
                        w
                        for w in words
                        if (
                            cell_box
                            .intersection_ratio(
                                w.bbox,
                                denominator=(
                                    "other"
                                ),
                            )
                            >= 0.30
                        )
                        or (
                            cell_box.x0
                            <= w.bbox.center[0]
                            <= cell_box.x1
                            and cell_box.y0
                            <= w.bbox.center[1]
                            <= cell_box.y1
                        )
                    ]

                    assigned = sorted(
                        assigned,
                        key=lambda w: (
                            w.bbox.y0,
                            w.bbox.x0,
                        ),
                    )

                    text = " ".join(
                        w.text
                        for w in assigned
                    ).strip()

                    confidence = (
                        float(
                            np.mean(
                                [
                                    w.confidence
                                    for w
                                    in assigned
                                ]
                            )
                        )
                        if assigned
                        else 0.0
                    )

                    crop_path = None

                    if (
                        page_debug.exists()
                        and config.get(
                            "cropping",
                            {},
                        ).get(
                            "save_all_crops",
                            True,
                        )
                    ):
                        (
                            _,
                            _,
                            crop_path,
                        ) = cropper.crop(
                            image,
                            cell_box,
                            (
                                f"p{page_number:04d}_"
                                f"t{region.table_id}_"
                                f"r{row_index:03d}_"
                                f"c{col_index:02d}"
                            ),
                            page_debug
                            / "crops",
                        )

                    cells.append(
                        ExtractedCell(
                            file_name,
                            page_number,
                            region.table_id,
                            row_index,
                            col_index,
                            cell_box,
                            crop_path,
                            (
                                assigned[0].source
                                if assigned
                                else "none"
                            ),
                            confidence,
                            text,
                            text,
                        )
                    )

                if (
                    geometry_only
                    or any(
                        c.raw_value
                        for c in cells
                    )
                ):
                    row_bbox = BBox(
                        xs[0],
                        y0,
                        xs[-1],
                        y1,
                    )

                    row_crop = None

                    if page_debug.exists():
                        (
                            _,
                            _,
                            row_crop,
                        ) = cropper.crop(
                            image,
                            row_bbox,
                            (
                                f"p{page_number:04d}_"
                                f"t{region.table_id}_"
                                f"row_{row_index:03d}"
                            ),
                            page_debug
                            / "crops",
                        )

                    nonempty = [
                        c.confidence
                        for c in cells
                        if c.raw_value
                    ]

                    output.append(
                        ExtractedRow(
                            file_name,
                            page_number,
                            region.table_id,
                            row_index,
                            cells,
                            row_bbox,
                            (
                                float(
                                    np.mean(
                                        nonempty
                                    )
                                )
                                if nonempty
                                else 0.0
                            ),
                            source_crop=(
                                row_crop
                            ),
                        )
                    )

        return output

    @staticmethod
    def _structural_row_score(
        rows: list[ExtractedRow],
    ) -> float:
        if not rows:
            return 0.0

        nonempty = [
            sum(
                bool(
                    c.raw_value.strip()
                )
                for c in row.cells
            )
            for row in rows
        ]

        confidence = (
            sum(
                row.row_confidence
                for row in rows
            )
            / len(rows)
        )

        median_nonempty = (
            float(
                np.median(
                    nonempty
                )
            )
            if nonempty
            else 0.0
        )

        return (
            len(rows)
            * max(
                0.25,
                median_nonempty,
            )
            * max(
                0.10,
                confidence,
            )
        )

    @staticmethod
    def _free_text_row(
        words,
        file_name,
        page_number,
    ) -> list[ExtractedRow]:
        text = " ".join(
            w.text
            for w in words
        )

        bbox = (
            union_bbox(
                [
                    w.bbox
                    for w in words
                ]
            )
            or BBox(
                0,
                0,
                0,
                0,
            )
        )

        cell = ExtractedCell(
            file_name,
            page_number,
            "free_text",
            0,
            0,
            bbox,
            None,
            (
                words[0].source
                if words
                else "none"
            ),
            (
                float(
                    np.mean(
                        [
                            w.confidence
                            for w
                            in words
                        ]
                    )
                )
                if words
                else 0.0
            ),
            text,
            text,
        )

        return [
            ExtractedRow(
                file_name,
                page_number,
                "free_text",
                0,
                [cell],
                bbox,
                cell.confidence,
            )
        ]

    @staticmethod
    def _save_structure_overlays(
        image,
        rows,
        issues,
        page_debug,
    ):
        row_overlay = image.copy()
        cell_overlay = image.copy()
        validation_overlay = (
            image.copy()
        )

        column_positions: set[
            int
        ] = set()

        issue_keys = {
            (
                issue.page_number,
                issue.table_id,
                issue.row_index,
            )
            for issue in issues
        }

        for row in rows:
            if row.bbox:
                (
                    x0,
                    y0,
                    x1,
                    y1,
                ) = row.bbox.to_int()

                cv2.rectangle(
                    row_overlay,
                    (x0, y0),
                    (x1, y1),
                    (255, 0, 0),
                    2,
                )

                cv2.putText(
                    row_overlay,
                    f"R{row.row_index}",
                    (
                        x0,
                        max(
                            15,
                            y0 - 3,
                        ),
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 0, 0),
                    1,
                )

                color = (
                    (0, 0, 255)
                    if (
                        row.page_number,
                        row.table_id,
                        row.row_index,
                    )
                    in issue_keys
                    else (
                        0,
                        180,
                        0,
                    )
                )

                cv2.rectangle(
                    validation_overlay,
                    (x0, y0),
                    (x1, y1),
                    color,
                    2,
                )

            for cell in row.cells:
                (
                    cx0,
                    cy0,
                    cx1,
                    cy1,
                ) = (
                    cell.bbox.to_int()
                )

                cv2.rectangle(
                    cell_overlay,
                    (cx0, cy0),
                    (cx1, cy1),
                    (0, 140, 255),
                    1,
                )

                cv2.putText(
                    cell_overlay,
                    (
                        f"R{row.row_index}"
                        f"C{cell.column_index}"
                    ),
                    (
                        cx0,
                        max(
                            10,
                            cy0 + 10,
                        ),
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.3,
                    (0, 140, 255),
                    1,
                )

                column_positions.add(
                    cx0
                )

                column_positions.add(
                    cx1
                )

        column_overlay = (
            image.copy()
        )

        for (
            index,
            x,
        ) in enumerate(
            sorted(
                column_positions
            )
        ):
            cv2.line(
                column_overlay,
                (x, 0),
                (
                    x,
                    image.shape[0] - 1,
                ),
                (180, 0, 180),
                1,
            )

            cv2.putText(
                column_overlay,
                f"X{index}",
                (
                    x + 2,
                    15,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (180, 0, 180),
                1,
            )

        cv2.imwrite(
            str(
                page_debug
                / "08_detected_rows.png"
            ),
            row_overlay,
        )

        cv2.imwrite(
            str(
                page_debug
                / "09_detected_columns.png"
            ),
            column_overlay,
        )

        cv2.imwrite(
            str(
                page_debug
                / "10_detected_cells.png"
            ),
            cell_overlay,
        )

        cv2.imwrite(
            str(
                page_debug
                / "12_validation_overlay.png"
            ),
            validation_overlay,
        )

    @staticmethod
    def _save_ocr_overlay(
        image,
        words,
        path,
    ):
        overlay = image.copy()

        for word in words:
            (
                x0,
                y0,
                x1,
                y1,
            ) = word.bbox.to_int()

            color = (
                (0, 180, 0)
                if word.confidence
                >= 0.75
                else (
                    0,
                    0,
                    255,
                )
            )

            cv2.rectangle(
                overlay,
                (x0, y0),
                (x1, y1),
                color,
                1,
            )

            cv2.putText(
                overlay,
                (
                    f"{word.confidence:.2f}"
                ),
                (
                    x0,
                    max(
                        10,
                        y0 - 2,
                    ),
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.3,
                color,
                1,
            )

        cv2.imwrite(
            str(path),
            overlay,
        )

    @staticmethod
    def _load_completed(
        path: Path,
    ) -> set[int]:
        if not path.exists():
            return set()

        try:
            return set(
                json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                ).get(
                    "completed_pages",
                    [],
                )
            )

        except Exception:
            return set()

    @staticmethod
    def _save_completed(
        path: Path,
        completed: set[int],
    ) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                {
                    "completed_pages": sorted(
                        completed
                    )
                },
                indent=2,
            ),
            encoding="utf-8",
        )