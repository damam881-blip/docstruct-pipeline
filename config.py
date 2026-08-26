from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


RUN_CONFIG_FORMAT = "universal_pdf_pipeline_run_config"
RUN_CONFIG_VERSION = 2


class ConfigurationError(ValueError):
    """Raised when a configuration file or command-line override is invalid."""


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into a deep copy of *base*.

    Dictionaries are merged recursively. Lists and scalar values replace the
    existing value completely. The input mappings are never modified.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def get_nested(mapping: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    """Read a value using a dotted path such as ``render.default_dpi``."""
    current: Any = mapping
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def set_nested(mapping: dict[str, Any], dotted_key: str, value: Any) -> None:
    """Set a value using a dotted path, creating intermediate mappings."""
    parts = dotted_key.split(".")
    current = mapping
    for part in parts[:-1]:
        existing = current.setdefault(part, {})
        if not isinstance(existing, dict):
            raise ConfigurationError(
                f"Cannot override {dotted_key!r}: {part!r} is not a mapping"
            )
        current = existing
    current[parts[-1]] = value


def parse_scalar(value: str) -> Any:
    """Parse CLI text using YAML rules, preserving strings when parsing fails."""
    try:
        return yaml.safe_load(value)
    except yaml.YAMLError:
        return value


def parse_cli_overrides(items: list[str] | None) -> dict[str, Any]:
    """Convert repeated ``key=value`` arguments into a nested dictionary."""
    result: dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise ConfigurationError(f"Override must be key=value, got: {item}")
        key, value = item.split("=", 1)
        set_nested(result, key.strip(), parse_scalar(value.strip()))
    return result


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load one YAML configuration file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(config_path)
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigurationError(f"Root YAML node must be a mapping: {config_path}")
    return data


def load_json(path: str | Path) -> dict[str, Any]:
    """Load a UTF-8 JSON object with a clear validation error."""
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(json_path)
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Invalid JSON in {json_path} at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"Root JSON node must be an object: {json_path}")
    return data


def extract_config_from_json(payload: dict[str, Any], source: str | Path) -> dict[str, Any]:
    """Extract the actual parameter mapping from supported JSON shapes.

    Supported inputs are:

    1. A generated run-config envelope containing ``config``.
    2. A debug ``page_report.json`` containing ``resolved_config``.
    3. A plain JSON object that is itself the configuration.

    This lets a user edit the JSON produced by a first run and pass the same
    file back to the next run without converting it to YAML.
    """
    if isinstance(payload.get("config"), dict):
        return copy.deepcopy(payload["config"])
    if isinstance(payload.get("resolved_config"), dict):
        return copy.deepcopy(payload["resolved_config"])

    metadata_keys = {
        "format",
        "version",
        "created_at_utc",
        "source_pdf",
        "output_file",
        "selected_pages",
        "base_yaml",
        "instructions",
        "last_run",
    }
    if payload and set(payload).issubset(metadata_keys):
        raise ConfigurationError(
            f"JSON file {source} contains metadata but no 'config' or "
            "'resolved_config' object"
        )
    return copy.deepcopy(payload)


def load_json_config(path: str | Path) -> dict[str, Any]:
    """Load any supported editable JSON configuration form."""
    payload = load_json(path)
    config = extract_config_from_json(payload, path)
    if not isinstance(config, dict):
        raise ConfigurationError(f"Configuration in {path} must be an object")
    return config


def build_run_config_payload(
    config: dict[str, Any],
    *,
    base_yaml: str | Path,
    run_config_input: str | Path | None = None,
    source_pdf: str | Path | None = None,
    output_file: str | Path | None = None,
    selected_pages: list[int] | None = None,
    last_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the editable JSON file written after an extraction run."""
    return {
        "format": RUN_CONFIG_FORMAT,
        "version": RUN_CONFIG_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_pdf": str(Path(source_pdf).resolve()) if source_pdf else None,
        "output_file": str(Path(output_file).resolve()) if output_file else None,
        "selected_pages": selected_pages,
        "base_yaml": str(Path(base_yaml).resolve()),
        "run_config_input": (
            str(Path(run_config_input).resolve()) if run_config_input else None
        ),
        "instructions": {
            "edit": "Edit values only inside the 'config' object.",
            "reuse": (
                "Pass this file with --run-config on the next analyze, "
                "diagnose, tune, or extract command."
            ),
            "priority": (
                "CLI --override > page_overrides > JSON run-config > base YAML"
            ),
            "output_modes": (
                "Set config.output.mode to full, data_only, cropped_cells_only, "
                "cropped_rows_only, cropped_rows_and_cells, training_dataset, "
                "or custom."
            ),
            "easyocr_custom_model": (
                "Set config.ocr.easyocr.recog_network to the custom model name "
                "after placing its .pth/.yaml/.py files in the configured model dirs."
            ),
        },
        "config": copy.deepcopy(config),
        "last_run": copy.deepcopy(last_run) if last_run is not None else None,
    }


def save_run_config(
    path: str | Path,
    config: dict[str, Any],
    *,
    base_yaml: str | Path,
    run_config_input: str | Path | None = None,
    source_pdf: str | Path | None = None,
    output_file: str | Path | None = None,
    selected_pages: list[int] | None = None,
    last_run: dict[str, Any] | None = None,
) -> Path:
    """Write an editable, reusable run configuration as UTF-8 JSON."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = build_run_config_payload(
        config,
        base_yaml=base_yaml,
        run_config_input=run_config_input,
        source_pdf=source_pdf,
        output_file=output_file,
        selected_pages=selected_pages,
        last_run=last_run,
    )
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return destination


@dataclass(slots=True)
class ResolvedConfig:
    """The effective parameters used for one page."""

    values: dict[str, Any]
    config_path: str
    run_config_path: str | None
    page_number: int | None
    page_overrides: dict[str, Any]
    cli_overrides: dict[str, Any]

    def get(self, dotted_key: str, default: Any = None) -> Any:
        return get_nested(self.values, dotted_key, default)

    def as_json(self) -> str:
        return json.dumps(self.values, ensure_ascii=False, indent=2, default=str)


class ConfigResolver:
    """Resolve generic YAML, editable JSON, page, and CLI parameters.

    Priority, from highest to lowest:

    1. Command-line ``--override`` values.
    2. ``page_overrides`` for the current page.
    3. Values loaded from ``--run-config`` JSON.
    4. Values in the base YAML configuration file.

    There is no PDF-name matching and no profile directory.
    """

    def __init__(
        self,
        config_path: str | Path = "configs/default.yaml",
        cli_overrides: dict[str, Any] | None = None,
        run_config_path: str | Path | None = None,
    ) -> None:
        self.config_path = str(config_path)
        self.run_config_path = str(run_config_path) if run_config_path else None
        self.yaml_defaults = load_yaml(config_path)
        self.json_overrides = (
            load_json_config(run_config_path) if run_config_path else {}
        )
        self.defaults = deep_merge(self.yaml_defaults, self.json_overrides)
        self.cli_overrides = cli_overrides or {}

    def resolve(self, page_number: int | None = None) -> ResolvedConfig:
        merged = copy.deepcopy(self.defaults)
        page_overrides: dict[str, Any] = {}
        if page_number is not None:
            page_map = merged.get("page_overrides", {})
            if isinstance(page_map, dict):
                page_overrides = (
                    page_map.get(page_number, page_map.get(str(page_number), {})) or {}
                )
        if page_overrides:
            merged = deep_merge(merged, page_overrides)
        merged = deep_merge(merged, self.cli_overrides)
        return ResolvedConfig(
            values=merged,
            config_path=self.config_path,
            run_config_path=self.run_config_path,
            page_number=page_number,
            page_overrides=copy.deepcopy(page_overrides),
            cli_overrides=copy.deepcopy(self.cli_overrides),
        )

    def save_editable_run_config(
        self,
        path: str | Path,
        *,
        source_pdf: str | Path | None = None,
        output_file: str | Path | None = None,
        selected_pages: list[int] | None = None,
        last_run: dict[str, Any] | None = None,
    ) -> Path:
        """Save the current effective global configuration for the next run."""
        return save_run_config(
            path,
            self.resolve().values,
            base_yaml=self.config_path,
            run_config_input=self.run_config_path,
            source_pdf=source_pdf,
            output_file=output_file,
            selected_pages=selected_pages,
            last_run=last_run,
        )


def flatten_config(mapping: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten a nested configuration for the Excel metadata sheet."""
    rows: list[tuple[str, Any]] = []
    for key, value in mapping.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            rows.extend(flatten_config(value, path))
        else:
            rows.append((path, value))
    return rows
