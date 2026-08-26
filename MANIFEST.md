# EasyOCR + Editable JSON Output Edition Manifest

هذه النسخة تحتوي على Core عام واحد وإعداد افتراضي واحد، دون Profiles مرتبطة باسم بنك أو شركة أو ملف.

## موجود

- `configs/default.yaml` مع EasyOCR كمحرك افتراضي.
- أوامر `analyze`, `diagnose`, `extract`, `tune`, `inspect-config`.
- دورة Run Config JSON: التشغيل الأول ينشئ JSON، والتشغيل التالي يستقبله عبر `--run-config`.
- أولوية إعدادات: CLI ثم Page overrides ثم JSON ثم YAML.
- أوضاع Output: Excel، Cropped cells، Cropped rows، Training dataset، Custom.
- `crop_manifest.csv` و`crop_manifest.json` و`output_summary.json`.
- أدوات إعداد بيانات تدريب Recognition Model وتثبيت نموذج EasyOCR مخصص.
- تحليل Page-level وDigital extraction وOCR.
- Bordered وBorderless detection وAnchor segmentation.
- Reconstruction وValidation وExcel export وDebug overlays.
- Unit tests وE2E tests.

## غير موجود عمدًا

- مجلد `profiles/`.
- ملفات `file_*_profile.yaml`.
- `--profile` أو `recommend-profile`.
- أي شرط يعتمد على اسم بنك أو شركة أو اسم ملف.
- تدريب تلقائي على نصوص OCR غير مصححة.
- تبعية تشغيلية على Tesseract أو `pytesseract`.

## أولوية الإعدادات

```text
CLI --override
→ page_overrides
→ JSON --run-config
→ configs/default.yaml
```


## إصلاحات 3.0.1

- `output.mode` الافتراضي أصبح `full` ليتطابق التشغيل الفعلي مع README واختبار E2E الخاص بوجود Excel.
- `digital_text.fallback_to_ocr_when_garbled` أصبح Parameter تشغيليًا فعليًا.
- `output.training_dataset.label_source` أصبح يدعم `ocr_draft`, `normalized`, `blank`.
- `project.deterministic` و`project.random_seed` أصبحا Runtime controls بأفضل جهد.
## إضافات 3.1.0

- `pipeline/visual_structure_detector.py`: كشف Structure عام بدون OCR للخلايا المظللة والجداول Borderless المعتمدة على Text-Ink Geometry.
- Crop-only للـDigital/Hybrid يستخدم Native PyMuPDF word coordinates بدون OCR.
- Startup log جديد `run_configuration` يوضح الـeffective mode وOCR/Excel state قبل معالجة الصفحات.
- Warning جديد `NO_STRUCTURE_DETECTED` عند عدم وجود Structure قابل للقص.
- `tools/upgrade_v310_config.py` يضيف Parameters الجديدة إلى YAML القائم بدون تغيير `output.mode`.
- اختبارات Regression جديدة لمسارات Shaded / Borderless / Digital geometry-only.
## إضافات 3.2.0

- `pipeline/ocr_engine.py` يحتوي Detection-only EasyOCR/CRAFT adapter (`recognizer=false`).
- Crop-only يستخدم Text Detection كـ fallback فقط بعد فشل Native/OpenCV structure detection.
- `07c_text_detection_boxes.png` لعرض Bounding Boxes الخاصة بالـ detector.
- `tools/upgrade_v320_config.py` يضيف الإعدادات الجديدة مع الحفاظ على القيم الحالية.
- Crop manifests تظل تميز Detection-only cells كـ geometry وليست OCR recognition.

