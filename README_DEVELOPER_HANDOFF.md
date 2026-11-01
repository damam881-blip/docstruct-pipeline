# Universal PDF Extraction Pipeline — Developer Handoff, Validated Baseline & Troubleshooting Guide

## Table of Contents

<p>Contents: Use the following links to navigate directly to the relevant section of this guide.</p>

- [0. Source-of-truth and current audit status](#toc-0-source-of-truth)
- [1. First opening in VS Code — exact onboarding sequence](#toc-1-onboarding)
  - [1.1 Open the correct folder](#toc-1-1-open-folder)
  - [1.2 Verify the VS Code Python interpreter](#toc-1-2-python-interpreter)
  - [1.3 Preflight the existing `.venv`](#toc-1-3-venv)
  - [1.4 Preflight the EasyOCR model directories](#toc-1-4-easyocr-models)
  - [1.5 Run the unit test suite](#toc-1-5-tests)
  - [1.6 Run a no-OCR analysis smoke test](#toc-1-6-no-ocr-smoke)
  - [1.7 Run an OCR smoke test](#toc-1-7-ocr-smoke)
- [2. The normal workflow for every new PDF](#toc-2-new-pdf-workflow)
  - [2.1 Config files: active YAML, reference YAML, backup, and generated JSON](#toc-2-config-inputs)
  - [Step A — Analyze representative pages](#toc-2-step-a)
  - [Step B — Ask the built-in advisor](#toc-2-step-b)
  - [Step C — Extract one representative page with debug artifacts](#toc-2-step-c)
  - [Step D — Inspect geometry before OCR text](#toc-2-step-d)
  - [Step E — Edit one parameter in the generated JSON](#toc-2-step-e)
  - [Step F — Re-run using YAML + JSON](#toc-2-step-f)
  - [Step G — Use `tune`](#toc-2-step-g)
  - [Step H — Scale to the whole PDF](#toc-2-step-h)
- [3. What each pipeline stage is responsible for](#toc-3-stage-responsibilities)
  - [3.1 Crop-only visual structure path](#toc-3-1-crop-only-visual-structure)
  - [3.2 What `digital_text`, `cell_ocr`, `row_ocr`, and the other strategies mean](#toc-3-2-strategies)
- [4. Complete error catalog](#toc-4-error-catalog)
  - [4.1 Error catalog index](#toc-4-1-error-index)
  - [4.1.1 Parameter tuning protocol used by every error card](#toc-4-1-1-parameter-tuning-protocol)
  - [4.1.2 `structure_method` → parameter family map](#toc-4-1-2-structure-method-map)
  - [4.1.2B Where exactly do I edit a parameter?](#toc-4-1-2b-where-to-edit-parameters)
  - [4.1.3 Simple explanation of each `structure_method`](#toc-4-1-3-structure-method-explained)
  - [4.2 Column Detection Errors](#toc-4-2-column-errors)
  - [4.3 Row Detection Errors](#toc-4-3-row-errors)
  - [4.4 Cell Detection Errors](#toc-4-4-cell-errors)
  - [4.5 Table Boundary Detection Errors](#toc-4-5-table-boundary-errors)
- [5. Stage-by-stage debugging rules](#toc-5-debugging-rules)
  - [5.1 Column detection](#toc-5-1-column-debug)
  - [5.2 Row detection](#toc-5-2-row-debug)
  - [5.3 Cell detection](#toc-5-3-cell-debug)
  - [5.4 Table boundaries](#toc-5-4-table-debug)
- [6. Fix-it code library](#toc-6-fix-library)
  - [Fix 1 — Separate multiple borderless tables](#toc-6-fix-1)
  - [Fix 2 — Link multi-page table continuations](#toc-6-fix-2)
  - [Fix 3 — Filter footer/summary rows](#toc-6-fix-3)
  - [Fix 4 — Distinguish confirmed blank from OCR failure](#toc-6-fix-4)
  - [Fix 5 — Detect merged bordered cells / spans](#toc-6-fix-5)
  - [Fix 6 — Per-cell orientation handling](#toc-6-fix-6)
  - [Fix 7 — Add bordered-table content ROI](#toc-6-fix-7)
  - [Fix 8 — Explicit header-body mapping](#toc-6-fix-8)
  - [Fix 9 — Page-template grouping](#toc-6-fix-9)
- [7. End-to-end troubleshooting decision flow](#toc-7-troubleshooting-flow)
- [8. Validation issue codes and what they mean](#toc-8-validation-codes)
- [9. CLI command reference](#toc-9-cli)
  - [`analyze`](#toc-9-analyze)
  - [`diagnose`](#toc-9-diagnose)
  - [`extract`](#toc-9-extract)
  - [`inspect-config`](#toc-9-inspect-config)
  - [`tune`](#toc-9-tune)
- [10. Output modes](#toc-10-output-modes)
- [11. Parameter reference](#toc-11-parameter-reference)
  - [Runtime-supported keys not present in default YAML](#toc-11-runtime-supported)
- [12. Parameter-selection principles](#toc-12-parameter-principles)
- [13. Recommended team release checklist](#toc-13-release-checklist)
- [14. Known limitations to communicate during handoff](#toc-14-known-limitations)
- [15. Validated baseline (2026-08-18) and the protocol for every new PDF](#toc-15-validated-baseline)

---

<p>This is the main guide for handing off, operating, and troubleshooting the PDF data extraction system. It takes a developer from opening the project in VS Code through full execution, diagnostics, configuration tuning, and determining when source-code changes are needed.</p>

> **Purpose:** This is the developer-facing front door for the workspace. A developer should be able to open the project in VS Code, verify the environment/model setup, process a new PDF, diagnose geometry/OCR failures, tune the correct parameter, and know when a source-code change is required.

<a id="toc-0-source-of-truth"></a>
## 0. Source-of-truth and current audit status

<p>This section identifies the files treated as sources of truth during the project review, together with test status and findings confirmed against the current code.</p>

This guide was built from the current workspace sources: `main.py`, `config.py`, `models.py`, `configs/default.yaml`, all `pipeline/*.py`, `tests/*.py`, `tools/*.py`, and the existing docs.

Last verified **validated-baseline** status on the upgraded v3.2.0 workspace (2026-08-18):

```text
51 passed, 5 skipped, 2 warnings
0 failed
```

The 5 skipped tests are the environment-driven E2E cases in `tests/test_e2e_uploaded_files.py` because `PDF_TEST_FILE_1..5` are not configured. The two warnings are PyTorch/EasyOCR deprecation warnings around `torch.ao.quantization`; they do not block extraction and are not extraction failures.

The current baseline has also completed a real three-page full E2E regression on `samples/Account_Statement_scanned.pdf` with **3 successful pages, 0 failed pages, and 0 pages completed with warnings**. The structural results were 4×7, 6×7, and 5×7 rows/columns on pages 1–3 respectively, all selected through `opencv_shaded_grid`. See [Section 15](#toc-15-validated-baseline) for the exact evidence and the mandatory protocol for the next PDF.

### Important current-source findings

<p>A summary of the most important findings from reviewing the current code, including actual pipeline behavior, implemented fixes, and features that still need improvement.</p>

1. **The project is generic by design.** There are no bank/company/file-name profiles in the current source; configuration is resolved generically.
2. **Actual engine precedence is:** CLI `--override` → `page_overrides` → JSON `--run-config` → base YAML. **However, the standard developer workflow in this guide intentionally does not use `--override`.** For normal work, change global/default values in YAML and PDF-specific values in the generated JSON.
3. **Fixed in 3.0.1:** the default `output.mode` is now `full`, matching the documented first-run behavior. A default extraction therefore creates Excel plus row/cell crops and manifests.
4. **Fixed in 3.0.1:** the existing README first-run Excel example is now consistent with `configs/default.yaml` and `OutputManager` behavior.
5. **Updated in 3.1.0:** tests no longer require a user-edited `default.yaml` to remain `full`. The output-mode contract test accepts every supported mode, and the environment-driven E2E tests assert Excel only when the resolved output plan enables Excel. The five E2E cases still skip when `PDF_TEST_FILE_1..5` are not configured.
6. **Fixed in 3.0.1:** `digital_text.fallback_to_ocr_when_garbled` is now consumed by `PageClassifier`. With the default `true`, low-quality selectable text falls back to OCR; set it to `false` only when intentionally forcing the digital text layer.
7. **Fixed in 3.0.1:** `output.training_dataset.label_source` is now operational with `ocr_draft`, `normalized`, and `blank`. `blank` also preserves OCR-empty cell crops for manual labeling.
8. **Fixed in 3.0.1:** `project.deterministic` and `project.random_seed` now apply best-effort Python/NumPy/PyTorch reproducibility controls; deterministic mode also disables cuDNN benchmarking.
9. **Added in 3.1.0:** crop-only modes now have a true no-OCR structure path using classic ruled geometry, native digital coordinates, repeated shaded/filled-cell rectangles, and borderless text-ink projection/alignment.
10. **Added in 3.1.0:** `run_configuration` is logged before page processing, and `recommended_strategy` is separated from `executed_strategy`.
11. **Added in 3.1.0:** crop-only pages with no inferred structure record `NO_STRUCTURE_DETECTED`; output summaries distinguish `pages_with_structure`, `pages_without_rows`, and pages completed with warnings.
12. **Added in 3.1.0:** native/digital borderless X clustering scales with measured word height to survive high-DPI rendering.
13. The v3.1 visual geometry route can split vertically separated borderless blocks, but the classic OCR-word borderless detector still reconstructs one region; arbitrary/nested multi-table layouts remain a partial limitation.
14. Cross-page table continuation/linking is not implemented. Pages are processed independently.
15. **Added in 3.2.0:** crop-only modes can lazily call EasyOCR/CRAFT in **detection-only** mode (`detector=true`, `recognizer=false`) when native/OpenCV structure evidence is insufficient. This returns text bounding boxes only; no characters are decoded.
16. **Added in 3.2.0:** page logs expose `structure_method`, `text_detection_used`, `text_detection_boxes`, `text_detection_device`, `ocr_recognition_enabled`, `structure_confidence`, and `page_status`, so a developer can see exactly how cells were found.
17. **Important mode distinction:** `full` and crop-only modes share structure evidence, but `full` also performs character recognition and may use recognized OCR word positions for borderless reconstruction. Crop-only never performs character recognition.
18. **Configuration roles are now explicit:** `configs/default.yaml` is the active project-wide baseline; `configs/default_v3.2.0.reference.yaml` is a read-only reference snapshot; `default.yaml.pre_v3_2_0.bak` is only the pre-upgrade backup; generated `*.run_config.json` files are the normal place for PDF-specific tuning after the first run.
19. **Validated baseline fix — structure candidate arbitration:** the final structure selector no longer rewards OCR line fragmentation with a near-linear `row_count × column_count` advantage. Candidate scoring now uses sub-linear row evidence plus confidence, vertical compactness, cell occupancy, and column-count consistency. This is generic: it uses no bank/company/file-name/template/fixed-column rule.
20. **Validated baseline debug evidence:** `page_report.json` now records `structure_candidates` with method, score, row count, median columns, confidence, row factor, compactness, median occupancy, occupancy factor, column consistency, and the selected candidate. This makes the final structure decision auditable instead of a black box.
21. **Validated baseline fix — geometry validation:** `Validator` no longer creates enormous false z-scores when MAD is zero. Geometry outlier checks require a minimum sample count (runtime default 8), then use MAD → IQR → standard-deviation fallback; if the distribution has no measurable spread, the z-test is skipped.
22. **Validated baseline fix — total-row classification:** a plain occurrence of the word `Total` inside a long transaction description is no longer sufficient to mark the row as `is_total=true`. Strong summary phrases such as `Grand Total`, `Subtotal`, `الإجمالي`, and short label-like `Total` cells are still recognized.
23. **Validated on a real sample:** the former wrong choice `borderless_spatial` (29 physical OCR rows × 6 inferred columns on page 2) was replaced by the evidence-supported `opencv_shaded_grid` candidate (6 logical rows × 7 columns, confidence 1.0). The same selector then produced coherent structures on pages 1 and 3 without PDF-specific configuration changes.

---

<a id="toc-1-onboarding"></a>
# 1. First opening in VS Code — exact onboarding sequence

<p>This section is the starting point for developers opening the project for the first time. Follow the steps in order to verify that the project directory, Python, virtual environment, OCR libraries, and models are ready before changing any parameter.</p>

<a id="toc-1-1-open-folder"></a>
## 1.1 Open the correct folder

<p>Make sure VS Code is open at the entire project root rather than a subfolder such as pipeline or docs, because commands and relative paths assume execution from the project root.</p>

Open the project root itself — the folder that contains:

```text
main.py
config.py
models.py
configs/
pipeline/
tests/
tools/
docs/
.venv/            # local machine only
models/easyocr/   # local machine only if already provisioned
```

Do **not** open only `pipeline/` or only `docs/` as the VS Code workspace root.

<a id="toc-1-2-python-interpreter"></a>
## 1.2 Verify the VS Code Python interpreter

<p>Make sure VS Code uses the Python interpreter inside the project's .venv. Another interpreter may have different dependencies or cause misleading import errors.</p>

The uploaded `.vscode/settings.json` only declares the venv environment manager; it does not pin an absolute interpreter path. In VS Code:

```text
Ctrl+Shift+P
→ Python: Select Interpreter
→ choose <workspace>\\.venv\\Scripts\\python.exe
```

Then open a PowerShell terminal and run:

```powershell
python -c "import sys; print(sys.executable)"
python --version
```

Expected: `sys.executable` points inside this workspace's `.venv`.

<a id="toc-1-3-venv"></a>
## 1.3 Preflight the existing `.venv`

<p>Inspect the existing virtual environment before creating a new one. The objective is to verify Python and installed dependencies and detect dependency conflicts.</p>

Because `.venv` is intentionally not committed/uploaded, verify it before installing anything:

```powershell
Test-Path .\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
```

Then test the runtime imports:

```powershell
.\.venv\Scripts\python.exe -c "import pymupdf, cv2, numpy, pandas, yaml, easyocr, torch, sklearn, PIL, openpyxl; print('Runtime imports OK'); print('Torch:', torch.__version__); print('CUDA:', torch.cuda.is_available())"
```

If this succeeds, **do not rebuild the venv**.

If it fails because packages are missing:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

Only install training helper dependencies when you actually need the training-data workflow:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements-training.txt
```

<a id="toc-1-4-easyocr-models"></a>
## 1.4 Preflight the EasyOCR model directories

<p>Check that standard or custom EasyOCR model directories and files exist at the expected paths before running OCR, so model problems are not mistaken for pipeline failures.</p>

The current default config expects:

```text
models/easyocr/model
models/easyocr/user_network
```

Verify them:

```powershell
Test-Path .\models\easyocr\model
Test-Path .\models\easyocr\user_network
Get-ChildItem .\models\easyocr\model -File
Get-ChildItem .\models\easyocr\user_network -File
```

Check the configured recognition network:

```powershell
python .\main.py inspect-config --parameter "ocr.easyocr.recog_network"
python .\main.py inspect-config --parameter "ocr.easyocr.model_storage_directory"
python .\main.py inspect-config --parameter "ocr.easyocr.user_network_directory"
```

For `recog_network: standard`, EasyOCR standard files must be available locally or `download_enabled` must be allowed to fetch them on first use.

For a custom recognition network named, for example, `my_model`, verify the matching files are provisioned according to the existing installation workflow:

```text
my_model.pth
my_model.yaml
my_model.py
```

Do not assume a model is healthy merely because the directory exists; the first OCR smoke test below is the real check.

<a id="toc-1-5-tests"></a>
## 1.5 Run the unit test suite before touching parameters

<p>Run tests before making changes to establish whether the project is healthy. If tests already fail, resolve those failures before tuning a new PDF.</p>

```powershell
python -m pytest -q
```

Treat new failures here as code/environment problems, not PDF tuning problems.

<a id="toc-1-6-no-ocr-smoke"></a>
## 1.6 Run a no-OCR analysis smoke test

<p>Run a quick analysis without OCR to verify PDF reading and basic analysis before introducing optical character recognition.</p>

```powershell
python .\main.py analyze `
  --input ".\samples\Account_Statement_scanned.pdf" `
  --pages 1 `
  --output ".\outputs\smoke_analysis.json"
```

This verifies PyMuPDF/OpenCV analysis without requiring a full OCR extraction.

<a id="toc-1-7-ocr-smoke"></a>
## 1.7 Run an OCR smoke test on one representative page

<p>Test OCR on one representative page rather than processing the entire document. This quickly exposes model, GPU/CPU, language, or configuration problems.</p>

Before this OCR smoke test, set the desired mode in `configs/default.yaml`. For a full OCR smoke test use:

```yaml
output:
  mode: full
```

Then run without a CLI override:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\Account_Statement_scanned.pdf" `
  --output ".\outputs\smoke_page1.xlsx" `
  --pages 1 `
  --debug `
  --debug-root ".\outputs\debug_smoke"
```

If your intended workflow is crop-only, keep `output.mode: cropped_rows_and_cells` in YAML. Character recognition will not be initialized. If pure geometry cannot recover structure, the pipeline may lazily load EasyOCR/CRAFT in detection-only mode (`recognizer=false`) to obtain text boxes without reading the text.

If this fails while analysis succeeded, inspect the OCR/model section of this guide first.

---

<a id="toc-2-new-pdf-workflow"></a>
# 2. The normal workflow for every new PDF

<p>For every new PDF, follow this standard workflow: analyze, diagnose, test one page, inspect geometry, change one parameter, save configuration, and then expand to the remaining pages.</p>

Use this exact loop instead of editing Python code immediately.

<a id="toc-2-config-inputs"></a>
## 2.1 Config files: active YAML, reference YAML, backup, and generated JSON

<p>Keep PDF input separate from configuration files. --input accepts only a PDF; --config supplies the base YAML, and --run-config supplies JSON generated by a previous run. Never pass YAML or JSON through --input.</p>

### Which YAML file do I edit?

<p>For day-to-day work, the only active YAML is configs/default.yaml. default_v3.2.0.reference.yaml is a backup reference for the original v3.2 settings and is not used unless explicitly passed to --config. default.yaml.pre_v3_2_0.bak is solely a pre-upgrade backup.</p>

| Workspace file | Role | Edit during normal work? | Used automatically? |
|---|---|---:|---:|
| `configs/default.yaml` | **Active project-wide baseline** | **Yes**, when changing a default for future PDFs | **Yes**, when passed with `--config` |
| `configs/default_v3.2.0.reference.yaml` | v3.2 reference snapshot | No; keep as reference | No |
| `configs/default.yaml.pre_v3_2_0.bak` | Pre-upgrade backup | No | No |
| `outputs/<name>.run_config.json` | PDF-specific working configuration after the first run | **Yes**, for tuning that PDF | Yes, only when passed with `--run-config` |

**Rule:** if a change should affect **all future PDFs**, change `configs/default.yaml`. If it is only for **one PDF**, make the change in that PDF's generated `*.run_config.json` after the first run.

| File | CLI argument | Purpose |
|---|---|---|
| PDF to process | `--input` | The actual document being analyzed/extracted |
| Base YAML | `--config` | Global/default pipeline settings |
| Generated JSON | `--run-config` | Editable PDF-specific settings from a previous run |

### First run — YAML is the configuration source

<p>On the first run, use configs/default.yaml as the base configuration and supply the PDF via --input. After a successful run, the system automatically creates *.run_config.json unless --no-save-run-config was specified.</p>

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\document.pdf" `
  --output ".\outputs\document_page1.xlsx" `
  --pages 1 `
  --debug `
  --debug-root ".\outputs\debug_document"
```

Flow:

```text
configs/default.yaml  ──> --config
document.pdf          ──> --input
                           │
                           ▼
                       first run
                           │
                           └──> document_page1.run_config.json
```

### Later runs — JSON becomes the PDF-specific working configuration

<p>After generating JSON, edit values inside its config object. For the next run, supply the same base YAML through --config and the modified JSON through --run-config. --input remains reserved for the PDF.</p>

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --run-config ".\outputs\document_page1.run_config.json" `
  --input ".\samples\document.pdf" `
  --output ".\outputs\document_page1_second.xlsx" `
  --pages 1 `
  --debug `
  --debug-root ".\outputs\debug_document_second"
```

Flow:

```text
configs/default.yaml                  ──> --config
document_page1.run_config.json        ──> --run-config
document.pdf                          ──> --input
                                           │
                                           ▼
                                      resolved config
                                           │
                                           ▼
                                        extract
```

**Important:** the JSON does not literally replace the YAML file in the current architecture. The YAML remains the base/fallback configuration, while the generated JSON overlays it and becomes the normal place to store PDF-specific tuning values. In the documented workflow, do not use CLI `--override` for mode changes or routine tuning.

For `output.mode` specifically:

- Before the first run: edit `output.mode` in `configs/default.yaml`.
- After the first run: edit `config.output.mode` in the generated `*.run_config.json` for that PDF.
- Do not use `--override "output.mode=..."` in the normal workflow.

### Verify the effective mode before a real extraction

<p>Before any important run, verify which output mode will actually be used. Do not rely on the output filename or your memory of edits. Inspect YAML directly, or pass the JSON to inspect-config as well.</p>

YAML only:

```powershell
python .\main.py inspect-config `
  --config ".\configs\default.yaml" `
  --parameter "output.mode"
```

YAML + generated JSON:

```powershell
python .\main.py inspect-config `
  --config ".\configs\default.yaml" `
  --run-config ".\outputs\document_page1.run_config.json" `
  --parameter "output.mode"
```

From v3.1.0 onward every `extract` run also prints a startup record **before page processing**. Treat it as the source of truth for what is about to run:

```json
{
  "event": "run_configuration",
  "output_mode": "cropped_rows_and_cells",
  "processing_mode": "geometry_plus_text_detection",
  "ocr_enabled": false,
  "ocr_recognition_enabled": false,
  "text_detection_fallback_enabled": true,
  "excel_enabled": false
}
```

For a real full run the corresponding fields must be:

```json
{
  "event": "run_configuration",
  "output_mode": "full",
  "processing_mode": "full_extraction",
  "ocr_enabled": true,
  "excel_enabled": true
}
```

If the startup record says `cropped_rows_and_cells`, then **the run is not full**, even if the output filename ends in `.xlsx`.

After each page, use these fields to understand how structure was actually obtained:

```text
structure_method          # winning structure detector
text_detection_used       # true only if detection-only CRAFT fallback was actually invoked
text_detection_boxes      # number of boxes returned by detection-only fallback
text_detection_device     # cpu/cuda/etc. for that fallback
ocr_recognition_enabled   # true in full/data modes; false in crop-only modes
rows_detected
columns_detected
page_status
```

Examples:

```text
structure_method=opencv_shaded_grid
text_detection_used=false
ocr_recognition_enabled=false
```

means OpenCV/shaded geometry found the cells and no OCR text detection/recognition was needed.

```text
structure_method=easyocr_detection_spatial
text_detection_used=true
ocr_recognition_enabled=false
```

means crop-only used CRAFT **bounding-box detection only** to recover structure; it still did not read the characters.

```text
structure_method=borderless_spatial
ocr_recognition_enabled=true
```

in a full run means recognized/native word positions participated in borderless reconstruction and semantic OCR is enabled.

<a id="toc-2-step-a"></a>
## Step A — Analyze representative pages

<p>Start by analyzing pages representative of different layouts to determine whether they are digital or scanned and identify table types before extraction.</p>

For a short PDF, analyze all pages. For a large PDF, start with page 1, a middle page, and the last page.

```powershell
python .\main.py analyze `
  --input ".\samples\document.pdf" `
  --pages "1,5,10" `
  --output ".\outputs\document_analysis.json"
```

Do not use `--fast` when you need line/layout evidence; `--fast` intentionally skips thumbnail rendering and quick line analysis.

<a id="toc-2-step-b"></a>
## Step B — Ask the built-in advisor for measurement-based suggestions

<p>Use diagnose to obtain recommendations based on actual page measurements instead of guessing parameters.</p>

```powershell
python .\main.py diagnose `
  --input ".\samples\document.pdf" `
  --pages "1,5,10" `
  --output ".\outputs\document_diagnose.json"
```

Treat advisor output as suggestions only. `digital_text.fallback_to_ocr_when_garbled` is now a supported runtime parameter; the advisor suggests enabling it only when it is currently disabled and the digital text quality is low.

<a id="toc-2-step-c"></a>
## Step C — Extract one representative page with debug artifacts

<p>Extract one page with debug artifacts so you can inspect the detected boundaries, rows, columns, and crops.</p>

Before running, choose `output.mode` in `configs/default.yaml` for this first run. Then:

**Pre-first-run checks for the current v3.2 workspace:**

```powershell
python .\main.py inspect-config `
  --config ".\configs\default.yaml" `
  --parameter "output.mode"

python -m pytest -ra
```

Expected from the latest validated workspace: `51 passed`, `5 skipped`, `0 failed`. The current two `torch.ao.quantization` deprecation warnings do not block extraction.

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\document.pdf" `
  --output ".\outputs\document_page1.xlsx" `
  --pages 1 `
  --debug `
  --debug-root ".\outputs\debug_document"
```

This also creates an editable `*.run_config.json` unless `--no-save-run-config` is used.

<a id="toc-2-step-d"></a>
## Step D — Inspect geometry before OCR text

<p>Inspect table geometry before evaluating OCR. Even excellent OCR cannot repair data generated from incorrect crops or row/column boundaries.</p>

Inspect in this order:

```text
01_original.png
02_grayscale.png
03_contrast.png
05_denoised.png / 05b_sharpened.png when present
06_threshold.png
07_morphology.png
08_deskewed.png / 08_deskewed_gray.png
05_horizontal_lines.png
06_vertical_lines.png
07_detected_regions.png
08_detected_rows.png
09_detected_columns.png
10_detected_cells.png
11_ocr_overlay.png
12_validation_overlay.png
page_report.json
```

**Rule:** if row/column/cell boxes are wrong, do not tune the recognition model first. Fix geometry first.

<a id="toc-2-step-e"></a>
## Step E — Edit one parameter in the generated JSON

<p>After the first run, use *.run_config.json as the working configuration for that PDF. Change one parameter per experiment to identify precisely what improved or degraded the result.</p>

Open:

```text
outputs/document_page1.run_config.json
```

Edit values only inside:

```json
{
  "config": {
    "...": "..."
  }
}
```

For example, to change the output mode after the first run:

```json
{
  "config": {
    "output": {
      "mode": "cropped_rows_and_cells"
    }
  }
}
```

For a geometry parameter:

```json
{
  "config": {
    "borderless_table": {
      "column_detection": {
        "x_tolerance_px": 10
      }
    }
  }
}
```

Do not change several unrelated parameters in one trial.

<a id="toc-2-step-f"></a>
## Step F — Re-run using YAML + JSON

<p>On subsequent runs, pass the base YAML using --config and the modified JSON using --run-config. Always supply the PDF itself through --input.</p>

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --run-config ".\outputs\document_page1.run_config.json" `
  --input ".\samples\document.pdf" `
  --output ".\outputs\document_second.xlsx" `
  --pages 1 `
  --debug `
  --debug-root ".\outputs\debug_document_second"
```

For the standard documented workflow:

```text
page_overrides inside the resolved configuration
→ JSON --run-config
→ configs/default.yaml
```

The engine still supports CLI `--override` as a highest-priority compatibility/advanced feature, but this guide intentionally does not use it for normal processing or mode changes.

<a id="toc-2-step-g"></a>
## Step G — Use `tune` for a single numeric parameter when useful

<p>Use tune to compare multiple values of a single numeric parameter in a measurable way when visual inspection alone is insufficient.</p>

```powershell
python .\main.py tune `
  --input ".\samples\document.pdf" `
  --page 1 `
  --parameter "borderless_table.column_detection.x_tolerance_px" `
  --values 8 10 12 15 18 22 `
  --output ".\outputs\tune_x_tolerance.json"
```

Never accept the top score blindly; visually inspect the winning geometry.

<a id="toc-2-step-h"></a>
## Step H — Scale to the whole PDF only after representative pages are correct

<p>Process the whole document only after representative pages succeed. This reduces experimentation time and prevents large volumes of incorrect output.</p>

Set the desired final `config.output.mode` in the generated JSON, then run:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --run-config ".\outputs\document_page1.run_config.json" `
  --input ".\samples\document.pdf" `
  --output ".\outputs\document_final.xlsx"
```

For final Excel-only delivery, edit the JSON:

```json
{
  "config": {
    "output": {
      "mode": "data_only"
    }
  }
}
```

Then re-run the same command.

---

<a id="toc-3-stage-responsibilities"></a>
# 3. What each pipeline stage is responsible for

<p>This section explains each pipeline stage so developers know where to investigate problems: analysis, preprocessing, table, row and column detection, OCR, reconstruction, validation, and export.</p>

```text
PDF
│
├─ PDFAnalyzer / PageClassifier
│   ├─ digital / scanned / hybrid
│   └─ bordered / borderless / mixed / free_text
│
├─ ImageExtractor
│   ├─ native embedded full-page image when suitable
│   └─ page render when needed
│
├─ ImagePreprocessor
│   ├─ contrast / shadow / denoise / sharpen
│   ├─ threshold / morphology
│   └─ deskew
│
├─ Structure evidence
│   ├─ classic ruled-line geometry
│   ├─ native PyMuPDF word coordinates for digital/hybrid PDFs (no OCR)
│   ├─ VisualStructureDetector
│   │   ├─ repeated shaded/filled-cell geometry
│   │   └─ borderless text-ink projection/alignment (no recognition)
│   ├─ EasyOCR/CRAFT detection-only fallback in crop-only modes
│   │   └─ bounding boxes only; recognizer=false; no decoded text
│   └─ OCR WordBoxes when semantic extraction is enabled
│       └─ EasyOCR default; optional PaddleOCR
│
├─ Row / column / cell reconstruction
│   ├─ anchor segmentation (optional)
│   ├─ bordered grid
│   ├─ borderless spatial reconstruction
│   └─ visual geometry fallback
│
├─ Cells / crops
│
├─ DataReconstructor (non-crop-only modes)
│   ├─ schema mapping
│   ├─ Arabic digit normalization
│   ├─ amount/date parsing
│   └─ header/total tagging
│
├─ Validator
│   ├─ structural warnings in crop-only
│   ├─ confidence / required values
│   ├─ geometry / type validation
│   └─ optional balance arithmetic
│
└─ OutputManager / Exporter
    ├─ Excel when enabled by output.mode
    ├─ crops / manifests
    └─ optional JSON/CSV/JSONL/Parquet
```

<a id="toc-3-1-crop-only-visual-structure"></a>
## 3.1 Shared structure path + detection-only fallback (v3.2.0)

<p>In crop-only modes, row and cell detection are genuinely independent of OCR recognition. The program does not wait for EasyOCR words to construct a grid; it combines geometry evidence appropriate to the page and selects the best structure candidate without conditions tied to a filename, company, or bank.</p>

Crop-only modes:

```text
cropped_cells_only
cropped_rows_only
cropped_rows_and_cells
```

execute this logic:

```text
PDF page
   │
   ├─ digital / hybrid
   │      └─ native PyMuPDF word coordinates (geometry only; no OCR)
   │
   └─ scanned / image geometry
          ├─ classic dark ruled lines
          ├─ repeated shaded/filled cell rectangles
          └─ borderless text-ink projection + repeated X/Y alignment
                    │
                    ▼
             structure found?
              │           │
             yes          no
              │           │
              │      EasyOCR/CRAFT detect() only
              │      recognizer=false
              │      bounding boxes only
              │           │
              └──────┬────┘
                     ▼
           rows + columns + cells
                     │
                     ▼
              row/cell crops

Character recognition is never initialized in these crop-only modes. The optional CRAFT fallback only answers **where text exists**; it does not decode Arabic, English, numbers, or any other characters.

### Crop-only vs full: what is shared and what is different?

<p>Full and crop-only modes both infer table structure, including rows, columns, and cells. Crop-only stops after saving crops without reading text; full mode continues to recognition, reconstruction, validation, and Excel export.</p>

| Capability | `cropped_rows_and_cells` | `full` |
|---|---:|---:|
| Native PDF geometry | ✅ | ✅ when useful |
| OpenCV ruled/shaded/projection structure | ✅ | ✅ |
| CRAFT detection-only fallback | ✅, only if needed | Not the normal fallback; full already has OCR word boxes |
| Character recognition | ❌ | ✅ |
| Use text positions to help borderless reconstruction | Detection boxes only, no decoded text | ✅ recognized/native word boxes |
| Row/cell crops | ✅ | ✅ |
| Data reconstruction / validation | ❌ | ✅ |
| Excel output | ❌ | ✅ |

The practical rule is: **cell detection is not an OCR-recognition task.** Recognition is an additional semantic stage. In crop-only, CRAFT may still be used only to answer “where is text?” when visual structure alone is insufficient.

A page that completes without an exception but yields no croppable structure now records `NO_STRUCTURE_DETECTED` and `page_status=completed_with_warning`; do not treat `pages_successful` alone as proof of extraction quality. Also inspect `pages_with_structure`, `pages_without_rows`, `row_crops`, and `cell_crops`.

Useful v3.2 debug evidence includes:

```text
05_horizontal_lines.png
06_vertical_lines.png
07_detected_regions.png
07a_visual_shaded_mask.png (name may include detector prefix)
07a_visual_projection_foreground.png
07a_visual_projection_text_mask.png
07b_visual_detected_regions.png
07c_text_detection_boxes.png   # only when detection-only fallback is invoked
08_detected_rows.png
09_detected_columns.png
10_detected_cells.png
page_report.json
```

---


<a id="toc-3-2-strategies"></a>
## 3.2 What `digital_text`, `cell_ocr`, `row_ocr`, and the other strategies mean

<p>A strategy is the high-level page-processing plan proposed after classifying the page as digital, scanned, or hybrid and identifying its layout. It is not necessarily the geometric detector that actually found the cells; structure_method identifies that detector.</p>

The available strategy values in `models.py` are:

```text
digital_text
cell_ocr
row_ocr
full_page_ocr
digital_with_ocr_fallback
```

### Very important: Strategy is not the same as `output.mode` or `structure_method`

```text
output.mode
→ What final processing/output level do we want?
  Example: full, data_only, cropped_rows_and_cells

recommended_strategy
→ What high-level extraction approach does the PageClassifier recommend?
  Example: cell_ocr

executed_strategy
→ What high-level strategy actually ran after mode/fallback decisions.

structure_method
→ Which concrete structure detector actually built rows/columns/cells?
  Example: bordered_grid, opencv_projection_grid, easyocr_detection_spatial
```

<p>Put simply, output.mode describes what should be produced, the strategy describes the preferred processing approach, and structure_method identifies which method actually succeeded in detecting structure.</p>

---

### How the classifier chooses the recommended strategy

The current `PageClassifier.choose_strategy()` logic is:

```text
IF page is DIGITAL or HYBRID
AND native digital-text quality >= digital_text.quality_min
    → digital_text

ELSE IF layout is BORDERED_TABLE
    → cell_ocr

ELSE IF layout is BORDERLESS_TABLE or MIXED
    → row_ocr

ELSE
    → full_page_ocr
```

With the current default:

```yaml
digital_text:
  quality_min: 0.72
```

<p>Strategy selection is not random. The system first evaluates digital-text quality, then examines whether the layout is bordered, borderless, mixed, or free text.</p>

---

### `digital_text`

<p>Use text already embedded in the PDF instead of OCR. This suits digital or hybrid PDFs whose original text layer is valid and trustworthy.</p>

**Think of it as:**

```text
PDF already knows the words
        ↓
read native text + coordinates
        ↓
reconstruct rows/columns/cells
```

#### When it is recommended

```text
page_type = digital or hybrid
digital_text_quality >= digital_text.quality_min
```

#### What it avoids

- No need to recognize characters that already exist in the PDF.
- Usually faster than OCR.
- Avoids OCR character mistakes when the native text layer is correct.

#### What can still go wrong

The text itself may be correct but its geometry can still reconstruct the table incorrectly.

Example:

```text
recommended_strategy = digital_text
structure_method = native_digital_spatial
```

If columns are wrong here, tune the **borderless spatial geometry parameters**, not OCR recognition first.

<p>For example, if you can select text in a PDF bank statement and the extracted words are correct, it is better to read those words and their coordinates directly than render the page as an image and recognize the characters again.</p>

---

### `cell_ocr`

<p>The idea is to detect cell boundaries first, then read each cell independently. This especially suits clearly bordered tables because the grid identifies each cell accurately.</p>

**Think of it as:**

```text
detect table grid
      ↓
build cells
      ↓
OCR Cell 1
OCR Cell 2
OCR Cell 3
...
      ↓
reconstruct row
```

#### When it is recommended

```text
layout_type = bordered_table
```

#### Typical example

```text
Page:
┌──────────┬──────────┬──────────┐
│ Date     │ Amount   │ Balance  │
├──────────┼──────────┼──────────┤
│ ...      │ ...      │ ...      │
└──────────┴──────────┴──────────┘

recommended_strategy = cell_ocr
```

A common successful combination is:

```text
recommended_strategy = cell_ocr
structure_method = bordered_grid
```

#### Why cell-level OCR can be useful

- Each OCR crop contains less unrelated text.
- Numeric/date columns can be processed more precisely.
- Table boundaries give strong geometry.
- One bad cell does not necessarily damage the entire row.

#### Main risk

If the detected cell boundaries are wrong, OCR will faithfully read the **wrong crop**.

Therefore:

```text
Wrong cell crop
→ fix geometry first

Correct crop but wrong characters
→ tune OCR second
```

<p>Important: seeing cell_ocr does not mean OCR should be tuned first. If cells are cropped, merged, or divided incorrectly, fix bordered_grid or the actual structure method before OCR.</p>

---

### `row_ocr`

<p>The idea is to detect each row as one block, read its content, and assign words to columns using their positions within that row. This is better suited to tables without clear cell borders and to mixed layouts.</p>

**Think of it as:**

```text
find logical row
      ↓
OCR the row
      ↓
get word positions
      ↓
map words to columns
```

#### When it is recommended

```text
layout_type = borderless_table
or
layout_type = mixed
```

#### Typical borderless example

```text
2026-01-01     Transfer ABC       1,200.00     8,500.00
2026-01-02     Payment XYZ          500.00     8,000.00
2026-01-03     Deposit            2,000.00    10,000.00
```

There may be no visible vertical lines separating columns.

So instead of:

```text
grid → cells
```

the system may need:

```text
rows → word positions → column clustering
```

Possible actual structure methods include:

```text
native_digital_spatial
borderless_spatial
opencv_projection_grid
easyocr_detection_spatial
opencv_anchor_projection
```

#### Why not always use `cell_ocr`?

Because a borderless table may not have reliable physical cell rectangles.

Trying to invent cell borders too early can create:

```text
false columns
merged columns
split descriptions
incorrect cell crops
```

<p>For example, in a statement without vertical column lines, each transaction appears as a row. Detect the row first, then use the positions of Date, Description, Amount, and Balance to form columns.</p>

---

### `full_page_ocr`

<p>Read the whole page as an image when there is not enough reliable structure for a cell- or row-based strategy. This is the broadest approach and relies least on orderly geometry.</p>

**Think of it as:**

```text
whole page image
      ↓
OCR all visible text
      ↓
use positions/content afterward
```

#### When it is recommended

In the current classifier:

```text
not trusted digital text
AND
layout is not bordered_table
AND
layout is not borderless_table or mixed
```

which normally means the page was classified closer to:

```text
free_text
```

#### Appropriate use cases

- Free-form scanned page.
- Letter/report-like page.
- Structure detection has little reliable table evidence.
- Last-resort recognition path.

#### Trade-off

It sees more context, but that also means:

- more OCR boxes,
- more unrelated text,
- more reconstruction work,
- greater chance of assigning text to the wrong logical field.

<p>Therefore, full_page_ocr is not automatically better OCR just because it reads the entire page. It is appropriate when the page cannot reliably be divided into cells or rows first.</p>

---

### `digital_with_ocr_fallback`

<p>Try the original digital text first. If its quality is unacceptable, fall back to OCR rather than trusting a corrupted or garbled text layer.</p>

**Think of it as:**

```text
try native PDF text
        ↓
is quality good?
   ├─ yes → use digital text
   └─ no  → use OCR fallback
```

The related runtime behavior is controlled by:

```yaml
digital_text:
  quality_min: 0.72
  fallback_to_ocr_when_garbled: true
```

#### Important implementation note

`DIGITAL_WITH_OCR_FALLBACK` exists in the `Strategy` enum, but the current `PageClassifier.choose_strategy()` source does **not** directly return this enum value.

Instead, the current classifier does this:

```text
digital/hybrid + good quality
→ digital_text

digital/hybrid + poor quality
→ continue strategy selection according to layout
   → cell_ocr / row_ocr / full_page_ocr
```

So treat `digital_with_ocr_fallback` as a **defined strategy concept / compatibility value**, not something you should expect to see on every bad digital page.

<p>What matters is the actual behavior, not just the enum name: when digital text is poor and fallback is enabled, do not trust the garbled layer; allow the pipeline to switch to an OCR path suited to the layout.</p>

---

### `recommended_strategy` vs `executed_strategy`

<p>Since v3.1.0, the classifier's recommendation and the strategy actually executed are recorded separately. This matters in debugging because output mode, fallbacks, and structure evidence may cause execution to differ from the initial recommendation.</p>

Example:

```text
recommended_strategy = row_ocr
executed_strategy    = row_ocr
structure_method     = opencv_projection_grid
```

This means:

```text
Classifier:
"Treat this page row-wise."

Actual structure engine:
"OpenCV projection was the method that successfully found the rows/columns."
```

Another example:

```text
recommended_strategy = cell_ocr
structure_method     = bordered_grid
ocr_recognition_enabled = true
```

Meaning:

```text
The page looked like a bordered table.
The ruled-grid detector successfully built cells.
Because output.mode requires semantic extraction,
OCR recognition then reads the cell contents.
```

---

### Practical examples

#### Example 1 — Clean digital borderless PDF

```text
page_type            = digital
layout_type          = borderless_table
digital_text_quality = 0.95

recommended_strategy = digital_text
structure_method     = native_digital_spatial
```

Interpretation:

<p>Use the original text and its coordinates. Do not begin by adjusting EasyOCR because OCR is not the primary text source here.</p>

---

#### Example 2 — Scanned bordered table

```text
page_type            = scanned
layout_type          = bordered_table

recommended_strategy = cell_ocr
structure_method     = bordered_grid
```

Interpretation:

<p>Construct cells from detected lines first, then read their contents. If columns merge, fix bordered_table.* parameters before OCR.</p>

---

#### Example 3 — Scanned borderless statement

```text
page_type            = scanned
layout_type          = borderless_table

recommended_strategy = row_ocr
structure_method     = easyocr_detection_spatial
```

Interpretation:

<p>There is no reliable grid. CRAFT detects text positions, the boxes are grouped into rows and columns, and recognition can then read the contents in full mode.</p>

---

#### Example 4 — Mixed page

```text
page_type            = scanned
layout_type          = mixed

recommended_strategy = row_ocr
structure_method     = opencv_projection_grid
```

Interpretation:

<p>The page has incomplete structure cues or mixes ruling lines with borderless content, so row-wise processing is more suitable than assuming a complete cell grid.</p>

---

#### Example 5 — Free-text scanned page

```text
page_type            = scanned
layout_type          = free_text

recommended_strategy = full_page_ocr
```

Interpretation:

<p>No clear and trustworthy table structure exists, so page-level reading is the most appropriate general plan.</p>

---

### Debugging rule for strategies

```text
1. Read page_type.
2. Read layout_type.
3. Read recommended_strategy.
4. Read executed_strategy.
5. Read structure_method.
6. Inspect rows/columns/cells.
7. Only then choose the parameter family to tune.
```

<p>Do not change a parameter merely because the strategy says row_ocr or cell_ocr. The strategy indicates the plan; structure_method identifies the actual detector whose parameters need tuning.</p>

### One-line memory aid

```text
digital_text
= Read what already exists in the PDF.

cell_ocr
= Find cells first, then read each cell.

row_ocr
= Find rows first, then read/map words across columns.

full_page_ocr
= Read the whole page because reliable row/cell structure is weak.

digital_with_ocr_fallback
= Trust native text when good; fall back to OCR when it is bad.
```

<p>Remember: Digital means original text; Cell means cell by cell; Row means row by row; Full Page means the entire page; Digital Fallback means try digital text first and use OCR if needed.</p>

---

<a id="toc-4-error-catalog"></a>
# 4. Complete error catalog mapped to the current code

<p>This is the main error catalog. Each error specifies symptoms, the cause in code, an initial corrective action, and whether configuration alone suffices or code enhancement is necessary.</p>

This catalog preserves the required column, row, cell, and table-boundary failure classes, but it is organized as **one compact diagnostic card per error** instead of one very wide table. This makes the section readable in VS Code source view as well as Markdown Preview.

> **How to use this section:** identify the visible symptom first, confirm the likely cause, apply the first resolution, then check the status to know whether the issue is solvable by configuration alone or requires a code enhancement.

<a id="toc-4-1-error-index"></a>
## 4.1 Error catalog index

<p>A quick stage-based error index. Use it to find the relevant category: column, row, cell, or table-boundary errors.</p>

| Stage | Error IDs | Count | Primary implementation areas |
|---|---:|---:|---|
| Column Detection Errors | `C1–C9` | 9 | `pipeline/column_detector.py`, `pipeline/borderless_table_detector.py`, `pipeline/bordered_table_detector.py`, `pipeline/visual_structure_detector.py` |
| Row Detection Errors | `R1–R9` | 9 | `pipeline/row_detector.py`, `pipeline/visual_structure_detector.py` |
| Cell Detection Errors | `CELL1–CELL9` | 9 | `pipeline/crop_generator.py`, `pipeline/visual_structure_detector.py`, `pipeline/ocr_engine.py`, reconstruction logic |
| Table Boundary Detection Errors | `T1–T8` | 8 | `pipeline/bordered_table_detector.py`, `pipeline/borderless_table_detector.py`, `pipeline/visual_structure_detector.py`, `pipeline/layout_analyzer.py` |

### Status meaning

<p>This explains each error card's Status field: whether a fix is configurable now, already supported, or requires code enhancement.</p>

| Status | Meaning |
|---|---|
| `Config` / `Workflow/config` | The current pipeline already supports the correction through parameters or workflow changes. |
| `Supported` | The behavior already exists in the current implementation. |
| `Config/model` | Try configuration first; recurring OCR errors may require a recognition-model change. |
| `Code enhancement` | There is no complete parameter-only fix in the current code; implementation work is required. |
| Mixed status | Start with the supported configuration fix; implement the enhancement only if the issue remains. |


<a id="toc-4-1-1-parameter-tuning-protocol"></a>
## 4.1.1 Parameter tuning protocol used by every error card

<p>Before changing any parameter, avoid guessing or changing several parameters together. Start from the actual value used by the run, make a small adjustment in the specified direction, rerun just one page, and decide whether to continue or revert.</p>

### The five-step tuning loop

<p>Use this loop for every tuning experiment: confirm the effective value, identify the detector used, change one value, rerun one page, and compare the same debug overlay before and after.</p>

1. **Confirm the effective value**, not what you remember editing:

```powershell
python .\main.py inspect-config `
  --config ".\configs\default.yaml" `
  --run-config ".\outputs\document.run_config.json" `
  --parameter "borderless_table.column_detection.x_tolerance_px"
```

Omit `--run-config` on the first run when no JSON exists yet.

2. **Check `structure_method` first.** Tune only the parameter family used by the selected detector. Changing `bordered_table.*` will not fix a page whose winning method is `opencv_projection_grid`.
3. **Change one parameter only.** After the first run, make the change inside the generated JSON, not in Python and not in the reference YAML.
4. **Re-run one failing representative page** with `--debug` and a new debug directory.
5. **Stop when the geometry is correct.** Do not keep “improving” a number after the row/column/cell overlay matches the source.

### Safe first-step sizes

<p>These are relatively safe initial adjustment sizes that let you observe effects without jumping to extremes. Each error recipe provides its own detailed values.</p>

These are tuning increments, not hard rules. The error cards below give exact first/second trials for the v3.2 baseline.

| Parameter type | Normal first change | Why |
|---|---:|---|
| Pixel tolerance / gap | about `±20–30%` | Large enough to observe an effect without jumping to an extreme |
| Ratio in `0..1` | about `±0.05` then `±0.05` again | Keeps structural thresholds interpretable |
| Line-length ratio | about `±0.02` | Small changes strongly affect ruled-line detection |
| DPI | `+50` per trial | Avoids large memory jumps |
| Integer support count | `±1` | Keeps evidence requirements gradual |

**DPI note:** the numeric recipes below assume the v3.2 baseline around **400 DPI**. Pixel-based tolerances are resolution-dependent. If you intentionally render at 600 DPI, a 10 px baseline-equivalent tolerance is roughly 15 px (`600 / 400 = 1.5`). Prefer the ratio/word-height-aware parameters where available instead of manually scaling many pixel values.

### How to edit a dotted parameter in JSON

<p>Parameter names often use dotted paths in this guide. In JSON, do not write the entire path as one key; represent it as nested objects inside config, as shown below.</p>

A dotted path such as:

```text
borderless_table.column_detection.x_tolerance_px
```

becomes nested JSON inside `config`:

```json
{
  "config": {
    "borderless_table": {
      "column_detection": {
        "x_tolerance_px": 12
      }
    }
  }
}
```

Keep the rest of the generated JSON unchanged.

<a id="toc-4-1-2-structure-method-map"></a>
## 4.1.2 `structure_method` → parameter family map

<p>Before changing a value, read structure_method in the console or page_report.json. It identifies the detector that produced the winning structure and therefore which parameter family to adjust.</p>

| `structure_method` | Tune these first | Primary debug evidence |
|---|---|---|
| `bordered_grid` | `bordered_table.horizontal.*`, `bordered_table.vertical.*`, row/column merge tolerances | `05_horizontal_lines.png`, `06_vertical_lines.png`, `07_detected_regions.png` |
| `native_digital_spatial` | `borderless_table.row_detection.*`, `borderless_table.column_detection.*` | `08_detected_rows.png`, `09_detected_columns.png` |
| `borderless_spatial` | same borderless row/column families; OCR word geometry is providing positions | OCR overlay + row/column overlays |
| `opencv_shaded_grid` | `visual_structure.shaded_grid.*` | `07a_visual_*shaded*`, `07b_visual_detected_regions.png` |
| `opencv_projection_grid` | `visual_structure.projection_grid.*` | `07a_visual_projection_*`, `07b_visual_detected_regions.png` |
| `opencv_anchor_projection` / `anchor_row_segmentation` | `borderless_table.row_detection.anchor_segmentation.*` | anchor/projection debug + rows/cells overlays |
| `easyocr_detection_spatial` | `visual_structure.text_detection_fallback.*`, `ocr.easyocr_detection.*`, then borderless row/column clustering | `07c_text_detection_boxes.png`, `08_detected_rows.png`, `09_detected_columns.png` |
| `none` | Do not randomly tune columns first. Follow `R9` / no-structure recovery and inspect threshold/lines/visual masks/text-detection boxes. | all structure-stage debug artifacts |

If the winning `structure_method` changes after a trial, **stop and reassess**. The new method may have different tuning parameters.


<a id="toc-4-1-2b-where-to-edit-parameters"></a>
## 4.1.2B Where exactly do I edit a parameter?

<p>A dotted parameter name in this README, such as bordered_table.vertical.merge_gap_px, represents a path within the configuration, not a literal line written in that exact form.</p>

For example:

```text
bordered_table.vertical.merge_gap_px
```

means:

```yaml
bordered_table:
  vertical:
    merge_gap_px: 12
```

The dots describe the nesting level:

```text
bordered_table
    ↓
vertical
    ↓
merge_gap_px
```

---

### A. Change the project-wide default

Use:

```text
configs/default.yaml
```

<p>Make changes here when the new value is a suitable general default for most future PDFs, not merely a single document.</p>

Example:

```yaml
bordered_table:
  vertical:
    merge_gap_px: 12
```

Change only the value:

```yaml
bordered_table:
  vertical:
    merge_gap_px: 16
```

Do **not** rename the key unless the code/config schema itself changes.

---

### B. Change one PDF only

After the first run, the pipeline generates a run config such as:

```text
outputs/Account_Statement_scanned.run_config.json
```

Use this file for PDF-specific tuning.

<p>If a problem affects only one PDF, do not change default.yaml for that document. Adjust its JSON instead to avoid affecting other PDFs.</p>

Inside the generated JSON, edit the parameter under:

```json
{
  "config": {
    "bordered_table": {
      "vertical": {
        "merge_gap_px": 16
      }
    }
  }
}
```

The same dotted path:

```text
bordered_table.vertical.merge_gap_px
```

becomes:

```text
config
└── bordered_table
    └── vertical
        └── merge_gap_px
```

---

### C. Change one page only

If most pages are correct and only one page needs a different value, use `page_overrides`.

Example:

```text
Page 11 only needs:
bordered_table.vertical.merge_gap_px = 18
```

Use:

```yaml
page_overrides:
  11:
    bordered_table:
      vertical:
        merge_gap_px: 18
```

or inside the generated run-config JSON:

```json
{
  "config": {
    "page_overrides": {
      "11": {
        "bordered_table": {
          "vertical": {
            "merge_gap_px": 18
          }
        }
      }
    }
  }
}
```

<p>In this example, the global value remains 12, while only page 11 uses 18.</p>

---

### D. Which file should I use?

```text
Need to change a parameter
          │
          ├── Good default for most future PDFs?
          │        ↓
          │   configs/default.yaml
          │
          ├── Only this PDF?
          │        ↓
          │   outputs/<pdf_name>.run_config.json
          │
          └── Only one/few pages?
                   ↓
              page_overrides
```

<p>Project rule: general changes belong in default.yaml; file-specific changes belong in run_config.json; page-specific changes belong in page_overrides.</p>

---

### E. How to find any dotted parameter quickly

Suppose the README tells you to tune:

```text
bordered_table.cells.minimum_width_px
```

Search in `default.yaml` for the last key:

```text
minimum_width_px
```

Then confirm the nesting is:

```yaml
bordered_table:
  cells:
    minimum_width_px: 15
```

Another example:

```text
visual_structure.shaded_grid.minimum_component_width_px
```

means:

```yaml
visual_structure:
  shaded_grid:
    minimum_component_width_px: 40
```

Another example:

```text
ocr.easyocr_detection.text_threshold
```

means:

```yaml
ocr:
  easyocr_detection:
    text_threshold: 0.55
```

---

### F. Recommended tuning workflow

<p>Do not change multiple values at once. Follow these steps to know exactly which parameter fixed the problem.</p>

```text
1. Run one representative page with --debug.
2. Read structure_method.
3. Open the matching method section in this README.
4. Identify the symptom/error.
5. Select ONE parameter or ONE closely related parameter family.
6. Edit:
      default.yaml          → project-wide
      run_config.json       → one PDF
      page_overrides        → one page
7. Rerun the same page.
8. Compare rows, columns, crops, overlays, and structure_method.
9. Keep the change only if the result moved in the correct direction.
10. If the error changes direction, stop increasing/decreasing that value and reassess.
```

---

### G. Example: broken vertical line merges two columns

Log/debug result:

```text
structure_method = bordered_grid
```

Visible symptom:

```text
Two real columns were merged because one vertical border is broken.
```

Relevant parameter:

```text
bordered_table.vertical.merge_gap_px
```

Current value:

```yaml
bordered_table:
  vertical:
    merge_gap_px: 12
```

First trial:

```yaml
bordered_table:
  vertical:
    merge_gap_px: 16
```

Then rerun only the affected page.

If the border reconnects and the correct column appears, keep the value.

If unrelated vertical fragments start joining, the value became too high. Reduce it.

---

### H. Example: two real close columns are merged

Relevant parameters may be:

```text
bordered_table.column_merge_tolerance_px
borderless_table.column_detection.x_tolerance_px
borderless_table.column_detection.minimum_column_gap_px
```

But **do not change all three**.

First check `structure_method`.

If:

```text
structure_method = bordered_grid
```

start with:

```text
bordered_table.column_merge_tolerance_px
```

If:

```text
structure_method = native_digital_spatial
```

or:

```text
structure_method = easyocr_detection_spatial
```

start with the borderless spatial column parameters instead.

<p>The same apparent error can require entirely different parameters depending on structure_method. Select parameters based on both the symptom and the method used to construct the structure.</p>

---

### I. Do not edit the reference file during normal tuning

Keep:

```text
configs/default_v3.2.0.reference.yaml
```

as a clean reference copy.

Do not use it as the normal working config.

Use:

```text
configs/default.yaml
```

for active project-wide defaults.

<p>The reference file is only for comparing with and recovering the original v3.2.0 settings. During everyday work, edit default.yaml or that PDF's run config.</p>

---

<a id="toc-4-1-3-structure-method-explained"></a>
## 4.1.3 Simple explanation of each `structure_method` + its parameters

<p>structure_method does not describe the PDF type; it describes the method that actually succeeded in constructing the page's rows, columns, and cells. Inspect it before tuning. The following tables map each method to the real v3.2.0 default.yaml parameters and explain adjustment directions.</p>

> **Baseline note:** The values below are the v3.2.0 defaults. `default.yaml` was verified to be semantically identical to `default_v3.2.0.reference.yaml` before the validated baseline run. The fixes documented in Section 15 were code-level generic fixes; the validated E2E was rerun without PDF-specific parameter tuning.

> **Tuning rule:** Change **one parameter family at a time**, rerun one representative page, compare debug outputs, and stop when the structure matches the source. Do not continue increasing/decreasing a value after the error changes direction.

---

### `bordered_grid`

<p>A table with clear ruling lines and boundaries. The system detected horizontal and vertical lines forming a grid, then used their intersections to construct rows, columns, and cells.</p>

**Think of it as:** `visible table lines → grid → cells`.

#### Parameters used by `bordered_grid`

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `bordered_table.enabled` | `true` | Enables the classic ruled-grid detector. | Keep `true` unless deliberately disabling this method. |
| `bordered_table.minimum_region_area_ratio` | `0.01` | Smallest page-area ratio accepted as a table region. | **Lower** if a real small table is ignored; **raise** if small non-table regions are accepted. |
| `bordered_table.horizontal.kernel_width_ratio` | `0.03` | Length of the morphology probe used to find horizontal rules. | **Lower** for short/faint horizontal rules; **raise** to reject short false fragments. |
| `bordered_table.horizontal.kernel_height` | `1` | Thickness of the horizontal morphology kernel. | Usually keep `1`; raise only for unusually thick horizontal rules. |
| `bordered_table.horizontal.minimum_line_length_ratio` | `0.10` | Minimum horizontal line length relative to page width. | **Lower** if valid short lines disappear; **raise** if text/underlines become false rules. |
| `bordered_table.horizontal.merge_gap_px` | `12` | Reconnects broken horizontal line pieces. | **Raise** if a real rule is broken; **lower** if unrelated fragments get joined. |
| `bordered_table.vertical.kernel_height_ratio` | `0.03` | Length of the morphology probe used to find vertical rules. | **Lower** for short/faint vertical rules; **raise** to reject short false vertical marks. |
| `bordered_table.vertical.kernel_width` | `1` | Thickness of the vertical morphology kernel. | Usually keep `1`; raise only for unusually thick vertical rules. |
| `bordered_table.vertical.minimum_line_length_ratio` | `0.10` | Minimum vertical line length relative to page height. | **Lower** if valid short lines disappear; **raise** if noise becomes a separator. |
| `bordered_table.vertical.merge_gap_px` | `12` | Reconnects broken vertical line pieces. | **Raise** for broken vertical rules; **lower** if neighboring fragments join incorrectly. |
| `bordered_table.row_merge_tolerance_px` | `8` | Merges very close Y line positions into one row boundary. | **Raise** if one physical border appears twice; **lower** if two real close row boundaries are merged. |
| `bordered_table.column_merge_tolerance_px` | `8` | Merges very close X line positions into one column boundary. | **Raise** for duplicate/double detected borders; **lower** if two true close columns collapse together. |
| `bordered_table.intersections.minimum_area` | `3` | Minimum connected intersection size counted as a real line crossing. | **Lower** for very faint intersections; **raise** if tiny noise intersections inflate confidence. |
| `bordered_table.cells.minimum_width_px` | `15` | Rejects cells narrower than this. | **Lower** if narrow real columns disappear; **raise** to filter tiny false cells. |
| `bordered_table.cells.minimum_height_px` | `10` | Rejects cells shorter than this. | **Lower** for short real rows; **raise** to filter tiny false rows. |
| `bordered_table.cells.minimum_area_px` | `150` | Rejects cells below this pixel area. | **Lower** if small legitimate cells disappear; **raise** if tiny noise cells survive. |

<p>For example, if seven columns become six because a vertical line is broken, slightly increase bordered_table.vertical.merge_gap_px. If noise creates a false vertical line, increase vertical.minimum_line_length_ratio rather than changing all column settings.</p>

---

### `opencv_shaded_grid`

<p>The table was detected from cell shading or different backgrounds, not lines alone. This is particularly useful with gray or shaded cells and light separators missed by conventional line detection.</p>

**Think of it as:** `cell shading/background blocks → aligned grid → cells`.

#### Global parameters affecting this method

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `visual_structure.enabled` | `true` | Enables the generic visual structure engine. | Must remain `true` for shaded/projection methods. |
| `visual_structure.maximum_analysis_dimension` | `1800` | Internal analysis resolution cap. | **Raise** for tiny/fine cells at cost of RAM/time; **lower** for speed/memory. |
| `visual_structure.shaded_preference_min_confidence` | `0.45` | Confidence at which shaded-grid is preferred over projection-grid. | **Lower** if valid shaded detection is losing to projection; **raise** if false shaded detection is stealing pages. |

#### Shading sensitivity and cleanup

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `visual_structure.shaded_grid.enabled` | `true` | Enables shaded-cell detection. | Keep `true` when shaded/background cells are expected. |
| `background_percentile` | `95.0` | Estimate of page background brightness. | **Raise** to become more sensitive to light shading; **lower** if too much background/noise is selected. |
| `contrast_deltas` | `[6, 8, 10, 12]` | Several darkness differences tested below the background. | Add/use **smaller deltas** for very light shading; **larger deltas** for darker, stricter detection. |
| `blur_kernel_ratio` | `0.006` | Smooths local noise before detecting filled regions. | **Raise** to smooth noisy fills; **lower** if small cell boundaries become blurred together. |
| `opening_kernel_ratio` | `0.0025` | Morphological opening used to remove tiny noise. | **Raise** to remove more speckles; **lower** if small shaded cells are being erased. |

#### Component filtering

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `minimum_component_width_px` | `40` | Minimum absolute width of a shaded component. | **Lower** for narrow real cells; **raise** to reject narrow noise. |
| `minimum_component_width_ratio` | `0.02` | Minimum width relative to page width. | Same direction as `minimum_component_width_px`. |
| `minimum_component_height_px` | `25` | Minimum absolute component height. | **Lower** for short rows; **raise** to reject short noise blocks. |
| `minimum_component_height_ratio` | `0.01` | Minimum height relative to page height. | Same direction as `minimum_component_height_px`. |
| `minimum_component_fill_ratio` | `0.80` | How solid/filled a rectangle must be. | **Lower** for patchy/faded shading; **raise** if text/noise blobs are mistaken for cells. |
| `maximum_component_width_ratio` | `0.75` | Rejects components that are too wide. | **Raise** if a legitimate wide cell is rejected; **lower** to reject page-wide backgrounds/logos. |
| `maximum_component_height_ratio` | `0.60` | Rejects components that are too tall. | **Raise** for genuinely tall blocks; **lower** to reject large background regions. |
| `edge_exclusion_px` | `2` | Ignores components touching page edges. | **Lower** only if a valid table genuinely touches the page edge. |

#### Row/column alignment and table construction

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `row_start_tolerance_px` | `10` | Allowed Y difference when grouping shaded boxes into the same row. | **Raise** for slightly skewed/misaligned row starts; **lower** if neighboring rows merge. |
| `row_start_tolerance_ratio` | `0.012` | DPI/page-height aware row-start tolerance. | Same direction as the pixel tolerance. |
| `minimum_columns` | `2` | Minimum number of blocks required for a row to be table-like. | Increase only if many non-table 2-column layouts are falsely accepted. Values below `2` have no practical effect. |
| `minimum_rows` | `2` | Minimum aligned rows needed to form a table. | **Raise** to reject tiny false tables; keep `2` for short real tables. |
| `maximum_columns` | `16` | Safety cap on detected columns. | **Lower** if text fragments cause severe over-segmentation; **raise** only for genuinely very wide tables. |
| `x_alignment_tolerance_px` | `12` | Allowed X drift when matching columns across rows. | **Raise** if skew/scan drift prevents matches; **lower** if neighboring columns are treated as aligned. |
| `x_alignment_tolerance_ratio` | `0.012` | Page-width-aware X alignment tolerance. | Same direction as the pixel value. |
| `minimum_row_match_ratio` | `0.35` | Fraction of seed columns a row must match. | **Lower** for irregular/sparse rows; **raise** to reject inconsistent rows. |
| `minimum_row_matches` | `2` | Absolute minimum matching columns per row. | **Lower** only for very sparse tables; **raise** for stronger structural consistency. |
| `minimum_column_width_px` | `12` | Removes inferred columns narrower than this. | **Lower** if a true narrow column vanishes; **raise** to remove tiny ghost columns. |
| `outer_padding_px` | `0` | Expands first/last table boundaries. | **Raise** if crops cut content at outer table edges; keep small to avoid neighboring content. |

#### Multi-table splitting and confidence

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `table_split_gap_factor` | `2.75` | Vertical gap multiplier used to split separate table blocks. | **Lower** if two tables are wrongly merged; **raise** if one table is split. |
| `table_split_gap_page_ratio` | `0.18` | Page-height based minimum split gap. | **Lower** to split more aggressively; **raise** to keep large-spaced rows together. |
| `table_split_gap_height_factor` | `4.0` | Row-height based split threshold. | **Lower** if separate blocks stay merged; **raise** for very tall/wrapped rows. |
| `confidence_rows_target` | `4` | Number of rows needed to reach full row-count confidence contribution. | **Lower** for valid very short tables; **raise** if tiny patterns get overconfident. |

<p>For example, if small gray cells are missed, gradually reduce minimum_component_width_px and/or minimum_component_height_px. If an entire background becomes one huge cell, increase contrast_deltas or tighten maximum_component_*_ratio.</p>

---

### `opencv_projection_grid`

<p>The system reconstructed the table from the visual distribution of ink and text in the image. It does not need to recognize words; instead, it groups ink components by position, gaps, and repeated alignment to infer rows and columns.</p>

**Think of it as:** `ink density + whitespace/alignment → rows/columns → cells`.

#### Line removal and component preparation

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `visual_structure.projection_grid.enabled` | `true` | Enables projection-based structure detection. | Keep `true` for scanned borderless fallback. |
| `remove_horizontal_line_ratio` | `0.08` | Length threshold for removing long horizontal rules before text grouping. | **Lower** if medium table rules remain and become text blocks; **raise** if real text strokes are being removed. |
| `remove_vertical_line_ratio` | `0.08` | Length threshold for removing long vertical rules. | Same logic as horizontal. |
| `close_width_px` | `4` | Horizontal closing that joins nearby text fragments. | **Raise** if one word/cell is fragmented; **lower** if adjacent columns merge. |
| `close_height_px` | `1` | Vertical closing of nearby fragments. | **Raise** very cautiously for fragmented glyphs; **lower** if separate text lines merge. |
| `minimum_text_component_area_px` | `8` | Minimum connected foreground area. | **Lower** for tiny/faint characters; **raise** to reject speckles/noise. |
| `minimum_text_component_height_px` | `3` | Minimum component height. | **Lower** for tiny text; **raise** to reject very small noise. |
| `maximum_text_component_height_ratio` | `0.08` | Rejects components that are too tall. | **Raise** for large-font/tall text; **lower** to reject logos/vertical artifacts. |
| `maximum_text_component_width_ratio` | `0.55` | Rejects components that are too wide. | **Raise** for legitimate long text blocks; **lower** if page furniture/lines survive. |

#### Row grouping

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `baseline_tolerance_px` | `4` | Allowed Y-center difference within one row. | **Raise** if one logical row is split because baselines drift; **lower** if neighboring rows merge. |
| `baseline_tolerance_height_ratio` | `0.8` | Tolerance scaled by typical text height. | **Raise** for irregular font heights/skew; **lower** for tightly spaced rows. |
| `baseline_tolerance_page_ratio` | `0.001` | Small page-height based minimum tolerance. | Usually leave stable; adjust only for unusually large/small render scales. |
| `intra_block_merge_gap_px` | `10` | Gap allowed when merging components inside one text block. | **Raise** to join words/fragments in one cell; **lower** if separate columns merge. |
| `intra_block_merge_height_ratio` | `1.5` | Merge gap scaled by text height. | Same direction as `intra_block_merge_gap_px`. |

#### Grid alignment, splitting, and boundaries

The following parameters behave the same way as in `opencv_shaded_grid`:

| Parameter | Default | Typical tuning direction |
|---|---:|---|
| `minimum_columns` | `2` | Raise to reject simple non-table layouts. |
| `minimum_rows` | `2` | Raise to reject tiny false tables. |
| `maximum_columns` | `16` | Lower if over-segmented; raise only for real wide tables. |
| `x_alignment_tolerance_px` | `12` | Raise for drift/skew; lower if nearby columns collapse. |
| `x_alignment_tolerance_ratio` | `0.012` | Same direction as above. |
| `minimum_row_match_ratio` | `0.35` | Lower for irregular rows; raise for stronger consistency. |
| `minimum_row_matches` | `2` | Lower for sparse rows; raise to reject weak rows. |
| `table_split_gap_factor` | `2.75` | Lower to split more; raise to keep one table together. |
| `table_split_gap_page_ratio` | `0.18` | Lower to split at smaller gaps; raise for large row spacing. |
| `table_split_gap_height_factor` | `4.0` | Lower to split more; raise for tall/wrapped rows. |
| `confidence_rows_target` | `4` | Lower for short valid tables; raise to reduce confidence on tiny patterns. |
| `outer_padding_px` | `0` | Raise if edge content is cut. |
| `minimum_column_width_px` | `12` | Lower to keep narrow true columns; raise to remove ghost columns. |

<p>For example, if a long Description is split into false columns, intra_block_merge_gap_px may be too small or x_alignment_tolerance inappropriate. If two real columns merge, reverse the adjustment rather than continuously increasing merge tolerances.</p>

---

### `easyocr_detection_spatial`

<p>Standard visual methods were insufficient, so EasyOCR/CRAFT was used to locate text without decoding it. In crop-only mode, only the detector is loaded with recognizer=false, and its bounding boxes are grouped spatially to construct rows, columns, and cells.</p>

**Think of it as:** `where text exists → spatial clustering → rows/columns → cells`.

#### Fallback activation parameters

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `visual_structure.text_detection_fallback.enabled` | `true` | Allows Detection-only fallback when visual structure produced no rows. | Keep `true` if you want CRAFT fallback in crop-only. |
| `visual_structure.text_detection_fallback.engine` | `easyocr` | Detector backend. | Keep `easyocr` in the current implementation. |
| `visual_structure.text_detection_fallback.minimum_boxes` | `4` | Minimum text boxes required before attempting spatial table reconstruction. | **Lower** for very sparse tables; **raise** if a few random text boxes cause false structure. |
| `visual_structure.text_detection_fallback.structural_confidence` | `0.60` | Fallback confidence used when a stronger region confidence is unavailable. | Usually leave stable; lower/raise only for downstream confidence behavior, not detection sensitivity. |

#### CRAFT / EasyOCR detection-only parameters

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `ocr.easyocr_detection.min_size` | `5` | Minimum detected text size. | **Lower** for tiny text; **raise** to ignore tiny noise. |
| `text_threshold` | `0.55` | Main CRAFT text confidence threshold. | **Lower** for faint/missed text; **raise** if many false boxes appear. |
| `low_text` | `0.30` | Lower-confidence text-region threshold used by CRAFT. | **Lower** to recover faint text; **raise** to reduce weak/noisy regions. |
| `link_threshold` | `0.30` | Controls linking neighboring character/text regions. | **Lower** generally links more weak regions; **raise** if unrelated regions are being connected. |
| `canvas_size` | `2560` | Maximum detector canvas size. | **Raise** for very small text if RAM/time allows; **lower** to reduce memory/time. |
| `mag_ratio` | `1.0` | Magnifies input before detection. | **Raise** (for example `1.2–1.5`) for tiny text; increases CPU/RAM/time. |
| `slope_ths` | `0.10` | Allowed slope difference when grouping boxes. | **Raise** for skewed/slanted text; **lower** to prevent unrelated sloped boxes merging. |
| `ycenter_ths` | `0.50` | Allowed vertical-center difference for grouping. | **Raise** for imperfect baselines; **lower** if adjacent rows group together. |
| `height_ths` | `0.50` | Allowed relative height difference during grouping. | **Raise** for mixed font heights; **lower** for stricter grouping. |
| `width_ths` | `0.50` | Horizontal-distance tolerance used in grouping. | **Raise** if words from one text region stay fragmented; **lower** if columns join. |
| `add_margin` | `0.10` | Margin added around detected text boxes. | **Raise** if boxes cut text edges; **lower** if neighboring cells overlap. |
| `binary_threshold` | `0.20` | Binary threshold passed to the detector when supported. | Tune only after visual inspection of `07c_text_detection_boxes.png`. |
| `bbox_min_score` | `0.20` | Minimum box score when supported by the installed EasyOCR API. | **Lower** for weak boxes; **raise** to remove low-quality boxes. |
| `bbox_min_size` | `3` | Minimum accepted detection box size when supported. | **Lower** for tiny text; **raise** to filter tiny artifacts. |
| `max_candidates` | `0` | Candidate cap (`0` means no explicit cap in this config). | Set a positive cap only for pathological/noisy pages or memory control. |
| `structural_box_confidence` | `0.60` | Confidence assigned to detection-only boxes for downstream structure scoring. | Does **not** make CRAFT more/less sensitive; change only if confidence scoring needs calibration. |

#### After CRAFT finds boxes: spatial clustering parameters

CRAFT only says **where text exists**. The boxes are then passed through the same borderless spatial clustering logic:

| Parameter | Default | Typical tuning direction |
|---|---:|---|
| `borderless_table.row_detection.baseline_tolerance_px` | `8` | Raise if one row splits; lower if adjacent rows merge. |
| `borderless_table.row_detection.y_overlap_ratio` | `0.50` | Lower makes row grouping more permissive; raise makes it stricter. |
| `borderless_table.row_detection.continuation_line_gap_px` | `18` | Raise to merge wrapped continuation lines more often; lower if separate rows merge. |
| `borderless_table.column_detection.x_tolerance_px` | `15` | Raise if same-column X positions drift; lower if nearby columns merge. |
| `x_tolerance_word_height_ratio` | `1.0` | Raise for high-DPI / large text alignment drift; lower for tighter X clustering. |
| `maximum_x_tolerance_page_ratio` | `0.05` | Safety cap on X tolerance relative to page width. | Lower to prevent excessive merging; raise only when page-scale drift is extreme. |
| `minimum_column_gap_px` | `20` | Higher merges close X clusters into fewer columns; lower preserves close separate columns. |
| `minimum_column_support_rows` | `3` | Raise to require a column alignment across more rows; lower for short/sparse columns. |
| `minimum_column_support_ratio` | `0.20` | Raise to suppress accidental prose alignments; lower if a legitimate sparse column is lost. |
| `expected_columns` | `null` | Leave `null` for generic operation; set only when the document schema is known and stable. |
| `maximum_columns` | `12` | Lower to suppress overcounting; raise for genuinely wider tables. |
| `borderless_table.clustering.min_samples` | `1` | Raise to reject singleton/noisy alignments; keep `1` for sparse documents. |

<p>Important: with this method, do not start changing borderless_table.column_detection.* if 07c_text_detection_boxes.png is already missing boxes. Fix CRAFT detection first, then row/column clustering.</p>

---

### `native_digital_spatial`

<p>This digital PDF already contains text with coordinates. PyMuPDF supplies words and bounding boxes directly, allowing spatial clustering without OCR.</p>

**Think of it as:** `native PDF word coordinates → spatial clustering → cells`.

#### Row parameters

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `borderless_table.enabled` | `true` | Enables borderless spatial reconstruction. | Must remain `true`. |
| `row_detection.baseline_tolerance_px` | `8` | Maximum baseline-center distance used to group words into one row. | **Raise** if one row splits; **lower** if nearby rows merge. |
| `row_detection.y_overlap_ratio` | `0.50` | Minimum Y-overlap ratio that can also group words into one row. | **Lower** = more permissive grouping; **raise** = stricter separation. |
| `row_detection.merge_multiline_rows` | `true` | Allows continuation lines to merge into previous records. | Set `false` only when multiline merging is consistently wrong. |
| `row_detection.continuation_line_gap_px` | `18` | Maximum vertical gap for a continuation line merge. | **Raise** for wrapped text that remains split; **lower** if two records merge. |
| `row_detection.anchor_type` | `auto` | Anchor heuristic for continuation merging: `auto`, `date`, `amount`. | Use `date` or `amount` only when that anchor is reliably present per logical row. |
| `row_detection.anchor_x_range_ratio` | `null` | Restricts anchor search to an X range. | Leave `null` generically; set only when a stable anchor column is known. |

#### Column parameters

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `column_detection.x_tolerance_px` | `15` | Base DBSCAN X alignment radius. | **Raise** if one logical column fragments due X drift; **lower** if adjacent columns merge. |
| `x_tolerance_word_height_ratio` | `1.0` | Scales X tolerance from measured word height. | **Raise** for high-DPI drift; **lower** for tight column layouts. |
| `maximum_x_tolerance_page_ratio` | `0.05` | Caps X tolerance relative to page width. | **Lower** if broad merging occurs; raise only for extreme page drift. |
| `minimum_column_gap_px` | `20` | Minimum separation between retained X centers. | **Raise** = merge close centers → fewer columns; **lower** = preserve close centers → more columns. |
| `minimum_column_support_rows` | `3` | Minimum rows supporting a repeated X alignment. | **Raise** to reject random prose positions; **lower** for very short tables. |
| `minimum_column_support_ratio` | `0.20` | Required proportion of rows supporting a column. | **Raise** to reduce ghost columns; **lower** if sparse real columns disappear. |
| `expected_columns` | `null` | Forces an exact column count using quantile centers. | Keep `null` for universal behavior; set only when the schema is genuinely known. |
| `maximum_columns` | `12` | Maximum retained columns. | **Lower** if severe overcounting; **raise** for genuine tables with >12 columns. |
| `clustering.min_samples` | `1` | Minimum samples in DBSCAN X clusters. | **Raise** to suppress singleton X noise; keep low for sparse pages. |

<p>If columns 3 and 4 merge in a valid digital PDF, gradually decrease minimum_column_gap_px and/or x_tolerance_px. If Description creates false columns, increase minimum_column_support_rows or minimum_column_support_ratio.</p>

---

### `borderless_spatial`

<p>This borderless table is reconstructed from word positions. Its geometry resembles native_digital_spatial, but word boxes may originate from OCR recognition rather than native text.</p>

**Think of it as:** `recognized/native word positions without ruling lines → row/column clustering`.

#### Parameters used by `borderless_spatial`

This method uses the **same `borderless_table.row_detection.*`, `borderless_table.column_detection.*`, and `borderless_table.clustering.*` parameters listed under `native_digital_spatial`**.

When the word boxes came from full OCR, OCR box quality can also affect the structure:

| Parameter family | Why it matters |
|---|---|
| `ocr.easyocr.text_threshold`, `low_text`, `link_threshold` | Controls which text regions survive OCR detection. |
| `ocr.easyocr.width_ths`, `ycenter_ths`, `height_ths` | Controls how EasyOCR groups detected pieces before returning word boxes. |
| `ocr.easyocr.modes.*` | Per-mode settings for `sparse`, `row`, `single_line`, etc. |

<p>If word boxes are wrong or missing, fix OCR detection or recognition first. If word boxes are correct but rows or columns are wrong, tune only borderless spatial parameters.</p>

---

### `opencv_anchor_projection` / `anchor_row_segmentation`

<p>Repeated anchors identify the start or center of each record. An anchor can be an amount, date, or digit line, derived from projection or OCR words according to candidate_source. This works best when every logical row has a stable anchor.</p>

**Think of it as:** `repeated anchor → row bands → configured/inferred columns → cells`.

#### Core anchor parameters

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `anchor_segmentation.enabled` | `false` | Enables this stronger row segmentation path. | Turn on only when the page truly has a stable per-row anchor pattern. |
| `boundary_mode` | `midpoint` | Row boundary placement: `midpoint` or `anchor_start`. | Use `midpoint` for balanced row bands; `anchor_start` when anchors reliably mark row starts. |
| `anchor_type` | `amount` | Anchor type: `amount`, `date`, `digit_line`. | Choose the value that is consistently present once per logical row. |
| `candidate_source` | `roi_ocr` | Anchor source: `roi_ocr`, `full_page_words`, `projection`. | For no-recognition visual cropping prefer `projection`; use word/OCR sources only when allowed/needed. |
| `roi_ratio` | `[0.0, 0.25, 0.20, 0.90]` | ROI used by `roi_ocr`. | Move/resize only when the anchor column is known and stable. |
| `ocr_mode` | `sparse` | OCR mode used by ROI anchor extraction. | Change only for OCR-based anchor sources. |
| `minimum_confidence` | `0.15` | Minimum OCR anchor confidence. | **Lower** for faint but valid anchors; **raise** to reject weak false anchors. |
| `minimum_digits` | `1` | Minimum digits in an anchor candidate. | **Raise** if random single digits become anchors; lower only for minimal identifiers. |
| `minimum_anchors` | `3` | Minimum anchors required to accept segmentation. | **Lower** for very short tables; **raise** to demand stronger repetition. |
| `minimum_anchor_gap_px` | `20` | Minimum vertical distance between anchors. | **Lower** for tightly spaced rows; **raise** if multiple anchors within one row are counted separately. |
| `default_row_height_px` | `80` | Fallback row height when the last boundary is not obvious. | Adjust toward observed row height if the final row crop is too tall/short. |
| `table_x0_ratio` | `0.0` | Left table crop boundary as page ratio. | Increase only to exclude known left-side non-table content. |
| `table_x1_ratio` | `1.0` | Right table crop boundary as page ratio. | Decrease only to exclude known right-side non-table content. |
| `column_boundaries_ratio` | `null` | Optional explicit column boundary ratios. | Keep `null` for generic operation; set only for a confirmed stable layout. |
| `expected_columns` | `1` | Expected columns when explicit anchor segmentation builds rows. | Set only after the table schema is known; do not force it during generic discovery. |

#### Projection anchor parameters

These matter when `candidate_source: projection`:

| Parameter | Default | What it controls | Typical tuning direction |
|---|---:|---|---|
| `projection_vertical_kernel_ratio` | `0.05` | Removes/isolates long vertical structures before anchor-band detection. | Lower for shorter vertical artifacts; raise if text is being removed as a line. |
| `projection_close_width_px` | `5` | Horizontal closing within projection candidates. | Raise for fragmented anchors; lower if adjacent content merges. |
| `projection_close_height_px` | `2` | Vertical closing within projection candidates. | Raise cautiously for broken anchor strokes; lower if nearby rows connect. |
| `projection_ink_threshold_ratio` | `0.02` | Required ink density for an anchor band. | Lower for faint anchors; raise to suppress weak noise bands. |
| `projection_min_ink_px` | `2` | Absolute minimum ink count. | Lower for tiny anchors; raise for noise rejection. |
| `projection_min_band_height_px` | `3` | Minimum candidate-band height. | Lower for tiny text; raise to reject thin noise. |
| `projection_merge_gap_px` | `40` | Merges nearby projection bands. | Raise if one anchor is fragmented into multiple bands; lower if two rows merge. |
| `projection_confidence` | `0.70` | Confidence assigned to projection anchors. | Mostly scoring; does not directly make pixel detection more sensitive. |

#### Optional `cell_ocr` subsection

`anchor_segmentation.cell_ocr.*` is **not required to build row geometry**. It is an optional recognition refinement after row/cell crops exist. Keep it disabled in pure crop-only workflows unless deliberately testing cell recognition.

---

### `none`

<p>No method produced a trustworthy page structure. There is no single parameter family called none; identify the stage that prevented all methods from succeeding.</p>

**Think of it as:** `no reliable structure was built yet`.

#### First parameters/gates to check — in this order

| Check | Default | What to verify |
|---|---:|---|
| `bordered_table.enabled` | `true` | Classic ruled-grid detector is not accidentally disabled. |
| `borderless_table.enabled` | `true` | Spatial word-box reconstruction is available. |
| `visual_structure.enabled` | `true` | Visual shaded/projection fallbacks are enabled. |
| `visual_structure.shaded_grid.enabled` | `true` | Shaded-cell detector is available. |
| `visual_structure.projection_grid.enabled` | `true` | Projection/ink detector is available. |
| `visual_structure.text_detection_fallback.enabled` | `true` | Crop-only may use CRAFT detection-only if visual methods fail. |
| `text_detection_fallback.minimum_boxes` | `4` | If CRAFT found fewer than this, no spatial reconstruction attempt occurs. |
| `render.default_dpi` | `400` | Increase toward `500–600` only if tiny/faint geometry is genuinely unresolved. |
| `preprocessing.threshold.enabled` | `true` | Binary structure image is being produced. |
| `preprocessing.threshold.method` | `adaptive_gaussian` | Switch only after inspecting the threshold debug image. |
| `preprocessing.threshold.block_size` | `31` | Larger handles broader illumination variation; too large can erase local detail. |
| `preprocessing.threshold.c` | `12` | Changes adaptive threshold aggressiveness; tune using the threshold image, not blindly. |
| `preprocessing.threshold.invert` | `true` | Verify foreground/background polarity is correct. |
| `preprocessing.deskew.enabled` | `true` | Important when row/column lines drift due page rotation. |

#### `none` troubleshooting sequence

```text
1. Open the debug original/preprocessed/threshold images.
2. Check horizontal + vertical line masks.
3. Check shaded/projection masks.
4. Check 07c_text_detection_boxes.png if text detection ran.
5. Identify the first stage where real page structure disappears.
6. Tune only that detector's parameters.
7. Rerun one page.
8. If structure_method becomes a real method, move to that method's table above.
```

<p>Do not adjust x_tolerance_px because there are zero columns when structure_method = none. Column clustering did not run. First determine why there are no valid rows, boxes, or grid.</p>

---

### Quick decision rule

<p>When output is wrong, inspect structure_method and tune its own parameters. If structure_method changes after tuning, reevaluate because a different detector now wins.</p>

```text
bordered_grid
→ bordered_table.*

opencv_shaded_grid
→ visual_structure.shaded_grid.*

opencv_projection_grid
→ visual_structure.projection_grid.*

easyocr_detection_spatial
→ visual_structure.text_detection_fallback.*
→ ocr.easyocr_detection.*
→ borderless_table row/column clustering

native_digital_spatial
→ borderless_table.row_detection.*
→ borderless_table.column_detection.*
→ borderless_table.clustering.*

borderless_spatial
→ same borderless spatial parameters
→ plus OCR word-box quality if OCR supplied the words

opencv_anchor_projection / anchor_row_segmentation
→ borderless_table.row_detection.anchor_segmentation.*

none
→ diagnose preprocessing + detector gates first
→ do not randomly tune column parameters
```

<a id="toc-4-2-column-errors"></a>
## 4.2 Column Detection Errors

<p>Column detection errors concern column count, boundaries, and consistency between rows and pages. Start here when values occupy incorrect columns or the detected column count is wrong.</p>

### C1 — Columns merged / undercounted

<p>Merged columns or too few columns occur when adjacent columns are treated as one. The output has fewer columns than the source and combines their values. Usually reduce merging tolerance or adjust separation according to the method.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Fewer columns; two fields jammed together |
| **Current-code cause** | Borderless DBSCAN/center merge too aggressive |
| **First resolution** | Decrease `borderless_table.column_detection.x_tolerance_px` and/or `minimum_column_gap_px`; if using anchor geometry, correct `column_boundaries_ratio`. |
| **Status** | `Config` |

<!-- tuning-recipe:C1 -->
#### Parameter tuning recipe

<p>For too few detected columns, gradually reduce merge tolerances to avoid combining neighboring column centers.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `borderless_table.column_detection.x_tolerance_px` | 15 | 12 | 9 | `native_digital_spatial` / `borderless_spatial` |
| `borderless_table.column_detection.minimum_column_gap_px` | 20 | 15 | 10 | Same borderless methods; smaller value preserves close real columns |
| `visual_structure.projection_grid.intra_block_merge_gap_px` | 10 | 8 | 6 | `opencv_projection_grid` when two close column blocks are fused |
| `visual_structure.projection_grid.x_alignment_tolerance_px` | 12 | 10 | 8 | Projection rows cross-match neighboring columns |
| `visual_structure.shaded_grid.x_alignment_tolerance_px` | 12 | 10 | 8 | `opencv_shaded_grid` cross-matches adjacent cells |
| `bordered_table.column_merge_tolerance_px` | 8 | 6 | 4 | `bordered_grid` when two close vertical boundaries are merged |

**Success criterion:** The detected column count matches the source on at least 3 representative rows, and no real column becomes fragmented.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### C2 — Columns split / overcounted

<p>A split column or too many columns occurs when a gap inside one column is mistaken for a separator. Extra empty or nearly empty columns appear, or one logical column is split.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Extra empty/near-empty columns; one field fragmented |
| **Current-code cause** | Wide internal spaces create multiple repeated X centers |
| **First resolution** | Increase `x_tolerance_px` or `minimum_column_gap_px`; raise support thresholds; for ruled tables prefer bordered detection. |
| **Status** | `Config` |

<!-- tuning-recipe:C2 -->
#### Parameter tuning recipe

<p>For too many columns, reverse C1: make grouping more permissive to merge duplicate or false centers without merging real columns.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `borderless_table.column_detection.x_tolerance_px` | 15 | 18 | 22 | Nearby X centers should cluster together |
| `borderless_table.column_detection.minimum_column_gap_px` | 20 | 25 | 30 | Merge duplicate supported centers |
| `visual_structure.projection_grid.intra_block_merge_gap_px` | 10 | 12 | 15 | One logical text block is split into fragments |
| `bordered_table.column_merge_tolerance_px` | 8 | 10 | 12 | Duplicate close vertical boundaries |
| `bordered_table.vertical.minimum_line_length_ratio` | 0.10 | 0.12 | 0.15 | Ghost columns are caused by short text/noise fragments misread as vertical rules |

**Success criterion:** Extra/ghost columns disappear while every real source column remains separate.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### C3 — Column boundary drift across rows

<p>Drifting column boundaries occur when positions change between rows, often due to skew or rotation. Values seem to shift between adjacent columns.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Values zigzag between adjacent columns |
| **Current-code cause** | Skew/rotation shifts X coordinates |
| **First resolution** | Ensure `preprocessing.deskew.enabled=true`; lower `minimum_detected_angle` if real small skew is ignored; verify 08_deskewed*. |
| **Status** | `Config` |

<!-- tuning-recipe:C3 -->
#### Parameter tuning recipe

<p>Correct page skew before increasing column tolerance. Large tolerance can conceal skew in one row and break another.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `preprocessing.deskew.minimum_detected_angle` | 0.15 | 0.10 | 0.05 | Small real skew is being ignored |
| `preprocessing.deskew.maximum_angle` | 10.0 | 12.0 | 15.0 | Only if the measured real page skew exceeds the current cap |
| `visual_structure.*.x_alignment_tolerance_px` | 12 | 15 | 18 | Only for small residual drift after deskew is visually correct |

**Success criterion:** Column boundaries are vertically stable in `09_detected_columns.png`; values no longer zigzag between adjacent columns.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### C4 — No columns detected in borderless table

<p>Missing columns in a borderless table occur when the detector returns a single column or cannot build stable columns. Common causes are insufficient repeated X-position support or missing OCR words in a geometry-only mode.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | 0/1 logical column |
| **Current-code cause** | Stable repeated X evidence is too weak, or the visual projection/shaded-grid candidate cannot form a repeatable grid. Crop-only no longer requires OCR words. |
| **First resolution** | Inspect `07a_visual_*` and `09_detected_columns.png`. For native/digital geometry tune `borderless_table.column_detection.*`; for scanned borderless tune `visual_structure.projection_grid.intra_block_merge_*`, X-alignment, and row-support controls. |
| **Status** | `Supported; Config` |

<!-- tuning-recipe:C4 -->
#### Parameter tuning recipe

<p>In borderless tables, missing columns signal insufficient X evidence or strict row and column acceptance conditions. Relax the appropriate criteria based on structure_method, not all methods simultaneously.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `borderless_table.column_detection.minimum_column_support_rows` | 3 | 2 | 1 | Native/OCR spatial method has too few repeated rows; value 1 is last-resort and noise-prone |
| `borderless_table.column_detection.minimum_column_support_ratio` | 0.20 | 0.15 | 0.10 | Real columns are present in only a minority of sparse rows |
| `visual_structure.projection_grid.minimum_row_match_ratio` | 0.35 | 0.30 | 0.25 | Projection rows contain many blanks |
| `visual_structure.projection_grid.x_alignment_tolerance_px` | 12 | 15 | 18 | Same real column drifts slightly across rows |
| `visual_structure.text_detection_fallback.minimum_boxes` | 4 | 3 | 2 | Crop-only sparse table reaches detection-only fallback |
| `ocr.easyocr_detection.text_threshold` | 0.55 | 0.50 | 0.45 | CRAFT overlay contains too few real text boxes |

**Success criterion:** At least 2 stable columns are reconstructed and the same boundaries repeat across multiple rows.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### C5 — False column boundary from noise

<p>Noise can create a false column boundary when watermarks, stray lines, or scan artifacts are mistaken for separators, causing an extra mostly empty column.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Ghost column mostly empty |
| **Current-code cause** | Watermark/noise creates repeated X evidence or false line |
| **First resolution** | Denoise/morphology; raise column support; for bordered raise minimum line length and/or kernel ratio. |
| **Status** | `Config` |

<!-- tuning-recipe:C5 -->
#### Parameter tuning recipe

<p>For false columns, increase evidence requirements instead of manually deleting columns. Require stronger row support or longer lines.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `borderless_table.column_detection.minimum_column_support_rows` | 3 | 4 | 5 | Ghost center has weak row support |
| `borderless_table.column_detection.minimum_column_support_ratio` | 0.20 | 0.30 | 0.40 | Reject low-support X centers |
| `borderless_table.column_detection.minimum_column_gap_px` | 20 | 25 | 30 | Merge very close duplicate centers |
| `bordered_table.vertical.minimum_line_length_ratio` | 0.10 | 0.15 | 0.20 | Noise/text fragments look like vertical rules |
| `ocr.easyocr_detection.text_threshold` | 0.55 | 0.60 | 0.65 | `easyocr_detection_spatial` is producing many weak/noisy boxes |

**Success criterion:** The ghost column disappears without reducing the real column count.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### C6 — Wrapped cell text becomes adjacent column

<p>Wrapped text moved into an adjacent column means the second line of a multiline cell was assigned elsewhere. Review row grouping before X tolerance and column boundaries.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Second line shifts into neighbor |
| **Current-code cause** | Unstable X inference plus multi-line grouping |
| **First resolution** | Increase `x_tolerance_px` carefully; use explicit boundaries for stable layouts; ensure row continuation merge is correct first. |
| **Status** | `Config` |

<!-- tuning-recipe:C6 -->
#### Parameter tuning recipe

<p>This often starts with row grouping rather than column detection. Associate the continuation line with its original row before tuning X.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `borderless_table.row_detection.continuation_line_gap_px` | 18 | 22 | 26 | Wrapped continuation line is incorrectly treated as a new row/column context |
| `borderless_table.row_detection.baseline_tolerance_px` | 8 | 10 | 12 | Words belonging to the same visual line are split |
| `visual_structure.projection_grid.intra_block_merge_gap_px` | 10 | 12 | 15 | Wrapped fragments inside one logical cell remain split horizontally |

**Success criterion:** Wrapped text remains in the same logical row/cell and does not create an adjacent-column value.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### C7 — Column count varies page to page

<p>Different page layouts can cause column counts to vary. Inspect pages independently and use page_overrides for distinct templates instead of imposing global fixed boundaries.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Later pages shifted/missing |
| **Current-code cause** | Fixed geometry reused where pages differ |
| **First resolution** | Core already re-detects per page by default. Do not reuse `column_boundaries_ratio` globally unless template is stable; use `page_overrides` for exceptions. |
| **Status** | `Workflow/config` |

<!-- tuning-recipe:C7 -->
#### Parameter tuning recipe

<p>Do not solve differing templates with one global value. Use page overrides for differing pages and keep the default generic.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `page_overrides.<page>...` | none | Add only the failing page/group | Keep global default unchanged | Best option when layouts genuinely differ |
| `borderless_table.column_detection.expected_columns` | null | Set exact count only in a page override | — | Use only when that page/template count is known with certainty |

**Success criterion:** Each template/page group is correct without degrading pages that were already correct.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### C8 — Numeric/text alignment inconsistency

<p>Numeric and text columns may differ in alignment, causing numeric columns to merge or split while textual columns succeed. Explicit boundaries or column-aware logic may be needed.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Numeric columns split/merge while text columns work |
| **Current-code cause** | Global X thresholds do not model alignment by semantic type |
| **First resolution** | Prefer explicit measured boundaries or anchor segmentation. Per-column gap thresholds are not implemented. |
| **Status** | `Code enhancement for per-column thresholds` |

<!-- tuning-recipe:C8 -->
#### Parameter tuning recipe

<p>Right-aligned numeric columns have different X centers. Use word-height-aware tolerance before making large pixel-tolerance increases.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `borderless_table.column_detection.x_tolerance_word_height_ratio` | 1.0 | 1.2 | 1.5 | Right/left alignment creates small X shifts |
| `borderless_table.column_detection.maximum_x_tolerance_page_ratio` | 0.05 | 0.06 | 0.08 | Only if the adaptive tolerance is being capped too early |
| `borderless_table.column_detection.expected_columns` | null | Exact known count | — | Last resort for a stable template; prefer page override |

**Success criterion:** Numeric and text columns share one stable logical boundary model across representative rows.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### C9 — Merged header cells reduce header count

<p>Merged header cells reduce the visible header column count. colspan can make it smaller than the data column count, so geometric position is more important than equal counts for header-body mapping.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Header/data do not map 1:1 |
| **Current-code cause** | Header colspan differs from body grid |
| **First resolution** | Tune `reconstruction.header_keywords` only for classification. Separate header geometry/colspan mapping is not implemented. |
| **Status** | `Code enhancement` |

<!-- tuning-recipe:C9 -->
#### Parameter tuning recipe

<p>Header colspan is not primarily a numeric tolerance problem. Do not force header and data counts to match; separate header mapping from body geometry.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `reconstruction.remove_repeated_headers` | true | Keep `true` | — | Remove repeated headers on continued pages |
| `reconstruction.header_keywords` | built-in list | Add the actual header tokens | — | Improve header identification |
| `validation.expected_columns` | null | Set body/data count only if truly fixed | — | Do not derive it from merged header count |

**Success criterion:** Body rows map to the correct columns even when the visual header has fewer cells.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

<a id="toc-4-3-row-errors"></a>
## 4.3 Row Detection Errors

<p>Row detection errors include merged records, split records, incorrect headers and footers, multiline rows, and multi-page continuations.</p>

### R1 — Rows merged

<p>Multiple records may merge when their vertical gap is small, producing a row containing data from successive records.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Two records concatenated |
| **Current-code cause** | Baseline/continuation/anchor gaps too permissive |
| **First resolution** | Decrease `baseline_tolerance_px`, `y_overlap_ratio`, `continuation_line_gap_px`; in anchor projection decrease `minimum_anchor_gap_px` / `projection_merge_gap_px`. |
| **Status** | `Config` |

<!-- tuning-recipe:R1 -->
#### Parameter tuning recipe

<p>To separate merged rows, gradually reduce baseline, continuation, and row-merge tolerances.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `borderless_table.row_detection.baseline_tolerance_px` | 8 | 6 | 4 | OCR/native spatial rows |
| `borderless_table.row_detection.continuation_line_gap_px` | 18 | 14 | 10 | Two transactions are being treated as multiline continuation |
| `bordered_table.row_merge_tolerance_px` | 8 | 6 | 4 | Ruled-grid row boundaries are merged |
| `visual_structure.projection_grid.baseline_tolerance_px` | 4 | 3 | 2 | Projection lines merge vertically |
| `visual_structure.shaded_grid.row_start_tolerance_px` | 10 | 8 | 6 | Shaded rows with close starts are grouped |

**Success criterion:** Every logical source record is a separate row and wrapped lines still remain attached to their own record.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### R2 — Rows split

<p>A record may split into multiple rows when wrapped text or a multiline cell's second line is interpreted as a new record, leaving a partial extra row.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | One record appears on two rows |
| **Current-code cause** | Wrapped line treated as new record or anchor split |
| **First resolution** | Increase `continuation_line_gap_px`/baseline tolerance; use reliable anchor; in projection increase merge gap when one record has multiple ink bands. |
| **Status** | `Config` |

<!-- tuning-recipe:R2 -->
#### Parameter tuning recipe

<p>For split rows, reverse R1 by gradually increasing grouping tolerances until continuation lines join their original record without merging unrelated records.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `borderless_table.row_detection.baseline_tolerance_px` | 8 | 10 | 12 | One visual line is split |
| `borderless_table.row_detection.continuation_line_gap_px` | 18 | 22 | 28 | Wrapped continuation should attach to previous record |
| `bordered_table.row_merge_tolerance_px` | 8 | 10 | 12 | Duplicate/nearby ruled Y boundaries split one row |
| `visual_structure.projection_grid.baseline_tolerance_px` | 4 | 5 | 6 | Projection line fragments split vertically |
| `visual_structure.shaded_grid.row_start_tolerance_px` | 10 | 12 | 15 | Shaded components belonging to one row start slightly apart |

**Success criterion:** A multiline logical record is one row, while two independent records never merge.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### R3 — Header misclassified

<p>Incorrect header classification places column titles in data or drops the first true data row as a header. Inspect header keywords and repeated-header rules.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Header exported as data or real row removed |
| **Current-code cause** | Keyword heuristic insufficient |
| **First resolution** | Adjust `reconstruction.header_keywords`; temporarily set `remove_repeated_headers=false` to inspect. Formatting/bold-based header detection is not implemented. |
| **Status** | `Config + optional code enhancement` |

<!-- tuning-recipe:R3 -->
#### Parameter tuning recipe

<p>Header classification depends mainly on keywords and structure, not arbitrary gap changes. Add actual header keywords when needed.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `reconstruction.remove_repeated_headers` | true | Keep `true` | — | Repeated page headers should not become data |
| `reconstruction.header_keywords` | built-in list | Append actual source header words | — | Header vocabulary differs from defaults |
| `output.crops.include_headers` | false | Set `true` only when you intentionally want header crops | — | Output behavior, not classification fix |

**Success criterion:** Headers are consistently marked/removed according to policy and the first real data row is preserved.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### R4 — Blank rows dropped/created

<p>Valid blank rows may disappear, or false blank rows appear, because of noise or the inability of word-driven methods to represent textless rows. Explicit blank-row state may be required.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Source row count differs |
| **Current-code cause** | Word-based paths cannot preserve truly blank rows; anchor full-mode drops all-empty rows |
| **First resolution** | For crop-only anchor geometry, empty bands can be preserved. For semantic full extraction, preserving confirmed blank rows requires code/state changes. |
| **Status** | `Code enhancement` |

<!-- tuning-recipe:R4 -->
#### Parameter tuning recipe

<p>These require opposite adjustments: relax row support if sparse real rows disappear, but tighten it if noise creates spurious rows.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `visual_structure.*.minimum_row_match_ratio` | 0.35 | 0.30 for missing sparse rows / 0.45 for false rows | 0.25 / 0.55 | Choose direction from symptom |
| `visual_structure.*.minimum_row_matches` | 2 | 1 for sparse rows / 3 for false rows | — / 4 | Use 1 only cautiously; noise risk |

**Success criterion:** Legitimate sparse rows remain, while noise-only rows disappear. Truly blank borderless rows cannot be inferred from text evidence alone; ruled geometry is required to preserve them deterministically.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### R5 — Skewed scan zigzags rows

<p>Skew may cause zigzag row baselines when deskew is inadequate, destabilizing row separation across page width.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Rows wave vertically |
| **Current-code cause** | Deskew missing/false |
| **First resolution** | Tune deskew thresholds and inspect 08_deskewed / 08_deskewed_gray. |
| **Status** | `Config` |

<!-- tuning-recipe:R5 -->
#### Parameter tuning recipe

<p>Fix deskew first; do not mask zigzag baselines by inflating row or column tolerances and creating false merges.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `preprocessing.deskew.minimum_detected_angle` | 0.15 | 0.10 | 0.05 | Small real skew ignored |
| `preprocessing.deskew.maximum_angle` | 10.0 | 12.0 | 15.0 | Only when actual measured skew exceeds 10° |

**Success criterion:** `08_deskewed.png` is visually straight and row baselines stay level across the page.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### R6 — Variable row height mishandled

<p>Variable-height or multiline rows may split or merge if a single fixed grouping tolerance is used.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Rows cut or combine |
| **Current-code cause** | Single baseline/continuation thresholds cannot represent all heights |
| **First resolution** | Use content clustering + anchor segmentation; raise geometry outlier z-score only after structure is correct. |
| **Status** | `Config; code if highly irregular` |

<!-- tuning-recipe:R6 -->
#### Parameter tuning recipe

<p>Increase only continuation or line-grouping tolerance needed for wrapped text. If very large values are needed, prefer anchor or content clustering over fixed-height assumptions.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `borderless_table.row_detection.continuation_line_gap_px` | 18 | 22 | 28 | Tall/wrapped row splits |
| `borderless_table.row_detection.baseline_tolerance_px` | 8 | 10 | 12 | Same-line words separated vertically |
| `borderless_table.row_detection.anchor_segmentation.default_row_height_px` | 80 | 90 | 110 | Only when anchor segmentation is enabled and its fallback row height is visibly too small |

**Success criterion:** Tall rows are fully captured and short rows do not absorb the next record.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### R7 — Footer/summary rows treated as data

<p>Footer or summary content can be misclassified as data records. Distinguish it structurally or exclude it on export as appropriate.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Totals/footer appear as records |
| **Current-code cause** | No export filter for totals/footer |
| **First resolution** | `DataReconstructor` marks `is_total`, but exporter does not exclude totals. Add footer/total filtering code or post-filter. |
| **Status** | `Code enhancement` |

<!-- tuning-recipe:R7 -->
#### Parameter tuning recipe

<p>To prevent footer content being treated as data, strengthen row consistency or separate the lower block across a large gap. Do not blindly drop the last N rows.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `visual_structure.*.minimum_row_match_ratio` | 0.35 | 0.45 | 0.55 | Footer has fewer matching columns than data rows |
| `visual_structure.*.minimum_row_matches` | 2 | 3 | 4 | Reject structurally weak footer lines |
| `visual_structure.*.table_split_gap_factor` | 2.75 | 2.25 | 1.75 | Footer/summary block is vertically separated and should become a separate region |

**Success criterion:** Footer/page furniture is excluded while legitimate totals that match the table structure remain available for explicit total handling.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### R8 — Multi-page table continuation not linked

<p>Cross-page table continuations are currently treated as independent tables, requiring cross-page linking logic in code.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Table IDs/logic reset each page |
| **Current-code cause** | Pages processed independently |
| **First resolution** | Repeated headers are detected per page, but cross-page table linkage is not implemented. Add continuation linker using layout signature/column geometry. |
| **Status** | `Code enhancement` |

<!-- tuning-recipe:R8 -->
#### Parameter tuning recipe

<p>No numeric parameter can link pages. Changing tolerances will not implement cross-page state; code enhancement is required.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| Configuration parameter | Not implemented | Do not tune | — | Use Fix 2 / continuation linker |

**Success criterion:** Requires code support: same logical table identity continues across pages and repeated headers are handled.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### R9 — Crop-only returns zero rows/cells despite visible table

<p>Crop-only mode may produce no rows or cells despite a clear table. Since v3.1, it should consider multiple geometry sources; investigate ruled lines, shaded cells, and borderless projection to identify failed evidence.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | `rows_detected: 0`, `cell_crops: 0`, `NO_STRUCTURE_DETECTED`, while the source visibly contains a table |
| **Current-code cause** | None of the generic geometry candidates reached a usable repeated row/column structure |
| **First resolution** | Confirm startup says `processing_mode=geometry_only` or `geometry_plus_text_detection`; inspect `05/06` line masks plus `07a_visual_*`. For gray/filled cells tune `visual_structure.shaded_grid.*`; for borderless scans tune `visual_structure.projection_grid.*`. Do not enable OCR merely to obtain crops. |
| **Status** | `Supported; Config`, with `NO_STRUCTURE_DETECTED` warning when geometry genuinely cannot be inferred |

<!-- tuning-recipe:R9 -->
#### Parameter tuning recipe

<p>If crop-only yields zero rows or cells, identify which stage failed: ruled lines, shaded grid, projection, or detection-only CRAFT. Do not begin by changing column tolerance.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `bordered_table.*.merge_gap_px` | 12 | 16 | 20 | Visible ruled lines are broken |
| `bordered_table.*.minimum_line_length_ratio` | 0.10 | 0.08 | 0.06 | Real short/faded rules are rejected |
| `visual_structure.shaded_grid.contrast_deltas` | [6,8,10,12] | [4,6,8,10] | [3,5,7,9] | Shaded cells are faint |
| `visual_structure.projection_grid.minimum_row_match_ratio` | 0.35 | 0.30 | 0.25 | Projection finds rows but rejects sparse ones |
| `visual_structure.text_detection_fallback.minimum_boxes` | 4 | 3 | 2 | CRAFT detects only a few populated boxes |
| `ocr.easyocr_detection.text_threshold` | 0.55 | 0.50 | 0.45 | `07c_text_detection_boxes.png` has too few real boxes |
| `ocr.easyocr_detection.low_text` | 0.30 | 0.25 | 0.20 | Weak text is missed by CRAFT |

**Success criterion:** `structure_method` is no longer `none`, `rows_detected > 0`, `columns_detected > 0`, and the row/cell overlays match the visible table.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

<a id="toc-4-4-cell-errors"></a>
## 4.4 Cell Detection Errors

<p>Cell errors include wrong crops, merged or ambiguous blank cells, rotated text, and poor OCR within correctly detected geometry.</p>

### CELL1 — No cell boundary in borderless table

<p>Borderless tables lack explicit cell outlines. Derive cells from logical row bands intersecting column boundaries instead of requiring independent contours.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Cell boxes malformed/whole row |
| **Current-code cause** | No physical gridlines |
| **First resolution** | Full mode derives cells from inferred row × column geometry. Crop-only now also builds cells from classic ruled lines, native digital coordinates, shaded-cell geometry, or projection/alignment geometry without OCR. Tune the detector that produced the selected `structure_method`. |
| **Status** | `Supported` |

<!-- tuning-recipe:CELL1 -->
#### Parameter tuning recipe

<p>Borderless cells are intersections of row bands and column boundaries; tune the structure-producing detector instead of looking for each cell contour.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `visual_structure.*.x_alignment_tolerance_px` | 12 | 15 | 18 | Real repeated column positions are not matching |
| `visual_structure.*.minimum_row_match_ratio` | 0.35 | 0.30 | 0.25 | Sparse rows prevent grid formation |
| `borderless_table.column_detection.minimum_column_support_ratio` | 0.20 | 0.15 | 0.10 | Native/OCR spatial columns have weak support |
| `visual_structure.text_detection_fallback.minimum_boxes` | 4 | 3 | 2 | Crop-only detection-only fallback is sparse |

**Success criterion:** Rows × columns produce a complete non-overlapping logical cell grid even though no physical cell contours exist.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### CELL2 — Merged cells rowspan/colspan misalign grid

<p>Merged rowspan or colspan cells disrupt a uniform grid, potentially shifting subsequent values into wrong rows or columns.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Content shifts after span |
| **Current-code cause** | Uniform grid assumption |
| **First resolution** | No span model exists; add span detection based on missing internal lines / modal cell size. |
| **Status** | `Code enhancement` |

<!-- tuning-recipe:CELL2 -->
#### Parameter tuning recipe

<p>There is no span model currently. Tolerances can obscure the issue but cannot correctly interpret rowspan or colspan.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| Configuration parameter | Not implemented | Do not tune around the span | — | Use Fix 5 / explicit span detection |

**Success criterion:** Requires code support: merged-cell geometry is represented explicitly rather than shifting all later cells.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### CELL3 — Ambiguous empty cell

<p>Empty output cannot distinguish a genuinely blank cell from an OCR failure. A complete solution needs separate metadata states for confirmed blanks and recognition failures.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Cannot distinguish blank vs OCR miss |
| **Current-code cause** | Empty string has no separate state |
| **First resolution** | Use confidence + required-field validation for review now. Add explicit `blank_state`/OCR-attempt metadata for deterministic distinction. |
| **Status** | `Code enhancement` |

<!-- tuning-recipe:CELL3 -->
#### Parameter tuning recipe

<p>Confidence threshold alone does not establish a true blank. Do not lower it to conceal OCR misses; record confirmed blank and OCR failure separately.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `validation.confidence_threshold` | 0.75 | Keep as validation threshold | — | Useful for review routing, not blank-state identification |
| Blank-state parameter | Not implemented | Do not invent a threshold | — | Use Fix 4 |

**Success criterion:** Requires metadata/code support for deterministic blank-vs-OCR-failure distinction.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### CELL4 — Crop margin too tight

<p>Too-narrow crop margins clip edge characters and truncate values, particularly first or last letters. Increase padding gradually while inspecting crops.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | First/last characters missing |
| **Current-code cause** | Padding too small |
| **First resolution** | Increase `cropping.padding.*`; for refinement increase `cell_ocr.padding_px.*`. |
| **Status** | `Config` |

<!-- tuning-recipe:CELL4 -->
#### Parameter tuning recipe

<p>When edge characters are clipped, increase padding only on the affected side, using small steps.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `cropping.padding.left/right` | 8 | 10 | 12 | Left/right characters clipped |
| `cropping.padding.top/bottom` | 5 | 7 | 9 | Top/bottom strokes clipped |
| `...cell_ocr.padding_px.left/right` | 8 | 10 | 12 | Only for anchor cell-OCR refinement crops |
| `...cell_ocr.padding_px.top/bottom` | 3 | 5 | 7 | Only for anchor cell-OCR refinement crops |

**Success criterion:** All edge characters are fully inside the crop and no neighboring cell text enters.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### CELL5 — Crop margin too wide

<p>Too-wide crop margins capture neighboring cell content, causing OCR to read two cells together. Reduce padding and check overlaps.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Neighbor text leaks in |
| **Current-code cause** | Padding too large |
| **First resolution** | Decrease relevant padding; keep `clamp_to_page=true`; inspect overlap. |
| **Status** | `Config` |

<!-- tuning-recipe:CELL5 -->
#### Parameter tuning recipe

<p>If adjacent text leaks into a crop, reduce padding only on the leaking side.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `cropping.padding.left/right` | 8 | 6 | 4 | Horizontal neighbor leakage |
| `cropping.padding.top/bottom` | 5 | 3 | 2 | Vertical neighbor leakage |
| `...cell_ocr.padding_px.left/right` | 8 | 6 | 4 | Anchor refinement crop leakage |

**Success criterion:** Crop contains the entire intended cell content and zero visible characters from adjacent cells.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### CELL6 — OCR misreads correct crop

<p>If the crop is correct but OCR is wrong, investigate DPI, image quality, preprocessing, and OCR recognition settings or model rather than geometry.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Garbled characters |
| **Current-code cause** | Low DPI/noise/model/mode |
| **First resolution** | Raise DPI, improve preprocessing, enable cell OCR refinement, tune EasyOCR mode/thresholds, or custom recognition model. |
| **Status** | `Config/model` |

<!-- tuning-recipe:CELL6 -->
#### Parameter tuning recipe

<p>Confirm correct crops before changing OCR. Improve image quality gradually, then test recognition settings; do not immediately train a custom model.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `render.default_dpi` | 400 | 450 | 500 | Small/thin Arabic text, decimal points, fine strokes; 600 is an upper practical trial with higher memory cost |
| `...cell_ocr.scale_factor` | 1.5 | 2.0 | 2.5 | Only for cell-refinement path; crop is correct but too small |
| `ocr.easyocr.contrast_ths` | 0.10 | 0.20 | 0.30 | Low-contrast crops should trigger contrast adjustment more often |
| `ocr.easyocr.adjust_contrast` | 0.50 | 0.70 | 0.90 | Contrast retry still weak |
| `ocr.easyocr.decoder` | greedy | beamsearch | — | Recognition remains ambiguous; slower but can improve decoding |
| `ocr.easyocr.beam_width` | 5 | 10 | 15 | Only when using a beam decoder; higher is slower |

**Success criterion:** The same correct crop is recognized consistently across representative examples without creating new false characters.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### CELL7 — Rotated/vertical text misread

<p>Vertical or rotated text may be unreadable, especially vertical headers. rotation_info may help, but reliable per-cell orientation handling requires a dedicated stage.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Consistent failure in rotated cells |
| **Current-code cause** | No per-cell orientation stage |
| **First resolution** | Try `ocr.easyocr.rotation_info=[90,180,270]`; true per-cell orientation detection is not implemented. |
| **Status** | `Config then code enhancement` |

<!-- tuning-recipe:CELL7 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">إذا كان الخطأ محصورًا في نص مدوّر، فعّل زوايا Rotation بدل تغيير DPI/threshold لكل الصفحة.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `ocr.easyocr.rotation_info` | null | [90,180,270] | Use only needed angles if known | Recognition mode only; crop-only does not decode text |

**Success criterion:** Rotated cells are read correctly while normal horizontal cells remain unchanged.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### CELL8 — Arabic/RTL/diacritics misread

<p dir="rtl" align="right"><strong>أخطاء العربية وRTL والتشكيل أو الخلايا المختلطة:</strong> تظهر كحروف عربية معكوسة/مبعثرة أو أخطاء عند مزج العربية بالأرقام. راجع لغات EasyOCR وترتيب RTL، وقد تحتاج نموذج Recognition مخصص إذا تكرر النمط.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Reversed/jumbled Arabic or mixed digits |
| **Current-code cause** | Language/model/segmentation issue |
| **First resolution** | Use `ocr.languages=[ar,en]` as needed; preserve RTL sorting; numeric passes for numeric cells; custom EasyOCR model if recurring. |
| **Status** | `Config/model` |

<!-- tuning-recipe:CELL8 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">تأكد أولًا أن العربية والإنجليزية مفعّلتان، ثم جرّب Decoder أقوى قبل الانتقال إلى Custom model. لا تغيّر Geometry إذا الـCrop صحيح.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `ocr.languages` | [ar,en] | Keep `[ar,en]` | — | Mixed Arabic/English documents |
| `ocr.easyocr.decoder` | greedy | beamsearch | — | Recurring recognition ambiguity |
| `ocr.easyocr.beam_width` | 5 | 10 | 15 | Only with beam decoder; slower |
| Custom `recog_network` | standard | custom model after corrected training labels | — | Only for recurring domain-specific recognition errors |

**Success criterion:** Arabic order/digits are stable across multiple cells; remaining errors are not caused by crop/segmentation.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### CELL9 — Numeric formatting parsed incorrectly

<p dir="rtl" align="right"><strong>تحليل التنسيق الرقمي بشكل غير صحيح:</strong> تحدث عند التباس الفاصلة العشرية وفاصل الآلاف أو رموز العملة والأرقام العربية. يجب أن تمر القيم الرقمية عبر Normalization واعٍ بنمط الأرقام المتوقع.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Wrong decimal or string value |
| **Current-code cause** | Locale/punctuation ambiguity |
| **First resolution** | Use schema type amount/number; current parser handles Arabic digits, comma/dot heuristic, parentheses. Add explicit locale parser if source conventions exceed this heuristic. |
| **Status** | `Supported partly; code for explicit locale` |

<!-- tuning-recipe:CELL9 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">هذه مشكلة Parsing/Schema أكثر من كونها Tolerance. لا تحاول إصلاح الفاصلة العشرية بتغيير OCR geometry.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `schema.columns[].type` | unset / project-defined | Set `amount` or `number` for numeric columns | — | Enable numeric normalization/validation |
| Explicit locale parser | Not implemented | Add only when source convention exceeds current heuristic | — | Example: unusual decimal/thousands conventions |

**Success criterion:** Normalized numeric value matches the source meaning, including sign, decimal point, and thousands separator.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

<a id="toc-4-5-table-boundary-errors"></a>
## 4.5 Table Boundary Detection Errors

<p dir="rtl" align="right">أخطاء حدود الجدول تتعلق بتحديد مكان بداية ونهاية الجدول أو فصل عدة جداول أو استبعاد النصوص والشعارات والعلامات المائية المحيطة بالجدول.</p>

### T1 — Table start/end boundary missed with multiple tables

<p dir="rtl" align="right"><strong>فقد بداية/نهاية الجدول عند وجود عدة جداول:</strong> يحدث عندما تُجمع كتلتان جدوليّتان منفصلتان في Region واحدة، خصوصًا في Borderless. تحتاج الصفحة إلى منطق يفصل الجداول باستخدام الفجوات أو تغيّر البنية.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Unrelated tables combined |
| **Current-code cause** | The classic OCR-word borderless detector still creates one region, while the v3.1 visual geometry path can split vertically separated aligned blocks using row-cadence/gap evidence. Arbitrary overlapping/nested multi-table layouts remain harder. |
| **First resolution** | In visual geometry tune `table_split_gap_factor`, `table_split_gap_page_ratio`, and `table_split_gap_height_factor`. If the classic word detector wins and fuses unrelated tables, a richer semantic multi-table splitter is still a code enhancement. |
| **Status** | `Partially supported; Config/code` |

<!-- tuning-recipe:T1 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">لفصل جدولين ملتصقين رأسيًا، اجعل شرط الانقسام أقل صرامة: قلّل عوامل/نسب فجوة الفصل تدريجيًا. إذا انقسم جدول واحد بالخطأ اعكس الاتجاه.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `visual_structure.*.table_split_gap_factor` | 2.75 | 2.25 | 1.75 | Separate vertically distant table blocks |
| `visual_structure.*.table_split_gap_page_ratio` | 0.18 | 0.14 | 0.10 | Large page-relative gap should trigger a split sooner |
| `visual_structure.*.table_split_gap_height_factor` | 4.0 | 3.0 | 2.5 | Gap relative to row height should split sooner |

**Success criterion:** Unrelated tables become separate regions; one continuous table is not split internally.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### T2 — False positive non-table content

<p dir="rtl" align="right"><strong>اعتبار نص عادي جدولًا:</strong> يحدث عندما تبدو فقرة كثيفة أو قائمة وكأن لها محاذاة أعمدة. يجب رفع شروط الاتساق والتحقق من أن Candidate لديه بنية صفوف وأعمدة حقيقية قبل قبوله.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Garbage table from prose |
| **Current-code cause** | Alignment/structure looks tabular |
| **First resolution** | Raise `classification.alignment_score_min`; strengthen column support; use validation/fallback scoring. Dedicated candidate consistency rejection threshold is not exposed. |
| **Status** | `Config; optional code enhancement` |

<!-- tuning-recipe:T2 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">عند اعتبار Paragraph جدولًا، ارفع شروط الاتساق بدل محاولة حذف Region يدويًا.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `classification.alignment_score_min` | 0.35 | 0.45 | 0.55 | Require stronger tabular alignment |
| `visual_structure.*.minimum_row_match_ratio` | 0.35 | 0.45 | 0.55 | Rows must match more seed columns |
| `visual_structure.*.minimum_row_matches` | 2 | 3 | 4 | Require more repeated column matches |
| `ocr.easyocr_detection.text_threshold` | 0.55 | 0.60 | 0.65 | Only if `easyocr_detection_spatial` is creating noisy text boxes |

**Success criterion:** Dense prose/list candidates are rejected while real tables still pass structure detection.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### T3 — Boundary cut off prematurely

<p dir="rtl" align="right"><strong>حدود الجدول تتوقف قبل نهايته:</strong> تظهر عندما تكون الصفوف السفلية مفقودة لأن Region انتهت عند خط أو فجوة داخلية بدل نهاية الجدول الحقيقية. راجع line detection والـ closing والـ region overlay.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Bottom rows missing |
| **Current-code cause** | Broken line candidate/region segmentation |
| **First resolution** | For bordered: lower minimum line length, increase merge gap/closing, inspect region overlay. Borderless uses word union, so cutoff usually comes from missing OCR/row segmentation. |
| **Status** | `Config` |

<!-- tuning-recipe:T3 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">إذا توقفت الحدود قبل آخر صف، أصلح الخطوط المكسورة أو منع الانقسام الداخلي المبكر حسب الـstructure_method.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `bordered_table.*.minimum_line_length_ratio` | 0.10 | 0.08 | 0.06 | Real short/faded border segments are rejected |
| `bordered_table.*.merge_gap_px` | 12 | 16 | 20 | Broken border segments need reconnection |
| `visual_structure.*.table_split_gap_factor` | 2.75 | 3.25 | 4.0 | One real table is being split at an internal gap; higher means a larger gap is required to split |

**Success criterion:** Detected region includes all real bottom rows and does not absorb unrelated footer content.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### T4 — Multi-page table not linked

<p dir="rtl" align="right"><strong>الجدول الممتد على صفحات يظهر كجداول منفصلة:</strong> هو نفس مفهوم الاستمرار بين الصفحات ولكن على مستوى Table Region. يحتاج النظام إلى ربط الصفحات المتتالية عندما تتطابق Geometry ولا يبدأ جدول جديد فعليًا.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | One logical table split per page |
| **Current-code cause** | No cross-page state |
| **First resolution** | Implement continuation linker; current `layout_signature` and `similar_to_previous_page` can be used as evidence. |
| **Status** | `Code enhancement` |

<!-- tuning-recipe:T4 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">لا توجد قيمة Config تربط Table regions بين الصفحات. استخدم Fix 2 بدل تعديل Gap/Tolerance.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| Configuration parameter | Not implemented | Do not tune | — | Cross-page continuation requires code state |

**Success criterion:** Requires code enhancement: logical table identity continues across page boundaries.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### T5 — Nested table double-counted

<p dir="rtl" align="right"><strong>اكتشاف جدول داخلي مرتين:</strong> يحدث عندما يتم احتساب Sub-table ضمن الجدول الأب ثم كمنطقة مستقلة أيضًا، فتتكرر البيانات. قد يلزم Containment/Deduplication صريح للحالات التي لا يمنعها contour retrieval الحالي.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Duplicate content |
| **Current-code cause** | Contained candidate appears twice |
| **First resolution** | Bordered detector uses `cv2.RETR_EXTERNAL`, which already suppresses many nested contours, but there is no explicit containment dedupe layer. |
| **Status** | `Mostly mitigated; code for explicit rule` |

<!-- tuning-recipe:T5 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">لا يوجد Containment-dedupe parameter صريح حاليًا. لا تحاول حل التكرار بتغيير minimum area عشوائيًا لأنه قد يحذف جداول حقيقية.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| Containment dedupe parameter | Not implemented | Do not tune | — | Add explicit containment rule if current `RETR_EXTERNAL` mitigation is insufficient |

**Success criterion:** Nested candidate is emitted once, with no duplicated rows/cells.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### T6 — Watermark/logo/margin distorts boundary

<p dir="rtl" align="right"><strong>Logo أو Watermark أو الهوامش توسع حدود الجدول:</strong> تدخل عناصر الصفحة غير الجدولية في الكشف فتنتج Region أكبر من الجدول أو Ghost table. ابدأ بالـ preprocessing والفلترة، وقد تحتاج Content ROI ثابتًا لهذه الفئة.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Region too large or ghost table |
| **Current-code cause** | Page furniture enters line/contour detection |
| **First resolution** | Tune preprocessing and line filters. There is no bordered-table content-ROI parameter; add one if persistent. |
| **Status** | `Config then code enhancement` |

<!-- tuning-recipe:T6 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">ابدأ برفع شروط الخط/الاتساق حتى لا تدخل العلامات القصيرة والـLogo في الجدول. إذا كان العنصر كبيرًا ويظل داخل Region فالحل الحقيقي Content ROI.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `bordered_table.*.minimum_line_length_ratio` | 0.10 | 0.15 | 0.20 | Reject short logo/text strokes as rules |
| `bordered_table.minimum_region_area_ratio` | 0.01 | 0.02 | 0.03 | Reject small isolated contour regions; do not use if the real table itself is small |
| `visual_structure.*.minimum_row_match_ratio` | 0.35 | 0.45 | 0.55 | Reject structurally inconsistent page furniture |
| Content ROI | Not implemented for bordered path | Use Fix 7 if persistent | — | Best fix for stable header/footer/logo zones |

**Success criterion:** Table boundary hugs the real table and excludes logo/watermark/margin furniture.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### T7 — Inconsistent page template breaks fixed boundary

<p dir="rtl" align="right"><strong>اختلاف Template الصفحات يكسر حدودًا ثابتة:</strong> يحدث عندما تُستخدم Geometry واحدة لصفحات ذات تنسيقات مختلفة. الأفضل الكشف لكل صفحة واستخدام Overrides فقط للصفحات الاستثنائية أو مجموعات Template مؤكدة.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Some pages correct, others cut |
| **Current-code cause** | Global explicit geometry used across variants |
| **First resolution** | Default detectors run per page. Use `page_overrides` for exceptional templates and avoid global fixed ratios unless verified. |
| **Status** | `Workflow/config` |

<!-- tuning-recipe:T7 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">Template مختلف = إعداد مختلف على مستوى الصفحة/المجموعة، وليس قيمة عالمية واحدة. استخدم `page_overrides` ولا تغيّر الـbaseline الذي يعمل على بقية الصفحات.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `page_overrides.<page>...` | none | Add only the exceptional page/group | — | Override exact detector parameters for that template |
| Global fixed ratios | generic defaults | Do not hardcode globally | — | Only reuse geometry after template equivalence is proven |

**Success criterion:** All template groups process correctly without special-casing file/company names in Python.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

### T8 — Blurred scan breaks boundary polygon

<p dir="rtl" align="right"><strong>الـ Scan الباهت أو المشوش يكسر إطار الجدول:</strong> عندما تكون الخطوط متقطعة أو باهتة لا تتكون Polygon مغلقة. يمكن تقوية Morphological closing وتقليل شروط طول الخط بحذر حتى تتصل الحدود بدون خلق خطوط وهمية.</p>

| Diagnostic field | Details |
|---|---|
| **How to recognize it** | Open/partial borders |
| **Current-code cause** | Faded/broken rules |
| **First resolution** | Increase preprocessing closing and bordered merge gaps; reduce minimum line length/kernel ratio carefully. |
| **Status** | `Config` |

<!-- tuning-recipe:T8 -->
#### Parameter tuning recipe

<p dir="rtl" align="right">للـScan الباهت، حسّن الاتصال بين الخطوط تدريجيًا. غيّر Parameter واحدًا كل مرة لأن Denoise/closing/line length يمكن أن تصنع خطوطًا وهمية إذا بالغت فيها.</p>

| Parameter | v3.2 baseline | First trial | Second trial | Use when |
|---|---:|---:|---:|---|
| `preprocessing.denoise.kernel_size` | 3 | 5 | — | Speckle/noise breaks lines; larger kernels may erase thin text |
| `preprocessing.contrast.clip_limit` | 2.0 | 2.5 | 3.0 | Faded borders need local contrast |
| `preprocessing.morphology.closing_kernel` | [2,2] | [3,3] | [4,4] | Reconnect small breaks |
| `bordered_table.*.merge_gap_px` | 12 | 16 | 20 | Reconnect longer broken rule segments |
| `bordered_table.*.minimum_line_length_ratio` | 0.10 | 0.08 | 0.06 | Allow real short faded fragments to survive |

**Success criterion:** Horizontal/vertical line debug images show continuous real borders without creating dense false rules.

**Retest rule:** run only the failing representative page with the generated `--run-config`, keep `--debug` enabled, and compare the same overlay before/after. If the first trial makes the geometry worse, restore the prior value and move in the opposite direction.

---

<a id="toc-5-debugging-rules"></a>
# 5. Stage-by-stage debugging rules

<p dir="rtl" align="right">هذا القسم يحول التشخيص إلى خطوات عملية حسب مرحلة الـ Pipeline. استخدمه بعد تحديد نوع الخطأ لمعرفة الملفات والـ Parameters والـ Debug Artifacts التي يجب مراجعتها.</p>

<a id="toc-5-1-column-debug"></a>
## 5.1 Column detection

<p dir="rtl" align="right">مرجع عملي لتصحيح اكتشاف الأعمدة، مع فصل طريقة التعامل مع الجداول بدون حدود عن الجداول ذات الخطوط والحدود.</p>

### Borderless path

<p dir="rtl" align="right">هذا المسار خاص بالجداول التي لا تحتوي على خطوط فاصلة واضحة، ويعتمد أكثر على مواقع النصوص والتجميع والمسافات بين الأعمدة.</p>

Primary parameters:

```text
borderless_table.column_detection.x_tolerance_px
borderless_table.column_detection.minimum_column_gap_px
borderless_table.column_detection.expected_columns
borderless_table.column_detection.minimum_column_support_rows
borderless_table.column_detection.minimum_column_support_ratio
borderless_table.column_detection.maximum_columns
borderless_table.clustering.min_samples
```

Key behavior in the current implementation:

- `x_tolerance_px` is DBSCAN `eps`. Bigger values join X positions more aggressively.
- `minimum_column_gap_px` merges neighboring supported centers. **Bigger value usually means fewer columns.**
- `expected_columns` forces quantile-based centers and bypasses support-based inference; use it only when the count is truly known.
- If supported centers collapse to ≤1, the detector deliberately returns one conservative column instead of inventing a grid.

### Bordered path

<p dir="rtl" align="right">هذا المسار خاص بالجداول ذات الخطوط أو الشبكة، ويعتمد على اكتشاف الخطوط والـ contours والمورفولوجي لتحديد الحدود.</p>

Primary parameters:

```text
bordered_table.horizontal.*
bordered_table.vertical.*
bordered_table.row_merge_tolerance_px
bordered_table.column_merge_tolerance_px
bordered_table.cells.*
```

Inspect `05_horizontal_lines.png`, `06_vertical_lines.png`, and `10_detected_cells.png` before changing OCR.

<a id="toc-5-2-row-debug"></a>
## 5.2 Row detection

<p dir="rtl" align="right">مرجع ضبط اكتشاف الصفوف، خاصة مشاكل المسافات الرأسية، النص الملتف، الـ anchors، وتفاوت ارتفاع الصفوف.</p>

Normal borderless rows use baseline clustering + optional continuation merging.

```text
baseline_tolerance_px ↑  => easier to keep words/lines together
baseline_tolerance_px ↓  => harder to merge nearby rows
continuation_line_gap_px ↑ => more multiline continuation merging
continuation_line_gap_px ↓ => more row separation
```

When records have a stable per-row anchor, prefer anchor segmentation rather than pushing baseline tolerances to extremes.

<a id="toc-5-3-cell-debug"></a>
## 5.3 Cell detection

<p dir="rtl" align="right">مرجع مراجعة الـ cell boxes والـ crops والـ padding والتأكد أن كل خلية تغطي المحتوى المطلوب فقط قبل تشغيل OCR.</p>

- Bordered cells are the Cartesian grid between detected line positions.
- Borderless cells are row bands × inferred column boundaries.
- Anchor segmentation can use explicit `column_boundaries_ratio` for deterministic cells.
- Current code has no rowspan/colspan model.

<a id="toc-5-4-table-debug"></a>
## 5.4 Table boundaries

<p dir="rtl" align="right">مرجع تشخيص منطقة الجدول نفسها قبل تقسيمها إلى صفوف وأعمدة، خصوصًا عند وجود أكثر من جدول أو عناصر صفحة قريبة منه.</p>

- Bordered detector can return multiple external table regions on one page.
- Borderless detector currently creates one table covering all words on the page.
- No cross-page continuation object currently links table regions.

---

<a id="toc-6-fix-library"></a>
# 6. Fix-it code library — when configuration is not enough

<p dir="rtl" align="right">مكتبة حلول برمجية للحالات التي لا يكفي فيها تغيير Parameters. لا تستخدم هذه التعديلات قبل إثبات أن المشكلة ليست قابلة للحل بالإعدادات الحالية.</p>

These are source-level fixes for required behaviors that are not currently implemented. Add them only after a config-only approach has been ruled out.

<a id="toc-6-fix-1"></a>
## Fix 1 — Separate multiple borderless tables by vertical gaps

<p dir="rtl" align="right">حل برمجي لفصل أكثر من جدول Borderless في الصفحة نفسها باستخدام الفجوات الرأسية الكبيرة بين مجموعات المحتوى.</p>

**Use when:** two unrelated borderless tables on one page are combined into `table_01`.

Add a block splitter before `BorderlessTableDetector._cluster_rows` consumes all page words:

```python
from models import WordBox


def split_word_blocks_by_vertical_gap(
    words: list[WordBox],
    minimum_gap_px: float,
) -> list[list[WordBox]]:
    if not words:
        return []

    ordered = sorted(words, key=lambda w: (w.bbox.y0, w.bbox.x0))
    blocks: list[list[WordBox]] = [[ordered[0]]]
    current_bottom = ordered[0].bbox.y1

    for word in ordered[1:]:
        gap = word.bbox.y0 - current_bottom
        if gap >= minimum_gap_px:
            blocks.append([word])
        else:
            blocks[-1].append(word)
        current_bottom = max(current_bottom, word.bbox.y1)

    return blocks
```

Then run the existing row/column reconstruction independently per block and assign `table_01`, `table_02`, ... . Add a ratio- or DPI-aware threshold rather than hardcoding one PDF's pixels.

<a id="toc-6-fix-2"></a>
## Fix 2 — Link multi-page table continuations

<p dir="rtl" align="right">حل لربط أجزاء الجدول نفسه عند استمراره من صفحة إلى أخرى بدل التعامل مع كل صفحة كجدول مستقل.</p>

**Use when:** one logical table spans pages and must remain one dataset/table identity.

Add a post-page linker using evidence already available in `PageAnalysis`:

```python
from dataclasses import dataclass

@dataclass
class TableContinuationState:
    logical_table_id: str
    previous_layout_signature: str
    previous_column_count: int


def is_continuation(previous, current, tolerance_columns: int = 0) -> bool:
    if previous is None:
        return False
    same_signature = (
        previous.previous_layout_signature
        == current.analysis.layout_signature
    )
    current_columns = max((len(r.cells) for r in current.rows), default=0)
    same_columns = abs(previous.previous_column_count - current_columns) <= tolerance_columns
    return same_signature and same_columns
```

For a stronger implementation, compare normalized column boundary ratios rather than only count/signature, and ignore/relabel repeated headers on continuation pages.

<a id="toc-6-fix-3"></a>
## Fix 3 — Filter footer/summary rows without deleting legitimate totals blindly

<p dir="rtl" align="right">حل لتمييز Footer أو Summary rows عن البيانات الفعلية بدون حذف صفوف الإجماليات الصحيحة بشكل عشوائي.</p>

`DataReconstructor` already sets `row.is_total`. Add an explicit export policy instead of silently treating totals as ordinary records:

```yaml
reconstruction:
  totals_policy: keep   # keep | separate | drop
```

Then in exporter/reconstruction:

```python
policy = config.get("reconstruction", {}).get("totals_policy", "keep")
if policy == "drop":
    data_rows = [row for row in data_rows if not row.is_total]
elif policy == "separate":
    total_rows = [row for row in data_rows if row.is_total]
    data_rows = [row for row in data_rows if not row.is_total]
```

Do not hardcode "bottom N rows" as footer logic.

<a id="toc-6-fix-4"></a>
## Fix 4 — Distinguish confirmed blank from OCR failure

<p dir="rtl" align="right">حل لإضافة حالة واضحة تفرق بين خلية فارغة فعلًا وبين خلية تحتوي محتوى لكن OCR فشل في قراءته.</p>

Add a state to `ExtractedCell`:

```python
blank_state: str = "unknown"  # confirmed_blank | ocr_empty | not_blank | unknown
ocr_attempted: bool = False
```

Set:

```python
if crop_has_foreground_ink and not raw_value:
    cell.blank_state = "ocr_empty"
elif not crop_has_foreground_ink:
    cell.blank_state = "confirmed_blank"
else:
    cell.blank_state = "not_blank"
```

Use a simple ink-density check on the final cell crop; keep the raw crop as evidence.

<a id="toc-6-fix-5"></a>
## Fix 5 — Detect merged bordered cells / spans

<p dir="rtl" align="right">حل لدعم الخلايا المدمجة <code>rowspan/colspan</code> في الجداول ذات الحدود بدل فرض شبكة موحدة على كل الخلايا.</p>

**Use when:** a missing internal ruling creates a cell wider/taller than the modal grid.

Start with geometry evidence:

```python
from statistics import median

widths = [cell.width for cell in cells if cell.width > 0]
heights = [cell.height for cell in cells if cell.height > 0]
modal_w = median(widths)
modal_h = median(heights)

for cell in cells:
    colspan = max(1, round(cell.width / modal_w))
    rowspan = max(1, round(cell.height / modal_h))
```

A production version must confirm spans against missing internal line evidence before propagating values; size alone is not enough.

<a id="toc-6-fix-6"></a>
## Fix 6 — Per-cell orientation handling

<p dir="rtl" align="right">حل لاكتشاف اتجاه النص داخل كل خلية وتدويرها عند الحاجة قبل OCR، خاصة للعناوين الرأسية أو النصوص المدورة.</p>

First try the configuration-only EasyOCR option:

```json
{
  "ocr": {
    "easyocr": {
      "rotation_info": [90, 180, 270]
    }
  }
}
```

If only specific columns are vertical, add orientation logic to cell refinement so all cells are not slowed down:

```python
ROTATIONS = (0, 90, 180, 270)

best = None
for angle in ROTATIONS:
    candidate_image = rotate_crop(crop, angle)
    result = ocr.recognize(candidate_image, mode="single_line")
    if best is None or result.confidence > best.confidence:
        best = result
```

Accept by confidence **and** semantic validation where possible.

<a id="toc-6-fix-7"></a>
## Fix 7 — Add bordered-table content ROI to ignore page furniture

<p dir="rtl" align="right">حل لتحديد منطقة بحث مخصصة للجدول واستبعاد Header/Footer/Logo والعناصر الثابتة التي قد تشوش اكتشاف الحدود.</p>

Add config:

```yaml
bordered_table:
  content_roi_ratio: [0.02, 0.98, 0.08, 0.94]  # x0,x1,y0,y1
```

Crop the binary image to ROI before line detection, then add the ROI origin back to every output bbox. Do not lose coordinate provenance.

<a id="toc-6-fix-8"></a>
## Fix 8 — Explicit header-body mapping when header uses colspan

<p dir="rtl" align="right">حل لربط Header يحتوي على خلايا مدمجة بأعمدة البيانات الفعلية اعتمادًا على المواضع بدل الاعتماد على تساوي عدد الخلايا.</p>

Do not infer body column count from header cell count. Detect body columns from data rows, then map header text to body column intervals by overlap:

```python
for header_box, header_text in headers:
    covered = [
        idx for idx, (x0, x1) in enumerate(body_columns)
        if overlap_1d(header_box.x0, header_box.x1, x0, x1) > 0.5
    ]
```

Store header span metadata rather than shifting body cells.

<a id="toc-6-fix-9"></a>
## Fix 9 — Page-template grouping without file-specific profiles

<p dir="rtl" align="right">حل لتجميع الصفحات المتشابهة في Template واحد وإعادة استخدام Geometry بينها بدون إنشاء Profiles مرتبطة باسم بنك أو شركة أو ملف.</p>

If pages fall into a small number of layouts, group them by measured signatures rather than PDF name:

```python
groups: dict[str, list[int]] = {}
for analysis in analyses:
    groups.setdefault(analysis.layout_signature, []).append(analysis.page_number)
```

Tune per layout signature, then store the differences in `page_overrides`. This preserves the project's generic design.

---

<a id="toc-7-troubleshooting-flow"></a>
# 7. End-to-end troubleshooting decision flow

<p dir="rtl" align="right">شجرة قرار كاملة لتحديد نقطة الفشل من البداية للنهاية. اتبعها بالترتيب عندما لا تعرف هل المشكلة من PDF أو Preprocessing أو Geometry أو OCR أو Reconstruction أو Validation.</p>

```text
START
  │
  ├─ Does `python -m pytest -q` fail?
  │      ├─ YES → fix environment/code first
  │      └─ NO
  │
  ├─ Does `analyze` open/classify the PDF?
  │      ├─ NO → file/PyMuPDF/input-path problem
  │      └─ YES
  │
  ├─ Does a one-page `extract --debug` run with `output.mode: full` set in YAML/JSON start OCR?
  │      ├─ NO → EasyOCR/model/device problem
  │      └─ YES
  │
  ├─ Are 01_original / preprocessing variants visually good?
  │      ├─ NO → render + preprocessing parameters
  │      └─ YES
  │
  ├─ Are rows wrong?
  │      ├─ YES → deskew → row baseline/continuation → anchor segmentation
  │      └─ NO
  │
  ├─ Are columns wrong?
  │      ├─ YES → x_tolerance → minimum gap → support → expected/fixed boundaries
  │      └─ NO
  │
  ├─ Are cell boxes/crops wrong?
  │      ├─ YES → grid/boundaries → crop padding
  │      └─ NO
  │
  ├─ Is OCR text wrong inside a correct crop?
  │      ├─ YES → DPI → crop preprocessing → EasyOCR mode/thresholds → custom model
  │      └─ NO
  │
  ├─ Is normalized data wrong despite correct raw OCR?
  │      ├─ YES → schema → date formats → amount parsing/sign convention
  │      └─ NO
  │
  ├─ Do validation checks fail?
  │      ├─ YES → inspect issue code; verify geometry before loosening validation
  │      └─ NO
  │
  ├─ Do later pages break?
  │      ├─ YES → analyze per-page variation; use page_overrides or implement continuation/template grouping
  │      └─ NO
  │
  └─ Scale to full PDF and run final QA
```

---

<a id="toc-8-validation-codes"></a>
# 8. Validation issue codes and what they mean

<p dir="rtl" align="right">مرجع لأكواد Validation التي قد تظهر بعد الاستخراج، وما الذي يعنيه كل كود وأي مرحلة يجب فحصها لمعالجة السبب الحقيقي.</p>

Current validator can emit:

```text
LOW_CONFIDENCE
UNEXPECTED_COLUMN_COUNT
MISSING_REQUIRED
DUPLICATE_ROW
INVALID_DATE
INVALID_NUMERIC
INVALID_BBOX
OUT_OF_PAGE_BBOX
OVERLAPPING_CELLS
UNUSUAL_ROW_HEIGHT
UNUSUAL_ROW_GAP
EMPTY_ROW
MISSING_CELLS
BALANCE_MISMATCH
```

Use validation as a **detector of structural/OCR problems**, not as a way to hide them. For example, do not simply raise `unusual_height_zscore` when merged rows are visually obvious.

---

<a id="toc-9-cli"></a>
# 9. CLI command reference

<p dir="rtl" align="right">مرجع أوامر سطر الأوامر الرئيسية للمشروع. استخدمه لمعرفة وظيفة كل Command ومتى يتم تشغيله أثناء التحليل أو التشخيص أو الاستخراج أو الضبط.</p>

<a id="toc-9-analyze"></a>
## `analyze`

<p dir="rtl" align="right">يحلل خصائص صفحات PDF ونوعها وتخطيطها بدون تنفيذ دورة الاستخراج الكاملة؛ مناسب كبداية لفهم الملف.</p>

```text
--config
--run-config
--override key=value        advanced/compatibility only; not used in the standard workflow
--input
--pages
--output
--fast
```

<a id="toc-9-diagnose"></a>
## `diagnose`

<p dir="rtl" align="right">يحوّل نتائج التحليل إلى ملاحظات واقتراحات Parameters مبنية على قياسات الصفحة، لمساعدة المطوّر في اختيار نقطة بداية للضبط.</p>

```text
--config
--run-config
--override key=value
--input
--pages
--output
```

<a id="toc-9-extract"></a>
## `extract`

<p dir="rtl" align="right">ينفّذ دورة الاستخراج الفعلية ويولّد المخرجات المطلوبة مثل Excel والـ crops والـ manifests والـ run config حسب وضع الإخراج.</p>

```text
--config
--run-config
--override key=value
--input
--output
--pages
--debug
--debug-root
--save-run-config
--no-save-run-config
```

<a id="toc-9-inspect-config"></a>
## `inspect-config`

<p dir="rtl" align="right">يعرض قيمة Parameter محدد ومرجعه من <code>parameter_catalog.yaml</code> حتى تعرف معناه قبل تغييره.</p>

```text
--config
--run-config
--override key=value
--parameter dotted.path
```

<a id="toc-9-tune"></a>
## `tune`

<p dir="rtl" align="right">يختبر عدة قيم لباراميتر واحد على صفحة محددة ويرتب النتائج باستخدام Score يجمع مؤشرات هيكلية وOCR وValidation.</p>

```text
--config
--run-config
--override key=value
--input
--page
--parameter dotted.path
--values value1 value2 ...
--output
```

---

<a id="toc-10-output-modes"></a>
# 10. Output modes — do not confuse them

<p dir="rtl" align="right">يشرح أوضاع الإخراج المختلفة وما الذي يولده كل Mode. راجع هذا القسم عندما تتوقع Excel أو crops ولا تجدها، قبل اعتبار ذلك خطأ في الاستخراج.</p>

| Mode | Excel | Cell crops | Row crops | Training labels | Character recognition? | Detection-only text boxes? |
|---|---:|---:|---:|---:|---:|---:|
| `full` | Yes | Yes | Yes | No | Yes when required | Recognition already provides positions |
| `data_only` | Yes | No | No | No | Yes when required | Recognition already provides positions |
| `cropped_cells_only` | No | Yes | No | No | **No** | Yes, lazily if geometry fails |
| `cropped_rows_only` | No | No | Yes | No | **No** | Yes, lazily if geometry fails |
| `cropped_rows_and_cells` | No | Yes | Yes | No | **No** | Yes, lazily if geometry fails |
| `training_dataset` | No | Yes | No | Yes | Yes — OCR draft labels are needed | Included through the OCR path |
| `custom` | Depends on switches | Depends | Depends | Depends | Depends on resulting processing path | Depends |

Important: crop-only modes first use native/OpenCV geometry. Only when that produces no usable structure may the CRAFT detection-only fallback run. This fallback loads the detector but not the recognizer, and cells built from it keep empty text values.

---

<a id="toc-11-parameter-reference"></a>
# 11. Parameter reference — every key in the current `configs/default.yaml`

<p dir="rtl" align="right">المرجع الشامل لجميع Parameters الموجودة حاليًا في <code>configs/default.yaml</code>: وظيفة كل قيمة، متى تعدلها، وما الأعراض التي تشير إلى أنها تحتاج تغييرًا.</p>

This appendix mirrors the current default YAML, including the v3.2 visual-structure and detection-only controls, so parameter names/defaults can be checked directly against the generated run-config JSON. Numeric values are not universally range-validated by the code; the "values" column states the safe/meaningful domain supported by the current implementation.

| Parameter | Default | What it does | Values | What symptom/criterion says to change it | Example new value/direction |
|---|---:|---|---|---|---|
| `project.name` | `universal_pdf_extraction_pipeline` | Project metadata only; not used to change extraction behavior. | string | Do not tune for PDF errors. | No change required. |
| `project.version` | `3.2.0-text-detection` | Project metadata only. | string | Do not tune for PDF errors. | No change required. |
| `project.deterministic` | `true` | Enables best-effort runtime reproducibility controls for Python/NumPy/PyTorch and deterministic cuDNN behavior. | boolean | Keep true when repeatability matters; set false when deterministic backend behavior is not required. | This is not a bit-for-bit guarantee across hardware or dependency versions. |
| `project.random_seed` | `42` | Seed applied when `project.deterministic=true`. | integer | Change only when you intentionally want a different reproducible seed. | Not a table/OCR quality tuning control. |
| `analysis.thumbnail_dpi` | `96` | Resolution used by page analysis for quick line/layout measurements. | positive number | Raise when small/faint structure is missed during analyze/diagnose; lower for speed. | 96→144/192 if analysis misses structure; 96→72 only for faster coarse inspection. |
| `analysis.digital_layout_dpi` | `144` | Render DPI used when a digital-text page still needs an image coordinate space for crops/debug. | positive number | Raise if digital-page crop geometry is too coarse. | 144→200/288 for small text/crops. |
| `classification.digital_min_characters` | `30` | Minimum selectable-text character count before a page can be considered digital/hybrid. | integer ≥0 | Raise when OCR garbage/text fragments make scans look digital; lower for very short digital pages. | 30→50/100 for false digital; 30→10/20 for short true digital pages. |
| `classification.scan_image_coverage_threshold` | `0.7` | Image coverage ratio that marks a page as having a scan image. | 0..1 ratio | Raise when incidental images cause hybrid classification; lower when full-page scans are not recognized. | 0.70→0.80/0.90 for false scan; 0.70→0.60 for missed scan. |
| `classification.horizontal_line_density_min` | `0.002` | Minimum horizontal-line density used by layout classification. | nonnegative ratio | Raise when text strokes trigger bordered/mixed; lower when faint horizontal rules are missed. | 0.002→0.003/0.005 for false lines; →0.001 for faint rules. |
| `classification.vertical_line_density_min` | `0.001` | Minimum vertical-line density used by layout classification. | nonnegative ratio | Raise for false vertical separators; lower for faint real separators. | 0.001→0.002/0.003 for false lines; →0.0005 for faint rules. |
| `classification.alignment_score_min` | `0.35` | Alignment threshold for classifying borderless tables. | 0..1 ratio | Raise when dense prose is misclassified as a table; lower when true borderless tables are called free text. | 0.35→0.45/0.60 for prose; →0.20/0.30 for missed tables. |
| `digital_text.quality_min` | `0.72` | Minimum selectable-text quality required to trust digital text directly. | 0..1 ratio | Raise when garbled PDF text is being trusted; lower when clean text unnecessarily goes through OCR. | 0.72→0.80/0.90 for garbled layers; →0.60/0.65 for clean text. |
| `digital_text.fallback_to_ocr_when_garbled` | `true` | If selectable digital text quality falls below `digital_text.quality_min`, allow the page strategy to switch to OCR instead of trusting the bad text layer. | boolean | Set true when garbled/incorrect selectable text must fall back to OCR; set false only when intentionally forcing the digital layer for diagnosis. | Keep true normally; false only for controlled digital-text debugging. |
| `render.default_dpi` | `400` | Requested page render DPI for scanned/OCR paths. | number; clamped by minimum/maximum | Raise for tiny text, decimal points, Arabic diacritics; lower for memory/time. | 400→500; use 600 only for difficult pages. 400→300 for clear large print. |
| `render.minimum_dpi` | `300` | Lower clamp for render DPI. | positive number | Raise to forbid low-quality runs; lower for quick previews. | 300→400 for quality-first; →200/250 only for diagnostics. |
| `render.maximum_dpi` | `600` | Upper clamp for render DPI. | positive number | Raise only when 600+ is intentionally needed; lower to protect memory. | 600 usually keep; 600→500 for constrained RAM. |
| `render.use_embedded_image_when_possible` | `true` | Prefer extracting a full-page embedded scan image instead of re-rendering the page. | boolean | Keep true for lossless scan extraction; false if embedded images are malformed or page composition must be rendered. | true normally; set false only when extracted embedded image is unusable. |
| `render.embedded_image_minimum_dpi` | `250` | Minimum estimated embedded-image DPI considered useful before optional re-render. | positive number | Raise to reject weak embedded scans; lower if native image is still preferable. | 250→300/350 to force re-render more often; →200 to retain more embedded images. |
| `render.rerender_low_resolution_embedded_images` | `true` | If embedded scan is below minimum DPI, re-render the PDF page. | boolean | Disable when preserving exact source pixels is more important than enlarged OCR input. | true for OCR convenience; false for strict native-image retention. |
| `preprocessing.selected_variant` | `auto` | Selects which preprocessing image is used for structure detection; auto chooses binary when foreground density is plausible. | `auto` or an existing variant key | Force only after inspecting debug variants. | Keep auto; choose `08_deskewed`, `07_morphology`, `06_threshold`, or `08_deskewed_gray` only when one is visibly superior. |
| `preprocessing.contrast.enabled` | `true` | Enable contrast enhancement. | boolean | Disable if enhancement amplifies watermark/noise. | true→false when 03_contrast.png is worse than grayscale. |
| `preprocessing.contrast.method` | `clahe` | Contrast method. Code uses CLAHE only for `clahe`; any other value falls back to normalize. | `clahe` or `normalize` | CLAHE for local uneven lighting; normalize for globally faded pages. | Switch clahe↔normalize based on 03_contrast.png. |
| `preprocessing.contrast.clip_limit` | `2.0` | CLAHE strength. | positive float | Raise for faint local text; lower when noise becomes strong. | 2.0→2.5/3.0 for faint text; →1.0/1.5 for noisy scans. |
| `preprocessing.contrast.tile_grid_size` | `[8, 8]` | CLAHE tile grid. | two positive integers | Use more/smaller tiles for local illumination variation; fewer/larger for smoother pages. | [8,8]→[12,12] for more local adaptation; →[4,4] for smoother global effect. |
| `preprocessing.shadow_removal.enabled` | `false` | Enable background/shadow normalization. | boolean | Enable for photographed pages or strong shading. | false→true when background gradients survive contrast. |
| `preprocessing.shadow_removal.kernel_size` | `31` | Median-blur kernel used to estimate background; code forces odd size. | positive integer | Raise for broad shadows; lower if text is being absorbed into background estimate. | 31→41/61 for broad shading; →15/21 for small-scale shading. |
| `preprocessing.denoise.enabled` | `true` | Enable denoising. | boolean | Disable when thin punctuation/Arabic dots disappear. | true→false for very clean scans or when detail loss is visible. |
| `preprocessing.denoise.method` | `median` | Denoising algorithm. | median / gaussian / bilateral | Median for speckle, bilateral to preserve edges, gaussian for smooth noise. | Switch method after comparing 05_denoised.png. |
| `preprocessing.denoise.kernel_size` | `3` | Denoise kernel size; code forces odd size. | positive integer | Raise for speckle; lower when dots/decimals vanish. | 3→5 for noise; 3→1 to preserve tiny marks. |
| `preprocessing.sharpening.enabled` | `false` | Enable unsharp-mask sharpening. | boolean | Enable for soft scans; disable for halos/noise. | false→true only when text edges are visibly blurred. |
| `preprocessing.sharpening.amount` | `1.0` | Unsharp-mask strength. | nonnegative float | Raise for blur; lower for halos. | 1.0→1.5 cautiously; →0.5 if edges ring. |
| `preprocessing.sharpening.radius` | `1.0` | Blur radius used by unsharp mask. | positive float | Raise for broader blur; lower for fine text. | 1.0→1.5/2.0 for broad blur; →0.5 for small fonts. |
| `preprocessing.threshold.enabled` | `true` | Enable binarization. | boolean | Disable/force grayscale when threshold destroys faint details. | true→false if binary variants are worse; selected_variant can also choose grayscale. |
| `preprocessing.threshold.method` | `adaptive_gaussian` | Binarization method. | adaptive_gaussian / adaptive_mean / otsu / global | Adaptive for uneven lighting; Otsu for uniform scans; global only with known histogram. | Try otsu when adaptive speckles; adaptive_gaussian when shadows vary. |
| `preprocessing.threshold.block_size` | `31` | Adaptive threshold neighborhood; code makes it odd ≥3. | odd positive integer | Raise for slowly varying background; lower for small local detail. | 31→41/61 for large illumination changes; →15/21 for tiny text. |
| `preprocessing.threshold.c` | `12` | Constant subtracted in adaptive threshold. | number | Raise to suppress background; lower to retain faint strokes. | 12→15/18 for background noise; →6/8 when decimals/strokes disappear. |
| `preprocessing.threshold.value` | `180` | Threshold used only by global threshold mode. | 0..255 integer | Tune from histogram/debug image when method=global. | 180→160 to retain faint text; →200 to suppress gray background. |
| `preprocessing.threshold.invert` | `true` | Controls binary polarity. | boolean | Structure morphology expects foreground to be white in this pipeline. | Keep true unless a forced downstream variant explicitly needs opposite polarity. |
| `preprocessing.morphology.opening_kernel` | `[1, 1]` | Remove isolated foreground noise using a 2-D kernel. | [width,height] positive integers | Increase only when the corresponding morphology effect is needed; reduce when punctuation/characters distort. | `[1, 1]` → one small step larger/smaller; inspect 07_morphology.png. |
| `preprocessing.morphology.closing_kernel` | `[2, 2]` | Reconnect broken foreground strokes/lines using a 2-D kernel. | [width,height] positive integers | Increase only when the corresponding morphology effect is needed; reduce when punctuation/characters distort. | `[2, 2]` → one small step larger/smaller; inspect 07_morphology.png. |
| `preprocessing.morphology.dilation_kernel` | `[1, 1]` | Thicken foreground using a 2-D kernel. | [width,height] positive integers | Increase only when the corresponding morphology effect is needed; reduce when punctuation/characters distort. | `[1, 1]` → one small step larger/smaller; inspect 07_morphology.png. |
| `preprocessing.morphology.erosion_kernel` | `[1, 1]` | Thin foreground using a 2-D kernel. | [width,height] positive integers | Increase only when the corresponding morphology effect is needed; reduce when punctuation/characters distort. | `[1, 1]` → one small step larger/smaller; inspect 07_morphology.png. |
| `preprocessing.deskew.enabled` | `true` | Enable skew estimation and rotation. | boolean | Disable if straight pages are being falsely rotated. | true normally; false for reliably aligned digital renders. |
| `preprocessing.deskew.maximum_angle` | `10.0` | Largest absolute angle that will be corrected. | nonnegative degrees | Raise only for strongly skewed scans; lower to reject wild estimates. | 10→15 for known tilted scans; →5 for conservative correction. |
| `preprocessing.deskew.minimum_detected_angle` | `0.15` | Skews smaller than this are ignored. | nonnegative degrees | Raise when almost-straight pages are damaged; lower when slight skew causes row/column drift. | 0.15→0.5 for false deskew; →0.05/0.10 for subtle real skew. |
| `bordered_table.enabled` | `true` | Enable line/grid-based bordered table detection. | boolean | Disable for documents where line-like graphics cause persistent false grids. | true normally; false only if borderless route is intentionally forced. |
| `bordered_table.minimum_region_area_ratio` | `0.01` | Minimum page-area fraction for a bordered candidate. | 0..1 ratio | Raise to reject small decorative boxes; lower for small true tables. | 0.01→0.02/0.03 for false regions; →0.005 for small tables. |
| `bordered_table.horizontal.kernel_width_ratio` | `0.03` | Horizontal morphology kernel width as page-width ratio. | positive ratio | Raise when text strokes are mistaken for lines; lower for short/broken real borders. | 0.03→0.05 for false lines; →0.015/0.02 for short rules. |
| `bordered_table.horizontal.kernel_height` | `1` | Horizontal line kernel height in pixels. | positive integer | Raise for thick horizontal rules; keep small to avoid swallowing text. | 1→2 only for thick rules. |
| `bordered_table.horizontal.minimum_line_length_ratio` | `0.1` | Minimum horizontal connected-line length as page-width ratio. | positive ratio | Raise to remove short noise; lower to keep short real borders. | 0.10→0.15/0.20 for noise; →0.05/0.07 for short borders. |
| `bordered_table.horizontal.merge_gap_px` | `12` | Morphological closing gap for horizontal line fragments. | nonnegative pixels | Raise for broken rules; lower when separate features get connected. | 12→18/24 for broken borders; →4/8 for over-merge. |
| `bordered_table.vertical.kernel_height_ratio` | `0.03` | Vertical morphology kernel height as page-height ratio. | positive ratio | Raise to suppress text strokes; lower for short/broken vertical borders. | 0.03→0.05 for false lines; →0.015/0.02 for short borders. |
| `bordered_table.vertical.kernel_width` | `1` | Vertical line kernel width in pixels. | positive integer | Raise for thick vertical rules. | 1→2 only for thick rules. |
| `bordered_table.vertical.minimum_line_length_ratio` | `0.1` | Minimum vertical connected-line length as page-height ratio. | positive ratio | Raise to reject noise; lower for short real separators. | 0.10→0.15/0.20 for noise; →0.05/0.07 for short borders. |
| `bordered_table.vertical.merge_gap_px` | `12` | Morphological closing gap for vertical fragments. | nonnegative pixels | Raise for broken vertical rules; lower for false merges. | 12→18/24 for broken rules; →4/8 for over-merge. |
| `bordered_table.intersections.minimum_area` | `3` | Minimum connected-component area to count a line intersection. | positive pixels | Raise when tiny noise intersections inflate confidence; lower for very thin faint grids. | 3→5/8 for noise; →1/2 for thin rules. |
| `bordered_table.cells.minimum_width_px` | `15` | Reject grid cells narrower than this. | positive pixels | Raise to remove sliver cells; lower when a real narrow column disappears. | 15→20/30 for slivers; →5/10 for narrow columns. |
| `bordered_table.cells.minimum_height_px` | `10` | Reject grid cells shorter than this. | positive pixels | Raise to remove tiny bands; lower for compact rows. | 10→15/20 for noise; →5/8 for compact rows. |
| `bordered_table.cells.minimum_area_px` | `150` | Reject grid cells below this area. | positive pixels² | Raise for noise cells; lower for small real cells. | 150→250/400 for noise; →50/100 for small cells. |
| `bordered_table.row_merge_tolerance_px` | `8` | Merge nearby detected horizontal line positions. | nonnegative pixels | Raise when a thick line creates duplicate boundaries; lower when adjacent real rows merge. | 8→12/16 for duplicate thick-line boundaries; →3/5 for narrow rows. |
| `bordered_table.column_merge_tolerance_px` | `8` | Merge nearby detected vertical line positions. | nonnegative pixels | Raise when thick lines create duplicate columns; lower when close real columns merge. | 8→12/16 for duplicates; →3/5 for close columns. |
| `borderless_table.enabled` | `true` | Enable OCR/digital-word spatial borderless reconstruction. | boolean | Disable only when borderless inference is known to be harmful. | true normally. |
| `borderless_table.row_detection.y_overlap_ratio` | `0.5` | Minimum vertical word overlap that can keep words in the same visual row. | 0..1 ratio | Raise to prevent adjacent lines merging; lower when mixed font sizes split a row. | 0.50→0.65/0.75 for merges; →0.30/0.40 for splits. |
| `borderless_table.row_detection.baseline_tolerance_px` | `8` | Maximum baseline-center distance for same-row clustering. | nonnegative pixels | Raise when one line splits; lower when two rows merge. | 8→12/16 for splits; →4/6 for merges. |
| `borderless_table.row_detection.continuation_line_gap_px` | `18` | Maximum vertical gap for merging a non-anchor continuation line into the previous row. | nonnegative pixels | Raise for wrapped descriptions split into rows; lower when transactions merge. | 18→24/32 for split multiline cells; →8/12 for merged transactions. |
| `borderless_table.row_detection.merge_multiline_rows` | `true` | Enable anchor-aware continuation merging. | boolean | Disable if continuation logic repeatedly merges real rows. | true generally; false for strictly one-line records. |
| `borderless_table.row_detection.anchor_type` | `auto` | Anchor heuristic used by normal borderless continuation logic. | auto / date / amount | Choose the most reliable primary-key-like field in each row. | Use date for date-led statements, amount for stable numeric anchors, auto otherwise. |
| `borderless_table.row_detection.anchor_x_range_ratio` | `null` | Optional horizontal range restricting where row anchors are searched. | null or [x0,x1] page-width ratios | Set when dates/amounts inside descriptions cause false anchors. | Example [0.0,0.25] for a left-side date column; use measured geometry, not a guessed template. |
| `borderless_table.row_detection.anchor_segmentation.enabled` | `false` | Enable stable-anchor row segmentation. | boolean | Enable when each logical record has a reliable date/amount/reference-like anchor and ordinary row clustering fails. | false→true after choosing ROI and candidate source. |
| `borderless_table.row_detection.anchor_segmentation.boundary_mode` | `midpoint` | Convert anchor Y positions to row bands. | midpoint / anchor_start | midpoint when anchor lies near row center; anchor_start when anchor marks row start. | Switch mode based on debug row boxes. |
| `borderless_table.row_detection.anchor_segmentation.anchor_type` | `amount` | Validation rule for anchor candidates. | amount / date / digit_line | Pick the most stable token in the ROI. | amount for balances, date for date column, digit_line when separators OCR poorly. |
| `borderless_table.row_detection.anchor_segmentation.candidate_source` | `roi_ocr` | Source of anchor candidates. | roi_ocr / full_page_words / projection | projection avoids OCR and is forced in crop-only modes; roi_ocr uses semantics; full_page_words reuses page OCR. | Use projection for geometry-only, roi_ocr for semantic reliability. |
| `borderless_table.row_detection.anchor_segmentation.roi_ratio` | `[0.0, 0.25, 0.2, 0.9]` | Anchor search ROI [x0,x1,y0,y1] in page ratios. | four ratios 0..1 | Tighten to exclude header/footer/noise; expand when first/last anchors are missing. | Move one boundary by 0.02–0.05 per test. |
| `borderless_table.row_detection.anchor_segmentation.ocr_mode` | `sparse` | EasyOCR mode for ROI anchor OCR. | mode key | Use sparse for a narrow multi-line ROI; single_line only if ROI is one line. | Keep sparse normally. |
| `borderless_table.row_detection.anchor_segmentation.minimum_confidence` | `0.15` | Reject OCR anchor words below confidence threshold. | 0..1 | Raise for false anchors; lower for faint valid anchors. | 0.15→0.30/0.50 for noise; →0.05/0.10 for faint anchors. |
| `borderless_table.row_detection.anchor_segmentation.minimum_digits` | `1` | Minimum digit count for valid anchor. | positive integer | Raise to reject short numeric noise; lower for one-digit references. | 1→3/4 for dates/amounts where appropriate. |
| `borderless_table.row_detection.anchor_segmentation.minimum_anchors` | `3` | Minimum anchors required for anchor segmentation to be accepted. | positive integer | Raise to avoid accidental segmentation from a few hits; lower for short tables. | 3→5 for long pages; →2 for a true two-row table. |
| `borderless_table.row_detection.anchor_segmentation.minimum_anchor_gap_px` | `20` | Minimum vertical separation before OCR anchor candidates become distinct groups. | nonnegative pixels | Lower when two records are merged; raise when one multi-line anchor becomes multiple rows. | 20→10/15 for merged records; →30/40 for duplicate anchors. |
| `borderless_table.row_detection.anchor_segmentation.default_row_height_px` | `80` | Fallback row height when fewer than two anchor gaps exist. | positive pixels | Set near expected row band height for very short tables. | Scale with DPI; e.g. 80→100 when DPI rises 25%. |
| `borderless_table.row_detection.anchor_segmentation.table_x0_ratio` | `0.0` | Left edge of table used by anchor segmentation. | 0..1 ratio | Move right to exclude margin content; left to include missing first column. | Adjust by ~0.01–0.03 after overlay inspection. |
| `borderless_table.row_detection.anchor_segmentation.table_x1_ratio` | `1.0` | Right edge of table used by anchor segmentation. | 0..1 ratio | Move left to exclude margin content; right to include missing last column. | Adjust by ~0.01–0.03. |
| `borderless_table.row_detection.anchor_segmentation.column_boundaries_ratio` | `null` | Explicit column boundary X ratios for anchor segmentation. | null or ordered ratio list including both edges | Use when auto borderless column inference is unreliable but template geometry is stable. | Set measured ratios; use page_overrides if layouts differ by page. |
| `borderless_table.row_detection.anchor_segmentation.expected_columns` | `1` | If no explicit boundaries are supplied, split table width into this many equal columns. | positive integer | Use only as a simple fallback; equal-width assumption is often wrong. | Set real count only for roughly equal columns; prefer explicit boundaries otherwise. |
| `borderless_table.row_detection.anchor_segmentation.projection_vertical_kernel_ratio` | `0.05` | Vertical-rule removal kernel length relative to ROI height for projection anchors. | positive ratio | Raise to remove longer vertical rules; lower if text strokes are removed. | 0.05→0.08/0.10 for strong rules; →0.02/0.03 for short ROI. |
| `borderless_table.row_detection.anchor_segmentation.projection_close_width_px` | `5` | Horizontal closing width before ink projection. | positive pixels | Raise to join fragmented characters; lower when neighboring content merges. | 5→7/9 for fragmentation; →2/3 for over-merge. |
| `borderless_table.row_detection.anchor_segmentation.projection_close_height_px` | `2` | Vertical closing height before ink projection. | positive pixels | Raise for broken strokes; lower when adjacent lines merge. | 2→3/4 cautiously; →1 for tight rows. |
| `borderless_table.row_detection.anchor_segmentation.projection_ink_threshold_ratio` | `0.02` | Minimum active ink as fraction of ROI width for a row band. | nonnegative ratio | Raise to reject tiny noise bands; lower for sparse/narrow anchors. | 0.02→0.03/0.05 for noise; →0.01 for faint anchors. |
| `borderless_table.row_detection.anchor_segmentation.projection_min_ink_px` | `2` | Absolute minimum active ink pixels for projection band. | nonnegative integer | Raise for noise; lower for tiny anchors. | 2→4/6 for noise; →1 for tiny text. |
| `borderless_table.row_detection.anchor_segmentation.projection_min_band_height_px` | `3` | Reject projection bands shorter than this. | positive pixels | Raise to reject speckles; lower for tiny text. | 3→5 for noise; →1/2 for small fonts. |
| `borderless_table.row_detection.anchor_segmentation.projection_merge_gap_px` | `40` | Merge nearby projection bands into one logical anchor. | nonnegative pixels | Lower when two transactions merge; raise when a two-line anchor splits. | 40→20/30 for merged rows; →50/60 for split multi-line anchors. |
| `borderless_table.row_detection.anchor_segmentation.projection_confidence` | `0.7` | Synthetic confidence assigned to projection-based anchors. | 0..1 | Affects reported confidence, not geometric detection. | Keep 0.70 unless downstream scoring policy changes. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.enabled` | `false` | Enable per-cell OCR refinement after anchor row segmentation. | boolean | Enable when geometry is correct but small numeric/date cells are misread. | false→true after column_types are set. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.types` | `["amount", "date", "time"]` | Semantic field types eligible for refinement. | list of strings | Restrict to fields that benefit from constrained OCR. | Keep amount/date/time; add number/integer if column_types uses them. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.column_types` | `[]` | Semantic type for each anchor-segmented column. | list aligned to columns | Required to know which cells to refine. | Example [date,text,amount,amount,balance/amount] using supported type names. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.retry_empty` | `true` | Re-OCR empty cells. | boolean | Keep true when empty OCR may be a miss. | true for QA; false to save time if blanks are trusted. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.always` | `false` | Always re-OCR eligible cells even when existing OCR is valid/high-confidence. | boolean | Use only for controlled experiments. | false normally; true temporarily for benchmarking. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.existing_confidence_threshold` | `0.9` | Skip refinement when existing value is valid and confidence meets this threshold. | 0..1 | Raise to reprocess more cells; lower to trust original OCR more. | 0.90→0.95 to refine more; →0.80 to refine fewer. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.minimum_confidence` | `0.2` | Minimum confidence for accepting refined OCR candidate. | 0..1 | Raise to reject weak replacements; lower for faint but valid fields. | 0.20→0.40 stricter; →0.10 permissive. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.prefer_valid_candidate` | `true` | Prefer a semantically valid candidate over an invalid existing value. | boolean | Keep true for typed amount/date/time fields. | true recommended. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.scale_factor` | `1.5` | Resize factor before cell OCR. | positive float | Raise for tiny text; reduce when interpolation blurs or runtime grows. | 1.5→2.0 for tiny text; →1.0 for clear crops. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.grayscale` | `true` | Convert crop to grayscale before refinement. | boolean | Disable only when color carries useful contrast. | true normally. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.threshold` | `none` | Optional cell-crop thresholding. | none / otsu / adaptive | Use Otsu for uniform background; adaptive for local shading; none to preserve punctuation. | none→otsu/adaptive only after crop inspection. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.adaptive_block_size` | `31` | Adaptive threshold neighborhood for cell OCR. | odd integer | Raise for broad illumination change; lower for tiny local detail. | 31→41/61 or →15/21. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.adaptive_c` | `11` | Adaptive threshold C for cell OCR. | number | Raise to suppress background; lower to retain faint strokes. | 11→15 for noise; →5/7 for faint text. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.padding_px.top` | `3` | Extra top padding for cell-level OCR refinement, separate from exported crop padding. | nonnegative pixels | Increase for clipped field characters; decrease when neighboring fields leak in. | 3→6 for clipping; reduce toward 0 for bleed. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.padding_px.bottom` | `3` | Extra bottom padding for cell-level OCR refinement, separate from exported crop padding. | nonnegative pixels | Increase for clipped field characters; decrease when neighboring fields leak in. | 3→6 for clipping; reduce toward 0 for bleed. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.padding_px.left` | `8` | Extra left padding for cell-level OCR refinement, separate from exported crop padding. | nonnegative pixels | Increase for clipped field characters; decrease when neighboring fields leak in. | 8→11 for clipping; reduce toward 0 for bleed. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.padding_px.right` | `8` | Extra right padding for cell-level OCR refinement, separate from exported crop padding. | nonnegative pixels | Increase for clipped field characters; decrease when neighboring fields leak in. | 8→11 for clipping; reduce toward 0 for bleed. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.modes.amount` | `single_line` | EasyOCR mode used to re-read amount cells. | mode key defined under ocr.easyocr.modes | Use single_line for one-line financial/date fields; change only if crop content shape differs. | Keep single_line for normal cells. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.modes.date` | `single_line` | EasyOCR mode used to re-read date cells. | mode key defined under ocr.easyocr.modes | Use single_line for one-line financial/date fields; change only if crop content shape differs. | Keep single_line for normal cells. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.modes.time` | `single_line` | EasyOCR mode used to re-read time cells. | mode key defined under ocr.easyocr.modes | Use single_line for one-line financial/date fields; change only if crop content shape differs. | Keep single_line for normal cells. |
| `borderless_table.row_detection.anchor_segmentation.cell_ocr.save_crops` | `true` | Save refined cell crops into debug crop directory. | boolean | Keep true while developing. | true for QA; false to reduce debug files. |
| `borderless_table.column_detection.x_tolerance_px` | `15` | DBSCAN horizontal tolerance when grouping repeated X positions. | positive pixels | Raise when one logical column fragments; lower when adjacent columns merge. | 15→20/25 for fragmentation; →8/10 for merged columns. |
| `borderless_table.column_detection.x_tolerance_word_height_ratio` | `1.0` | Scale borderless X-clustering tolerance from measured word height so native/digital geometry survives render-DPI changes. | 0.2-4.0 | Increase when one logical column fragments because word centers vary with text width/high DPI. Decrease when adjacent real columns merge. | 1.0→1.5/2.0 for fragmented high-DPI columns; →0.5/0.75 if neighbors merge. |
| `borderless_table.column_detection.maximum_x_tolerance_page_ratio` | `0.05` | Safety cap for the DPI-aware borderless X-clustering tolerance as a fraction of page width. | 0.005-0.15 | Increase only when very wide/high-DPI pages still fragment one logical column. Decrease when clustering reaches too far across neighboring columns. | 0.05→0.07/0.10 only if needed; →0.02/0.03 when adjacent columns merge. |
| `borderless_table.column_detection.minimum_column_gap_px` | `20` | Minimum gap between accepted column centers after clustering. Higher values merge more centers. | nonnegative pixels | Raise when one logical column appears as multiple close columns; lower when two close columns merge. | 20→30/40 for over-split; →8/12/15 for undercounted close columns. |
| `borderless_table.column_detection.expected_columns` | `null` | If set, bypasses support-based centers and forces that many center quantiles. | null or positive integer | Use only when column count is truly stable/known. | Set exact count for a stable template; return to null when pages vary. |
| `borderless_table.column_detection.minimum_column_support_rows` | `3` | Minimum number of visual rows that must support an X cluster. | positive integer | Raise to reject random description-word positions; lower for sparse columns. | 3→5/8 for ghost columns; →1/2 for sparse columns. |
| `borderless_table.column_detection.minimum_column_support_ratio` | `0.2` | Minimum fraction of rows supporting a column X cluster. | 0..1 ratio | Raise to reject noise/prose; lower when valid sparse columns vanish. | 0.20→0.35/0.50 for noise; →0.10 for sparse columns. |
| `borderless_table.column_detection.maximum_columns` | `12` | Safety cap on inferred column centers. | positive integer | Raise for genuinely wide tables; lower to constrain over-clustering. | 12→16/20 for wide tables; →8/10 for noisy layouts. |
| `borderless_table.clustering.min_samples` | `1` | DBSCAN minimum samples for horizontal X clusters. | positive integer | Raise to suppress one-off anchors; lower for sparse data. | 1→2/3 for noise; keep 1 for sparse pages. |
| `visual_structure.enabled` | `true` | Enable generic no-OCR visual structure detection used by crop-only modes and as a geometry fallback. | true, false | not numeric; set true to allow shaded/projection structure fallback. not numeric; set false only to isolate/disable this detector for debugging. | Keep true normally; false only to isolate the legacy geometry routes. |
| `visual_structure.text_detection_fallback.enabled` | `true` | Allow detection-only EasyOCR/CRAFT boxes when crop-only visual/native geometry finds no usable structure. | boolean | Disable only when absolutely no neural text detector should be loaded; keep enabled for difficult borderless scans. | Normally `true`. |
| `visual_structure.text_detection_fallback.engine` | `easyocr` | Detection-only text-box backend. | `easyocr` | Change only when another supported backend is added in code. | Keep `easyocr`. |
| `visual_structure.text_detection_fallback.minimum_boxes` | `4` | Minimum detected text boxes before positional row/column clustering is attempted. | integer >=1 | Raise for noisy pages; lower for very sparse tables. | 4→6/10 for noise; 4→2/3 for sparse layouts. |
| `visual_structure.text_detection_fallback.structural_confidence` | `0.60` | Structural confidence hint for detection-only geometry. This is not OCR recognition confidence. | 0.0-1.0 | Lower if detector-only boxes should influence structure less strongly. | Usually keep 0.60. |
| `visual_structure.maximum_analysis_dimension` | `1800` | Maximum internal width/height used by visual-structure analysis before mapping coordinates back to full resolution. | 600-4000 | Increase when tiny structure disappears after internal downscaling and memory permits. Decrease when visual geometry analysis is too slow or memory-heavy. | 1800→2400/3000 for tiny missed structure; →1200/1500 for speed. |
| `visual_structure.shaded_preference_min_confidence` | `0.45` | Confidence above which repeated shaded/filled-cell geometry is preferred over projection geometry. | 0-1 | Increase when weak shaded artifacts incorrectly beat a cleaner borderless projection result. Decrease when real shaded cells are being ignored in favor of projection. | 0.45→0.60 for false shaded wins; →0.30/0.35 when real shaded cells lose. |
| `visual_structure.shaded_grid.enabled` | `true` | Enable detection of repeated filled/shaded cell rectangles without OCR. | true, false | not numeric; true enables this route. not numeric; false disables it for isolation. | Change one small step in the indicated direction, then re-run the failing page only. |
| `visual_structure.shaded_grid.background_percentile` | `95.0` | Estimate page background intensity from this grayscale percentile. | 50-100 | Increase for pages dominated by bright background. Decrease when the high percentile is biased by bright artifacts and misses light-gray cell fills. | 95→98 for very bright backgrounds; →90 when light fills are missed. |
| `visual_structure.shaded_grid.contrast_deltas` | `[6, 8, 10, 12]` | Try multiple darkness deltas below estimated background when isolating shaded cell fills. | list of positive grayscale deltas | Add/larger deltas for darker fills or noisy backgrounds. Use smaller deltas for very faint/light-gray cell fills. | [6,8,10,12]→include 4 for very faint fills; include 16/20 for darker fills. |
| `visual_structure.shaded_grid.blur_kernel_ratio` | `0.006` | Blur scale used to suppress text while preserving broad shaded cell fills. | 0.001-0.03 | Increase when text strokes remain as false filled components. Decrease when small/narrow shaded cells are blurred away. | 0.006→0.008/0.012 to suppress text remnants; →0.003/0.004 for small cells. |
| `visual_structure.shaded_grid.opening_kernel_ratio` | `0.0025` | Morphological opening scale used to remove small noise from the shaded mask. | 0-0.02 | Increase when small noise/text remnants produce false components. Decrease when thin/light real cell fills disappear. | 0.0025→0.004/0.006 for noise; →0.001/0.002 when cells disappear. |
| `visual_structure.shaded_grid.minimum_component_width_px` | `40` | Absolute minimum shaded-component width. | 1+ | Increase to reject small text/logo blobs. Decrease for genuinely narrow shaded columns. | 40→60/80 for small false blobs; →20/30 for narrow real cells. |
| `visual_structure.shaded_grid.minimum_component_width_ratio` | `0.02` | Page-width-relative minimum shaded-component width. | 0-1 | Increase to reject small non-cell rectangles. Decrease for narrow real cells. | 0.02→0.03/0.05 for small false blobs; →0.01 for narrow real cells. |
| `visual_structure.shaded_grid.minimum_component_height_px` | `25` | Absolute minimum shaded-component height. | 1+ | Increase to reject text-line artifacts. Decrease for short real rows. | 25→35/50 for text-line artifacts; →12/18 for short rows. |
| `visual_structure.shaded_grid.minimum_component_height_ratio` | `0.01` | Page-height-relative minimum shaded-component height. | 0-1 | Increase to reject small artifacts. Decrease for short real rows. | 0.01→0.015/0.02 for tiny artifacts; →0.005 for short rows. |
| `visual_structure.shaded_grid.minimum_component_fill_ratio` | `0.8` | Minimum connected-component fill density required to treat a rectangle as a shaded cell. | 0-1 | Increase when text/outline blobs are mistaken for filled cells. Decrease when textured/light real cells are rejected. | 0.80→0.88/0.92 for false text blobs; →0.65/0.75 for textured fills. |
| `visual_structure.shaded_grid.maximum_component_width_ratio` | `0.75` | Reject single shaded components wider than this page-width fraction. | 0-1 | Increase for unusually wide legitimate cells. Decrease when banners/background bands are mistaken for cells. | 0.75→0.90 for legitimate wide cells; →0.50/0.60 for banners. |
| `visual_structure.shaded_grid.maximum_component_height_ratio` | `0.6` | Reject single shaded components taller than this page-height fraction. | 0-1 | Increase for unusually tall legitimate cells. Decrease when large page backgrounds/sidebars become candidates. | 0.60→0.75 for tall cells; →0.30/0.40 for large background regions. |
| `visual_structure.shaded_grid.edge_exclusion_px` | `2` | Ignore shaded components touching the page edge by this margin. | 0+ | Increase when page-edge background/scan borders create false cells. Decrease when a real table intentionally touches the page edge. | 2→5/10 for scan-edge artifacts; →0 when a real table touches the edge. |
| `visual_structure.shaded_grid.row_start_tolerance_px` | `10` | Absolute Y-start tolerance for grouping shaded rectangles into the same row. | 0+ | Increase when one physical row fragments into multiple row groups. Decrease when adjacent rows merge. | 10→15/20 when one row fragments; →4/6 when adjacent rows merge. |
| `visual_structure.shaded_grid.row_start_tolerance_ratio` | `0.012` | Page-height-relative Y-start tolerance for grouping shaded rectangles. | 0-0.1 | Increase for high-resolution/skewed rows that should align. Decrease when neighboring rows are grouped together. | 0.012→0.018/0.025 for drift; →0.005/0.008 for row over-merge. |
| `visual_structure.shaded_grid.minimum_columns` | `2` | Minimum aligned shaded components required to consider a row tabular. | 2+ | Increase to reject two-block layouts that are not tables. Decrease only when two-column tables must be retained. | 2→3/4 to reject non-tables; keep 2 for real two-column tables. |
| `visual_structure.shaded_grid.minimum_rows` | `2` | Minimum aligned rows required to emit a shaded-grid table. | 1+ | Increase to reject isolated decorative grids. Decrease for legitimate one-row tables. | 2→3/4 to reject isolated grids; →1 only for legitimate one-row tables. |
| `visual_structure.shaded_grid.maximum_columns` | `16` | Maximum seed columns accepted before suppressing fragmented/noisy candidates. | 2+ | Increase for genuine very-wide tables. Decrease when text fragments create excessive columns. | 16→20/24 for genuinely wide tables; →10/12 for fragmented noise. |
| `visual_structure.shaded_grid.x_alignment_tolerance_px` | `12` | Absolute X-start tolerance when matching row components to seed columns. | 0+ | Increase when one logical column drifts across rows. Decrease when neighboring columns cross-match. | 12→18/24 for column drift; →6/8 when adjacent columns cross-match. |
| `visual_structure.shaded_grid.x_alignment_tolerance_ratio` | `0.012` | Page-width-relative X alignment tolerance for shaded cells. | 0-0.1 | Increase for high-DPI/layout drift. Decrease for closely spaced columns that merge. | 0.012→0.02 for drift; →0.006/0.008 for close columns. |
| `visual_structure.shaded_grid.minimum_row_match_ratio` | `0.35` | Minimum fraction of seed columns that a row must match. | 0-1 | Increase to reject structurally inconsistent rows/noise. Decrease to keep sparse rows containing many blanks. | 0.35→0.50/0.70 to reject inconsistent rows; →0.20/0.25 for sparse rows. |
| `visual_structure.shaded_grid.minimum_row_matches` | `2` | Absolute minimum seed-column matches required to retain a row. | 1+ | Increase to reject weak/non-tabular rows. Decrease for sparse but valid tables. | 2→3/4 to reject weak rows; →1 for very sparse valid rows. |
| `visual_structure.shaded_grid.table_split_gap_factor` | `2.75` | Multiplier on observed row cadence used when splitting vertically separated table blocks. | 1+ | Increase when one table is incorrectly split. Decrease when separate vertically distant tables are fused. | 2.75→3.5/4.5 if one table splits; →1.8/2.2 if separate tables fuse. |
| `visual_structure.shaded_grid.table_split_gap_page_ratio` | `0.18` | Minimum page-height-relative gap considered when splitting table blocks. | 0-1 | Increase to avoid splitting tables with large row spacing. Decrease to separate tables closer together. | 0.18→0.25/0.30 if one table splits; →0.08/0.12 to split closer tables. |
| `visual_structure.shaded_grid.table_split_gap_height_factor` | `4.0` | Row-height-relative gap factor used for table-block splitting. | 1+ | Increase when wrapped/tall rows trigger false table splits. Decrease when separate tables remain joined. | 4.0→5/6 for tall rows; →2.5/3 when separate blocks stay joined. |
| `visual_structure.shaded_grid.confidence_rows_target` | `4` | Number of aligned rows at which structural confidence reaches its full row-count contribution. | 1+ | Increase to be more conservative on short tables. Decrease to give short tables higher confidence. | 4→6/8 to be conservative; →2/3 to trust short tables sooner. |
| `visual_structure.shaded_grid.outer_padding_px` | `0` | Extra padding added to outer inferred table boundaries. | 0+ | Increase when crop edges cut into the first/last cells. Decrease when table crops bleed into surrounding content. | 0→3/6 when outer cell content is clipped; keep/reduce to 0 for bleed. |
| `visual_structure.shaded_grid.minimum_column_width_px` | `12` | Minimum spacing retained between inferred shaded-grid column boundaries. | 1+ | Increase to remove tiny ghost columns. Decrease for genuine narrow columns. | 12→18/24 to remove ghost columns; →6/8 for narrow real columns. |
| `visual_structure.projection_grid.enabled` | `true` | Enable borderless scanned table inference from text-ink geometry without OCR recognition. | true, false | not numeric; true enables this route. not numeric; false disables it for isolation. | Change one small step in the indicated direction, then re-run the failing page only. |
| `visual_structure.projection_grid.remove_horizontal_line_ratio` | `0.08` | Morphology length used to remove long horizontal rules before text-ink projection. | 0.005-0.5 | Increase when normal text strokes are being removed as rules. Decrease when real long rules remain and become giant text components. | 0.08→0.12/0.18 if text is removed as lines; →0.04/0.06 when real rules remain. |
| `visual_structure.projection_grid.remove_vertical_line_ratio` | `0.08` | Morphology length used to remove long vertical rules before projection. | 0.005-0.5 | Increase when normal glyph strokes are removed as rules. Decrease when long vertical rules remain as false text components. | 0.08→0.12/0.18 if glyphs are removed; →0.04/0.06 when real rules remain. |
| `visual_structure.projection_grid.close_width_px` | `4` | Horizontal closing width that reconnects nearby text fragments before component analysis. | 1+ | Increase when characters/words in one cell remain excessively fragmented. Decrease when adjacent columns begin to connect. | 4→6/10 when text fragments remain separate; →2/3 when neighboring columns connect. |
| `visual_structure.projection_grid.close_height_px` | `1` | Vertical closing height for text-ink components. | 1+ | Increase when broken glyph strokes need reconnecting. Decrease when text from adjacent lines connects vertically. | 1→2/3 for broken strokes; keep 1 when adjacent lines start connecting. |
| `visual_structure.projection_grid.minimum_text_component_area_px` | `8` | Minimum foreground component area retained as text-like ink. | 1+ | Increase to reject speckle/noise. Decrease when tiny punctuation/small-font components vanish. | 8→15/25 for speckle; →3/5 for tiny text. |
| `visual_structure.projection_grid.minimum_text_component_height_px` | `3` | Minimum component height retained as text-like ink. | 1+ | Increase to reject tiny noise. Decrease for very small text. | 3→5/7 for noise; →1/2 for very small text. |
| `visual_structure.projection_grid.maximum_text_component_height_ratio` | `0.08` | Reject projection components taller than this page-height fraction. | 0-1 | Increase for unusually tall text blocks. Decrease when logos/graphics survive as text components. | 0.08→0.12 for tall text blocks; →0.04/0.06 for logos/graphics. |
| `visual_structure.projection_grid.maximum_text_component_width_ratio` | `0.55` | Reject projection components wider than this page-width fraction. | 0-1 | Increase for very long legitimate single-cell text. Decrease when paragraphs/banners become table blocks. | 0.55→0.70 for long cell text; →0.35/0.45 to reject paragraph blocks. |
| `visual_structure.projection_grid.baseline_tolerance_px` | `4` | Absolute vertical tolerance for grouping text components onto one visual line. | 0+ | Increase when one physical line fragments. Decrease when adjacent lines merge. | 4→6/10 when one line fragments; →2/3 when adjacent lines merge. |
| `visual_structure.projection_grid.baseline_tolerance_height_ratio` | `0.8` | Scale baseline grouping tolerance from measured component height. | 0+ | Increase for uneven baselines/scan jitter. Decrease when nearby lines merge. | 0.8→1.2/1.5 for baseline jitter; →0.4/0.6 when lines merge. |
| `visual_structure.projection_grid.baseline_tolerance_page_ratio` | `0.001` | Page-height-relative floor for baseline grouping tolerance. | 0-0.1 | Increase when high-resolution pages fragment rows. Decrease when neighboring lines merge. | 0.001→0.002/0.004 for high-DPI fragmentation; →0.0005 when lines merge. |
| `visual_structure.projection_grid.intra_block_merge_gap_px` | `10` | Absolute horizontal gap below which neighboring text components on one line may be merged into one logical cell block. | 0+ | Increase when one cell remains split into several fragments. Decrease when two close columns merge. | 10→15/25 when one cell fragments; →4/8 when close columns merge. |
| `visual_structure.projection_grid.intra_block_merge_height_ratio` | `1.5` | Adaptive intra-cell merge gap measured in typical text heights. | 0+ | Increase when dates/descriptions/amounts fragment into fake columns. Decrease when genuinely close columns merge. | 1.5→2.0/2.5 for fragmented dates/descriptions; →0.8/1.2 if columns merge. |
| `visual_structure.projection_grid.minimum_columns` | `2` | Minimum text blocks required on a line to consider projection tabular. | 2+ | Increase to reject simple two-block layouts. Decrease only for two-column tables. | 2→3/4 to reject non-tables; keep 2 for true two-column tables. |
| `visual_structure.projection_grid.minimum_rows` | `2` | Minimum aligned projection rows required to emit a table. | 1+ | Increase to reject isolated aligned lines. Decrease for legitimate one-row tables. | 2→3/4 to reject isolated lines; →1 only for legitimate one-row tables. |
| `visual_structure.projection_grid.maximum_columns` | `16` | Maximum projection seed columns before fragment suppression. | 2+ | Increase for genuine very-wide tables. Decrease when fragmented text produces too many columns. | 16→20/24 for wide tables; →10/12 when text fragments create ghost columns. |
| `visual_structure.projection_grid.x_alignment_tolerance_px` | `12` | Absolute X-start tolerance when matching projection blocks to seed columns. | 0+ | Increase when one column drifts across rows. Decrease when neighboring columns cross-match. | 12→18/24 for drift; →6/8 for close columns. |
| `visual_structure.projection_grid.x_alignment_tolerance_ratio` | `0.012` | Page-width-relative X alignment tolerance for projection blocks. | 0-0.1 | Increase for high-DPI/layout drift. Decrease for closely spaced real columns. | 0.012→0.02 for drift/high DPI; →0.006/0.008 for close columns. |
| `visual_structure.projection_grid.minimum_row_match_ratio` | `0.35` | Minimum fraction of seed columns a projection row must match. | 0-1 | Increase to reject inconsistent prose/noise. Decrease for sparse tables with blank cells. | 0.35→0.50/0.70 to reject prose/noise; →0.20/0.25 for sparse rows. |
| `visual_structure.projection_grid.minimum_row_matches` | `2` | Absolute minimum aligned projection blocks needed to retain a row. | 1+ | Increase to reject weak rows. Decrease for sparse valid rows. | 2→3/4 to reject weak rows; →1 for sparse valid rows. |
| `visual_structure.projection_grid.table_split_gap_factor` | `2.75` | Observed-row-cadence multiplier used to split separate projection table blocks. | 1+ | Increase when one table splits incorrectly. Decrease when separate tables are fused. | 2.75→3.5/4.5 if one table splits; →1.8/2.2 if separate tables fuse. |
| `visual_structure.projection_grid.table_split_gap_page_ratio` | `0.18` | Page-height-relative gap threshold for projection table splitting. | 0-1 | Increase for tables with large row spacing. Decrease to split tables that are closer together. | 0.18→0.25/0.30 if one table splits; →0.08/0.12 for closer table separation. |
| `visual_structure.projection_grid.table_split_gap_height_factor` | `4.0` | Row-height-relative projection table split threshold. | 1+ | Increase when tall/wrapped rows cause false splits. Decrease when separate blocks remain joined. | 4.0→5/6 for tall rows; →2.5/3 when separate blocks remain joined. |
| `visual_structure.projection_grid.confidence_rows_target` | `4` | Aligned-row target used when scaling projection structural confidence. | 1+ | Increase to be conservative about short candidates. Decrease to trust short tables more quickly. | 4→6/8 for stricter confidence; →2/3 for short tables. |
| `visual_structure.projection_grid.outer_padding_px` | `0` | Extra padding around outer projection-derived table boundaries. | 0+ | Increase when first/last cells are clipped. Decrease when surrounding content bleeds into crops. | 0→3/6 if outer text is clipped; keep/reduce to 0 for bleed. |
| `visual_structure.projection_grid.minimum_column_width_px` | `12` | Minimum width retained between projection-derived column boundaries. | 1+ | Increase to remove tiny ghost columns. Decrease for narrow legitimate columns. | 12→18/24 to remove tiny ghost columns; →6/8 for narrow real columns. |
| `cropping.add_padding` | `true` | Enable global row/cell crop padding. | boolean | Disable when exact grid boundaries must be preserved. | true normally; false for strict non-overlap crops. |
| `cropping.padding.top` | `5` | Extra pixels above crops. | nonnegative pixels | Raise for clipped ascenders; lower if previous row leaks in. | 5→8/12 for clipping; →0/2 for bleed. |
| `cropping.padding.bottom` | `5` | Extra pixels below crops. | nonnegative pixels | Raise for clipped descenders/decimal marks; lower if next row leaks in. | 5→8/12 for clipping; →0/2 for bleed. |
| `cropping.padding.left` | `8` | Extra pixels left of crops. | nonnegative pixels | Raise when first character is clipped; lower if neighbor text enters. | 8→12/16 for clipping; →2/4 for bleed. |
| `cropping.padding.right` | `8` | Extra pixels right of crops. | nonnegative pixels | Raise when right-edge/RTL characters are clipped; lower if neighbor enters. | 8→12/16 for clipping; →2/4 for bleed. |
| `cropping.clamp_to_page` | `true` | Clamp padded crop box to page image boundaries. | boolean | Keep true to avoid invalid slicing near edges. | true recommended. |
| `cropping.save_all_crops` | `true` | Controls extra bordered-debug crops under the debug directory; independent of output.mode crop export. | boolean | Disable to reduce debug disk usage. | true for debugging; false for lean runs. |
| `fallback.minimum_rows_for_bordered` | `4` | Minimum bordered rows required before bordered candidate can win over borderless. | positive integer | Raise if small false grids win; lower for short real tables. | 4→6/8 for false grids; →2/3 for short tables. |
| `fallback.bordered_score_ratio` | `0.75` | Bordered structural score must reach borderless score × this ratio. Lower values favor bordered. | positive float | Raise to demand stronger bordered evidence; lower when correct grid is being rejected. | 0.75→1.0 for stricter bordered; →0.50/0.60 to favor reliable grid. |
| `fallback.prefer_bordered_when_detected` | `false` | If true, valid bordered rows can be preferred regardless of score comparison once minimum row count is met. | boolean | Enable only when visible grid is authoritative. | false→true for reliably ruled tables; leave false for mixed/noisy documents. |
| `ocr.engine` | `easyocr` | OCR backend. | easyocr / paddleocr | Use EasyOCR by default; PaddleOCR only if installed and intentionally tested. | Keep easyocr unless benchmark shows advantage. |
| `ocr.languages` | `["ar", "en"]` | EasyOCR language list passed to Reader. | list of EasyOCR language codes | Include only languages present in the document to reduce ambiguity. | [ar,en] for mixed Arabic/English; [en] for English-only; [ar] for Arabic-only. |
| `ocr.use_gpu` | `auto` | Device selection for EasyOCR. | auto / true / false / cpu / cuda / mps | Use auto for portability; explicit cpu for reproducible CPU runs. | auto normally; cuda when CUDA is verified; cpu for troubleshooting. |
| `ocr.fallback_to_easyocr` | `true` | When PaddleOCR initialization fails, fall back to EasyOCR. | boolean | Disable only if PaddleOCR failure must be fatal. | true normally. |
| `ocr.page_mode` | `sparse` | Mode name selecting overrides from ocr.easyocr.modes for full-page OCR. | typically sparse / block / row / single_line / single_word / raw_line | Use sparse for full pages; row/single_line for constrained crops. | Keep sparse for page OCR. |
| `ocr.numeric_columns.allowlist` | `0123456789٠١٢٣٤٥٦٧٨٩.,/:-()` | Character allowlist used when OCR call is marked numeric. | string | Add valid currency/date punctuation; remove letters when numeric OCR is confused. | Keep digits plus .,/:-(); add symbols only if truly present. |
| `ocr.easyocr.download_enabled` | `true` | Allow EasyOCR to download missing standard model weights. | boolean | Set false in offline/controlled environments after models are provisioned. | true for first setup with internet; false for production/offline. |
| `ocr.easyocr.model_storage_directory` | `models/easyocr/model` | Directory for EasyOCR detector/recognition weights. | path string | Change only if models are stored elsewhere. | Keep models/easyocr/model when using workspace-local models. |
| `ocr.easyocr.user_network_directory` | `models/easyocr/user_network` | Directory for custom EasyOCR recognition network Python/YAML files. | path string | Change only for alternate model layout. | Keep models/easyocr/user_network for project-local custom networks. |
| `ocr.easyocr.detect_network` | `craft` | EasyOCR detection network name. | string supported by EasyOCR, default craft | Change only when the installed EasyOCR supports and you have tested another detector. | Keep craft for baseline. |
| `ocr.easyocr.recog_network` | `standard` | Recognition network name; `standard` or installed custom network name. | string | Switch after a custom model triplet is installed and validated. | standard→your_model only after .pth/.yaml/.py names match. |
| `ocr.easyocr.verbose` | `true` | EasyOCR Reader verbosity. | boolean | Disable for cleaner logs. | true during setup; false in quiet production runs. |
| `ocr.easyocr_detection.verbose` | `false` | Verbosity for the detection-only Reader. Pipeline device logging remains available even when this is false. | boolean | Set true only while debugging detector initialization. | Keep false normally. |
| `ocr.easyocr_detection.text_threshold` | `0.55` | CRAFT text threshold used only for detection-only structure evidence. | 0.1-0.95 | Lower when faint text boxes are missed; raise when noise becomes boxes. | 0.55→0.45 or 0.65. |
| `ocr.easyocr_detection.low_text` | `0.30` | Lower CRAFT text threshold used while forming candidate regions. | 0.05-0.90 | Lower for faint strokes; raise for noisy backgrounds. | 0.30→0.20 or 0.40. |
| `ocr.easyocr_detection.link_threshold` | `0.30` | Controls how strongly nearby character regions are linked into one box. | 0.05-0.90 | Raise when neighboring fields merge; lower when words fragment. | 0.30→0.40 or 0.20. |
| `ocr.easyocr_detection.canvas_size` | `2560` | Internal CRAFT analysis canvas limit. | positive integer | Raise for tiny text on large pages if memory allows; lower for CPU/memory pressure. | 2560→3200 or 1920. |
| `ocr.easyocr_detection.mag_ratio` | `1.0` | Detector magnification. | positive float | Raise for small text; lower for speed/memory. | 1.0→1.5 or 0.8. |
| `ocr.easyocr_detection.bbox_min_score` | `0.20` | Minimum detector box score when supported by the installed EasyOCR version. | 0.0-1.0 | Raise for false boxes; lower for faint real boxes. | 0.20→0.30 or 0.15. |
| `ocr.easyocr_detection.bbox_min_size` | `3` | Minimum detector box size when supported. | integer >=1 | Raise for tiny noise; lower for very small text. | 3→5 or 2. |
| `ocr.easyocr_detection.structural_box_confidence` | `0.60` | Internal geometry confidence attached to detection-only boxes; never treat it as OCR text confidence. | 0.0-1.0 | Lower if detector boxes should influence structure less. | Usually keep 0.60. |
| `ocr.easyocr.quantize` | `true` | EasyOCR quantization option, mainly CPU-oriented. | boolean | Toggle only after performance/accuracy benchmark. | Keep true on CPU unless model incompatibility appears. |
| `ocr.easyocr.cudnn_benchmark` | `false` | cuDNN benchmark behavior for GPU. | boolean | Enable only for stable image shapes when speed matters. | false for deterministic-ish operation; true only after GPU benchmark. |
| `ocr.easyocr.decoder` | `greedy` | Recognition decoder. | greedy / beamsearch / wordbeamsearch | Use beamsearch when recognition quality improves enough to justify cost. | greedy→beamsearch for difficult text; revert if slow with no gain. |
| `ocr.easyocr.beam_width` | `5` | Beam width for beam decoding. | positive integer | Raise only when using beamsearch and quality improves. | 5→10 cautiously; keep 5 otherwise. |
| `ocr.easyocr.batch_size` | `1` | Recognition batch size. | positive integer | Raise on GPU for throughput if memory allows. | 1→4/8 after VRAM test; keep 1 for reliability. |
| `ocr.easyocr.workers` | `0` | Data-loader worker count used by EasyOCR readtext. | nonnegative integer | Raise for throughput only after Windows multiprocessing behavior is verified. | 0 baseline on Windows; test 1/2 on controlled runs. |
| `ocr.easyocr.min_size` | `5` | Minimum text box size accepted by EasyOCR. | nonnegative integer | Lower for tiny text; raise to reject small noise. | 5→2/3 for tiny text; →8/10 for speckle. |
| `ocr.easyocr.rotation_info` | `null` | Optional rotations EasyOCR tests for text boxes. | null or list such as [90,180,270] | Use when rotated/vertical text is consistently missed. | null→[90,180,270] for rotated headers; expect slower OCR. |
| `ocr.easyocr.contrast_ths` | `0.1` | EasyOCR low-contrast threshold controlling contrast-adjustment retry. | float | Tune when low-contrast boxes are not retried or overprocessed. | 0.10 baseline; test 0.05/0.20 on low-contrast crops. |
| `ocr.easyocr.adjust_contrast` | `0.5` | Contrast adjustment factor used by EasyOCR retry. | float | Raise/lower based on faded crop recognition. | 0.50→0.7 for stronger adjustment; →0.3 if overdone. |
| `ocr.easyocr.filter_ths` | `0.003` | EasyOCR recognition filter threshold. | float | Raise cautiously to reject very weak predictions; lower to retain faint text. | 0.003 baseline; adjust only with measured evidence. |
| `ocr.easyocr.text_threshold` | `0.7` | Detector confidence threshold for text pixels. | 0..1 | Lower for faint text; raise for noise. | 0.70→0.55/0.60 for faint text; →0.80 for false boxes. |
| `ocr.easyocr.low_text` | `0.4` | Lower detector threshold for weak text regions. | 0..1 | Lower for faded text; raise for noise. | 0.40→0.25/0.30 for faint text; →0.50 for noise. |
| `ocr.easyocr.link_threshold` | `0.4` | Text-link confidence threshold joining character regions. | 0..1 | Lower to join broken characters; raise when neighboring text merges. | 0.40→0.30 for fragmented words; →0.50/0.60 for over-merge. |
| `ocr.easyocr.canvas_size` | `2560` | Maximum detector canvas dimension. | positive integer | Raise for large/high-DPI pages if text is missed; lower for memory. | 2560→3200/4096 for large pages; →1920 for memory pressure. |
| `ocr.easyocr.mag_ratio` | `1.0` | Image magnification used by EasyOCR detector. | positive float | Raise for tiny text; lower for speed/memory. | 1.0→1.25/1.5 for tiny text; →0.75 for speed. |
| `ocr.easyocr.slope_ths` | `0.1` | Tolerance for slope when merging text boxes. | float | Raise for slanted same-line text; lower when different lines merge. | 0.10→0.2 for slant; →0.05 for strict rows. |
| `ocr.easyocr.ycenter_ths` | `0.5` | Vertical-center tolerance for merging boxes. | float | Raise when same-line boxes stay split; lower when adjacent lines merge. | 0.50→0.7/0.8 for split lines; →0.3 for merges. |
| `ocr.easyocr.height_ths` | `0.5` | Relative height tolerance for merging boxes. | float | Raise for mixed font sizes in same line; lower for incorrect merges. | 0.50→0.7/0.8 for mixed sizes; →0.3 for over-merge. |
| `ocr.easyocr.width_ths` | `0.5` | Horizontal gap tolerance for merging boxes. | float | Raise to join pieces of one line; lower when adjacent fields merge. | 0.50→0.8/1.0 for split phrases; →0.2/0.3 for merged fields. |
| `ocr.easyocr.add_margin` | `0.1` | Extra margin around detected text boxes. | nonnegative float | Raise for clipped characters; lower for neighbor leakage. | 0.10→0.15/0.20 for clipping; →0.02/0.05 for bleed. |
| `ocr.easyocr.x_ths` | `1.0` | Paragraph-mode horizontal grouping threshold; passed through if supported. | float | Mainly relevant when paragraph grouping is enabled. | Keep 1.0 while paragraph=false. |
| `ocr.easyocr.y_ths` | `0.5` | Paragraph-mode vertical grouping threshold; passed through if supported. | float | Mainly relevant when paragraph grouping is enabled. | Keep 0.50 while paragraph=false. |
| `ocr.easyocr.binary_threshold` | `0.2` | EasyOCR detector binary threshold argument (`threshold`). | float | Tune only after text/low_text/link thresholds. | 0.20 baseline; adjust cautiously by ±0.05. |
| `ocr.easyocr.modes.sparse.paragraph` | `false` | EasyOCR `paragraph` override applied only when OCR mode `sparse` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.sparse.min_size` | `5` | EasyOCR `min_size` override applied only when OCR mode `sparse` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.sparse.text_threshold` | `0.55` | EasyOCR `text_threshold` override applied only when OCR mode `sparse` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.sparse.low_text` | `0.3` | EasyOCR `low_text` override applied only when OCR mode `sparse` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.sparse.link_threshold` | `0.3` | EasyOCR `link_threshold` override applied only when OCR mode `sparse` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.block.paragraph` | `false` | EasyOCR `paragraph` override applied only when OCR mode `block` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.block.width_ths` | `0.7` | EasyOCR `width_ths` override applied only when OCR mode `block` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.block.ycenter_ths` | `0.6` | EasyOCR `ycenter_ths` override applied only when OCR mode `block` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.row.paragraph` | `false` | EasyOCR `paragraph` override applied only when OCR mode `row` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.row.width_ths` | `1.5` | EasyOCR `width_ths` override applied only when OCR mode `row` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.row.ycenter_ths` | `0.8` | EasyOCR `ycenter_ths` override applied only when OCR mode `row` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.row.height_ths` | `0.8` | EasyOCR `height_ths` override applied only when OCR mode `row` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_line.paragraph` | `false` | EasyOCR `paragraph` override applied only when OCR mode `single_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_line.min_size` | `3` | EasyOCR `min_size` override applied only when OCR mode `single_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_line.width_ths` | `10.0` | EasyOCR `width_ths` override applied only when OCR mode `single_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_line.ycenter_ths` | `1.0` | EasyOCR `ycenter_ths` override applied only when OCR mode `single_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_line.height_ths` | `1.0` | EasyOCR `height_ths` override applied only when OCR mode `single_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_line.add_margin` | `0.05` | EasyOCR `add_margin` override applied only when OCR mode `single_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_word.paragraph` | `false` | EasyOCR `paragraph` override applied only when OCR mode `single_word` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_word.min_size` | `2` | EasyOCR `min_size` override applied only when OCR mode `single_word` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_word.width_ths` | `10.0` | EasyOCR `width_ths` override applied only when OCR mode `single_word` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_word.ycenter_ths` | `1.0` | EasyOCR `ycenter_ths` override applied only when OCR mode `single_word` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_word.height_ths` | `1.0` | EasyOCR `height_ths` override applied only when OCR mode `single_word` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.single_word.add_margin` | `0.02` | EasyOCR `add_margin` override applied only when OCR mode `single_word` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.raw_line.paragraph` | `false` | EasyOCR `paragraph` override applied only when OCR mode `raw_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.raw_line.min_size` | `2` | EasyOCR `min_size` override applied only when OCR mode `raw_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.raw_line.width_ths` | `10.0` | EasyOCR `width_ths` override applied only when OCR mode `raw_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.raw_line.ycenter_ths` | `1.0` | EasyOCR `ycenter_ths` override applied only when OCR mode `raw_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.easyocr.modes.raw_line.height_ths` | `1.0` | EasyOCR `height_ths` override applied only when OCR mode `raw_line` is selected. | same type/range as the matching EasyOCR readtext parameter | Tune the mode used by the failing OCR call rather than the global value. | Adjust in small steps; mode-specific value overrides global EasyOCR setting. |
| `ocr.paddleocr.lang` | `arabic` | PaddleOCR backend option `lang`; used only when ocr.engine=paddleocr. | backend-specific value | Tune only if PaddleOCR is intentionally enabled and installed. | Leave default while EasyOCR is primary. |
| `ocr.paddleocr.use_angle_classifier` | `true` | PaddleOCR backend option `use_angle_classifier`; used only when ocr.engine=paddleocr. | backend-specific value | Tune only if PaddleOCR is intentionally enabled and installed. | Leave default while EasyOCR is primary. |
| `ocr.paddleocr.det_db_thresh` | `0.3` | PaddleOCR backend option `det_db_thresh`; used only when ocr.engine=paddleocr. | backend-specific value | Tune only if PaddleOCR is intentionally enabled and installed. | Leave default while EasyOCR is primary. |
| `ocr.paddleocr.det_db_box_thresh` | `0.5` | PaddleOCR backend option `det_db_box_thresh`; used only when ocr.engine=paddleocr. | backend-specific value | Tune only if PaddleOCR is intentionally enabled and installed. | Leave default while EasyOCR is primary. |
| `ocr.paddleocr.det_db_unclip_ratio` | `1.5` | PaddleOCR backend option `det_db_unclip_ratio`; used only when ocr.engine=paddleocr. | backend-specific value | Tune only if PaddleOCR is intentionally enabled and installed. | Leave default while EasyOCR is primary. |
| `schema.columns` | `[]` | Ordered semantic schema for reconstructed columns; each item may contain name and type. | list of objects; supported normalization types include text/date/amount/number | Define only after geometry is correct. Wrong order causes valid OCR to normalize into wrong fields. | Start empty for generic extraction; then add exact ordered column definitions. |
| `reconstruction.remove_repeated_headers` | `true` | Remove repeated rows classified as headers, retaining the first header within each page normalization call. | boolean | Disable if true data rows are being removed as headers. | true normally; false while debugging header heuristics. |
| `reconstruction.header_keywords` | `["date", "description", "debit", "credit", "balance", "invoice", "total", "التاريخ", "البيان", "الوصف", "مدين", "دائن", "الرصيد", "الإجمالي"]` | Keywords used to recognize header rows; at least two matches are required unless row has multiple parseable amounts. | list of strings | Add exact header terms when headers leak into data; remove broad terms if data rows become headers. | Use document vocabulary, not generic words that often occur in descriptions. |
| `validation.enabled` | `true` | Enable validation issue generation. | boolean | Disable only for raw geometry/OCR benchmarking. | true for handoff/production. |
| `validation.confidence_threshold` | `0.75` | Rows below this OCR confidence are flagged. | 0..1 | Raise for stricter review; lower if engine confidence is systematically conservative. | 0.75→0.85 strict; →0.60 permissive. |
| `validation.expected_columns` | `null` | Expected cell count per row for validation. | null or integer | Set after geometry is stable to catch row/column failures. | Set exact count when stable; null for variable layouts. |
| `validation.required_columns` | `[]` | Normalized field names that must be nonempty. | list of schema names | Use for primary key/date/balance fields. | Add only after schema names are defined. |
| `validation.geometry_check.enabled` | `true` | Enable cell bbox overlap/outlier checks. | boolean | Keep on for debugging structure. | true recommended. |
| `validation.geometry_check.overlap_ratio_threshold` | `0.2` | Cell overlap ratio above which a row is flagged. | 0..1 | Lower for stricter non-overlap; raise if intentional overlap/padding triggers false issues. | 0.20→0.10 stricter; →0.30/0.40 if benign overlap. |
| `validation.geometry_check.out_of_page_tolerance_px` | `3` | Negative-coordinate tolerance before OUT_OF_PAGE_BBOX. | nonnegative pixels | Raise only for harmless rounding. | 3→5 for minor transforms; keep low. |
| `validation.geometry_check.unusual_height_zscore` | `3.0` | Robust z-score threshold for unusual row height. | positive float | Lower to catch more merge/split anomalies; raise when legitimate row-height variation causes noise. | 3→2 stricter; →4/5 for variable-height tables. |
| `validation.geometry_check.unusual_gap_zscore` | `3.0` | Robust z-score threshold for unusual row gaps. | positive float | Lower to catch missing/split rows; raise for naturally irregular spacing. | 3→2 stricter; →4/5 for irregular layouts. |
| `validation.balance_check.enabled` | `false` | Enable sequential balance arithmetic validation. | boolean | Enable for statements after schema/sign convention is correct. | false→true only when debit/credit/balance fields are mapped. |
| `validation.balance_check.formula` | `previous_balance + credit - debit` | Balance recurrence. Code recognizes four specific strings; unknown values fall back to previous_balance + credit - debit. | one of the four supported formula strings | Choose based on statement sign convention. | Test a few known consecutive rows before enabling globally. |
| `validation.balance_check.order` | `chronological` | Direction of row sequence for balance validation. | chronological / reverse_chronological | Set to match document ordering. | chronological↔reverse_chronological when all rows mismatch but values are otherwise correct. |
| `validation.balance_check.absolute_debit_credit` | `true` | Use absolute debit/credit magnitudes before formula. | boolean | Disable if source already encodes signs meaningfully. | true for separate debit/credit positive columns; false for signed transaction columns. |
| `validation.balance_check.tolerance` | `0.01` | Allowed absolute arithmetic difference. | nonnegative number | Raise for rounding/currency precision; keep small for exact statements. | 0.01→0.05/0.10 only if source rounds. |
| `validation.balance_check.fields.debit` | `debit` | Schema field name used as debit. | string | Change when schema uses a different name. | Must exactly match schema column name. |
| `validation.balance_check.fields.credit` | `credit` | Schema field name used as credit. | string | Change when schema uses a different name. | Must exactly match schema column name. |
| `validation.balance_check.fields.balance` | `balance` | Schema field name used as balance. | string | Change when schema uses a different name. | Must exactly match schema column name. |
| `validation.date_check.enabled` | `true` | Enable INVALID_DATE checks for schema date fields. | boolean | Keep true after date formats are configured. | true generally. |
| `validation.date_check.allowed_formats` | `["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]` | Accepted strptime formats before a limited YYYYMMDD fallback. | list of format strings | Add source format when valid dates normalize to None. | Add exact format, e.g. %d.%m.%Y; avoid ambiguous formats unless source requires them. |
| `validation.numeric_check.enabled` | `true` | Enable INVALID_NUMERIC checks for amount/number schema fields. | boolean | Keep true after numeric columns are mapped. | true generally. |
| `output.mode` | `full` | Preset controlling Excel/crop/training outputs. Presets override individual switches unless mode=custom. | full / data_only / cropped_cells_only / cropped_rows_only / cropped_rows_and_cells / training_dataset / custom | Use full during debugging/handoff; data_only for final Excel-only; crop modes for geometry/training workflows. | The default now produces Excel plus row/cell crops and manifests. |
| `output.artifact_directory` | `null` | Optional crop/manifest root; relative paths are resolved beside --output. | null or path | Set when artifacts need a stable dedicated location. | Keep null for <output_stem>_artifacts. |
| `output.excel.enabled` | `true` | Excel switch used only when output.mode=custom. | boolean | Do not expect it to override preset modes. | Set mode=custom first, then toggle. |
| `output.crops.save_cells` | `true` | Cell crop switch used only when output.mode=custom. | boolean | Use custom mode for exact output composition. | Set mode=custom first. |
| `output.crops.save_rows` | `true` | Row crop switch used only when output.mode=custom. | boolean | Use custom mode for exact output composition. | Set mode=custom first. |
| `output.crops.include_empty_cells` | `true` | Whether output crop manager saves cells whose raw OCR value is empty. | boolean | Keep true for training/manual review and ambiguous blank detection; false to reduce files. | true for QA; false for compact outputs. |
| `output.crops.include_headers` | `false` | Whether crop manager saves rows marked as headers. | boolean | Enable when header crops are needed for debugging/training. | false→true for header QA. |
| `output.crops.image_format` | `png` | Crop image encoding. | png / jpg / jpeg / webp | Use PNG for OCR/training lossless crops; JPEG/WebP for storage only. | Keep png for data extraction. |
| `output.crops.jpeg_quality` | `95` | JPEG/WebP quality; clamped 1..100. | integer 1..100 | Raise for OCR-visible artifacts; lower for storage. | 95 baseline; avoid lossy formats for OCR training. |
| `output.crops.manifest_csv` | `true` | Write crop_manifest.csv. | boolean | Keep true for developer handoff. | true recommended. |
| `output.crops.manifest_json` | `true` | Write crop_manifest.json. | boolean | Keep true for machine-readable QA. | true recommended. |
| `output.training_dataset.enabled` | `false` | Training dataset switch used only when output.mode=custom; training_dataset preset enables it automatically. | boolean | Use training_dataset preset unless custom composition is required. | Set mode=training_dataset normally. |
| `output.training_dataset.label_source` | `ocr_draft` | Controls the draft label placed in `training_labels.csv`. | `ocr_draft` / `normalized` / `blank` | Use `ocr_draft` for OCR-proposed labels, `normalized` when normalized values are the better draft, and `blank` for fully manual labeling/OCR-miss recovery. | Change this when the training-label workflow—not table geometry—needs adjustment. |
| `export.csv` | `false` | Write optional CSV beside Excel when Excel export runs. | boolean | Enable when flat CSV is needed. | false→true. |
| `export.json` | `true` | Write optional JSON beside Excel when Excel export runs. | boolean | Enable for machine-readable row/cell metadata. | Current default true. |
| `export.jsonl` | `false` | Write optional JSONL beside Excel when Excel export runs. | boolean | Enable for streaming/ML ingestion. | false→true. |
| `export.parquet` | `false` | Write optional Parquet; failures are currently swallowed. | boolean | Enable for analytics when pyarrow is installed. | false→true; verify file exists because exceptions are suppressed. |
| `logging.level` | `INFO` | Python log level used by pipeline logger. | standard level such as DEBUG/INFO/WARNING/ERROR | DEBUG for development; INFO for normal runs. | INFO→DEBUG when diagnosing pipeline control flow. |
| `resume.enabled` | `true` | Maintain resume_state.json of successfully processed pages. | boolean | Disable when every run must be stateless. | true generally. |
| `resume.skip_completed_pages` | `false` | Skip pages already recorded successful in resume state. | boolean | Enable for long resumable jobs; keep false while tuning so pages rerun. | false during tuning; true for stable long jobs. |
| `debug.enabled` | `false` | Enable per-page debug files through configuration. | boolean | Enable when diagnosing geometry/OCR. | false→true for debugging; CLI --debug is often clearer. |
| `debug.output_dir` | `debug_output` | Default root for debug output when --debug-root is not supplied. | path string | Change for workspace organization. | Keep debug_output or set outputs/debug. |

<a id="toc-11-runtime-supported"></a>
## Runtime-supported keys not present in default YAML

<p dir="rtl" align="right">قيم يستطيع الكود التعامل معها وقت التشغيل لكنها ليست مكتوبة افتراضيًا في <code>default.yaml</code>. استخدمها فقط عندما تكون الحالة المطلوبة واضحة ومذكورة هنا.</p>

| Parameter | Status | Use |
|---|---|---|
| `borderless_table.row_detection.anchor_segmentation.boundary_offset_px` | Implemented | In `anchor_start` mode, shifts internal row boundaries relative to anchor centers. Use small ±pixel adjustments after overlay inspection. |
| `borderless_table.row_detection.anchor_segmentation.column_types` | Legacy/fallback read path | Used only if `cell_ocr.column_types` is empty. Prefer `cell_ocr.column_types` for clarity. |
| `ocr.easyocr.blocklist` | Implemented | Passed to EasyOCR for non-numeric calls when set. Use sparingly; an aggressive blocklist can delete legitimate characters. |
| `validation.geometry_check.minimum_samples_for_outlier_stats` | Implemented; code default `8` when omitted | Minimum number of non-header height/gap samples required before robust outlier z-tests run. Prevents unreliable statistics on very small tables with legitimately variable multiline row heights. |

---

<a id="toc-12-parameter-principles"></a>
# 12. Parameter-selection principles

<p dir="rtl" align="right">قواعد اختيار وتعديل الـ Parameters بطريقة منهجية: غيّر أقل عدد ممكن من القيم، استخدم القياسات والـ debug، وثبّت القيم الناجحة بدل التخمين.</p>

1. **Ratios survive DPI changes better than pixel values.** If you raise render DPI from 400 to 500 (+25%), revisit pixel gaps/padding/morphology values; ratio parameters generally do not need the same scaling.
2. **Tune one parameter at a time.** Otherwise you cannot tell which change fixed or broke the page.
3. **Geometry before recognition.** Correct OCR from a wrong crop is not a stable solution.
4. **Use fixed geometry only when measured and stable.** `column_boundaries_ratio` is powerful, but global fixed ratios can break inconsistent pages; use `page_overrides` when necessary.
5. **Do not lower validation just to make warnings disappear.** Fix the underlying row/column/crop problem first.
6. **Do not train on uncorrected OCR.** `training_dataset` produces draft labels; human-correct `corrected_label` before using data for final recognition training.
7. **Preserve evidence.** Keep manifests, raw values, crop paths, and debug overlays for every tuning decision that will be handed to another developer.
8. **Do not equate more OCR rows with better structure.** Multi-line logical records can create many physical OCR lines. Inspect `structure_candidates` and prefer coherent table geometry, not raw row count.
9. **The classifier is a prior, not an order.** `recommended_strategy` says what the page looks like; `structure_method` tells you which evidence actually won. Do not force bordered/borderless behavior globally unless diverse debug evidence proves it is necessary.
10. **For a new PDF, do not pre-tune the baseline.** First run it with the unchanged `configs/default.yaml`; only after inspecting the generated run-config and debug evidence should PDF-specific changes be made.

---

<a id="toc-13-release-checklist"></a>
# 13. Recommended team release checklist

<p dir="rtl" align="right">قائمة تحقق قبل تسليم نسخة جديدة للفريق أو اعتمادها: اختبارات، Smoke tests، توافق الإعدادات، المخرجات، التوثيق، وعدم كسر السلوك العام للمشروع.</p>

Before calling a configuration "done" for a PDF family/template group:

- [ ] `.venv` import smoke test passes.
- [ ] `inspect-config` and the startup `run_configuration` record confirm the intended `output.mode` / OCR state.
- [ ] EasyOCR standard/custom model loads without download surprises.
- [ ] `python -m pytest -q` passes.
- [ ] Representative first/middle/last pages analyzed.
- [ ] Debug rows/columns/cells visually match source.
- [ ] `page_report.json.structure_candidates` was inspected when more than one structure candidate existed; the selected method is supported by geometry rather than inflated physical OCR-line count.
- [ ] `is_header` and `is_total` classifications were spot-checked against real row meaning; transaction descriptions containing words such as `Total` were not misclassified as summary rows.
- [ ] Source row count reconciled where a reliable expected count exists.
- [ ] Column count and semantic schema verified.
- [ ] Required fields validation configured.
- [ ] Numeric/date normalization spot-checked against source.
- [ ] Balance validation enabled when mathematically applicable and sign/order proven.
- [ ] No unexpected repeated headers/footer rows in exported data.
- [ ] Page-specific overrides are documented and minimal.
- [ ] Final run config JSON is saved with the deliverable/test evidence.
- [ ] Final output mode is explicitly selected (`full` during QA, `data_only` for Excel-only delivery when desired).

---

<a id="toc-14-known-limitations"></a>
# 14. Known limitations to communicate during handoff

<p dir="rtl" align="right">قائمة القيود المعروفة حاليًا التي يجب إبلاغ أي مطوّر بها حتى لا يضيع وقتًا في البحث عن Parameter غير موجود أو يفترض أن ميزة غير مطبقة تعمل بالفعل.</p>

The current pipeline is strong as a generic page-adaptive foundation, but the handoff should not claim features that are not yet present:

- No cross-page logical table continuation/linker.
- The v3.1 visual geometry detector can split vertically separated table blocks, but the classic OCR-word borderless detector still emits one region and arbitrary/nested multi-table layouts are not fully solved.
- No rowspan/colspan model.
- No explicit confirmed-blank vs OCR-failure state.
- No dedicated per-cell orientation detector (only EasyOCR rotation options/global retry possibilities).
- No per-column semantic gap thresholds in borderless inference.
- No bordered-table content ROI/margin-exclusion parameter.
- Header recognition is keyword/row-content based, not font/bold/layout-aware.
- Total-row classification now avoids the known `Total POS Purchase` false-positive pattern, but total/summary detection remains heuristic and totals are not automatically separated/dropped from data export.
- The former ParameterAdvisor no-op key was fixed in 3.0.1.
- The former default-output/README/E2E mismatch was fixed in 3.0.1.
- `project.deterministic` and `project.random_seed` are now operational best-effort reproducibility controls.
- The structure candidate selector is now substantially safer against OCR line fragmentation, but it remains a heuristic evidence scorer. Diverse new PDF families must still be validated; no system should claim zero-error structure selection for every possible PDF layout.

These are not reasons to abandon the current architecture; they are explicit boundaries so a new developer knows when to tune configuration and when to implement a feature.

---

<a id="toc-15-validated-baseline"></a>
# 15. Validated baseline (2026-08-18) and the protocol for every new PDF

<p dir="rtl" align="right">هذا القسم يسجل آخر نقطة مستقرة وصل إليها المشروع فعليًا بعد الاختبارات، ويوضح بالضبط ما تم إصلاحه ولماذا، ثم يحدد طريقة بدء أي PDF جديد بدون كسر الـ baseline أو تحويل النظام إلى Template خاص بملف واحد.</p>

## 15.1 What is considered the current baseline?

The current source-of-truth baseline is the project after the following three generic code fixes were applied:

```text
pipeline/pipeline.py
  → structure-candidate arbitration fix

pipeline/validator.py
  → robust geometry outlier statistics fix

pipeline/data_reconstructor.py
  → total-row classification false-positive fix
```

Keep the local backup files temporarily while validating additional PDF families:

```text
pipeline/pipeline.py.before_structure_fix.bak
pipeline/validator.py.before_geometry_fix.bak
pipeline/data_reconstructor.py.before_total_fix.bak
```

Do **not** restore these backups during normal new-PDF testing unless intentionally bisecting a regression.

## 15.2 Why the old selector chose the wrong structure

On the real scanned sample, page 2 visually contains one header plus five logical transactions and seven columns. The visual detector correctly found:

```text
opencv_shaded_grid
rows       = 6
columns    = 7
confidence = 1.0
```

The OCR spatial route also produced a candidate, but it split multiline transaction descriptions into physical text lines:

```text
borderless_spatial
~29 physical OCR rows
6 inferred columns
confidence ≈ 0.77
```

The older scalar score effectively rewarded the larger physical-row count too strongly. A fragmented OCR candidate could therefore beat the correct logical grid simply because it contained more lines.

That is the wrong principle for a universal extractor:

```text
more OCR lines ≠ better table structure
```

A single logical transaction may legitimately contain 5–10 printed text lines inside one tall cell.

## 15.3 How candidate selection works now

The current generic selector compares each available structure candidate using evidence that describes structural quality:

```text
sub-linear row evidence
× median column count
× confidence
× vertical compactness
× text/cell occupancy factor
× column-count consistency
```

The row contribution uses `1 + log1p(row_count)`, so extra rows remain evidence but cannot dominate simply through fragmentation.

`compactness` penalizes candidates stretched across unrelated vertical gaps such as footer text. `median_occupancy` helps distinguish repeatedly populated table rows from sparse continuation fragments when semantic text exists. `column_consistency` rewards a stable column count across rows. In pure crop-only geometry modes, occupancy stays neutral because empty cell text is intentional.

No selector rule uses:

```text
bank name
company name
file name
account-statement keyword
fixed number of columns
hard-coded 6×7 or 7-column template
```

This is the key reason the fix is suitable for future PDF families rather than only the sample that exposed the bug.

### Auditing the decision

Every relevant `page_report.json` now exposes `structure_candidates`. Typical fields are:

```json
{
  "method": "opencv_shaded_grid",
  "score": 27.986,
  "row_count": 6,
  "median_columns": 7,
  "confidence": 1.0,
  "row_factor": 2.946,
  "compactness": 1.0,
  "median_occupancy": 0.0,
  "occupancy_factor": 1.0,
  "column_consistency": 1.0,
  "selected": true
}
```

The exact values depend on the PDF. The purpose is not to force `opencv_shaded_grid`; the purpose is to make the choice explainable. On another document, `bordered_grid`, `borderless_spatial`, `native_digital_spatial`, projection geometry, anchor segmentation, or detection-only fallback may correctly win.

## 15.4 Geometry validator fix

The previous geometry validator could generate impossible warnings such as:

```text
Row height z-score 555675555555.56
```

This occurred when MAD (median absolute deviation) was zero and a tiny epsilon was used as the denominator. The current validator instead:

```text
1. requires enough samples before running height/gap outlier statistics;
2. uses MAD when it has measurable spread;
3. falls back to IQR when MAD is zero;
4. falls back to standard deviation when needed;
5. skips the z-test when no meaningful scale exists.
```

The runtime default is:

```text
validation.geometry_check.minimum_samples_for_outlier_stats = 8
```

The key rule is still: **do not hide geometry warnings by raising z-score thresholds. Fix structure first; fix statistics only when the warning mathematics itself is invalid.**

## 15.5 Total-row classification fix

The previous total classifier could mark a normal transaction as a total simply because a description contained the word `Total`, for example:

```text
Total POS Purchase for MADA Net ...
Fees for Total POS Purchase ...
```

The current logic treats strong summary phrases as totals, and treats plain English `total` as a total marker only when it appears in a short label-like cell. Examples intended to remain totals include:

```text
Total
Total Amount
Grand Total
Subtotal
الإجمالي
المجموع
الرصيد الختامي
```

Long narrative transaction descriptions containing `total` remain normal data rows.

## 15.6 Final validated test evidence

Unit/regression suite:

```text
51 passed, 5 skipped, 2 warnings
0 failed
```

The five skips are still `PDF_TEST_FILE_1..5` environment-driven E2E placeholders. The two warnings are the known EasyOCR/PyTorch quantization deprecation warnings.

Full E2E regression command:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\Account_Statement_scanned.pdf" `
  --output ".\outputs\Account_Statement_scanned_baseline.xlsx" `
  --pages 1-3 `
  --debug `
  --debug-root ".\outputs\debug_baseline"
```

Observed final page results:

| Page | Page/layout classification | Recommended strategy | Selected structure | Structure confidence | Rows | Columns | OCR confidence | Page status |
|---:|---|---|---|---:|---:|---:|---:|---|
| 1 | scanned / mixed | `row_ocr` | `opencv_shaded_grid` | 0.75 | 4 | 7 | 0.8303 | `completed` |
| 2 | scanned / bordered_table | `cell_ocr` | `opencv_shaded_grid` | 1.00 | 6 | 7 | 0.8880 | `completed` |
| 3 | scanned / bordered_table | `cell_ocr` | `opencv_shaded_grid` | 0.9143 | 5 | 7 | 0.9035 | `completed` |

Output summary:

```text
pages_successful             = 3
pages_failed                 = 0
pages_without_rows           = 0
pages_with_structure         = 3
pages_completed_with_warnings = 0
row_crops                    = 13
cell_crops                   = 91
```

The 13 row crops are expected: page 1 has one detected header + 3 data rows, page 2 has one detected header + 5 data rows, and page 3 begins with data and has 5 data rows. With `output.crops.include_headers=false`, that yields `3 + 5 + 5 = 13` saved row crops. `13 × 7 = 91` saved cell crops.

After the total-classification fix, checking all three page reports returned no `is_total=true` rows for the normal `Total POS Purchase` / `Fees for Total POS Purchase` transactions.

## 15.7 Mandatory protocol for the next PDF

A new PDF must first test the **unchanged baseline**. Do not pre-tune because the document looks similar to a previous bank/template.

### Step 1 — keep the active baseline unchanged

Use:

```text
configs/default.yaml
```

Do not edit `default_v3.2.0.reference.yaml`, and do not add filename/company/bank conditions.

### Step 2 — run a representative first extraction with debug

For a small PDF, run representative pages. For a large PDF, start with first/middle/last or other visibly different pages.

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\NEW_FILE.pdf" `
  --output ".\outputs\NEW_FILE_first_run.xlsx" `
  --pages 1 `
  --debug `
  --debug-root ".\outputs\debug_NEW_FILE"
```

### Step 3 — inspect control-flow evidence before tuning

Record at minimum:

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
```

Then inspect `structure_candidates` in the page report. If the structure is wrong, ask **why the wrong candidate scored higher** before touching OCR recognition parameters.

### Step 4 — inspect geometry images in this order

```text
01_original.png
07b_visual_detected_regions.png
08_detected_rows.png
09_detected_columns.png
10_detected_cells.png
12_validation_overlay.png
```

OCR text accuracy is secondary until the geometry matches the source.

### Step 5 — only then decide whether the problem is generic code or PDF-specific tuning

Use this rule:

```text
Bug reproduces across different PDF families / violates a general invariant
→ generic code fix + regression test

Baseline architecture is correct but one PDF needs different tolerances
→ edit that PDF's generated *.run_config.json

A parameter would improve every future PDF and has diverse evidence
→ consider changing configs/default.yaml
```

Do not use `--override` in the normal handoff workflow.

### Step 6 — rerun the unit suite after every code-level generic fix

```powershell
python -m pytest -ra
```

Do not accept a code fix with new failures merely because the current PDF looks better.

## 15.8 What this validation does — and does not — prove

The validated baseline proves that:

```text
the project runs end-to-end on the regression sample;
the selector can reject a high-row-count fragmented OCR candidate;
visual table geometry can win when it has stronger evidence;
geometry validation no longer emits the known zero-MAD false warnings;
transaction descriptions containing "Total" no longer trigger the known false total classification;
all current tests pass.
```

It does **not** prove that every possible PDF in the world will extract without error. PDF structure varies enormously: digital text, scans, hybrid pages, borderless reports, nested tables, rotations, merged cells, poor compression, and multi-page logical tables can expose new failure modes. The architecture is designed to make those failures diagnosable and fixable without turning the system into a collection of document-name-specific hacks.

