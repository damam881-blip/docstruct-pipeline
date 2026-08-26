from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass(slots=True)
class PreprocessResult:
    original: np.ndarray
    selected: np.ndarray
    variants: dict[str, np.ndarray] = field(default_factory=dict)
    deskew_angle: float = 0.0
    selected_name: str = "original"
    measurements: dict[str, Any] = field(default_factory=dict)


class ImagePreprocessor:
    def __init__(self, config: dict) -> None:
        self.config = config.get("preprocessing", {})

    def process(self, image: np.ndarray, debug_dir: str | Path | None = None) -> PreprocessResult:
        variants: dict[str, np.ndarray] = {"01_original": image.copy()}
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        variants["02_grayscale"] = gray

        current = gray
        contrast_cfg = self.config.get("contrast", {})
        if contrast_cfg.get("enabled", True):
            method = contrast_cfg.get("method", "clahe")
            if method == "clahe":
                tile = tuple(int(v) for v in contrast_cfg.get("tile_grid_size", [8, 8]))
                clahe = cv2.createCLAHE(clipLimit=float(contrast_cfg.get("clip_limit", 2.0)), tileGridSize=tile)
                current = clahe.apply(current)
            else:
                current = cv2.normalize(current, None, 0, 255, cv2.NORM_MINMAX)
            variants["03_contrast"] = current

        shadow_cfg = self.config.get("shadow_removal", {})
        if shadow_cfg.get("enabled", False):
            kernel = int(shadow_cfg.get("kernel_size", 31))
            kernel = kernel + 1 if kernel % 2 == 0 else kernel
            background = cv2.medianBlur(current, kernel)
            current = cv2.divide(current, background, scale=255)
            variants["04_shadow_removed"] = current

        denoise_cfg = self.config.get("denoise", {})
        if denoise_cfg.get("enabled", True):
            k = int(denoise_cfg.get("kernel_size", 3))
            k = max(1, k + 1 if k % 2 == 0 else k)
            method = denoise_cfg.get("method", "median")
            if method == "gaussian":
                current = cv2.GaussianBlur(current, (k, k), 0)
            elif method == "bilateral":
                current = cv2.bilateralFilter(current, k, 50, 50)
            else:
                current = cv2.medianBlur(current, k)
            variants["05_denoised"] = current

        sharpening_cfg = self.config.get("sharpening", {})
        if sharpening_cfg.get("enabled", False):
            amount = float(sharpening_cfg.get("amount", 1.0))
            radius = max(0.1, float(sharpening_cfg.get("radius", 1.0)))
            blurred = cv2.GaussianBlur(current, (0, 0), radius)
            current = cv2.addWeighted(current, 1.0 + amount, blurred, -amount, 0)
            variants["05b_sharpened"] = current

        threshold_cfg = self.config.get("threshold", {})
        thresholded = current
        if threshold_cfg.get("enabled", True):
            method = threshold_cfg.get("method", "adaptive_gaussian")
            invert = bool(threshold_cfg.get("invert", True))
            out_type = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
            if method == "otsu":
                _, thresholded = cv2.threshold(current, 0, 255, out_type | cv2.THRESH_OTSU)
            elif method == "global":
                _, thresholded = cv2.threshold(current, int(threshold_cfg.get("value", 180)), 255, out_type)
            else:
                block = int(threshold_cfg.get("block_size", 31))
                block = max(3, block + 1 if block % 2 == 0 else block)
                adaptive_method = cv2.ADAPTIVE_THRESH_GAUSSIAN_C if method == "adaptive_gaussian" else cv2.ADAPTIVE_THRESH_MEAN_C
                thresholded = cv2.adaptiveThreshold(
                    current,
                    255,
                    adaptive_method,
                    out_type,
                    block,
                    float(threshold_cfg.get("c", 12)),
                )
            variants["06_threshold"] = thresholded

        morph_cfg = self.config.get("morphology", {})
        processed = thresholded
        opening = tuple(int(v) for v in morph_cfg.get("opening_kernel", [1, 1]))
        closing = tuple(int(v) for v in morph_cfg.get("closing_kernel", [2, 2]))
        if opening != (1, 1):
            processed = cv2.morphologyEx(processed, cv2.MORPH_OPEN, np.ones(opening, np.uint8))
        if closing != (1, 1):
            processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, np.ones(closing, np.uint8))
        dilation = tuple(int(v) for v in morph_cfg.get("dilation_kernel", [1, 1]))
        erosion = tuple(int(v) for v in morph_cfg.get("erosion_kernel", [1, 1]))
        if dilation != (1, 1):
            processed = cv2.dilate(processed, np.ones(dilation, np.uint8), iterations=1)
        if erosion != (1, 1):
            processed = cv2.erode(processed, np.ones(erosion, np.uint8), iterations=1)
        variants["07_morphology"] = processed

        deskew_angle = 0.0
        deskew_cfg = self.config.get("deskew", {})
        deskewed = processed
        if deskew_cfg.get("enabled", True):
            deskew_angle = self._estimate_skew(processed)
            max_angle = float(deskew_cfg.get("maximum_angle", 10.0))
            min_angle = float(deskew_cfg.get("minimum_detected_angle", 0.15))
            if min_angle <= abs(deskew_angle) <= max_angle:
                deskewed = self._rotate(processed, deskew_angle)
                current = self._rotate(current, deskew_angle)
            else:
                deskew_angle = 0.0
            variants["08_deskewed"] = deskewed
            variants["08_deskewed_gray"] = current

        selected_name = self._choose_variant(variants)
        selected = variants[selected_name]
        measurements = {
            "mean": float(np.mean(selected)),
            "std": float(np.std(selected)),
            "foreground_ratio": float(np.mean(selected > 0)) if selected_name != "08_deskewed_gray" else float(np.mean(selected < 200)),
            "sharpness": float(cv2.Laplacian(current, cv2.CV_64F).var()),
        }
        if debug_dir:
            self._save_variants(variants, Path(debug_dir))
        return PreprocessResult(image, selected, variants, deskew_angle, selected_name, measurements)

    def _choose_variant(self, variants: dict[str, np.ndarray]) -> str:
        requested = self.config.get("selected_variant", "auto")
        if requested != "auto" and requested in variants:
            return requested
        threshold = variants.get("08_deskewed", variants.get("07_morphology", variants.get("06_threshold")))
        if threshold is not None:
            ratio = float(np.mean(threshold > 0))
            if 0.01 <= ratio <= 0.45:
                return "08_deskewed" if "08_deskewed" in variants else "07_morphology"
        return "08_deskewed_gray" if "08_deskewed_gray" in variants else "02_grayscale"

    @staticmethod
    def _estimate_skew(binary: np.ndarray) -> float:
        points = np.column_stack(np.where(binary > 0))
        if len(points) < 100:
            return 0.0
        angle = cv2.minAreaRect(points[:, ::-1].astype(np.float32))[-1]
        if angle < -45:
            angle = 90 + angle
        return -float(angle)

    @staticmethod
    def _rotate(image: np.ndarray, angle: float) -> np.ndarray:
        h, w = image.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
        border = 255 if image.ndim == 2 and np.mean(image) > 127 else 0
        return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=border)

    @staticmethod
    def _save_variants(variants: dict[str, np.ndarray], directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for name, variant in variants.items():
            cv2.imwrite(str(directory / f"{name}.png"), variant)
