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
    PageType,
    Strategy,
    ValidationIssue,
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
from pipeline.ocr_engine import create_ocr_engine, create_text_detector
from pipeline.output_manager import OutputManager
from pipeline.pdf_analyzer import PDFAnalyzer
from pipeline.row_detector import AnchorRowSegmenter
from pipeline.runtime import configure_runtime_determinism
from pipeline.validator import Validator
from pipeline.visual_structure_detector import VisualStructureDetector


class UniversalPDFPipeline:
    def __init__(
        self,
        resolver: ConfigResolver,
        debug: bool = False,
    ) -> None:
        self.resolver = resolver
        self.debug = debug

        base = resolver.resolve().values

        # Make project.deterministic / project.random_seed operational rather
        # than metadata-only. The returned status is kept for diagnostics.
        self.runtime_settings = configure_runtime_determinism(base)

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

        crop_only_modes = {
            "cropped_cells_only",
            "cropped_rows_only",
            "cropped_rows_and_cells",
        }
        run_crop_only = output_manager.plan.mode in crop_only_modes
        text_detection_fallback_enabled = bool(
            base_config.get("visual_structure", {})
            .get("text_detection_fallback", {})
            .get("enabled", True)
        )
        run_processing_mode = (
            "geometry_plus_text_detection"
            if run_crop_only and text_detection_fallback_enabled
            else ("geometry_only" if run_crop_only else "full_extraction")
        )
        log(
            self.logger,
            "run_configuration",
            stage="startup",
            file_name=input_path.name,
            output_mode=output_manager.plan.mode,
            processing_mode=run_processing_mode,
            ocr_enabled=not run_crop_only,
            ocr_recognition_enabled=not run_crop_only,
            text_detection_fallback_enabled=(
                run_crop_only and text_detection_fallback_enabled
            ),
            excel_enabled=output_manager.plan.excel_enabled,
            save_rows=output_manager.plan.save_rows,
            save_cells=output_manager.plan.save_cells,
            config_path=self.resolver.config_path,
            run_config_path=self.resolver.run_config_path,
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
        self.last_output_summary.update(
            {
                "processing_mode": (
                    "geometry_plus_text_detection"
                    if (
                        output_manager.plan.mode in crop_only_modes
                        and text_detection_fallback_enabled
                    )
                    else (
                        "geometry_only"
                        if output_manager.plan.mode in crop_only_modes
                        else "full_extraction"
                    )
                ),
                "ocr_enabled": output_manager.plan.mode not in crop_only_modes,
                "ocr_recognition_enabled": output_manager.plan.mode not in crop_only_modes,
                "text_detection_fallback_enabled": (
                    output_manager.plan.mode in crop_only_modes
                    and text_detection_fallback_enabled
                ),
                "base_yaml": str(Path(self.resolver.config_path).resolve()),
                "run_config_input": (
                    str(Path(self.resolver.run_config_path).resolve())
                    if self.resolver.run_config_path
                    else None
                ),
            }
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
        issues: list[ValidationIssue] = []
        fallback: list[str] = []
        free_text = ""
        structure_method = "none"
        structure_confidence = 0.0
        structure_candidates: list[dict[str, Any]] = []
        executed_strategy = "unresolved"
        text_detection_result = None
        text_detection_error: str | None = None

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
            # OCR RECOGNITION INITIALIZATION
            #
            # IMPORTANT:
            # In crop-only modes character recognition is never initialized.
            # A lightweight detection-only CRAFT reader may be initialized
            # later, and only if pure visual geometry cannot find structure.
            # =====================================================

            if crop_only:
                ocr = None

                # Keep the legacy marker for compatibility with existing tests
                # and add the more precise wording for new diagnostics.
                fallback.append("ocr_initialization_skipped")
                fallback.append("ocr_recognition_skipped")

            else:
                ocr = create_ocr_engine(
                    config
                )

            strategy = (
                analysis.recommended_strategy
            )

            digital = DigitalTextExtractor()
            native_pdf_words = []

            # In crop-only mode, digital/hybrid PDFs can still provide native
            # word coordinates from PyMuPDF.  This is geometry metadata, not OCR.
            if crop_only and analysis.page_type in {PageType.DIGITAL, PageType.HYBRID}:
                try:
                    native_pdf_words = digital.extract_words(page)
                except Exception:
                    native_pdf_words = []
                if native_pdf_words:
                    fallback.append("native_digital_word_geometry")

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
                executed_strategy = "digital_text"

            else:
                # Image-based processing is required for scanned pages and for
                # geometry-only crop modes.
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
                    # Recognition stays off.  Pure visual/native geometry is
                    # attempted first; detection-only CRAFT is a later fallback.
                    words = []
                    executed_strategy = "geometry_only"
                    fallback.append("geometry_only_no_page_ocr")

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
                    executed_strategy = f"{ocr_result.engine}_layout_ocr"

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

                words = self._scale_pdf_words_to_image(
                    words,
                    page,
                    image,
                )

            # Native digital coordinates are scaled only after the crop-only
            # page image exists.  They remain non-OCR geometry evidence.
            if crop_only and native_pdf_words:
                words = self._scale_pdf_words_to_image(
                    native_pdf_words,
                    page,
                    image,
                )
                fallback.append("native_digital_words_scaled_to_image")

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

                if anchor_cfg.get("enabled", False):
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
                        structure_method = "opencv_anchor_projection"
                        structure_confidence = anchor_result.confidence
                        fallback.append(
                            "anchor_geometry_"
                            f"{len(anchor_result.anchors_y)}"
                            "_anchors"
                        )

            elif anchor_result.rows:
                rows = (
                    anchor_result.rows
                )

                structure_method = "anchor_row_segmentation"
                structure_confidence = anchor_result.confidence
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
            # GENERIC STRUCTURE FALLBACKS
            #
            # Evidence is ranked rather than tied to a filename/template:
            #   1) ruled grid geometry
            #   2) native/OCR spatial word geometry
            #   3) visual no-OCR geometry (shaded cells / projection)
            # =====================================================

            structure_image = (
                preprocessed.variants.get("08_deskewed_gray", image)
                if preprocessed is not None
                else image
            )

            visual = VisualStructureDetector(config).detect(
                structure_image,
                binary,
                input_path.name,
                page_number,
            )

            if page_debug.exists():
                for mask_name, mask in visual.debug_masks.items():
                    safe_name = mask_name.replace("/", "_").replace(" ", "_")
                    cv2.imwrite(
                        str(page_debug / f"07a_visual_{safe_name}.png"),
                        mask,
                    )

            if not rows:
                bordered_rows: list[ExtractedRow] = []
                if bordered.regions:
                    bordered_rows = self._rows_from_bordered(
                        words,
                        bordered,
                        input_path.name,
                        page_number,
                        config,
                        structure_image,
                        page_debug,
                        geometry_only=crop_only,
                    )

                borderless_rows: list[ExtractedRow] = []
                if words:
                    borderless = BorderlessTableDetector(config).detect(
                        words,
                        input_path.name,
                        page_number,
                        page_bbox,
                    )
                    borderless_rows = [
                        row
                        for table_rows in borderless.rows_by_table.values()
                        for row in table_rows
                    ]

                visual_rows = visual.rows
                if visual_rows and words and not crop_only:
                    visual_rows = self._assign_words_to_geometry_rows(
                        visual_rows,
                        words,
                    )

                bordered_confidence = max(
                    (region.confidence for region in bordered.regions),
                    default=0.0,
                )
                borderless_confidence = (
                    float(np.mean([row.row_confidence for row in borderless_rows]))
                    if borderless_rows
                    else 0.0
                )

                candidates = [
                    ("bordered_grid", bordered_rows, bordered_confidence),
                    (
                        "native_digital_spatial" if crop_only and words else "borderless_spatial",
                        borderless_rows,
                        borderless_confidence,
                    ),
                    (visual.method, visual_rows, visual.confidence),
                ]
                candidates = [candidate for candidate in candidates if candidate[1]]

                if candidates:
                    scored = []
                    structure_candidates = []
                    for method, candidate_rows, confidence in candidates:
                        metrics = self._geometry_candidate_metrics(
                            candidate_rows,
                            confidence,
                        )
                        score = float(metrics["score"])
                        scored.append(
                            (
                                score,
                                method,
                                candidate_rows,
                                confidence,
                            )
                        )
                        structure_candidates.append(
                            {
                                "method": method,
                                **metrics,
                                "selected": False,
                            }
                        )

                    score, structure_method, rows, structure_confidence = max(
                        scored, key=lambda item: item[0]
                    )
                    for candidate_info in structure_candidates:
                        candidate_info["selected"] = (
                            candidate_info["method"] == structure_method
                            and abs(float(candidate_info["score"]) - score) < 1e-9
                        )
                    fallback.append(f"structure_{structure_method}_score={score:.2f}")

            # =====================================================
            # DETECTION-ONLY TEXT-BOX FALLBACK (CROP-ONLY)
            #
            # This is not character recognition.  EasyOCR/CRAFT returns only
            # bounding boxes that say "text exists here".  The spatial boxes
            # are clustered into rows/columns/cells and the cell values remain
            # blank.  It is invoked lazily only when visual/native geometry has
            # not already produced a usable structure.
            # =====================================================

            text_detection_cfg = (
                config.get("visual_structure", {})
                .get("text_detection_fallback", {})
            )
            text_detection_enabled = (
                crop_only and bool(text_detection_cfg.get("enabled", True))
            )
            if not rows and text_detection_enabled:
                try:
                    detector = create_text_detector(config)
                    text_detection_result = detector.detect(structure_image)
                    detected_boxes = text_detection_result.boxes
                    minimum_boxes = max(1, int(text_detection_cfg.get("minimum_boxes", 4)))
                    fallback.append(
                        f"text_detection_only_{text_detection_result.engine}_"
                        f"{text_detection_result.device}_{len(detected_boxes)}_boxes"
                    )
                    log(
                        self.logger,
                        "text_detection_fallback",
                        stage="structure_detection",
                        file_name=input_path.name,
                        page_number=page_number,
                        engine=text_detection_result.engine,
                        device=text_detection_result.device,
                        recognizer_loaded=False,
                        boxes_detected=len(detected_boxes),
                    )

                    if page_debug.exists() and detected_boxes:
                        self._save_ocr_overlay(
                            structure_image,
                            detected_boxes,
                            page_debug / "07c_text_detection_boxes.png",
                        )

                    if len(detected_boxes) >= minimum_boxes:
                        detected_structure = BorderlessTableDetector(config).detect(
                            detected_boxes,
                            input_path.name,
                            page_number,
                            page_bbox,
                        )
                        detected_rows = [
                            row
                            for table_rows in detected_structure.rows_by_table.values()
                            for row in table_rows
                        ]
                        if detected_rows:
                            detection_confidence = max(
                                (region.confidence for region in detected_structure.regions),
                                default=float(text_detection_cfg.get("structural_confidence", 0.60)),
                            )
                            rows = self._prepare_detection_only_rows(
                                detected_rows,
                                detection_confidence,
                            )
                            structure_method = "easyocr_detection_spatial"
                            structure_confidence = detection_confidence
                            executed_strategy = "geometry_plus_text_detection"
                            fallback.append("structure_recovered_by_text_detection")
                except Exception as exc:
                    text_detection_error = f"{type(exc).__name__}: {exc}"
                    fallback.append("text_detection_fallback_failed")
                    issues.append(
                        ValidationIssue(
                            code="TEXT_DETECTION_FALLBACK_FAILED",
                            message=(
                                "Detection-only text-box fallback could not run: "
                                f"{text_detection_error}"
                            ),
                            severity="warning",
                            page_number=page_number,
                        )
                    )

            # Save a visual-region overlay independently from the classic ruled
            # detector so a developer can see why geometry-only cropping worked.
            if page_debug.exists() and visual.regions:
                visual_overlay = LayoutAnalyzer.draw_regions(
                    structure_image,
                    visual.regions,
                )
                cv2.imwrite(
                    str(page_debug / "07b_visual_detected_regions.png"),
                    visual_overlay,
                )

            # =====================================================
            # FREE TEXT FALLBACK
            # =====================================================

            if not rows:
                if crop_only:
                    # Do not create an artificial OCR row.  A geometry-only run
                    # that found no croppable structure is completed, but it is
                    # explicitly reported as a warning rather than a silent success.
                    fallback.append(
                        "geometry_only_"
                        "no_rows_detected"
                    )
                    issues.append(
                        ValidationIssue(
                            code="NO_STRUCTURE_DETECTED",
                            message=(
                                "Crop-only processing completed but no row/cell "
                                "structure could be inferred from page geometry."
                            ),
                            severity="warning",
                            page_number=page_number,
                        )
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
                # No semantic OCR validation runs here, but structural warnings
                # (for example NO_STRUCTURE_DETECTED) must be preserved.
                pass

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

            crop_image = structure_image

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
            # PAGE COMPLETION STATUS
            # =====================================================

            issue_severities = {str(issue.severity).lower() for issue in issues}
            if "error" in issue_severities:
                page_status = "completed_with_validation_errors"
            elif issues:
                page_status = "completed_with_warning"
            else:
                page_status = "completed"

            # =====================================================
            # DEBUG OUTPUTS
            # =====================================================

            if page_debug.exists():
                self._save_structure_overlays(
                    structure_image,
                    rows,
                    issues,
                    page_debug,
                )

                # No meaningless OCR overlay in crop-only.
                if not crop_only:
                    self._save_ocr_overlay(
                        structure_image,
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
                    "page_status": page_status,
                    "processing_mode": (
                        "geometry_plus_text_detection"
                        if crop_only and bool(
                            config.get("visual_structure", {})
                            .get("text_detection_fallback", {})
                            .get("enabled", True)
                        )
                        else ("geometry_only" if crop_only else "full_extraction")
                    ),
                    "ocr_enabled": (not crop_only),
                    "ocr_recognition_enabled": (not crop_only),
                    "text_detection_fallback": {
                        "enabled": crop_only and bool(
                            config.get("visual_structure", {})
                            .get("text_detection_fallback", {})
                            .get("enabled", True)
                        ),
                        "used": text_detection_result is not None,
                        "engine": (
                            text_detection_result.engine
                            if text_detection_result is not None
                            else None
                        ),
                        "device": (
                            text_detection_result.device
                            if text_detection_result is not None
                            else None
                        ),
                        "boxes_detected": (
                            len(text_detection_result.boxes)
                            if text_detection_result is not None
                            else 0
                        ),
                        "recognizer_loaded": False,
                        "error": text_detection_error,
                    },
                    "output_mode": (
                        output_mode
                    ),
                    "recommended_strategy": analysis.recommended_strategy.value,
                    "executed_strategy": executed_strategy,
                    "structure_method": structure_method,
                    "structure_confidence": structure_confidence,
                    "structure_detected": bool(rows),
                    "structure_candidates": structure_candidates,
                    "visual_structure": {
                        "method": visual.method,
                        "confidence": visual.confidence,
                        "measurements": visual.measurements,
                    },
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
                recommended_strategy=analysis.recommended_strategy.value,
                executed_strategy=executed_strategy,
                processing_mode=(
                    "geometry_plus_text_detection"
                    if crop_only and bool(
                        config.get("visual_structure", {})
                        .get("text_detection_fallback", {})
                        .get("enabled", True)
                    )
                    else ("geometry_only" if crop_only else "full_extraction")
                ),
                output_mode=output_mode,
                ocr_enabled=not crop_only,
                ocr_recognition_enabled=not crop_only,
                text_detection_used=text_detection_result is not None,
                text_detection_boxes=(
                    len(text_detection_result.boxes)
                    if text_detection_result is not None
                    else 0
                ),
                text_detection_device=(
                    text_detection_result.device
                    if text_detection_result is not None
                    else None
                ),
                structure_method=structure_method,
                structure_confidence=structure_confidence,
                structure_detected=bool(rows),
                structure_candidates=[
                    {
                        "method": candidate.get("method"),
                        "score": candidate.get("score"),
                        "selected": candidate.get("selected", False),
                    }
                    for candidate in structure_candidates
                ],
                page_status=page_status,
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
                    0.0
                    if crop_only
                    else (
                        (
                            sum(r.row_confidence for r in rows) / len(rows)
                        )
                        if rows
                        else 0.0
                    )
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
    def _scale_pdf_words_to_image(words, page, image):
        if not words:
            return []
        sx = image.shape[1] / page.rect.width if page.rect.width else 1.0
        sy = image.shape[0] / page.rect.height if page.rect.height else 1.0
        return [
            type(word)(
                word.text,
                BBox(
                    word.bbox.x0 * sx,
                    word.bbox.y0 * sy,
                    word.bbox.x1 * sx,
                    word.bbox.y1 * sy,
                ),
                word.confidence,
                word.source,
                word.block_no,
                word.line_no,
                word.word_no,
                word.language,
            )
            for word in words
        ]

    @staticmethod
    def _assign_words_to_geometry_rows(rows: list[ExtractedRow], words) -> list[ExtractedRow]:
        for row in rows:
            confidences: list[float] = []
            for cell in row.cells:
                assigned = [
                    word
                    for word in words
                    if (
                        cell.bbox.intersection_ratio(word.bbox, denominator="other") >= 0.30
                        or (
                            cell.bbox.x0 <= word.bbox.center[0] <= cell.bbox.x1
                            and cell.bbox.y0 <= word.bbox.center[1] <= cell.bbox.y1
                        )
                    )
                ]
                assigned.sort(key=lambda word: (word.bbox.y0, word.bbox.x0))
                cell.raw_value = " ".join(word.text for word in assigned).strip()
                cell.normalized_value = cell.raw_value
                cell.confidence = (
                    float(np.mean([word.confidence for word in assigned]))
                    if assigned
                    else 0.0
                )
                cell.engine = assigned[0].source if assigned else "opencv_geometry"
                if assigned:
                    confidences.append(cell.confidence)
            row.row_confidence = float(np.mean(confidences)) if confidences else row.row_confidence
        return rows

    @staticmethod
    def _prepare_detection_only_rows(
        rows: list[ExtractedRow],
        structural_confidence: float,
    ) -> list[ExtractedRow]:
        """Mark rows built from text boxes as geometry, never recognized text.

        BorderlessTableDetector is reused for its positional clustering.  This
        helper removes any placeholder semantics and records a structural
        confidence only, so crop manifests cannot accidentally look like OCR
        output.
        """
        confidence = max(0.0, min(1.0, float(structural_confidence)))
        for row in rows:
            row.row_confidence = confidence
            row.normalized = {}
            for cell in row.cells:
                cell.raw_value = ""
                cell.normalized_value = None
                cell.confidence = confidence
                cell.engine = "easyocr_detection_geometry"
                cell.validation_status = "unvalidated"
        return rows

    @staticmethod
    def _geometry_candidate_metrics(
        rows: list[ExtractedRow],
        confidence_hint: float = 0.0,
    ) -> dict[str, float]:
        """Score a structure candidate without rewarding physical-line fragmentation.

        Older scoring multiplied ``row_count * column_count * confidence``.
        That makes OCR spatial clustering win simply by splitting a multiline
        logical record into many physical text lines.  A six-row shaded grid can
        therefore lose to twenty-nine OCR line fragments even when the grid is
        the real table structure.

        The v3.2 selection score keeps row coverage useful but makes it
        sub-linear, then adds two generic quality signals:

        * compactness: rows that explain one coherent table region are preferred
          over candidates stretched across large unrelated page gaps/footer text;
        * occupancy: when recognized/native words exist, candidates whose rows
          repeatedly populate a useful fraction of their columns are preferred
          over sparse continuation-line fragments.

        No filename, company, template, fixed column count, or bank-specific
        keyword is used.  Geometry-only candidates still work because occupancy
        becomes neutral when cell text is intentionally absent.
        """
        if not rows:
            return {
                "score": 0.0,
                "row_count": 0.0,
                "median_columns": 0.0,
                "confidence": 0.0,
                "row_factor": 0.0,
                "compactness": 0.0,
                "median_occupancy": 0.0,
                "occupancy_factor": 1.0,
                "column_consistency": 0.0,
            }

        column_counts = [len(row.cells) for row in rows if row.cells]
        median_columns = float(np.median(column_counts)) if column_counts else 0.0

        row_confidences = [float(row.row_confidence) for row in rows]
        row_confidence = float(np.mean(row_confidences)) if row_confidences else 0.0
        confidence = max(0.10, row_confidence, float(confidence_hint))

        # More rows are useful evidence, but the gain must be sub-linear so an
        # OCR candidate cannot win merely by fragmenting multiline records.
        row_factor = 1.0 + float(np.log1p(len(rows)))

        # Reward a coherent vertical region.  The 0.50 floor prevents legitimate
        # forms with generous row spacing from being over-penalized.
        row_boxes = [row.bbox for row in rows if row.bbox is not None and row.bbox.height > 0]
        compactness = 1.0
        if row_boxes:
            min_y = min(box.y0 for box in row_boxes)
            max_y = max(box.y1 for box in row_boxes)
            span = max(1.0, max_y - min_y)
            occupied_height = sum(box.height for box in row_boxes)
            compactness = max(0.50, min(1.0, occupied_height / span))

        # Text occupancy is only a signal when semantic text actually exists.
        # In crop-only geometry modes all cells are intentionally blank, so the
        # factor stays neutral at 1.0.
        occupancy_ratios: list[float] = []
        semantic_cells_seen = False
        for row in rows:
            if not row.cells:
                continue
            nonempty = sum(bool((cell.raw_value or "").strip()) for cell in row.cells)
            if nonempty:
                semantic_cells_seen = True
            occupancy_ratios.append(nonempty / len(row.cells))

        median_occupancy = (
            float(np.median(occupancy_ratios))
            if occupancy_ratios
            else 0.0
        )
        occupancy_factor = (
            0.50 + median_occupancy
            if semantic_cells_seen
            else 1.0
        )

        # Candidates should repeat a stable number of columns across rows.
        column_consistency = 1.0
        if len(column_counts) > 1 and median_columns > 0:
            spread = float(np.std(column_counts)) / max(1.0, median_columns)
            column_consistency = max(0.50, 1.0 / (1.0 + spread))

        score = (
            row_factor
            * max(1.0, median_columns)
            * confidence
            * compactness
            * occupancy_factor
            * column_consistency
        )

        return {
            "score": float(score),
            "row_count": float(len(rows)),
            "median_columns": float(median_columns),
            "confidence": float(confidence),
            "row_factor": float(row_factor),
            "compactness": float(compactness),
            "median_occupancy": float(median_occupancy),
            "occupancy_factor": float(occupancy_factor),
            "column_consistency": float(column_consistency),
        }

    @staticmethod
    def _geometry_candidate_score(
        rows: list[ExtractedRow],
        confidence_hint: float = 0.0,
    ) -> float:
        """Backward-compatible scalar wrapper for candidate scoring."""
        return float(
            UniversalPDFPipeline._geometry_candidate_metrics(
                rows,
                confidence_hint,
            )["score"]
        )

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