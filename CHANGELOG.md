# Changelog

## 3.2.0 — Detection-Only Text-Box Structure Fallback

- Added `EasyOCRTextDetector`, which initializes EasyOCR with `detector=true` and `recognizer=false`.
- Crop-only modes now keep character recognition disabled but may lazily use CRAFT bounding boxes when native/OpenCV geometry finds no usable structure.
- Detection-only boxes are clustered positionally into rows, columns, and cells; generated cell values remain blank and are recorded as geometry, not OCR text.
- Added `07c_text_detection_boxes.png` debug overlay when the fallback is used.
- Added explicit logging fields for OCR recognition vs. detection-only fallback, including detector device and box count.
- Added `visual_structure.text_detection_fallback.*` and `ocr.easyocr_detection.*` configuration controls.
- Added `tools/upgrade_v320_config.py`, cumulative from v3.0.x/v3.1.x, preserving the user's existing `output.mode` and tuning values.
- Added regression tests proving detection-only Reader initialization does not load the recognizer, crop-only can recover cells from text boxes, and full mode still builds cells from recognized positional WordBoxes.

## 3.1.0 — Generic Visual Structure Detection

- Added `VisualStructureDetector` for true no-OCR row/cell detection in crop-only modes.
- Added repeated shaded/filled-cell geometry detection for tables whose separators are light/white rather than dark ruled lines.
- Added borderless scanned-table fallback using text-ink projection and repeated X/Y alignment without recognition.
- Crop-only digital/hybrid pages now reuse native PyMuPDF word coordinates as geometry evidence without EasyOCR.
- Added candidate scoring across ruled-grid, native/spatial, and visual geometry instead of tying behavior to file/template identity.
- Added DPI-aware borderless X-clustering based on measured word height with a page-width safety cap.
- Added startup `run_configuration` logging that exposes the effective output mode, processing mode, OCR state, Excel state, YAML path, and JSON path before processing starts.
- Added `recommended_strategy` vs `executed_strategy` logging so crop-only geometry runs are not mislabeled as executed OCR.
- Added `NO_STRUCTURE_DETECTED` warning and `page_status=completed_with_warning` for crop-only pages that complete without usable row/cell geometry.
- Added structure-aware output summary fields: `pages_with_structure` and `pages_without_rows`.
- Crop manifests now separate OCR confidence from geometry confidence.
- Added `tools/upgrade_v310_config.py` to merge the new generic visual-structure settings into an existing YAML without changing `output.mode` or other operational tuning values.
- Added automated shaded-grid, scanned-borderless, scanned crop-only E2E, digital native-geometry, and config-upgrade regression coverage.
- Updated generic/E2E tests so intentionally changing `output.mode` in `default.yaml` does not create a false test failure; Excel is asserted only when the resolved output plan enables it.

## 3.0.1 — Audit Consistency Fixes

- Changed the generic default `output.mode` to `full` so the documented first run and E2E Excel expectation match runtime behavior.
- Made `digital_text.fallback_to_ocr_when_garbled` an actual runtime parameter and added it to the default configuration.
- Made `output.training_dataset.label_source` operational with `ocr_draft`, `normalized`, and `blank` modes.
- Made `project.deterministic` and `project.random_seed` operational as best-effort Python/NumPy/PyTorch reproducibility controls.
- Deterministic mode now forces EasyOCR `cudnn_benchmark=false`.
- Added regression tests covering the corrected behavior.

## 3.0.0 — EasyOCR + JSON Output Control

- Replaced the runtime Tesseract adapter with EasyOCR as the default OCR engine.
- Added reusable EasyOCR Reader caching across pages.
- Added CPU/GPU selection and custom recognition-network paths in configuration.
- Preserved editable `*.run_config.json` workflow and added Run Config version 2 metadata.
- Added `output.mode` presets, including `cropped_cells_only` and `training_dataset`.
- Added row/cell crop manifests and output summaries.
- Added training-label generation with separate draft and corrected label columns.
- Added dataset split helper and custom-model installer helper.
- Improved logical row/cell bounding boxes so exported crops cover full bands.
- Removed `pytesseract` from runtime requirements.
