# استخدام ملف JSON قابل للتعديل بين التشغيلات

## الفكرة

لا تعدّل Parameters داخل ملفات Python. التشغيل الأول يقرأ `configs/default.yaml`، ثم يكتب ملفًا كاملًا قابلًا لإعادة الاستخدام:

```text
outputs/result.run_config.json
```

عدّل القيم داخل الكائن `config` فقط، ثم مرّر الملف نفسه في التشغيل التالي باستخدام `--run-config`.

## أولوية الإعدادات

```text
CLI --override
→ page_overrides
→ JSON --run-config
→ configs/default.yaml
```

هذا يعني أن قيمة موجودة داخل JSON تتغلب على القيمة الافتراضية داخل YAML، دون تعديل الكود.

## التشغيل الأول

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\Account_Statement_scanned.pdf" `
  --output ".\outputs\account_statement_first.xlsx" `
  --pages "1" `
  --debug `
  --debug-root ".\outputs\debug_first" `
  --save-run-config ".\outputs\account_statement_first.run_config.json"
```

ينشأ افتراضيًا:

```text
outputs\account_statement_first.xlsx
outputs\account_statement_first.run_config.json
outputs\account_statement_first_artifacts\
```

## الجزء الذي يتم تعديله

لا تحذف معلومات الغلاف مثل `format` و`version` و`last_run`. عدّل القيم الموجودة داخل:

```json
{
  "config": {
    "borderless_table": {
      "row_detection": {
        "anchor_segmentation": {
          "enabled": true,
          "boundary_mode": "anchor_start",
          "candidate_source": "roi_ocr",
          "roi_ratio": [0.02, 0.13, 0.475, 0.90],
          "minimum_anchors": 3
        }
      }
    }
  }
}
```

يمكن تعديل Parameters EasyOCR بالطريقة نفسها:

```json
{
  "config": {
    "ocr": {
      "engine": "easyocr",
      "use_gpu": "auto",
      "easyocr": {
        "text_threshold": 0.55,
        "low_text": 0.30,
        "mag_ratio": 1.25
      }
    }
  }
}
```

## التحكم في Output من JSON

### صور الخلايا فقط

```json
{
  "config": {
    "output": {
      "mode": "cropped_cells_only"
    }
  }
}
```

### صور الصفوف فقط

```json
{
  "config": {
    "output": {
      "mode": "cropped_rows_only"
    }
  }
}
```

### Excel فقط

```json
{
  "config": {
    "output": {
      "mode": "data_only"
    }
  }
}
```

### إعداد صور وLabels للتدريب

```json
{
  "config": {
    "output": {
      "mode": "training_dataset",
      "training_dataset": {
        "label_source": "ocr_draft"
      }
    }
  }
}
```

`label_source` يدعم `ocr_draft` أو `normalized` أو `blank`. وضع `blank` مناسب عندما تريد مراجعة/وسم كل Crop يدويًا، ويحتفظ أيضًا بالخلايا التي رجع OCR منها بقيمة فارغة.

القيم المدعومة:

| القيمة | الناتج |
|---|---|
| `full` | Excel + صور الصفوف والخلايا + manifests |
| `data_only` | Excel فقط |
| `cropped_cells_only` | صور الخلايا فقط + manifests |
| `cropped_rows_only` | صور الصفوف فقط + manifests |
| `cropped_rows_and_cells` | صور الصفوف والخلايا دون Excel |
| `training_dataset` | صور الخلايا + `training_labels.csv` |
| `custom` | استخدام المفاتيح الفردية تحت `output.excel` و`output.crops` |

الوضع الافتراضي في `configs/default.yaml` هو `full` حتى يكون التشغيل الأول متوافقًا مع مسار Excel الموثق واختبارات E2E.

توجد أمثلة جاهزة داخل:

```text
configs/examples/cropped_cells_only.json
configs/examples/data_only.json
configs/examples/training_dataset.json
```

## التشغيل الثاني باستخدام JSON المعدّل

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --run-config ".\outputs\account_statement_first.run_config.json" `
  --input ".\samples\Account_Statement_scanned.pdf" `
  --output ".\outputs\account_statement_second.xlsx" `
  --pages "1" `
  --debug `
  --debug-root ".\outputs\debug_second"
```

لا تحتاج إلى كتابة `--override` مرة أخرى؛ القيم أصبحت محفوظة في JSON.

في أوضاع القص فقط، يظل `--output` مطلوبًا كاسم أساسي لملف Run Config ومجلد Artifacts، لكن لن يُنشأ ملف Excel.

## استخدام JSON مختصر بدل الملف الناتج

يمكن تمرير مثال جاهز مباشرة:

```powershell
python .\main.py extract `
  --run-config ".\configs\examples\cropped_cells_only.json" `
  --input ".\samples\Account_Statement_scanned.pdf" `
  --output ".\outputs\cells_only.xlsx" `
  --pages "1"
```

## اختيار اسم ملف JSON الناتج

```powershell
python .\main.py extract `
  --input ".\samples\document.pdf" `
  --output ".\outputs\document.xlsx" `
  --save-run-config ".\configs_runtime\document_parameters.json"
```

## تعطيل إنشاء JSON

```powershell
python .\main.py extract `
  --input ".\samples\document.pdf" `
  --output ".\outputs\document.xlsx" `
  --no-save-run-config
```

## صيغ JSON المقبولة كمدخل

يدعم `--run-config`:

1. ملف `*.run_config.json` الناتج تلقائيًا.
2. ملف `page_report.json` الذي يحتوي على `resolved_config`.
3. ملف JSON عادي يحتوي على كائن `config`.
4. ملف JSON عادي يمثل الإعدادات مباشرة.

يوصى باستخدام `*.run_config.json` لأنه يحتفظ بالإعداد الكامل ومعلومات آخر تشغيل.

## التحقق من القيم قبل التشغيل

فحص وضع Output:

```powershell
python .\main.py inspect-config `
  --run-config ".\outputs\account_statement_first.run_config.json" `
  --parameter "output.mode"
```

فحص Recognition Network:

```powershell
python .\main.py inspect-config `
  --run-config ".\outputs\account_statement_first.run_config.json" `
  --parameter "ocr.easyocr.recog_network"
```
