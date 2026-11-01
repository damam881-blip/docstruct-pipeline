# EasyOCR + Editable JSON Output Edition Manifest

This edition contains a single generic core and a single default configuration, with no profiles tied to a bank, company, or file name.

## Included

- `configs/default.yaml` with EasyOCR as the default engine.
- Commands: `analyze`, `diagnose`, `extract`, `tune`, `inspect-config`.
- Run Config JSON cycle: the first run creates a JSON file, and the next run accepts it via `--run-config`.
- Configuration precedence: CLI, then page overrides, then JSON, then YAML.
- Output modes: Excel, Cropped cells, Cropped rows, Training dataset, Custom.
- `crop_manifest.csv`, `crop_manifest.json`, and `output_summary.json`.
- Tools for preparing Recognition Model training data and installing a custom EasyOCR model.
- Page-level analysis, digital extraction, and OCR.
- Bordered and borderless detection, and anchor segmentation.
- Reconstruction, validation, Excel export, and debug overlays.
- Unit tests and E2E tests.

## Intentionally Not Included

- The `profiles/` folder.
- `file_*_profile.yaml` files.
- `--profile` or `recommend-profile`.
- Any condition that depends on a bank name, company name, or file name.
- Automatic training on uncorrected OCR text.
- Any runtime dependency on Tesseract or `pytesseract`.

## Configuration Precedence

```text
CLI --override
→ page_overrides
→ JSON --run-config
→ configs/default.yaml
```


## 3.0.1 Fixes

- The default `output.mode` is now `full`, so actual runs match the README and the E2E test that checks for the Excel file.
- `digital_text.fallback_to_ocr_when_garbled` is now an actual operational parameter.
- `output.training_dataset.label_source` now supports `ocr_draft`, `normalized`, and `blank`.
- `project.deterministic` and `project.random_seed` are now runtime controls on a best-effort basis.

## 3.1.0 Additions

- `pipeline/visual_structure_detector.py`: generic structure detection without OCR for shaded cells and borderless tables based on text-ink geometry.
- Crop-only for digital/hybrid pages uses native PyMuPDF word coordinates without OCR.
- New `run_configuration` startup log showing the effective mode and OCR/Excel state before pages are processed.
- New `NO_STRUCTURE_DETECTED` warning when no croppable structure is found.
- `tools/upgrade_v310_config.py` adds the new parameters to an existing YAML without changing `output.mode`.
- New regression tests for the shaded / borderless / digital geometry-only paths.

## 3.2.0 Additions

- `pipeline/ocr_engine.py` contains a detection-only EasyOCR/CRAFT adapter (`recognizer=false`).
- Crop-only uses text detection as a fallback only after native/OpenCV structure detection fails.
- `07c_text_detection_boxes.png` shows the detector's bounding boxes.
- `tools/upgrade_v320_config.py` adds the new settings while preserving existing values.
- Crop manifests continue to distinguish detection-only cells as geometry, not OCR recognition.
