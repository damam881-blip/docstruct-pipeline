from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        for key in (
            "stage",
            "file_name",
            "page_number",
            "page_type",
            "layout_type",
            "strategy",
            "recommended_strategy",
            "executed_strategy",
            "processing_mode",
            "output_mode",
            "ocr_enabled",
            "ocr_recognition_enabled",
            "text_detection_fallback_enabled",
            "text_detection_used",
            "text_detection_boxes",
            "text_detection_device",
            "engine",
            "device",
            "recognizer_loaded",
            "boxes_detected",
            "structure_method",
            "structure_confidence",
            "structure_detected",
            "page_status",
            "rows_detected",
            "columns_detected",
            "ocr_confidence",
            "duration_seconds",
            "fallback",
            "excel_enabled",
            "save_rows",
            "save_cells",
            "config_path",
            "run_config_path",
            "warning",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("pdf_pipeline")
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(event, extra=fields)
