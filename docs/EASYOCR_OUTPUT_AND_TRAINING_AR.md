# EasyOCR والتحكم في المخرجات وإعداد بيانات التدريب

## 1. ما الذي تغيّر؟

تم استبدال Tesseract بمحرك EasyOCR في المسار الأساسي للمشروع. المحرك يُنشأ مرة واحدة ويُعاد استخدامه بين الصفحات بدل تحميل النموذج لكل صفحة.

الإعدادات الرئيسية:

```json
{
  "config": {
    "ocr": {
      "engine": "easyocr",
      "languages": ["ar", "en"],
      "use_gpu": "auto",
      "easyocr": {
        "recog_network": "standard",
        "model_storage_directory": "models/easyocr/model",
        "user_network_directory": "models/easyocr/user_network",
        "download_enabled": true
      }
    }
  }
}
```

## 2. هل EasyOCR يتعلم تلقائيًا من كل تشغيل؟

لا. التشغيل العادي هو Inference فقط. لكي يتعلم النموذج:

1. استخراج صور الخلايا.
2. مراجعة النص المقترح وتصحيحه بشريًا.
3. تقسيم البيانات إلى Train وValidation.
4. تدريب Recognition Model.
5. وضع النموذج الناتج في مجلدات EasyOCR.
6. تحديد اسمه في `recog_network`.

المشروع ينفذ الخطوات الخاصة بالاستخراج وإعداد الـLabels وتحميل النموذج المخصص، لكنه لا يزعم أن النص الخام غير المصحح يصبح Training Data صالحًا تلقائيًا.

## 3. وضع Cropped Cells فقط

داخل ملف `*.run_config.json`:

```json
{
  "config": {
    "output": {
      "mode": "cropped_cells_only",
      "crops": {
        "image_format": "png",
        "include_empty_cells": true,
        "manifest_csv": true,
        "manifest_json": true
      }
    }
  }
}
```

ثم التشغيل:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --run-config ".\outputs\first.run_config.json" `
  --input ".\samples\Account_Statement_scanned.pdf" `
  --output ".\outputs\cells_only.xlsx" `
  --pages 1
```

لن يُنشأ `cells_only.xlsx`. سيستخدم الاسم لإنشاء:

```text
outputs/cells_only_artifacts/
├── cells/page_0001/*.png
├── crop_manifest.csv
├── crop_manifest.json
└── output_summary.json
```

## 4. وضع Training Dataset

داخل JSON:

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

الناتج يتضمن:

- صور الخلايا.
- `training_labels.csv`.
- `training_labels_draft.tsv`.

أعمدة CSV الأساسية:

| العمود | المعنى |
|---|---|
| `image_path` | مسار صورة الخلية |
| `ocr_draft_label` | النص المقترح من EasyOCR |
| `corrected_label` | النص الصحيح الذي يكتبه المراجع |
| `ocr_confidence` | ثقة OCR |
| `needs_manual_review` | هل تحتاج الخلية مراجعة بسبب ثقة منخفضة أو label فارغ/يدوي؟ |

`output.training_dataset.label_source` له ثلاث قيم تشغيلية:

- `ocr_draft`: يضع `raw_value` في عمود `ocr_draft_label`.
- `normalized`: يضع القيمة بعد normalization في نفس عمود الـdraft.
- `blank`: يترك draft فارغًا ويحافظ على OCR-empty crops حتى يمكن تصحيح حالات الفشل يدويًا.

لا تبدأ التدريب قبل تعبئة `corrected_label` للصور المختارة.

## 5. تجهيز Train وValidation

```powershell
python .\tools\prepare_easyocr_training_dataset.py `
  --labels ".\outputs\training_artifacts\training_labels.csv" `
  --output-dir ".\training_data\my_model" `
  --validation-ratio 0.10 `
  --seed 42
```

الناتج:

```text
training_data/my_model/
├── train/
│   ├── images/
│   ├── labels.csv
│   └── labels.tsv
└── validation/
    ├── images/
    ├── labels.csv
    └── labels.tsv
```

الأداة تتجاهل الصفوف التي لا تحتوي على `corrected_label`. خيار `--allow-draft-labels` موجود للتجارب فقط، وليس المسار الموصى به للتدريب النهائي.

## 6. تحميل Custom Recognition Model

بعد التدريب يجب توفر ثلاثة ملفات بنفس الاسم:

```text
custom_account.pth
custom_account.yaml
custom_account.py
```

تثبيت الملفات:

```powershell
python .\tools\install_custom_easyocr_model.py `
  --name "custom_account" `
  --weights ".\trained\custom_account.pth" `
  --network-yaml ".\trained\custom_account.yaml" `
  --network-py ".\trained\custom_account.py"
```

ثم تعديل JSON:

```json
{
  "config": {
    "ocr": {
      "easyocr": {
        "recog_network": "custom_account"
      }
    }
  }
}
```

## 7. Parameters مهمة داخل EasyOCR

| Parameter | الاستخدام |
|---|---|
| `text_threshold` | قبول مناطق النص القوية |
| `low_text` | السماح بمناطق نص ضعيفة |
| `link_threshold` | دمج أجزاء الحروف والكلمات |
| `mag_ratio` | تكبير الصورة قبل الكشف |
| `width_ths` | دمج الكلمات أفقيًا |
| `ycenter_ths` | دمج الكلمات الموجودة على نفس السطر |
| `add_margin` | هامش إضافي حول النص |
| `decoder` | طريقة فك النص: greedy أو beamsearch |
| `batch_size` | سرعة أعلى على GPU مقابل استهلاك ذاكرة أكبر |

كل هذه القيم قابلة للتعديل داخل JSON الناتج من التشغيل الأول.
