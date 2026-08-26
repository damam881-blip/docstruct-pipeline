from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from models import BBox, ExtractedRow, PageExtractionResult
from pipeline.crop_generator import CropGenerator


_ALLOWED_MODES = {
    "full",
    "data_only",
    "cropped_cells_only",
    "cropped_rows_only",
    "cropped_rows_and_cells",
    "training_dataset",
    "custom",
}

_ALLOWED_TRAINING_LABEL_SOURCES = {"ocr_draft", "normalized", "blank"}


@dataclass(frozen=True, slots=True)
class OutputPlan:
    mode: str
    excel_enabled: bool
    save_cells: bool
    save_rows: bool
    manifest_csv: bool
    manifest_json: bool
    training_dataset_enabled: bool
    training_label_source: str
    include_empty_cells: bool
    artifact_root: Path
    image_format: str
    jpeg_quality: int


class OutputManager:
    """Create output crops and manifests according to the JSON/YAML output plan.

    The plan is intentionally configuration-driven. This means the same PDF can
    be rerun with ``--run-config`` after changing only ``config.output`` in the
    generated JSON file.
    """

    def __init__(self, config: dict[str, Any], output_path: str | Path) -> None:
        self.config = config
        self.output_path = Path(output_path)
        self.plan = self._build_plan(config, self.output_path)
        self.cropper = CropGenerator(config)
        self.records: list[dict[str, Any]] = []
        self.plan.artifact_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _build_plan(config: dict[str, Any], output_path: Path) -> OutputPlan:
        output_cfg = config.get("output", {})
        mode = str(output_cfg.get("mode", "full")).strip().lower()
        if mode not in _ALLOWED_MODES:
            raise ValueError(
                f"Unsupported output.mode {mode!r}. Allowed values: "
                + ", ".join(sorted(_ALLOWED_MODES))
            )

        # Mode presets are deliberately explicit. Use mode=custom when every
        # individual switch should be controlled independently.
        presets: dict[str, tuple[bool, bool, bool, bool]] = {
            # excel, cells, rows, training dataset
            "full": (True, True, True, False),
            "data_only": (True, False, False, False),
            "cropped_cells_only": (False, True, False, False),
            "cropped_rows_only": (False, False, True, False),
            "cropped_rows_and_cells": (False, True, True, False),
            "training_dataset": (False, True, False, True),
        }

        excel_cfg = output_cfg.get("excel", {})
        crops_cfg = output_cfg.get("crops", {})
        training_cfg = output_cfg.get("training_dataset", {})
        if mode == "custom":
            excel_enabled = bool(excel_cfg.get("enabled", True))
            save_cells = bool(crops_cfg.get("save_cells", False))
            save_rows = bool(crops_cfg.get("save_rows", False))
            training_enabled = bool(training_cfg.get("enabled", False))
        else:
            excel_enabled, save_cells, save_rows, training_enabled = presets[mode]

        label_source = str(training_cfg.get("label_source", "ocr_draft")).strip().lower()
        if label_source not in _ALLOWED_TRAINING_LABEL_SOURCES:
            raise ValueError(
                "output.training_dataset.label_source must be one of: "
                + ", ".join(sorted(_ALLOWED_TRAINING_LABEL_SOURCES))
            )

        raw_root = output_cfg.get("artifact_directory")
        if raw_root:
            artifact_root = Path(raw_root)
            if not artifact_root.is_absolute():
                artifact_root = output_path.parent / artifact_root
        else:
            artifact_root = output_path.parent / f"{output_path.stem}_artifacts"

        image_format = str(crops_cfg.get("image_format", "png")).strip().lower().lstrip(".")
        if image_format not in {"png", "jpg", "jpeg", "webp"}:
            raise ValueError("output.crops.image_format must be png, jpg, jpeg, or webp")

        return OutputPlan(
            mode=mode,
            excel_enabled=excel_enabled,
            save_cells=save_cells,
            save_rows=save_rows,
            manifest_csv=bool(crops_cfg.get("manifest_csv", True)),
            manifest_json=bool(crops_cfg.get("manifest_json", True)),
            training_dataset_enabled=training_enabled,
            training_label_source=label_source,
            include_empty_cells=bool(crops_cfg.get("include_empty_cells", True)),
            artifact_root=artifact_root,
            image_format=image_format,
            jpeg_quality=max(1, min(100, int(crops_cfg.get("jpeg_quality", 95)))),
        )

    @property
    def any_crop_requested(self) -> bool:
        return self.plan.save_cells or self.plan.save_rows

    def save_page_crops(
        self,
        image: np.ndarray,
        rows: list[ExtractedRow],
        page_number: int,
    ) -> None:
        if not self.any_crop_requested:
            return
        if image is None or image.size == 0:
            return

        page_name = f"page_{page_number:04d}"
        rows_dir = self.plan.artifact_root / "rows" / page_name
        cells_dir = self.plan.artifact_root / "cells" / page_name

        for row in rows:
            if row.is_header and not bool(
                self.config.get("output", {}).get("crops", {}).get("include_headers", False)
            ):
                continue

            if self.plan.save_rows and row.bbox and row.bbox.area > 0:
                row_name = (
                    f"p{page_number:04d}_{self._safe_name(row.table_id)}_"
                    f"r{row.row_index:04d}"
                )
                row_path = self._save_crop(image, row.bbox, row_name, rows_dir)
                row.source_crop = str(row_path) if row_path else row.source_crop
                if row_path:
                    self.records.append(
                        self._record(
                            level="row",
                            path=row_path,
                            row=row,
                            bbox=row.bbox,
                            column_index=None,
                            raw_value=" | ".join(row.raw_values()),
                            normalized_value=row.normalized,
                            confidence=row.row_confidence,
                            engine=self._row_engine(row),
                        )
                    )

            if not self.plan.save_cells:
                continue
            for cell in row.cells:
                if not self.plan.include_empty_cells and not cell.raw_value.strip():
                    continue
                if cell.bbox.area <= 0:
                    continue
                cell_name = (
                    f"p{page_number:04d}_{self._safe_name(row.table_id)}_"
                    f"r{row.row_index:04d}_c{cell.column_index:03d}"
                )
                cell_path = self._save_crop(image, cell.bbox, cell_name, cells_dir)
                if not cell_path:
                    continue
                cell.crop_path = str(cell_path)
                self.records.append(
                    self._record(
                        level="cell",
                        path=cell_path,
                        row=row,
                        bbox=cell.bbox,
                        column_index=cell.column_index,
                        raw_value=cell.raw_value,
                        normalized_value=cell.normalized_value,
                        confidence=cell.confidence,
                        engine=cell.engine,
                    )
                )

    def _save_crop(self, image: np.ndarray, bbox: BBox, stem: str, directory: Path) -> Path | None:
        directory.mkdir(parents=True, exist_ok=True)
        cropped, _, _ = self.cropper.crop(image, bbox, stem, directory, save=False)
        if cropped.size == 0:
            return None
        path = directory / f"{stem}.{self.plan.image_format}"
        params: list[int] = []
        if self.plan.image_format in {"jpg", "jpeg"}:
            params = [cv2.IMWRITE_JPEG_QUALITY, self.plan.jpeg_quality]
        elif self.plan.image_format == "webp":
            params = [cv2.IMWRITE_WEBP_QUALITY, self.plan.jpeg_quality]
        if not cv2.imwrite(str(path), cropped, params):
            raise RuntimeError(f"Failed to write crop: {path}")
        return path

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_")
        return cleaned or "table"

    @staticmethod
    def _row_engine(row: ExtractedRow) -> str:
        engines = [cell.engine for cell in row.cells if cell.engine]
        return engines[0] if engines else "none"

    @staticmethod
    def _record(
        *,
        level: str,
        path: Path,
        row: ExtractedRow,
        bbox: BBox,
        column_index: int | None,
        raw_value: str,
        normalized_value: Any,
        confidence: float,
        engine: str,
    ) -> dict[str, Any]:
        engine_text = str(engine)
        geometry_engine = (
            engine_text.startswith("opencv_")
            or engine_text == "geometry"
            or engine_text.startswith("easyocr_detection")
            or engine_text.endswith("_geometry")
        )
        return {
            "level": level,
            "crop_path": str(path.resolve()),
            "crop_relative_path": str(path),
            "source_file": row.file_name,
            "page_number": row.page_number,
            "table_id": row.table_id,
            "row_index": row.row_index,
            "column_index": column_index,
            "bbox_x0": bbox.x0,
            "bbox_y0": bbox.y0,
            "bbox_x1": bbox.x1,
            "bbox_y1": bbox.y1,
            "confidence_type": "geometry" if geometry_engine else "ocr",
            "confidence": confidence,
            "ocr_engine": "none" if geometry_engine else engine,
            "ocr_confidence": 0.0 if geometry_engine else confidence,
            "geometry_confidence": confidence if geometry_engine else None,
            "raw_value": raw_value,
            "normalized_value": normalized_value,
            "validation_status": row.validation_status,
            "validation_errors": row.validation_errors,
        }

    def finalize(self, results: list[PageExtractionResult]) -> dict[str, Any]:
        root = self.plan.artifact_root
        root.mkdir(parents=True, exist_ok=True)
        records = self.records

        if self.any_crop_requested and self.plan.manifest_csv:
            self._write_csv(root / "crop_manifest.csv", records)
        if self.any_crop_requested and self.plan.manifest_json:
            (root / "crop_manifest.json").write_text(
                json.dumps(records, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        if self.plan.training_dataset_enabled:
            self._write_training_manifests(root, records)

        summary = {
            "mode": self.plan.mode,
            "excel_enabled": self.plan.excel_enabled,
            "artifact_directory": str(root.resolve()),
            "row_crops": sum(record["level"] == "row" for record in records),
            "cell_crops": sum(record["level"] == "cell" for record in records),
            "crop_manifest_csv": str((root / "crop_manifest.csv").resolve())
            if self.any_crop_requested and self.plan.manifest_csv
            else None,
            "crop_manifest_json": str((root / "crop_manifest.json").resolve())
            if self.any_crop_requested and self.plan.manifest_json
            else None,
            "training_labels_csv": str((root / "training_labels.csv").resolve())
            if self.plan.training_dataset_enabled
            else None,
            "training_label_source": self.plan.training_label_source
            if self.plan.training_dataset_enabled
            else None,
            "pages_successful": sum(result.success for result in results),
            "pages_failed": sum(not result.success for result in results),
            "pages_without_rows": sum(
                bool(getattr(result, "success", False))
                and not bool(getattr(result, "rows", []))
                for result in results
            ),
            "pages_with_structure": sum(
                bool(getattr(result, "success", False))
                and bool(getattr(result, "rows", []))
                for result in results
            ),
            "pages_completed_with_warnings": sum(
                bool(getattr(result, "success", False))
                and bool(getattr(result, "issues", []))
                for result in results
            ),
        }
        (root / "output_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return summary

    @staticmethod
    def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "level",
            "crop_path",
            "crop_relative_path",
            "source_file",
            "page_number",
            "table_id",
            "row_index",
            "column_index",
            "bbox_x0",
            "bbox_y0",
            "bbox_x1",
            "bbox_y1",
            "confidence_type",
            "confidence",
            "ocr_engine",
            "ocr_confidence",
            "geometry_confidence",
            "raw_value",
            "normalized_value",
            "validation_status",
            "validation_errors",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for record in records:
                normalized = dict(record)
                normalized["normalized_value"] = json.dumps(
                    record.get("normalized_value"), ensure_ascii=False, default=str
                )
                normalized["validation_errors"] = "; ".join(
                    record.get("validation_errors") or []
                )
                writer.writerow(normalized)

    def _write_training_manifests(self, root: Path, records: list[dict[str, Any]]) -> None:
        label_source = self.plan.training_label_source

        def draft_label(record: dict[str, Any]) -> str:
            if label_source == "ocr_draft":
                value = record.get("raw_value", "")
            elif label_source == "normalized":
                value = record.get("normalized_value", "")
            else:  # blank
                value = ""
            if value is None:
                return ""
            if isinstance(value, (dict, list, tuple)):
                return json.dumps(value, ensure_ascii=False, default=str)
            return str(value)

        all_cell_records = [
            record for record in records if record.get("level") == "cell"
        ]
        if label_source == "blank":
            # Manual-label mode intentionally preserves OCR-empty crops so a
            # reviewer can recover text that the current model failed to read.
            cell_records = all_cell_records
        else:
            cell_records = [
                record for record in all_cell_records if draft_label(record).strip()
            ]

        csv_path = root / "training_labels.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            fields = [
                "image_path",
                "ocr_draft_label",
                "corrected_label",
                "page_number",
                "table_id",
                "row_index",
                "column_index",
                "ocr_confidence",
                "needs_manual_review",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for record in cell_records:
                draft = draft_label(record)
                writer.writerow(
                    {
                        "image_path": record["crop_path"],
                        # The column name is kept stable for compatibility with
                        # prepare_easyocr_training_dataset.py. Its content now
                        # follows output.training_dataset.label_source.
                        "ocr_draft_label": draft,
                        "corrected_label": "",
                        "page_number": record["page_number"],
                        "table_id": record["table_id"],
                        "row_index": record["row_index"],
                        "column_index": record["column_index"],
                        "ocr_confidence": record["ocr_confidence"],
                        "needs_manual_review": (
                            label_source == "blank"
                            or not draft.strip()
                            or float(record.get("ocr_confidence", 0.0) or 0.0) < 0.90
                        ),
                    }
                )

        # A simple UTF-8 TSV is useful for downstream conversion scripts. The
        # corrected label should replace the draft label after human review.
        tsv_path = root / "training_labels_draft.tsv"
        with tsv_path.open("w", encoding="utf-8", newline="") as handle:
            for record in cell_records:
                label = draft_label(record).replace("\t", " ").replace("\n", " ")
                handle.write(f"{record['crop_path']}\t{label}\n")
