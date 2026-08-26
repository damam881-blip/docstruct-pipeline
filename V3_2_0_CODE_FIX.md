# v3.2.0 Code Fix — Detection-Only Text-Box Fallback

## المشكلة

Crop-only كان يمنع Character Recognition بشكل صحيح، لكن لو Native/OpenCV geometry فشل في جدول Borderless أو ضعيف الحدود، لم يكن هناك مصدر إضافي قوي لمواضع النص، وبالتالي قد ينتج `0 rows / 0 cells`.

## الحل

أضيف مسار Lazy Detection-only باستخدام EasyOCR/CRAFT:

```text
Native PDF geometry
      ↓
OpenCV ruled/shaded/projection geometry
      ↓
Structure found? ── yes ──> Rows / Columns / Cells
      │
      no
      ↓
EasyOCR CRAFT detect() only
recognizer=false
      ↓
Bounding boxes only
      ↓
Positional row/column clustering
      ↓
Rows / Columns / Cells
      ↓
Crops
```

لا يتم وضع أي نص وهمي داخل الخلايا. الخلايا الناتجة من Detection-only يكون `raw_value=""` ويتم تسجيل الثقة كـGeometry confidence وليس OCR confidence.

## Full mode

Full mode يستمر في استخدام نفس مصادر الـStructure، ومعه OCR WordBoxes المقروءة كدليل مكاني إضافي. الاختبارات الجديدة تثبت أن Full يستطيع بناء Cells من مواضع الكلمات المقروءة، بينما Crop-only يستطيع بناء Cells من Detection-only boxes بدون Recognition.

## CPU/GPU

`ocr.use_gpu: auto` ما زال هو الاختيار العام. على جهاز لا يحتوي CUDA-compatible NVIDIA GPU سيعمل detector والrecognizer على CPU. Detection-only Reader مضبوط افتراضيًا على `verbose: false`، بينما الـPipeline يسجل الجهاز المستخدم بوضوح عند تشغيل fallback.

## Regression tests

- Detection-only Reader ينشأ بـ `detector=True`, `recognizer=False`.
- Crop-only يستعيد Rows/Columns/Cells من Bounding Boxes فقط.
- Detection-only crops تسجل كـGeometry وليس OCR.
- Full mode يبني Cells من OCR positional WordBoxes.
- Config upgrade من v3.0.x/v3.1.x يحافظ على `output.mode`.
