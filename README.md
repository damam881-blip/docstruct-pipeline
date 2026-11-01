# DocStruct Pipeline — Validated Baseline

**Multi-Strategy Document Structure Analysis & Data Reconstruction Pipeline**

A general-purpose, configurable system for analyzing document layouts, recognizing table structures, extracting text and data, reconstructing structured records, and validating results from digital, scanned, and hybrid PDF files. It uses PyMuPDF, OpenCV, and EasyOCR, with configuration through YAML and JSON.

> **Validated baseline date:** 2026-08-18  
> **Current project metadata:** `3.2.0-text-detection`  
> **Regression status:** `51 passed, 5 skipped, 2 warnings, 0 failed`

For full documentation, usage, error interpretation, and parameter tuning, use:

```text
README_DEVELOPER_HANDOFF.md
```

## 1. Core Idea

The pipeline is not built for any specific bank, company, or template. There are no conditions that depend on a file name, an organization name, or a fixed number of columns.

General flow:

```text
PDF
 ↓
Page Analysis / Classification
 ↓
Preprocessing
 ↓
Generate multiple structure candidates
 ↓
Evidence-based Structure Candidate Selection
 ↓
Rows / Columns / Cells
 ↓
OCR / Native Text
 ↓
Reconstruction
 ↓
Validation
 ↓
Excel + JSON + crops + debug artifacts
```

## 2. Latest Approved Baseline

Three general issues that surfaced during real E2E runs were fixed:

### A. Structure Candidate Selection

`borderless_spatial` could win simply because it split a multi-line transaction into many physical OCR rows. This logic was replaced with a generic evaluation based on:

```text
sub-linear row evidence
confidence
vertical compactness
cell/text occupancy
column consistency
```

The final decision is now auditable inside:

```text
page_report.json → structure_candidates
```

### B. Geometry Validation

Fixed the `MAD = 0` case, which could produce nonsensical z-scores. The current check uses:

```text
minimum sample count
MAD
→ IQR fallback
→ standard deviation fallback
→ skip when no measurable spread exists
```

### C. Total-row Classification

The word `Total` appearing inside a long description such as:

```text
Total POS Purchase for MADA Net
Fees for Total POS Purchase
```

no longer makes the transaction `is_total=true`. Summary phrases such as `Grand Total`, `Subtotal`, `الإجمالي`, `المجموع`, and a short label-like `Total` can still be classified as Total.

## 3. Latest E2E Regression

The following was run:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\Account_Statement_scanned.pdf" `
  --output ".\outputs\Account_Statement_scanned_baseline.xlsx" `
  --pages 1-3 `
  --debug `
  --debug-root ".\outputs\debug_baseline"
```

Result:

| Page | Selected structure | Rows | Columns | Structure confidence | OCR confidence | Status |
|---:|---|---:|---:|---:|---:|---|
| 1 | `opencv_shaded_grid` | 4 | 7 | 0.75 | 0.8303 | `completed` |
| 2 | `opencv_shaded_grid` | 6 | 7 | 1.00 | 0.8880 | `completed` |
| 3 | `opencv_shaded_grid` | 5 | 7 | 0.9143 | 0.9035 | `completed` |

```text
pages_successful              = 3
pages_failed                  = 0
pages_completed_with_warnings = 0
row_crops                     = 13
cell_crops                    = 91
```

## 4. Config Workflow

### Before the first run on a new file

Do not modify the baseline just because the file looks similar to a previous one.

Use:

```text
configs/default.yaml
```

as-is.

### After the first run

The following file is created:

```text
<output_stem>.run_config.json
```

If the adjustment is specific to this PDF, edit the values inside `config` in this JSON, then use:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --run-config ".\outputs\FILE.run_config.json" `
  --input ".\samples\FILE.pdf" `
  --output ".\outputs\FILE_second.xlsx"
```

The technical precedence is still:

```text
CLI --override
→ page_overrides
→ JSON --run-config
→ base YAML
```

However, the project's standard workflow **does not use `--override`**.

## 5. First Test for Any New PDF

Start with the current baseline, without tuning:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\NEW_FILE.pdf" `
  --output ".\outputs\NEW_FILE_first_run.xlsx" `
  --pages 1 `
  --debug `
  --debug-root ".\outputs\debug_NEW_FILE"
```

Review these first:

```text
page_type
layout_type
recommended_strategy
executed_strategy
structure_method
structure_confidence
rows_detected
columns_detected
ocr_confidence
page_status
fallback_chain
structure_candidates
```

Then review the images in this order:

```text
01_original.png
07b_visual_detected_regions.png
08_detected_rows.png
09_detected_columns.png
10_detected_cells.png
12_validation_overlay.png
```

**Geometry before recognition:** Do not tune OCR to improve text that came from a wrong crop or wrong cell geometry.

## 6. Recommendation vs. Actual Execution

```text
recommended_strategy
```

is the classifier's recommendation based on the page's appearance, such as `cell_ocr` or `row_ocr`.

```text
structure_method
```

is the method that actually won in building the rows/columns/cells, for example:

```text
bordered_grid
opencv_shaded_grid
opencv_projection_grid
native_digital_spatial
borderless_spatial
anchor_row_segmentation
easyocr_detection_spatial
```

Do not assume that `bordered_table` must always force `bordered_grid`. The best evidence wins.

## 7. Output Modes

| mode | Output |
|---|---|
| `full` | Excel + row/cell crops + manifests |
| `data_only` | Excel/data outputs only |
| `cropped_cells_only` | Cell crops only |
| `cropped_rows_only` | Row crops only |
| `cropped_rows_and_cells` | Rows + cells, without Excel |
| `training_dataset` | Crops + training labels |
| `custom` | Manual control over outputs |

In crop-only modes, character recognition does not run. If the native/OpenCV geometry fails, EasyOCR/CRAFT detection-only can be used as a fallback (`recognizer=false`) to obtain text boxes only.

## 8. Tests

Before any code change and after any generic fix:

```powershell
python -m pytest -ra
```

Latest approved result:

```text
51 passed
5 skipped
2 warnings
0 failed
```

The 5 skips are because `PDF_TEST_FILE_1..5` are not defined. The 2 warnings are EasyOCR/PyTorch quantization deprecation warnings, not extraction failures.

## 9. Decision Rule When a Problem Appears

```text
A general problem that breaks an invariant and appears across different file types
→ Generic code fix + regression test

The architecture is correct, but a specific PDF needs a different tolerance
→ PDF-specific *.run_config.json

A value proven to be better for all future files after diverse testing
→ consider configs/default.yaml
```

Do not add bank-, company-, or file-name-specific conditions to the core pipeline.

## 10. Source-of-Truth Files

```text
configs/default.yaml                         active global baseline
configs/default_v3.2.0.reference.yaml        reference snapshot only
*.run_config.json                            PDF-specific tuning after first run
pipeline/pipeline.py                         candidate arbitration + orchestration
pipeline/validator.py                        validation
pipeline/data_reconstructor.py               reconstruction/header/total logic
docs/parameter_catalog.yaml                  inspect-config parameter documentation
README_DEVELOPER_HANDOFF.md                  complete handoff/troubleshooting source
```

Backup files from the latest fixes can be kept temporarily while testing new PDFs, but they are not the actual runtime files.

## 11. Known Limitations

The current baseline is a strong generic foundation, but that does not mean every PDF in the world will work without errors. Limitations remain, such as:

- cross-page logical table continuation is not fully implemented;
- arbitrary/nested multi-table layouts are not fully solved;
- there is no general rowspan/colspan model;
- there is no explicit confirmed-blank vs. OCR-failure state;
- total/header classification is still heuristic despite the latest fixes;
- candidate scoring is generic but heuristic, and must be tested on different PDF families.

The goal is to make any new failure **diagnosable** from the logs, debug output, and candidate evidence, then fix it generically or tune it through a run-config, instead of turning the project into a collection of special-purpose templates.
