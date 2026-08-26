from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import yaml

from config import ConfigResolver, get_nested, parse_cli_overrides
from pipeline.parameter_advisor import ParameterAdvisor
from pipeline.pipeline import UniversalPDFPipeline


def parse_pages(spec: str | None, total_pages: int | None = None) -> list[int] | None:
    """Parse page specifications such as ``1,3,5-8`` into 1-based numbers."""
    if not spec:
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            pages.update(range(int(start), int(end) + 1))
        else:
            pages.add(int(part))
    if total_pages:
        pages = {page for page in pages if 1 <= page <= total_pages}
    return sorted(pages)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generic page-adaptive PDF data extraction and OCR pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config",
        default="configs/default.yaml",
        help=(
            "Base YAML configuration file. This supplies the global/default "
            "pipeline settings and defaults to configs/default.yaml. "
            "Do not pass the PDF here; use --input for the PDF."
        ),
    )
    common.add_argument(
        "--run-config",
        help=(
            "Optional editable JSON produced by a previous run. It overlays the "
            "base YAML and is the normal place for PDF-specific tuning after the "
            "first run. It may be a generated *.run_config.json file, a "
            "page_report.json containing resolved_config, or a plain JSON "
            "configuration object. Do not pass the PDF here; use --input."
        ),
    )
    common.add_argument(
        "--override",
        action="append",
        default=[],
        help=(
            "Advanced one-off highest-priority dotted parameter override, "
            "e.g. render.default_dpi=500. The standard developer workflow "
            "uses YAML for defaults and the generated JSON for PDF-specific "
            "changes instead of this option."
        ),
    )

    extract = subparsers.add_parser("extract", parents=[common])
    extract.add_argument("--input", required=True, help=(
            "PDF file to process. This option accepts the PDF only. "
            "Use --config for the base YAML and --run-config for an optional "
            "generated/editable JSON configuration."
        ))
    extract.add_argument(
        "--output",
        required=True,
        help=(
            "Output target/base path. In crop-only modes no Excel is written; "
            "the stem is used to name the artifact directory and run-config JSON."
        ),
    )
    extract.add_argument("--pages", help="Page list/range, e.g. 1,3,5-8")
    extract.add_argument("--debug", action="store_true")
    extract.add_argument("--debug-root")
    extract.add_argument(
        "--save-run-config",
        help=(
            "Path for the reusable JSON configuration. When omitted, the "
            "pipeline writes <output_stem>.run_config.json beside the Excel file."
        ),
    )
    extract.add_argument(
        "--no-save-run-config",
        action="store_true",
        help="Do not write the reusable JSON configuration after extraction.",
    )

    analyze = subparsers.add_parser("analyze", parents=[common])
    analyze.add_argument("--input", required=True, help=(
            "PDF file to process. This option accepts the PDF only. "
            "Use --config for the base YAML and --run-config for an optional "
            "generated/editable JSON configuration."
        ))
    analyze.add_argument("--pages")
    analyze.add_argument("--output")
    analyze.add_argument(
        "--fast", action="store_true", help="Skip thumbnail rendering and quick line analysis"
    )

    diagnose = subparsers.add_parser("diagnose", parents=[common])
    diagnose.add_argument("--input", required=True, help=(
            "PDF file to process. This option accepts the PDF only. "
            "Use --config for the base YAML and --run-config for an optional "
            "generated/editable JSON configuration."
        ))
    diagnose.add_argument("--pages", help="Representative pages, e.g. 1,5,10")
    diagnose.add_argument("--output")

    inspect = subparsers.add_parser("inspect-config", parents=[common])
    inspect.add_argument("--parameter", required=True)

    tune = subparsers.add_parser("tune", parents=[common])
    tune.add_argument("--input", required=True, help=(
            "PDF file to process. This option accepts the PDF only. "
            "Use --config for the base YAML and --run-config for an optional "
            "generated/editable JSON configuration."
        ))
    tune.add_argument("--page", type=int, required=True)
    tune.add_argument("--parameter", required=True)
    tune.add_argument("--values", nargs="+", required=True)
    tune.add_argument("--output", default="tuning_results.json")
    return parser


def resolver_from_args(args: argparse.Namespace) -> ConfigResolver:
    return ConfigResolver(
        config_path=args.config,
        cli_overrides=parse_cli_overrides(args.override),
        run_config_path=getattr(args, "run_config", None),
    )


def _result_summary(results: list[Any]) -> dict[str, Any]:
    """Build a compact serializable summary for the reusable run-config JSON."""
    successful = [result for result in results if result.success]
    failed = [result for result in results if not result.success]
    rows = sum(len(result.rows) for result in results)
    issues = sum(len(result.issues) for result in results)
    return {
        "pages_processed": len(results),
        "pages_successful": len(successful),
        "pages_failed": len(failed),
        "rows_extracted": rows,
        "validation_issues": issues,
        "processing_seconds": sum(result.processing_seconds for result in results),
        "failed_pages": [
            {
                "page_number": result.analysis.page_number,
                "error": result.error,
            }
            for result in failed
        ],
    }


def _default_run_config_path(output_path: str | Path) -> Path:
    output = Path(output_path)
    return output.with_suffix(".run_config.json")


def cmd_extract(args: argparse.Namespace) -> int:
    resolver = resolver_from_args(args)
    pipeline = UniversalPDFPipeline(resolver, debug=args.debug)
    pages = parse_pages(args.pages)
    results = pipeline.extract(args.input, args.output, pages, args.debug_root)

    last_run = _result_summary(results)
    last_run["outputs"] = pipeline.last_output_summary
    run_config_path: Path | None = None
    if not args.no_save_run_config:
        run_config_path = Path(
            args.save_run_config or _default_run_config_path(args.output)
        )
        resolver.save_editable_run_config(
            run_config_path,
            source_pdf=args.input,
            output_file=args.output,
            selected_pages=pages,
            last_run=last_run,
        )

    print(
        json.dumps(
            {
                "output_target": str(Path(args.output).resolve()),
                "outputs": pipeline.last_output_summary,
                "run_config": (
                    str(run_config_path.resolve()) if run_config_path else None
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    resolver = resolver_from_args(args)
    pipeline = UniversalPDFPipeline(resolver)
    records = pipeline.analyze(
        args.input, parse_pages(args.pages), render_layout=not args.fast
    )
    payload = json.dumps(records, ensure_ascii=False, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    """Analyze representative pages and produce generic tuning advice.

    The advice is based only on measured page characteristics. It does not
    identify a company or select a saved PDF-specific profile.
    """
    resolver = resolver_from_args(args)
    pipeline = UniversalPDFPipeline(resolver)
    analyses = pipeline.analyze(args.input, parse_pages(args.pages), render_layout=True)
    advisor = ParameterAdvisor(resolver.resolve().values)
    report: list[dict[str, Any]] = []
    for analysis in analyses:
        advice = advisor.advise(analysis)
        report.append(
            {
                "page_number": analysis.get("page_number"),
                "page_type": analysis.get("page_type"),
                "layout_type": analysis.get("layout_type"),
                "recommended_strategy": analysis.get("recommended_strategy"),
                "observations": advice.observations,
                "suggested_overrides": advice.suggested_overrides,
                "inspect_debug_files": advice.inspect_debug_files,
                "cautions": advice.cautions,
            }
        )
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    resolver = resolver_from_args(args)
    cfg = resolver.resolve().values
    value = get_nested(cfg, args.parameter, "<not configured>")
    guide_path = Path(__file__).parent / "docs" / "parameter_catalog.yaml"
    guide = (
        yaml.safe_load(guide_path.read_text(encoding="utf-8"))
        if guide_path.exists()
        else {}
    )
    payload = {
        "parameter": args.parameter,
        "value": value,
        "guide": guide.get(args.parameter, {}),
    }
    print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))
    return 0


def cmd_tune(args: argparse.Namespace) -> int:
    """Run a transparent one-parameter grid search on one actual page.

    OCR confidence is only one component. Structural consistency, valid dates,
    valid numbers, balance checks, overlaps, and missing required values also
    contribute to the score.
    """
    values = [yaml.safe_load(value) for value in args.values]
    outputs: list[dict[str, Any]] = []
    weights = {
        "valid_dates_ratio": 1.0,
        "valid_numeric_ratio": 1.0,
        "balance_success_ratio": 2.0,
        "structural_consistency": 2.0,
        "ocr_confidence": 0.5,
        "overlap_penalty": -1.0,
        "empty_required_penalty": -1.0,
    }

    with tempfile.TemporaryDirectory(prefix="pdf_tune_") as temporary:
        temp_root = Path(temporary)
        for index, value in enumerate(values):
            override_items = list(args.override) + [
                f"{args.parameter}={yaml.safe_dump(value).strip()}"
            ]
            candidate = ConfigResolver(
                config_path=args.config,
                cli_overrides=parse_cli_overrides(override_items),
                run_config_path=args.run_config,
            )
            output = temp_root / f"candidate_{index}.xlsx"
            result = UniversalPDFPipeline(candidate, debug=False).extract(
                args.input,
                output,
                pages=[args.page],
                debug_root=temp_root / f"debug_{index}",
            )[0]
            cfg = candidate.resolve(args.page).values
            schema = cfg.get("schema", {}).get("columns", [])
            expected = cfg.get("validation", {}).get("expected_columns")
            rows = result.rows
            total_cells = sum(len(row.cells) for row in rows)
            nonempty_cells = sum(
                bool(cell.raw_value.strip()) for row in rows for cell in row.cells
            )
            structural = 0.0
            if rows:
                if expected:
                    structural = sum(
                        min(len(row.cells), int(expected)) / max(int(expected), 1)
                        for row in rows
                    ) / len(rows)
                else:
                    structural = nonempty_cells / max(total_cells, 1)

            date_indices = [
                index
                for index, spec in enumerate(schema)
                if spec.get("type") == "date"
            ]
            numeric_indices = [
                index
                for index, spec in enumerate(schema)
                if spec.get("type") in {"amount", "number"}
            ]
            date_values = [
                row.cells[index].normalized_value
                for row in rows
                for index in date_indices
                if index < len(row.cells)
            ]
            numeric_values = [
                row.cells[index].normalized_value
                for row in rows
                for index in numeric_indices
                if index < len(row.cells)
            ]
            codes = [issue.code for issue in result.issues]
            balance_failures = sum(code == "BALANCE_MISMATCH" for code in codes)
            metrics = {
                "valid_dates_ratio": (
                    sum(value is not None for value in date_values) / len(date_values)
                    if date_values
                    else 1.0
                ),
                "valid_numeric_ratio": (
                    sum(value is not None for value in numeric_values)
                    / len(numeric_values)
                    if numeric_values
                    else 1.0
                ),
                "balance_success_ratio": (
                    1.0
                    if not cfg.get("validation", {})
                    .get("balance_check", {})
                    .get("enabled", False)
                    else max(
                        0.0,
                        1.0 - balance_failures / max(len(rows) - 1, 1),
                    )
                ),
                "structural_consistency": structural,
                "ocr_confidence": (
                    sum(row.row_confidence for row in rows) / len(rows)
                    if rows
                    else 0.0
                ),
                "overlap_penalty": sum(
                    code == "OVERLAPPING_CELLS" for code in codes
                )
                / max(len(rows), 1),
                "empty_required_penalty": sum(
                    code == "MISSING_REQUIRED" for code in codes
                )
                / max(len(rows), 1),
            }
            score = sum(metrics[name] * weight for name, weight in weights.items())
            outputs.append(
                {
                    "value": value,
                    "score": score,
                    "metrics": metrics,
                    "rows": len(rows),
                    "issues": codes,
                    "fallback_chain": result.fallback_chain,
                    "success": result.success,
                    "error": result.error,
                }
            )

    outputs.sort(key=lambda record: record["score"], reverse=True)
    Path(args.output).write_text(
        json.dumps(outputs, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"best": outputs[0] if outputs else None, "output": args.output},
            ensure_ascii=False,
            default=str,
        )
    )
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    commands = {
        "extract": cmd_extract,
        "analyze": cmd_analyze,
        "diagnose": cmd_diagnose,
        "inspect-config": cmd_inspect,
        "tune": cmd_tune,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
