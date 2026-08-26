# Audit Fixes — v3.0.1

This maintenance release reconciles the concrete inconsistencies found during the source audit without introducing PDF-, bank-, company-, or filename-specific behavior.

## Fixed

1. Default output contract
   - `configs/default.yaml` now uses `output.mode: full`.
   - The documented first run, runtime output plan, and environment-driven E2E Excel expectation now agree.

2. Garbled digital-text fallback
   - Added `digital_text.fallback_to_ocr_when_garbled: true` to the default config.
   - `PageClassifier` now consumes it.
   - When digital text quality is below `digital_text.quality_min`, `true` routes to OCR; `false` deliberately keeps digital extraction.
   - `ParameterAdvisor` suggests enabling it only when it is currently disabled.

3. Training label source
   - `output.training_dataset.label_source` is now operational.
   - Supported values: `ocr_draft`, `normalized`, `blank`.
   - `blank` preserves OCR-empty cell crops for human labeling/recovery.

4. Determinism controls
   - `project.deterministic` and `project.random_seed` now seed Python, NumPy, and PyTorch when available.
   - Deterministic mode disables cuDNN benchmarking and requests deterministic PyTorch algorithms on a best-effort basis.
   - This improves reproducibility but is not a bit-for-bit guarantee across hardware/library versions.

5. Documentation/version consistency
   - Version updated to 3.0.1.
   - README, manifest, parameter catalog, training docs, JSON workflow, parameter mastery guide, changelog, and developer handoff guide were updated.

## Verification performed

- `pytest`: 40 tests collected; 35 passed; 5 skipped because `PDF_TEST_FILE_1..5` were not configured.
- `main.py analyze` succeeded on `samples/Account_Statement_scanned.pdf`, page 1.
- Crop-only smoke extraction succeeded without initializing OCR.
- `inspect-config` confirmed:
  - `output.mode = full`
  - `digital_text.fallback_to_ocr_when_garbled = true`
  - `output.training_dataset.label_source = ocr_draft`

## Environment limitation of this review container

The review container did not have EasyOCR installed, so a full OCR extraction was not executed here. This does not indicate a project defect. The real workspace should run the documented `.venv`/model health checks before the release gate.
