# Apply v3.2.0 — Shared Structure + Detection-Only Fallback

> الهدف: تحديث الكود بدون حذف `.venv` أو مجلد `models` وبدون استبدال قيم `configs/default.yaml` الحالية.

## 1. خذ نسخة احتياطية من المشروع

يفضل نسخ مجلد المشروع أو عمل Git commit قبل استبدال الملفات.

## 2. فك Patch في Root المشروع

فك محتويات:

```text
PDF_Reading_Pipeline_v3.2.0_CUMULATIVE_PATCH_PRESERVE_CONFIG.zip
```

داخل:

```text
D:\PDF Reading Pipeline
```

واسمح باستبدال الملفات الموجودة.

الـPatch **لا يحتوي `configs/default.yaml`** حتى لا يمس إعداداتك الحالية. يحتوي فقط Reference YAML منفصل.

## 3. حدّث YAML الحالي بدون تغيير قيمك

```powershell
python .\tools\upgrade_v320_config.py `
  --config ".\configs\default.yaml"
```

سيتم إنشاء Backup تلقائيًا:

```text
configs\default.yaml.pre_v3_2_0.bak
```

الأداة تضيف فقط الإعدادات الناقصة الخاصة بـ Visual Structure وDetection-only fallback وتترك `output.mode` والقيم التشغيلية الحالية كما هي.

## 4. تحقق من الـMode الحالي

```powershell
python .\main.py inspect-config `
  --config ".\configs\default.yaml" `
  --parameter "output.mode"
```

## 5. شغل الاختبارات

```powershell
python -m pytest -ra
```

## 6. اختبار Crop-only

إذا كان:

```yaml
output:
  mode: cropped_rows_and_cells
```

شغل:

```powershell
python .\main.py extract `
  --config ".\configs\default.yaml" `
  --input ".\samples\Account_Statement_scanned.pdf" `
  --output ".\outputs\Account_Statement_scanned.xlsx" `
  --pages 1-3 `
  --debug `
  --debug-root ".\outputs\debug_document"
```

المطلوب في بداية التشغيل:

```text
processing_mode = geometry_plus_text_detection
ocr_recognition_enabled = false
text_detection_fallback_enabled = true
```

هذا **لا يعني أن CRAFT سيعمل في كل صفحة**. يتم تحميله فقط إذا فشل Native/OpenCV geometry في تكوين Structure صالحة.

إذا تم استخدام Detection-only fallback سيظهر في الـlog:

```text
event = text_detection_fallback
recognizer_loaded = false
boxes_detected = ...
```

وفي Debug:

```text
07c_text_detection_boxes.png
```

## 7. اختبار Full

غيّر `output.mode` إلى `full` في YAML لأول تشغيل أو في generated JSON بعد ذلك، ثم شغل نفس أمر `extract`.

في Full:

```text
ocr_recognition_enabled = true
processing_mode = full_extraction
```

ويستمر نفس مبدأ Structure Detection، لكن الـRecognition متاح أيضًا لقراءة محتوى الخلايا وإنتاج Excel.
