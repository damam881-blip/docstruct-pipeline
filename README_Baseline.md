# Universal PDF Extraction Pipeline — Validated Baseline

مشروع عام لاستخراج الجداول والصفوف والخلايا والبيانات من ملفات PDF الرقمية والممسوحة ضوئيًا والهجينة، باستخدام PyMuPDF + OpenCV + EasyOCR مع نظام Configuration قابل للتعديل عبر YAML وJSON.

> **Validated baseline date:** 2026-08-18  
> **Current project metadata:** `3.2.0-text-detection`  
> **Regression status:** `51 passed, 5 skipped, 2 warnings, 0 failed`

للتوثيق الكامل، التشغيل، تفسير الأخطاء، وضبط الـParameters استخدم:

```text
README_DEVELOPER_HANDOFF.md
```

## 1. الفكرة الأساسية

الـPipeline ليست مخصصة لبنك أو شركة أو Template معين. لا توجد شروط تعتمد على اسم الملف أو اسم الجهة أو عدد أعمدة ثابت.

المسار العام:

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

## 2. آخر Baseline تم اعتمادها

تم إصلاح ثلاث مشاكل عامة ظهرت أثناء الـE2E الحقيقي:

### A. Structure Candidate Selection

كان `borderless_spatial` يستطيع الفوز لمجرد أنه يقسم الـmulti-line transaction إلى physical OCR rows كثيرة. تم استبدال هذا المنطق بتقييم Generic يعتمد على:

```text
sub-linear row evidence
confidence
vertical compactness
cell/text occupancy
column consistency
```

القرار النهائي أصبح قابلًا للمراجعة داخل:

```text
page_report.json → structure_candidates
```

### B. Geometry Validation

تم إصلاح حالة `MAD = 0` التي كانت قد تنتج z-scores غير منطقية. الفحص الحالي يستخدم:

```text
minimum sample count
MAD
→ IQR fallback
→ standard deviation fallback
→ skip when no measurable spread exists
```

### C. Total-row Classification

وجود كلمة `Total` داخل وصف طويل مثل:

```text
Total POS Purchase for MADA Net
Fees for Total POS Purchase
```

لم يعد يجعل الـtransaction `is_total=true`. ما زالت العبارات الملخصة مثل `Grand Total`, `Subtotal`, `الإجمالي`, `المجموع` والـshort label-like `Total` قابلة للتصنيف كـTotal.

## 3. آخر E2E Regression

تم تشغيل:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\Account_Statement_scanned.pdf" `
  --output ".\outputs\Account_Statement_scanned_baseline.xlsx" `
  --pages 1-3 `
  --debug `
  --debug-root ".\outputs\debug_baseline"
```

النتيجة:

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

## 4. Config workflow

### قبل أول Run لملف جديد

لا تعدل الـbaseline لأن الملف يبدو مشابهًا لملف سابق.

استخدم:

```text
configs/default.yaml
```

كما هو.

### بعد أول Run

يتم إنشاء:

```text
<output_stem>.run_config.json
```

إذا كان التعديل خاصًا بهذا الـPDF، عدّل القيم داخل `config` في هذا JSON ثم استخدم:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --run-config ".\outputs\FILE.run_config.json" `
  --input ".\samples\FILE.pdf" `
  --output ".\outputs\FILE_second.xlsx"
```

الأولوية التقنية ما زالت:

```text
CLI --override
→ page_overrides
→ JSON --run-config
→ base YAML
```

لكن الـworkflow القياسي للمشروع **لا يستخدم `--override`**.

## 5. أول Test لأي PDF جديد

ابدأ بالـbaseline الحالية بدون tuning:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\NEW_FILE.pdf" `
  --output ".\outputs\NEW_FILE_first_run.xlsx" `
  --pages 1 `
  --debug `
  --debug-root ".\outputs\debug_NEW_FILE"
```

راجع أولًا:

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

ثم الصور بالترتيب:

```text
01_original.png
07b_visual_detected_regions.png
08_detected_rows.png
09_detected_columns.png
10_detected_cells.png
12_validation_overlay.png
```

**Geometry before recognition:** لا تضبط OCR لتحسين Text ناتج من Crop أو Cell geometry خاطئة.

## 6. الفرق بين recommendation والتنفيذ الفعلي

```text
recommended_strategy
```

هو توصية الـclassifier بناءً على شكل الصفحة، مثل `cell_ocr` أو `row_ocr`.

```text
structure_method
```

هو الأسلوب الذي فاز فعليًا في بناء الـrows/columns/cells، مثل:

```text
bordered_grid
opencv_shaded_grid
opencv_projection_grid
native_digital_spatial
borderless_spatial
anchor_row_segmentation
easyocr_detection_spatial
```

لا تفترض أن `bordered_table` يجب دائمًا أن يجبر `bordered_grid`. أفضل Evidence هو الذي يفوز.

## 7. Output modes

| mode | الناتج |
|---|---|
| `full` | Excel + row/cell crops + manifests |
| `data_only` | Excel/data outputs فقط |
| `cropped_cells_only` | Cell crops فقط |
| `cropped_rows_only` | Row crops فقط |
| `cropped_rows_and_cells` | Rows + cells بدون Excel |
| `training_dataset` | Crops + training labels |
| `custom` | تحكم يدوي بالمخرجات |

في crop-only، Character Recognition لا يعمل. إذا فشلت الـnative/OpenCV geometry يمكن استخدام EasyOCR/CRAFT detection-only كـfallback (`recognizer=false`) للحصول على text boxes فقط.

## 8. الاختبارات

قبل أي تعديل Code وبعد أي Generic fix:

```powershell
python -m pytest -ra
```

آخر نتيجة معتمدة:

```text
51 passed
5 skipped
2 warnings
0 failed
```

الـ5 skips بسبب `PDF_TEST_FILE_1..5` غير المعرّفة. الـ2 warnings هي EasyOCR/PyTorch quantization deprecation warnings وليست extraction failures.

## 9. قاعدة اتخاذ القرار عند ظهور مشكلة

```text
مشكلة عامة تكسر invariant وتظهر عبر أنواع ملفات مختلفة
→ Generic code fix + regression test

الـArchitecture صحيحة لكن PDF محدد يحتاج tolerance مختلف
→ PDF-specific *.run_config.json

قيمة مثبت أنها أفضل لكل الملفات المستقبلية بعد اختبارات متنوعة
→ consider configs/default.yaml
```

لا تضف Bank/Company/File-name specific conditions إلى الـcore pipeline.

## 10. Source-of-truth files

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

الـbackup files الخاصة بالإصلاحات الأخيرة يمكن الاحتفاظ بها مؤقتًا أثناء اختبار PDFs جديدة، لكنها ليست ملفات التشغيل الفعلية.

## 11. حدود معروفة

الـbaseline الحالية قوية كأساس Generic لكنها لا تعني أن كل PDF في العالم سيعمل بلا خطأ. ما زالت هناك حدود مثل:

- cross-page logical table continuation غير مطبق بالكامل؛
- arbitrary/nested multi-table layouts ليست محلولة بالكامل؛
- لا يوجد rowspan/colspan model عام؛
- لا يوجد confirmed-blank vs OCR-failure state صريح؛
- total/header classification ما زالا heuristic رغم الإصلاحات الأخيرة؛
- candidate scoring Generic لكنه heuristic ويجب اختباره على PDF families مختلفة.

الهدف هو جعل أي Failure جديد **قابلًا للتشخيص** من الـlogs والـdebug والـcandidate evidence، ثم إصلاحه بشكل عام أو ضبطه عبر run-config بدل تحويل المشروع إلى مجموعة Templates خاصة.
