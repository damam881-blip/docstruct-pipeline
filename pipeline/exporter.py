from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from config import flatten_config
from models import ExtractedRow, PageExtractionResult, ValidationIssue, dataclass_to_dict


class Exporter:
    def __init__(self, config: dict) -> None:
        self.config = config.get("export", {})

    def export(
        self,
        output_path: str | Path,
        results: list[PageExtractionResult],
        resolved_config: dict[str, Any],
        source_file: str,
        config_source: str,
    ) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [row for result in results for row in result.rows if not row.is_header]
        issues = [issue for result in results for issue in result.issues]
        wb = Workbook()
        wb.remove(wb.active)
        self._data_sheet(wb, rows)
        self._review_sheet(wb, rows, issues)
        self._metadata_sheet(wb, results, source_file, config_source)
        self._config_sheet(wb, resolved_config)
        self._summary_sheet(wb, results)
        self._cell_metadata_sheet(wb, rows)
        wb.save(output_path)
        self._optional_exports(output_path, rows, results)

    def _data_sheet(self, wb: Workbook, rows: list[ExtractedRow]) -> None:
        ws = wb.create_sheet("Extracted Data")
        normalized_keys: list[str] = []
        for row in rows:
            for key in row.normalized:
                if key not in normalized_keys:
                    normalized_keys.append(key)
        headers = ["Source File", "Page", "Table ID", "Row", *normalized_keys, "Row Confidence", "Validation Status", "Validation Errors", "Source Crop", "Raw Values"]
        ws.append(headers)
        for row in rows:
            ws.append(
                [
                    row.file_name,
                    row.page_number,
                    row.table_id,
                    row.row_index,
                    *[row.normalized.get(k) for k in normalized_keys],
                    row.row_confidence,
                    row.validation_status,
                    "; ".join(row.validation_errors),
                    row.source_crop,
                    json.dumps(row.raw_values(), ensure_ascii=False),
                ]
            )
            if row.source_crop:
                cell = ws.cell(ws.max_row, headers.index("Source Crop") + 1)
                cell.hyperlink = Path(row.source_crop).resolve().as_uri()
                cell.style = "Hyperlink"
        self._format_table(ws, "ExtractedDataTable")
        status_col = get_column_letter(headers.index("Validation Status") + 1)
        ws.conditional_formatting.add(f"{status_col}2:{status_col}{max(2, ws.max_row)}", FormulaRule(formula=[f'${status_col}2="review"'], fill=PatternFill("solid", fgColor="FFC7CE")))

    def _review_sheet(self, wb: Workbook, rows: list[ExtractedRow], issues: list[ValidationIssue]) -> None:
        ws = wb.create_sheet("Review Required")
        headers = ["Source File", "Page", "Table ID", "Row", "Issue Codes", "Reasons", "Confidence", "Raw Values", "Source Crop"]
        ws.append(headers)
        issue_map: dict[tuple[int | None, str | None, int | None], list[ValidationIssue]] = {}
        for issue in issues:
            issue_map.setdefault((issue.page_number, issue.table_id, issue.row_index), []).append(issue)
        for row in rows:
            if row.validation_status != "review":
                continue
            row_issues = issue_map.get((row.page_number, row.table_id, row.row_index), [])
            ws.append([
                row.file_name,
                row.page_number,
                row.table_id,
                row.row_index,
                ", ".join(i.code for i in row_issues),
                "; ".join(i.message for i in row_issues) or "; ".join(row.validation_errors),
                row.row_confidence,
                json.dumps(row.raw_values(), ensure_ascii=False),
                row.source_crop,
            ])
            if row.source_crop:
                cell = ws.cell(ws.max_row, 9)
                cell.hyperlink = Path(row.source_crop).resolve().as_uri()
                cell.style = "Hyperlink"
        self._format_table(ws, "ReviewRequiredTable")

    def _metadata_sheet(self, wb: Workbook, results: list[PageExtractionResult], source_file: str, config_source: str) -> None:
        ws = wb.create_sheet("Extraction Metadata")
        headers = ["Source File", "Page", "Page Type", "Layout Type", "Strategy", "OCR Required", "Rows", "Columns", "Average Confidence", "Processing Seconds", "Fallback Chain", "Layout Signature", "Success", "Error"]
        ws.append(headers)
        for result in results:
            cols = max((len(row.cells) for row in result.rows), default=0)
            conf = sum(row.row_confidence for row in result.rows) / len(result.rows) if result.rows else 0.0
            ws.append([
                source_file,
                result.analysis.page_number,
                result.analysis.page_type.value,
                result.analysis.layout_type.value,
                result.analysis.recommended_strategy.value,
                result.analysis.requires_ocr,
                len(result.rows),
                cols,
                conf,
                result.processing_seconds,
                " -> ".join(result.fallback_chain),
                result.analysis.layout_signature,
                result.success,
                result.error,
            ])
        ws["P1"] = "Configuration Source"
        ws["P2"] = config_source
        self._format_table(ws, "ExtractionMetadataTable", end_column=14)

    def _config_sheet(self, wb: Workbook, config: dict[str, Any]) -> None:
        ws = wb.create_sheet("Parameter Configuration")
        ws.append(["Parameter", "Value"])
        for key, value in flatten_config(config):
            ws.append([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value])
        self._format_table(ws, "ParameterConfigurationTable")

    def _summary_sheet(self, wb: Workbook, results: list[PageExtractionResult]) -> None:
        ws = wb.create_sheet("Test Summary")
        exported_rows = [row for result in results for row in result.rows if not row.is_header]
        total_rows = len(exported_rows)
        valid_rows = sum(row.validation_status == "valid" for row in exported_rows)
        review_rows = sum(row.validation_status == "review" for row in exported_rows)
        avg_conf = sum(row.row_confidence for row in exported_rows) / total_rows if total_rows else 0.0
        ws.append(["Metric", "Value"])
        for metric, value in [
            ("Pages processed", len(results)),
            ("Pages successful", sum(r.success for r in results)),
            ("Rows extracted", total_rows),
            ("Valid rows", valid_rows),
            ("Review-required rows", review_rows),
            ("Validation success rate", valid_rows / total_rows if total_rows else 0.0),
            ("Average OCR/row confidence", avg_conf),
            ("Processing time seconds", sum(r.processing_seconds for r in results)),
        ]:
            ws.append([metric, value])
        self._format_table(ws, "TestSummaryTable")

    @staticmethod
    def _format_table(ws, table_name: str, end_column: int | None = None) -> None:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        max_col = end_column or ws.max_column
        if ws.max_row >= 2:
            ref = f"A1:{get_column_letter(max_col)}{ws.max_row}"
            table = Table(displayName=table_name, ref=ref)
            table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=False)
            ws.add_table(table)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for column_cells in ws.columns:
            values = [str(c.value) if c.value is not None else "" for c in column_cells[: min(len(column_cells), 200)]]
            width = min(45, max(10, max((len(v) for v in values), default=10) + 2))
            ws.column_dimensions[get_column_letter(column_cells[0].column)].width = width
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                # No sheet in this exporter intentionally writes formulas. OCR text
                # beginning with '=' must remain evidence, not execute as a formula.
                if cell.data_type == "f":
                    cell.data_type = "s"
                cell.alignment = Alignment(vertical="top", wrap_text=True)


    def _cell_metadata_sheet(self, wb: Workbook, rows: list[ExtractedRow]) -> None:
        ws = wb.create_sheet("Cell Metadata")
        headers = [
            "Source File", "Page", "Table ID", "Row", "Column", "BBox X0", "BBox Y0", "BBox X1", "BBox Y1",
            "Crop Path", "OCR Engine", "OCR Confidence", "Raw Value", "Normalized Value", "Validation Status", "Validation Errors",
        ]
        ws.append(headers)
        for row in rows:
            for cell in row.cells:
                ws.append([
                    cell.file_name,
                    cell.page_number,
                    cell.table_id,
                    cell.row_index,
                    cell.column_index,
                    cell.bbox.x0,
                    cell.bbox.y0,
                    cell.bbox.x1,
                    cell.bbox.y1,
                    cell.crop_path,
                    cell.engine,
                    cell.confidence,
                    cell.raw_value,
                    json.dumps(cell.normalized_value, ensure_ascii=False, default=str) if isinstance(cell.normalized_value, (dict, list)) else cell.normalized_value,
                    cell.validation_status,
                    "; ".join(cell.validation_errors),
                ])
                if cell.crop_path:
                    link_cell = ws.cell(ws.max_row, headers.index("Crop Path") + 1)
                    link_cell.hyperlink = Path(cell.crop_path).resolve().as_uri()
                    link_cell.style = "Hyperlink"
        self._format_table(ws, "CellMetadataTable")
        ws.column_dimensions["M"].width = 45
        ws.column_dimensions["N"].width = 24

    def _optional_exports(self, output_path: Path, rows: list[ExtractedRow], results: list[PageExtractionResult]) -> None:
        records = []
        for row in rows:
            record = {
                "source_file": row.file_name,
                "page_number": row.page_number,
                "table_id": row.table_id,
                "row_index": row.row_index,
                **row.normalized,
                "raw_values": row.raw_values(),
                "confidence": row.row_confidence,
                "validation_status": row.validation_status,
                "validation_errors": row.validation_errors,
                "cells": [
                    {
                        "column_index": cell.column_index,
                        "bbox": cell.bbox.to_list(),
                        "crop_path": cell.crop_path,
                        "engine": cell.engine,
                        "confidence": cell.confidence,
                        "raw_value": cell.raw_value,
                        "normalized_value": cell.normalized_value,
                        "validation_status": cell.validation_status,
                        "validation_errors": cell.validation_errors,
                    }
                    for cell in row.cells
                ],
            }
            records.append(record)
        df = pd.DataFrame(records)
        stem = output_path.with_suffix("")
        if self.config.get("csv", False):
            df.to_csv(stem.with_suffix(".csv"), index=False, encoding="utf-8-sig")
        if self.config.get("json", False):
            stem.with_suffix(".json").write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        if self.config.get("jsonl", False):
            stem.with_suffix(".jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in records), encoding="utf-8")
        if self.config.get("parquet", False):
            try:
                df.to_parquet(stem.with_suffix(".parquet"), index=False)
            except Exception:
                pass
