from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

import cv2
import numpy as np

from models import BBox, WordBox


@dataclass(slots=True)
class OCRResult:
    text: str
    confidence: float
    words: list[WordBox]
    language: str
    engine: str


@dataclass(slots=True)
class TextDetectionResult:
    """Spatial text evidence without character recognition.

    ``boxes`` deliberately contain empty ``text`` values. They are structural
    evidence only and must never be treated as OCR-recognized content.
    """

    boxes: list[WordBox]
    engine: str
    device: str
    measurements: dict[str, Any]


class OCREngine(Protocol):
    def recognize(self, image: np.ndarray, mode: str = "block", numeric: bool = False) -> OCRResult:
        ...


class TextDetector(Protocol):
    def detect(self, image: np.ndarray) -> TextDetectionResult:
        ...


class EasyOCREngine:
    """EasyOCR adapter with reusable Reader instances and JSON parameters.

    Loading EasyOCR weights is expensive. Reader objects are therefore cached
    by language/device/model settings and reused across all pages in the run.
    Read-time thresholds remain configurable per page through the wrapper.
    """

    _reader_cache: dict[tuple[Any, ...], Any] = {}
    _cache_lock = Lock()

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import easyocr  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "EasyOCR is not installed. Activate the project environment and run "
                "'python -m pip install -r requirements.txt'."
            ) from exc

        self.easyocr = easyocr
        self.ocr_cfg = config.get("ocr", {})
        self.engine_cfg = self.ocr_cfg.get("easyocr", {})
        self.languages = [str(item) for item in self.ocr_cfg.get("languages", ["ar", "en"])]
        self.language = "+".join(self.languages)
        self.gpu = self._resolve_gpu(self.ocr_cfg.get("use_gpu", "auto"))

        model_dir = self._optional_path(self.engine_cfg.get("model_storage_directory"))
        user_network_dir = self._optional_path(self.engine_cfg.get("user_network_directory"))
        detect_network = str(self.engine_cfg.get("detect_network", "craft"))
        recog_network = str(self.engine_cfg.get("recog_network", "standard"))
        download_enabled = bool(self.engine_cfg.get("download_enabled", True))
        quantize = bool(self.engine_cfg.get("quantize", True))
        cudnn_benchmark = bool(self.engine_cfg.get("cudnn_benchmark", False))
        if bool(config.get("project", {}).get("deterministic", True)):
            # cuDNN benchmarking can select different kernels between runs;
            # deterministic project mode takes precedence over this speed flag.
            cudnn_benchmark = False
        verbose = bool(self.engine_cfg.get("verbose", True))

        cache_key = (
            tuple(self.languages),
            str(self.gpu),
            model_dir,
            user_network_dir,
            detect_network,
            recog_network,
            download_enabled,
            quantize,
            cudnn_benchmark,
        )
        with self._cache_lock:
            reader = self._reader_cache.get(cache_key)
            if reader is None:
                kwargs: dict[str, Any] = {
                    "lang_list": self.languages,
                    "gpu": self.gpu,
                    "detect_network": detect_network,
                    "recog_network": recog_network,
                    "download_enabled": download_enabled,
                    "detector": True,
                    "recognizer": True,
                    "verbose": verbose,
                    "quantize": quantize,
                    "cudnn_benchmark": cudnn_benchmark,
                }
                if model_dir:
                    kwargs["model_storage_directory"] = model_dir
                if user_network_dir:
                    kwargs["user_network_directory"] = user_network_dir
                reader = easyocr.Reader(**kwargs)
                self._reader_cache[cache_key] = reader
        self.reader = reader

    @staticmethod
    def _optional_path(value: Any) -> str | None:
        if value in (None, "", False):
            return None
        return str(Path(str(value)).expanduser())

    @staticmethod
    def _resolve_gpu(value: Any) -> bool | str:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"false", "0", "no", "off", "cpu"}:
            return False
        if text in {"cuda", "mps"}:
            return text
        if text in {"true", "1", "yes", "on", "gpu"}:
            return True
        if text != "auto":
            raise ValueError("ocr.use_gpu must be auto, true, false, cpu, cuda, or mps")
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        return False

    @staticmethod
    def _device_label(value: bool | str) -> str:
        if value is False:
            return "cpu"
        if value is True:
            return "gpu"
        return str(value)

    def recognize(self, image: np.ndarray, mode: str = "block", numeric: bool = False) -> OCRResult:
        if image is None or image.size == 0:
            return OCRResult("", 0.0, [], self.language, "easyocr")
        prepared = self._prepare_image(image)
        kwargs = self._readtext_kwargs(mode=mode, numeric=numeric)
        supported = inspect.signature(self.reader.readtext).parameters
        kwargs = {key: value for key, value in kwargs.items() if key in supported}
        raw_result = self.reader.readtext(prepared, **kwargs)

        words: list[WordBox] = []
        for item in raw_result or []:
            parsed = self._parse_item(item)
            if parsed is None:
                continue
            points, text, confidence = parsed
            if not text.strip():
                continue
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
            words.append(
                WordBox(
                    text=text.strip(),
                    bbox=BBox(min(xs), min(ys), max(xs), max(ys)),
                    confidence=max(0.0, min(1.0, float(confidence))),
                    source="easyocr",
                    language=self.language,
                )
            )

        ordered = self._assign_reading_order(words)
        confidences = [word.confidence for word in ordered]
        return OCRResult(
            text=" ".join(word.text for word in ordered).strip(),
            confidence=float(np.mean(confidences)) if confidences else 0.0,
            words=ordered,
            language=self.language,
            engine="easyocr",
        )

    @staticmethod
    def _prepare_image(image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    def _readtext_kwargs(self, mode: str, numeric: bool) -> dict[str, Any]:
        cfg = self.engine_cfg
        base: dict[str, Any] = {
            "decoder": cfg.get("decoder", "greedy"),
            "beamWidth": int(cfg.get("beam_width", 5)),
            "batch_size": int(cfg.get("batch_size", 1)),
            "workers": int(cfg.get("workers", 0)),
            "detail": 1,
            "paragraph": False,
            "min_size": int(cfg.get("min_size", 5)),
            "rotation_info": cfg.get("rotation_info"),
            "contrast_ths": float(cfg.get("contrast_ths", 0.10)),
            "adjust_contrast": float(cfg.get("adjust_contrast", 0.50)),
            "filter_ths": float(cfg.get("filter_ths", 0.003)),
            "text_threshold": float(cfg.get("text_threshold", 0.70)),
            "low_text": float(cfg.get("low_text", 0.40)),
            "link_threshold": float(cfg.get("link_threshold", 0.40)),
            "canvas_size": int(cfg.get("canvas_size", 2560)),
            "mag_ratio": float(cfg.get("mag_ratio", 1.0)),
            "slope_ths": float(cfg.get("slope_ths", 0.10)),
            "ycenter_ths": float(cfg.get("ycenter_ths", 0.50)),
            "height_ths": float(cfg.get("height_ths", 0.50)),
            "width_ths": float(cfg.get("width_ths", 0.50)),
            "add_margin": float(cfg.get("add_margin", 0.10)),
            "x_ths": float(cfg.get("x_ths", 1.0)),
            "y_ths": float(cfg.get("y_ths", 0.50)),
            "threshold": float(cfg.get("binary_threshold", 0.20)),
        }
        mode_cfg = cfg.get("modes", {}).get(str(mode), {})
        if isinstance(mode_cfg, dict):
            aliases = {
                "beam_width": "beamWidth",
                "binary_threshold": "threshold",
            }
            for key, value in mode_cfg.items():
                base[aliases.get(key, key)] = value
        if numeric:
            base["allowlist"] = str(
                self.ocr_cfg.get("numeric_columns", {}).get(
                    "allowlist", "0123456789٠١٢٣٤٥٦٧٨٩.,/:-()"
                )
            )
        else:
            blocklist = cfg.get("blocklist")
            if blocklist:
                base["blocklist"] = str(blocklist)
        return {key: value for key, value in base.items() if value is not None}

    @staticmethod
    def _parse_item(item: Any) -> tuple[list[list[float]], str, float] | None:
        if isinstance(item, dict):
            points = item.get("boxes") or item.get("bbox") or item.get("box")
            text = item.get("text", "")
            confidence = item.get("confident", item.get("confidence", 0.0))
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            points, text, confidence = item[0], item[1], item[2]
        else:
            return None
        if not isinstance(points, (list, tuple)) or len(points) < 2:
            return None
        normalized_points: list[list[float]] = []
        for point in points:
            if isinstance(point, (list, tuple, np.ndarray)) and len(point) >= 2:
                normalized_points.append([float(point[0]), float(point[1])])
        if len(normalized_points) < 2:
            return None
        return normalized_points, str(text), float(confidence)

    @classmethod
    def _assign_reading_order(cls, words: list[WordBox]) -> list[WordBox]:
        if not words:
            return []
        median_height = float(np.median([max(1.0, word.bbox.height) for word in words]))
        tolerance = max(4.0, median_height * 0.60)
        lines: list[list[WordBox]] = []
        for word in sorted(words, key=lambda item: item.bbox.center[1]):
            if not lines:
                lines.append([word])
                continue
            line_y = float(np.mean([item.bbox.center[1] for item in lines[-1]]))
            if abs(word.bbox.center[1] - line_y) <= tolerance:
                lines[-1].append(word)
            else:
                lines.append([word])

        ordered: list[WordBox] = []
        for line_number, line in enumerate(lines, start=1):
            rtl = cls._arabic_ratio(" ".join(word.text for word in line)) > 0.50
            line.sort(key=lambda item: item.bbox.x0, reverse=rtl)
            for word_number, word in enumerate(line, start=1):
                word.line_no = line_number
                word.word_no = word_number
                ordered.append(word)
        return ordered

    @staticmethod
    def _arabic_ratio(text: str) -> float:
        letters = [character for character in text if character.isalpha()]
        if not letters:
            return 0.0
        return sum("\u0600" <= character <= "\u06ff" for character in letters) / len(letters)


class EasyOCRTextDetector:
    """EasyOCR/CRAFT adapter that loads detection only, not recognition.

    Crop-only modes can use CRAFT boxes as spatial evidence without loading
    the recognition network or decoding any characters. Reader instances are
    cached so repeated pages do not reload the detector weights.
    """

    _reader_cache: dict[tuple[Any, ...], Any] = {}
    _cache_lock = Lock()

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import easyocr  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "EasyOCR is not installed. Activate the project environment and run "
                "'python -m pip install -r requirements.txt'."
            ) from exc

        self.ocr_cfg = config.get("ocr", {})
        self.base_cfg = self.ocr_cfg.get("easyocr", {})
        self.det_cfg = self.ocr_cfg.get("easyocr_detection", {})
        self.languages = [str(item) for item in self.ocr_cfg.get("languages", ["ar", "en"])]
        self.gpu = EasyOCREngine._resolve_gpu(self.ocr_cfg.get("use_gpu", "auto"))
        self.device = EasyOCREngine._device_label(self.gpu)

        model_dir = EasyOCREngine._optional_path(self.base_cfg.get("model_storage_directory"))
        user_network_dir = EasyOCREngine._optional_path(self.base_cfg.get("user_network_directory"))
        detect_network = str(self.base_cfg.get("detect_network", "craft"))
        download_enabled = bool(self.base_cfg.get("download_enabled", True))
        quantize = bool(self.base_cfg.get("quantize", True))
        cudnn_benchmark = bool(self.base_cfg.get("cudnn_benchmark", False))
        if bool(config.get("project", {}).get("deterministic", True)):
            cudnn_benchmark = False
        verbose = bool(self.det_cfg.get("verbose", False))

        cache_key = (
            tuple(self.languages), str(self.gpu), model_dir, user_network_dir,
            detect_network, download_enabled, quantize, cudnn_benchmark, verbose,
        )
        with self._cache_lock:
            reader = self._reader_cache.get(cache_key)
            if reader is None:
                kwargs: dict[str, Any] = {
                    "lang_list": self.languages,
                    "gpu": self.gpu,
                    "detect_network": detect_network,
                    "download_enabled": download_enabled,
                    "detector": True,
                    "recognizer": False,
                    "verbose": verbose,
                    "quantize": quantize,
                    "cudnn_benchmark": cudnn_benchmark,
                }
                if model_dir:
                    kwargs["model_storage_directory"] = model_dir
                if user_network_dir:
                    kwargs["user_network_directory"] = user_network_dir
                reader = easyocr.Reader(**kwargs)
                self._reader_cache[cache_key] = reader
        self.reader = reader

    def detect(self, image: np.ndarray) -> TextDetectionResult:
        if image is None or image.size == 0:
            return TextDetectionResult([], "easyocr_detection", self.device, {"box_count": 0})

        prepared = EasyOCREngine._prepare_image(image)
        cfg = self.det_cfg
        kwargs: dict[str, Any] = {
            "min_size": int(cfg.get("min_size", self.base_cfg.get("min_size", 5))),
            "text_threshold": float(cfg.get("text_threshold", self.base_cfg.get("text_threshold", 0.70))),
            "low_text": float(cfg.get("low_text", self.base_cfg.get("low_text", 0.40))),
            "link_threshold": float(cfg.get("link_threshold", self.base_cfg.get("link_threshold", 0.40))),
            "canvas_size": int(cfg.get("canvas_size", self.base_cfg.get("canvas_size", 2560))),
            "mag_ratio": float(cfg.get("mag_ratio", self.base_cfg.get("mag_ratio", 1.0))),
            "slope_ths": float(cfg.get("slope_ths", self.base_cfg.get("slope_ths", 0.10))),
            "ycenter_ths": float(cfg.get("ycenter_ths", self.base_cfg.get("ycenter_ths", 0.50))),
            "height_ths": float(cfg.get("height_ths", self.base_cfg.get("height_ths", 0.50))),
            "width_ths": float(cfg.get("width_ths", self.base_cfg.get("width_ths", 0.50))),
            "add_margin": float(cfg.get("add_margin", self.base_cfg.get("add_margin", 0.10))),
            "threshold": float(cfg.get("binary_threshold", self.base_cfg.get("binary_threshold", 0.20))),
            "bbox_min_score": float(cfg.get("bbox_min_score", 0.20)),
            "bbox_min_size": int(cfg.get("bbox_min_size", 3)),
            "max_candidates": int(cfg.get("max_candidates", 0)),
        }
        supported = inspect.signature(self.reader.detect).parameters
        kwargs = {key: value for key, value in kwargs.items() if key in supported}
        raw_result = self.reader.detect(prepared, **kwargs)
        horizontal, free = self._split_detect_result(raw_result)

        confidence = float(cfg.get("structural_box_confidence", 0.60))
        boxes: list[WordBox] = []
        for item in self._single_image_items(horizontal, kind="horizontal"):
            bbox = self._horizontal_bbox(item)
            if bbox is not None:
                boxes.append(WordBox("", bbox, confidence, "easyocr_detection"))
        for item in self._single_image_items(free, kind="free"):
            bbox = self._polygon_bbox(item)
            if bbox is not None:
                boxes.append(WordBox("", bbox, confidence, "easyocr_detection"))

        boxes = self._deduplicate_boxes(boxes)
        return TextDetectionResult(
            boxes=boxes, engine="easyocr_detection", device=self.device,
            measurements={
                "box_count": len(boxes),
                "device": self.device,
                "recognizer_loaded": False,
            },
        )

    @staticmethod
    def _split_detect_result(raw_result: Any) -> tuple[Any, Any]:
        if isinstance(raw_result, tuple) and len(raw_result) >= 2:
            return raw_result[0], raw_result[1]
        if isinstance(raw_result, list) and len(raw_result) == 2:
            return raw_result[0], raw_result[1]
        return raw_result or [], []

    @staticmethod
    def _single_image_items(value: Any, *, kind: str) -> list[Any]:
        if not isinstance(value, (list, tuple)):
            return []
        items = list(value)
        if not items:
            return []

        def is_horizontal_box(item: Any) -> bool:
            return (
                isinstance(item, (list, tuple, np.ndarray)) and len(item) >= 4
                and all(np.isscalar(v) for v in list(item)[:4])
            )

        def is_polygon(item: Any) -> bool:
            return (
                isinstance(item, (list, tuple, np.ndarray)) and len(item) >= 2
                and isinstance(item[0], (list, tuple, np.ndarray))
                and len(item[0]) >= 2
                and all(np.isscalar(v) for v in list(item[0])[:2])
            )

        predicate = is_horizontal_box if kind == "horizontal" else is_polygon
        if predicate(items[0]):
            return items
        if isinstance(items[0], (list, tuple)):
            first_batch = list(items[0])
            if not first_batch or predicate(first_batch[0]):
                return first_batch
        return []

    @staticmethod
    def _horizontal_bbox(item: Any) -> BBox | None:
        if not isinstance(item, (list, tuple, np.ndarray)) or len(item) < 4:
            return None
        try:
            x0, x1, y0, y1 = (float(item[index]) for index in range(4))
        except (TypeError, ValueError):
            return None
        if x1 <= x0 or y1 <= y0:
            return None
        return BBox(x0, y0, x1, y1)

    @staticmethod
    def _polygon_bbox(item: Any) -> BBox | None:
        if not isinstance(item, (list, tuple, np.ndarray)):
            return None
        points: list[tuple[float, float]] = []
        for point in item:
            if isinstance(point, (list, tuple, np.ndarray)) and len(point) >= 2:
                try:
                    points.append((float(point[0]), float(point[1])))
                except (TypeError, ValueError):
                    continue
        if len(points) < 2:
            return None
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        if max(xs) <= min(xs) or max(ys) <= min(ys):
            return None
        return BBox(min(xs), min(ys), max(xs), max(ys))

    @staticmethod
    def _deduplicate_boxes(boxes: list[WordBox]) -> list[WordBox]:
        result: list[WordBox] = []
        for box in sorted(boxes, key=lambda item: (item.bbox.y0, item.bbox.x0)):
            duplicate = any(
                box.bbox.intersection_ratio(existing.bbox, denominator="self") >= 0.90
                and box.bbox.intersection_ratio(existing.bbox, denominator="other") >= 0.90
                for existing in result
            )
            if not duplicate:
                result.append(box)
        return result


def create_text_detector(config: dict[str, Any]) -> TextDetector:
    """Create a detection-only text-box engine; character recognition stays off."""
    engine = str(
        config.get("visual_structure", {})
        .get("text_detection_fallback", {})
        .get("engine", "easyocr")
    ).strip().lower()
    if engine == "easyocr":
        return EasyOCRTextDetector(config)
    raise ValueError("visual_structure.text_detection_fallback.engine must be 'easyocr'")


class PaddleOCREngine:
    """Optional secondary adapter retained for experimentation."""

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PaddleOCR is not installed.") from exc
        pcfg = config.get("ocr", {}).get("paddleocr", {})
        self._ocr = PaddleOCR(
            use_angle_cls=bool(pcfg.get("use_angle_classifier", True)),
            lang=pcfg.get("lang", "arabic"),
            det_db_thresh=float(pcfg.get("det_db_thresh", 0.30)),
            det_db_box_thresh=float(pcfg.get("det_db_box_thresh", 0.50)),
            det_db_unclip_ratio=float(pcfg.get("det_db_unclip_ratio", 1.5)),
            use_gpu=bool(config.get("ocr", {}).get("use_gpu", False)),
        )

    def recognize(self, image: np.ndarray, mode: str = "block", numeric: bool = False) -> OCRResult:
        result = self._ocr.ocr(image, cls=True)
        words: list[WordBox] = []
        for page in result or []:
            for line in page or []:
                points, (text, confidence) = line
                xs = [point[0] for point in points]
                ys = [point[1] for point in points]
                words.append(
                    WordBox(
                        text,
                        BBox(min(xs), min(ys), max(xs), max(ys)),
                        float(confidence),
                        "paddleocr",
                    )
                )
        confidence = float(np.mean([word.confidence for word in words])) if words else 0.0
        return OCRResult(" ".join(word.text for word in words), confidence, words, "ar+en", "paddleocr")


def create_ocr_engine(config: dict[str, Any]) -> OCREngine:
    engine = str(config.get("ocr", {}).get("engine", "easyocr")).strip().lower()
    if engine == "easyocr":
        return EasyOCREngine(config)
    if engine == "paddleocr":
        try:
            return PaddleOCREngine(config)
        except RuntimeError:
            if bool(config.get("ocr", {}).get("fallback_to_easyocr", True)):
                return EasyOCREngine(config)
            raise
    raise ValueError("ocr.engine must be 'easyocr' or 'paddleocr'")
