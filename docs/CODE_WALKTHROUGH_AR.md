# شرح ملفات الـPipeline — النسخة العامة

هذا المستند يشرح مسؤولية كل ملف، البيانات التي يستقبلها، النتائج التي يعيدها، الـParameters المرتبطة به، ومتى يكون تعديل الـParameter كافيًا ومتى يصبح تعديل الكود ضروريًا.

---

# 1. الصورة العامة

المسار التنفيذي الأساسي هو:

```text
main.py
→ ConfigResolver
→ UniversalPDFPipeline
→ PDFAnalyzer
→ PageClassifier
→ DigitalTextExtractor أو ImageExtractor
→ ImagePreprocessor
→ OCR Engine
→ Anchor / Bordered / Borderless detection
→ DataReconstructor
→ Validator
→ Exporter
```

هناك ثلاثة أنواع من التعديل:

## أ. تعديل Parameter فقط

استخدمه عندما تكون الخوارزمية الصحيحة موجودة لكن حساسيتها غير مناسبة، مثل:

- الصفوف تندمج أو تنقسم.
- خطوط الجدول قصيرة أو ضعيفة.
- Padding يقطع أول حرف.
- DPI غير كافٍ.
- Threshold يمحو النقطة العشرية.
- عدد الأعمدة معروف لكن الاستنتاج التلقائي أخطأ.

## ب. تعديل Schema

استخدمه عندما تم اكتشاف الصفوف والأعمدة صحيحًا، لكنك تريد أسماء وأنواعًا محاسبية مثل:

```yaml
schema:
  columns:
    - name: date
      type: date
    - name: description
      type: text
    - name: debit
      type: amount
```

هذا ليس تغييرًا في خوارزمية الاستخراج؛ إنه تعريف معنى الأعمدة.

## ج. تعديل كود Python

يصبح ضروريًا فقط عندما لا توجد الخوارزمية المطلوبة أصلًا، مثل:

- جدول يحتوي صفوفًا متداخلة لا يمكن تمثيلها بالنموذج الحالي.
- الحاجة إلى ربط معاملة استمرت من صفحة إلى الصفحة التالية وفق قاعدة جديدة.
- اكتشاف نوع مستند أو Region جديد لا تدعمه الخوارزمية.
- دمج خلايا معقد يعتمد على سياق دلالي وليس حدودًا هندسية فقط.
- إضافة OCR engine جديد.

---

# 2. `main.py`

## المسؤولية

هو واجهة التشغيل من الـTerminal. لا ينفذ OCR أو OpenCV بنفسه؛ بل يقرأ Arguments ويبني الـPipeline المناسب.

## أهم الوظائف

### `parse_pages()`

تحول:

```text
1,3,5-8
```

إلى:

```python
[1, 3, 5, 6, 7, 8]
```

### `build_parser()`

تعرف الأوامر المتاحة:

- `analyze`
- `diagnose`
- `extract`
- `tune`
- `inspect-config`

### `resolver_from_args()`

يقرأ `default.yaml` ويطبق `--override`.

### `cmd_analyze()`

يشغل التحليل فقط ولا يستخرج Excel.

### `cmd_diagnose()`

يحول القياسات إلى اقتراحات Parameters عامة. لا يحدد اسم البنك ولا يختار Profile.

### `cmd_extract()`

يشغل الـPipeline الكامل.

### `cmd_tune()`

يجرب عدة قيم لParameter واحد ويحسب Score يجمع:

- صحة التواريخ.
- صحة الأرقام.
- نجاح معادلة الرصيد.
- اتساق الهيكل.
- OCR confidence.
- عقوبة Overlap.
- عقوبة القيم المطلوبة الفارغة.

## متى تعدل هذا الملف؟

تعدله فقط إذا أردت:

- إضافة Command جديد.
- إضافة CLI option جديد.
- تغيير طريقة قراءة الصفحات.
- تغيير طريقة حساب Score في `tune`.

لا تعدله لأن OCR أخطأ أو الصفوف اندمجت؛ هذه مشكلات في Modules أخرى أو Parameters.

---

# 3. `config.py`

## المسؤولية

إدارة كل Parameters من مصدر واحد.

## أهم الوظائف

### `deep_merge(base, override)`

تدمج Dictionaries دون تعديل الأصل.

### `get_nested()`

تقرأ Parameter باستخدام dotted path:

```python
get_nested(config, "render.default_dpi")
```

### `set_nested()`

تكتب قيمة داخل Dictionary متداخل.

### `parse_cli_overrides()`

تحول:

```text
--override render.default_dpi=500
```

إلى:

```python
{"render": {"default_dpi": 500}}
```

### `ConfigResolver`

ترتيب الأولوية:

```text
CLI override
→ page override
→ default.yaml
```

## متى تعدل هذا الملف؟

نادرًا. تعدله فقط إذا أردت:

- مصدر Configuration جديد مثل Database.
- Validation صارم لأنواع Parameters.
- Environment variables.
- منع Parameters غير معروفة.

لا تعدله لتغيير DPI أو Threshold؛ عدل YAML أو استخدم `--override`.

---

# 4. `models.py`

## المسؤولية

تعريف شكل البيانات التي تنتقل بين Modules. هذا الملف هو العقد المشترك بين أجزاء النظام.

## Enums

### `PageType`

- `digital`
- `scanned`
- `hybrid`

### `LayoutType`

- `bordered_table`
- `borderless_table`
- `mixed`
- `free_text`

### `Strategy`

- `digital_text`
- `cell_ocr`
- `row_ocr`
- `full_page_ocr`
- `digital_with_ocr_fallback`

## Dataclasses

### `BBox`

يمثل مستطيلًا:

```text
x0, y0, x1, y1
```

ويحتوي وظائف:

- حساب العرض والارتفاع والمساحة.
- التقاطع.
- نسبة التقاطع.
- إضافة Padding.
- Clamp داخل الصفحة.

### `WordBox`

كلمة مع:

- النص.
- الإحداثيات.
- الثقة.
- المصدر Digital أو OCR.

### `TableRegion`

منطقة جدول مستقلة مع حدود صفوف وأعمدة.

### `PageAnalysis`

نتيجة تحليل صفحة كاملة.

### `ExtractedCell`

خلية مستخرجة مع Raw وNormalized وConfidence وCrop path.

### `ExtractedRow`

صف كامل مع الخلايا وحالة Validation.

### `ValidationIssue`

مشكلة واضحة بكود وسبب وموقع.

### `PageExtractionResult`

النتيجة النهائية لصفحة واحدة.

### `TransformChain`

تحويل الإحداثيات بين PDF points وImage pixels وCrop coordinates.

## متى تعدل هذا الملف؟

عندما تحتاج نوع بيانات جديدًا تنتقل به معلومات جديدة بين أكثر من Module، مثل:

- Polygon بدل BBox.
- Confidence منفصل للهيكل وللنص.
- Page role مثل invoice_summary أو transaction_page.

لا تعدله لتغيير حساسية الاكتشاف.

---

# 5. `pipeline/pdf_analyzer.py`

## المسؤولية

فحص PDF وصفحاته قبل الاستخراج.

## ماذا يقيس؟

- النص الرقمي.
- الكلمات الرقمية وإحداثياتها.
- عدد الصور.
- Drawing objects.
- Image coverage.
- Digital text quality.
- Alignment score.
- Estimated embedded-image DPI.
- Horizontal/vertical line density.
- مناطق جداول أولية.
- Average component height.
- Average row and column gaps.

## `analyze_pdf()`

يمر على الصفحات واحدة واحدة ويقارن Layout signature بالصفحة السابقة.

## `analyze_page()`

ينشئ `PageAnalysis` لصفحة واحدة.

## `_quick_lines()`

تحليل منخفض الدقة سريع لتحديد وجود Grid ومؤشرات Layout، وليس الاستخراج النهائي.

## Parameters المرتبطة

```yaml
analysis.thumbnail_dpi
analysis.digital_layout_dpi
classification.*
digital_text.quality_min
```

## متى تعدل Parameters؟

- الصفحة Digital لكن صُنفت Scanned: راجع `digital_min_characters`.
- الصفحة Hybrid لكن صُنفت Digital: راجع `scan_image_coverage_threshold`.
- Borderless صُنفت Free text: راجع `alignment_score_min`.

## متى تعدل الكود؟

- تريد قياسًا جديدًا غير موجود مثل لون الخلفية أو عدد Regions النصية.
- تريد Layout signature أكثر تطورًا من المساواة الحالية.
- تريد أخذ Sample من عدة DPI تلقائيًا.

---

# 6. `pipeline/page_classifier.py`

## المسؤولية

تحويل القياسات إلى قرار:

- نوع الصفحة.
- نوع الـLayout.
- Strategy أولية.

## `classify_page_type()`

يستخدم النص وعدد الكلمات وImage coverage.

## `classify_layout()`

يستخدم كثافة الخطوط وAlignment.

## `choose_strategy()`

- Digital text جيد → Direct extraction.
- Grid واضح → Cell OCR.
- Borderless/Mixed → Row OCR.
- غير ذلك → Full-page OCR.

## متى تعدل Parameters؟

عندما تكون القرارات قريبة من الصحيح لكن Threshold غير مناسب.

## متى تعدل الكود؟

عندما تريد Classifier متعدد الخصائص أو ML model، أو تريد Strategy جديدة.

---

# 7. `pipeline/digital_extractor.py`

## المسؤولية

استخراج الكلمات والـSpans مباشرة من PDF دون OCR.

## `extract_words()`

يستخدم:

```python
page.get_text("words")
```

ويحافظ على BBox وBlock/Line/Word numbers.

## `extract_spans()`

يحافظ على Font وSize وColor.

## `text_quality()`

يحسب جودة النص اعتمادًا على:

- Printable characters.
- Useful characters.
- Control/private characters.
- Replacement characters.

## `alignment_score()`

يقيس مقدار الكلمات التي تشترك في Baselines متقاربة.

## متى تعدل الكود؟

- PDF لديه Encoding غريب لا تكتشفه معادلة الجودة الحالية.
- تحتاج Character-level extraction.
- تحتاج إصلاح Reading order خاص بالـRTL.

---

# 8. `pipeline/image_extractor.py`

## المسؤولية

الحصول على أفضل صورة للصفحة.

## `extract_or_render()`

يحاول بالترتيب:

1. استخراج Full-page embedded image.
2. حساب DPI الحقيقي للصورة.
3. إذا كانت الدقة أقل من الحد، يعمل Render للصفحة.

## `_extract_full_page_image()`

لا يعتبر كل Image داخل PDF صفحة كاملة؛ يشترط Coverage كبيرًا.

## Parameters

```yaml
render.default_dpi
render.minimum_dpi
render.maximum_dpi
render.use_embedded_image_when_possible
render.embedded_image_minimum_dpi
render.rerender_low_resolution_embedded_images
```

## أعراض تحتاج Parameter

- النص صغير وغير واضح → ارفع DPI.
- استهلاك الذاكرة كبير → خفض DPI.
- Embedded scan أوضح من Render → فعّل استخدامه.

## تعديل الكود

- دعم TIFF multi-frame خارجي.
- تحسين اختيار عدة Images مركبة.
- Tile rendering للصفحات الضخمة.

---

# 9. `pipeline/image_preprocessor.py`

## المسؤولية

بناء Variants متعددة من الصورة واختيار Variant مناسب.

## المراحل

1. Original.
2. Grayscale.
3. Contrast/CLAHE.
4. Shadow removal.
5. Denoise.
6. Threshold.
7. Morphology.
8. Deskew.

## `process()`

ينشئ `PreprocessResult` يحتوي:

- كل Variants.
- الصورة المختارة.
- زاوية الميل.
- قياسات Sharpness وForeground ratio.

## `_choose_variant()`

إذا `selected_variant=auto` يقيم نسبة Foreground ويختار Binary أو Gray.

## `_estimate_skew()`

يستخدم `minAreaRect` على Pixels الأمامية.

## أهم الأعراض

### اختفاء النقطة العشرية

- قلل `threshold.c`.
- أوقف Opening/Erosion.
- جرب Gray بدل Binary.

### الحروف مندمجة

- قلل Closing.
- أوقف Dilation.

### Noise كثير

- ارفع denoise قليلًا.
- استخدم median أو bilateral.

### Deskew يفسد الصفحة

- ارفع `minimum_detected_angle`.
- أو عطله.

## متى تعدل الكود؟

- تحتاج تقييمًا متعدد المعايير لاختيار Variant.
- تحتاج Perspective correction فعليًا.
- تحتاج إزالة Stamp متقدمة.
- تريد Unsharp mask أو Sauvola threshold.

---

# 10. `pipeline/layout_analyzer.py`

## المسؤولية

واجهة بسيطة فوق `BorderedTableDetector` مع وظائف رسم Regions/Grid.

لا يحتوي منطقًا كبيرًا حاليًا؛ هو نقطة توسعة لتنظيم Layout analysis مستقبلًا.

## متى تعدل الكود؟

- إضافة Region detector جديد.
- دمج نتائج Bordered وBorderless على مستوى مناطق الصفحة.
- اكتشاف Header/Footer blocks بصورة مستقلة.

---

# 11. `pipeline/bordered_table_detector.py`

## المسؤولية

اكتشاف الجداول ذات الخطوط.

## `detect()`

1. يحول الصورة إلى Foreground أبيض على خلفية سوداء عند الحاجة.
2. يبني Horizontal kernel.
3. يبني Vertical kernel.
4. يعمل Morphological opening لاستخراج الخطوط.
5. يغلق الفجوات الصغيرة.
6. يجمع الخطوط.
7. يجد Contours كمرشحين لجداول.
8. يستخرج X/Y line positions.
9. يبني Cells.
10. يحسب Confidence.

## أهم Parameters

```yaml
bordered_table.horizontal.kernel_width_ratio
bordered_table.vertical.kernel_height_ratio
bordered_table.horizontal.merge_gap_px
bordered_table.vertical.merge_gap_px
bordered_table.minimum_region_area_ratio
bordered_table.row_merge_tolerance_px
bordered_table.column_merge_tolerance_px
bordered_table.cells.minimum_*
```

## تشخيص Debug

- `05_horizontal_lines.png`
- `06_vertical_lines.png`
- `07_detected_regions.png`
- `10_detected_cells.png`

## متى تعدل الكود؟

- التعامل مع Missing borders بصورة أكثر ذكاءً.
- اكتشاف Merged cells فعلي بدل Grid كامل.
- Hough transform كFallback.
- خطوط منحنية أو غير مستقيمة.

---

# 12. `pipeline/borderless_table_detector.py`

## المسؤولية

تحويل WordBoxes إلى صفوف وأعمدة دون الاعتماد على خطوط.

## المراحل

### `_cluster_rows()`

يجمع الكلمات في Baselines بناءً على:

- فرق Y center.
- Y-overlap ratio.

### `_merge_continuations()`

يلحق سطر وصف تابع بالصف السابق إذا:

- المسافة صغيرة.
- الصف السابق يحتوي Anchor.
- السطر الحالي لا يحتوي Anchor.

### `_has_row_anchor()`

يبحث عن Date أو Amount داخل الصف، ويمكن قصر البحث على نطاق X نسبي.

### `_infer_anchors()`

يستخدم DBSCAN على X centers لاستنتاج Column centers ثم يحولها إلى Boundaries.

### `_build_rows()`

يوزع الكلمات على الأعمدة ويكوّن `ExtractedCell` و`ExtractedRow`.

## Parameters

```yaml
borderless_table.row_detection.baseline_tolerance_px
borderless_table.row_detection.y_overlap_ratio
borderless_table.row_detection.continuation_line_gap_px
borderless_table.row_detection.anchor_type
borderless_table.row_detection.anchor_x_range_ratio
borderless_table.column_detection.x_tolerance_px
borderless_table.column_detection.minimum_column_gap_px
borderless_table.column_detection.expected_columns
```

## أعراض شائعة

- معاملة واحدة مقسمة → زد row tolerance/continuation gap.
- معاملتان مدمجتان → قللها.
- عمودان مدمجان → قلل X tolerance أو minimum gap وفق Debug.
- عمود واحد مقسم → زد X tolerance.

## متى تعدل الكود؟

- أكثر من جدول Borderless مستقل في الصفحة.
- Column anchors تتغير جذريًا بين الصفوف.
- تحتاج اكتشاف Header-based columns بدل DBSCAN فقط.
- تحتاج التعامل مع nested tables.

---

# 13. `pipeline/row_detector.py`

## المسؤولية

يوفر طريقتين:

1. `detect_rows_by_baseline()` البسيطة.
2. `AnchorRowSegmenter` للصفوف متعددة الأسطر التي لديها Anchor ثابت.

## `AnchorRowSegmenter.segment()`

1. يحدد ROI نسبية.
2. يجلب Anchor candidates من:
   - ROI OCR.
   - Full-page words.
   - Projection.
3. يتحقق من Amount/Date/Digit line.
4. يدمج Anchors المتقاربة.
5. يحول مراكز Anchors إلى Row boundaries.
6. يستخدم Column boundaries النسبية أو توزيعًا متساويًا.
7. يوزع كلمات الصفحة على الصفوف والخلايا.
8. يمكن إعادة OCR لخلايا رقمية صعبة.

## `_refine_cell_with_crop_ocr()`

يعيد OCR لحقل محدد باستخدام Crop وMode مناسب، ولا يستبدل القيمة إلا إذا كانت المرشحة أفضل أو أكثر صحة.

## `_projection_anchors()`

يستخدم Horizontal ink projection داخل عمود ضيق لاكتشاف Text bands.

## متى تستخدم Parameters؟

عندما يوجد عمود ثابت مثل Date أو Balance أو Reference يحدد كل معاملة.

## متى تعدل الكود؟

- Anchor مكوّن من أكثر من حقل.
- الصف يبدأ بعلامة بصرية وليس نصًا.
- Anchor position يتغير بين أجزاء الصفحة.
- تريد Auto-discovery كامل لعمود Anchor.

---

# 14. `pipeline/column_detector.py`

Helper صغير يستخدم DBSCAN على X centers.

تعدله فقط إذا قررت توحيد أو تطوير Column detection بدل وجود جزء منه داخل `BorderlessTableDetector`.

---

# 15. `pipeline/crop_generator.py`

## المسؤولية

إضافة Padding، Clamp، حفظ Crop، وإنشاء Transform chain جديد للـCrop.

## Symptoms

- أول حرف مقطوع → زد Left padding.
- آخر رقم مقطوع → زد Right padding.
- نص صف مجاور داخل Crop → قلل Top/Bottom padding أو أصلح Row boundary.

## تعديل الكود

- إزالة خطوط من Crop قبل OCR.
- Perspective crop.
- Polygon crop.

---

# 16. `pipeline/ocr_engine.py`

## المسؤولية

واجهة موحدة لمحركات OCR، والمحرك الافتراضي في هذه النسخة هو EasyOCR.

## `OCRResult`

يحتوي النص، الثقة، WordBoxes، اللغة، والمحرك.

## `EasyOCREngine`

- ينشئ `easyocr.Reader` للغتين المحددتين داخل `ocr.languages`.
- يخزن Reader في Cache حتى لا يعيد تحميل الأوزان لكل صفحة.
- يحدد CPU/GPU من `ocr.use_gpu`.
- يمرر Parameters الخاصة بكل نوع Crop من `ocr.easyocr.modes`.
- يطبق `allowlist` على الحقول الرقمية.
- يستطيع تحميل Recognition Model مخصص من `model_storage_directory` و`user_network_directory`.

## `PaddleOCREngine`

Adapter اختياري. عند فشله يمكن الرجوع إلى EasyOCR وفق `ocr.fallback_to_easyocr`.

## `create_ocr_engine()`

Factory يقبل `easyocr` أو `paddleocr`. لا توجد تبعية تشغيلية على Tesseract في هذا الإصدار.

## متى تعدل Parameters؟

- Crop رقم واحد → `single_word` أو `single_line`.
- Description طويلة → `block` أو `row`.
- Full page → `sparse`.
- علامات مالية تضيع → عدّل `numeric_columns.allowlist` وPadding.
- نص صغير → جرّب `mag_ratio` أو DPI أعلى.

## متى تعدل الكود؟

- إضافة محرك OCR جديد.
- Ensemble بين أكثر من Engine.
- Language detection لكل Crop.

---

# 17. `pipeline/data_reconstructor.py`

## المسؤولية

تحويل Raw OCR إلى قيم قابلة للاستخدام دون حذف Raw evidence.

## `normalize_digits()`

يحول Arabic-Indic وPersian digits إلى Western digits.

## `parse_amount()`

يتعامل مع:

- Commas.
- Decimal points.
- Parentheses negative.
- Unicode minus.
- Thousands separators.

## `parse_date()`

يجرب Formats المعرفة في Validation.

## `normalize_rows()`

يستخدم Schema لإعطاء كل عمود اسمًا ونوعًا.

## Header/Total detection

يحدد الصفوف المتكررة والإجماليات باستخدام Keywords مع حماية من اعتبار معاملة مالية Header.

## متى تعدل Parameters؟

- Date format جديد → `allowed_formats`.
- أسماء أعمدة جديدة → Schema.
- Header keywords جديدة.

## متى تعدل الكود؟

- Decimal convention معقد خاص ببلد.
- Date هجري.
- Currency code extraction.
- قواعد تصحيح OCR مؤكدة ودقيقة.

---

# 18. `pipeline/validator.py`

## المسؤولية

منع النظام من الادعاء أن النتائج صحيحة دون دليل.

## أنواع Validation

- Confidence.
- Expected column count.
- Required fields.
- Duplicate rows.
- Date/number validity.
- Invalid/out-of-page BBox.
- Overlapping cells.
- Unusual row height/gap.
- Missing cells.
- Balance sequence.

## Balance validation

يدعم عدة صيغ آمنة دون `eval`.

## متى تعدل Parameters؟

- Threshold مراجعة منخفض/مرتفع.
- Tolerance الرصيد.
- ترتيب Chronological/Reverse.
- أسماء Debit/Credit/Balance.

## متى تعدل الكود؟

- معادلات مالية إضافية.
- Validation بين صفحات.
- VAT arithmetic.
- Invoice line total checks.

---

# 19. `pipeline/exporter.py`

## المسؤولية

إنشاء Excel وإصدارات CSV/JSON/JSONL/Parquet.

## Sheets

- Extracted Data.
- Review Required.
- Extraction Metadata.
- Parameter Configuration.
- Test Summary.
- Cell Metadata.

## نقاط مهمة

- Raw values محفوظة.
- Crop links تتحول إلى Hyperlinks.
- Rows المراجعة Highlighted.
- النص الذي يبدأ بـ`=` لا يترك كFormula.

## متى تعدل الكود؟

- تصميم Excel مختلف.
- Sheets إضافية.
- Mapping خاص إلى Template محاسبي.
- Database output.

---

# 20. `pipeline/parameter_advisor.py`

## المسؤولية

تحويل Measurements إلى اقتراحات عامة واضحة.

لا يقرأ اسم الملف ولا يختار Config محفوظة.

أمثلة:

- Scan low DPI → يقترح 500 DPI.
- Borderless → يقترح Row cropping وفحص صور الصفوف والأعمدة.
- Bordered ضعيف → يقترح تقليل Kernel ratios وMinimum line length.
- Digital text corrupted → يؤكد OCR fallback.

## متى تعدل الكود؟

عندما تتعلم قاعدة تشخيص عامة تنطبق على مستندات كثيرة، وليس على شركة واحدة فقط.

مثال صالح:

> إذا Foreground ratio أقل من حد معين والنص ضعيف، اقترح تقليل Threshold C.

مثال غير صالح:

> إذا اسم الملف يحتوي الراجحي، استخدم ROI معينة.

---

# 21. `pipeline/logging_utils.py`

يخرج Structured JSON logs لتسهيل البحث والتحليل.

تعدله إذا أردت:

- Log file rotation.
- إضافة Trace ID.
- إرسال Logs إلى ELK أو Loki.

---

# 22. `pipeline/pipeline.py`

## المسؤولية

Orchestrator الرئيسي. يجمع كل Modules لكنه لا يجب أن يحتوي تفاصيل خوارزمية كثيرة.

## `extract()`

- يفتح PDF مرة واحدة.
- يمر على الصفحات تدريجيًا.
- يستخدم Resume state.
- يصدر النتيجة بعد انتهاء الصفحات.

## `_process_page()`

المسار الحقيقي للصفحة:

1. Analyze.
2. Create OCR engine.
3. Digital words أو render/OCR.
4. Coordinate scaling.
5. Anchor segmentation إن كانت مفعلة.
6. Bordered detection.
7. Borderless detection.
8. مقارنة Structural scores.
9. Free-text fallback.
10. Normalize.
11. Validate.
12. Save debug report.
13. Structured logging.

## `_rows_from_bordered()`

يوزع الكلمات على Grid cells باستخدام Intersection أو Center point.

## `_structural_row_score()`

يقارن مرشحي Bordered وBorderless بناءً على:

- عدد الصفوف.
- عدد الخلايا غير الفارغة.
- Confidence.

## متى تعدل الكود؟

- تغيير ترتيب الـFallback.
- تشغيل أكثر من OCR variant والمقارنة.
- Region-by-region strategy routing.
- Parallel page processing.
- Cross-page reconstruction.

لا تعدله عندما تحتاج فقط DPI أو Row tolerance.

---

# 23. `configs/default.yaml`

هو المكان الطبيعي لمعظم الضبط.

تذكر الفرق:

- Ratio: مرتبط بحجم الصفحة ويظل قريبًا عند تغيير DPI.
- Pixel: مرتبط بدقة الصورة وقد يحتاج Scale عند تغيير DPI.

استخدم `--override` أولًا، وبعد التأكد من نجاح القيمة يمكنك تعديل Default إذا أصبحت قاعدة عامة مناسبة لمعظم المستندات.

لا تضف Coordinate خاصة باسم ملف إلى Default؛ هذا يحول المشروع إلى Script مخفي خاص بمستند.

---

# 24. `tests/`

## الهدف

التأكد أن تعديل Parameter أو Code لم يكسر أجزاء أخرى.

## الملفات

- `test_classification.py`: Digital/Scanned/Hybrid.
- `test_layout.py`: Bordered/Borderless/Columns/Multiline.
- `test_reconstruction_validation.py`: أرقام وتواريخ ورصيد.
- `test_transform_config.py`: Coordinates وترتيب Configuration.
- `test_generic_edition.py`: لا Profiles ولا اعتماد على اسم ملف.
- `test_e2e_uploaded_files.py`: تشغيل نفس Default config على ملفات فعلية عند توفير Environment variables.

شغل الاختبارات بعد أي تعديل كود:

```powershell
pytest
```

---

# 25. خريطة: النتيجة الخاطئة تقودك إلى أي ملف؟

| العرض | ابدأ من | غالبًا Parameter أم Code؟ |
|---|---|---|
| الصفحة صُنفت خطأ | `pdf_analyzer.py`, `page_classifier.py` | Parameter أولًا |
| الصورة ضعيفة | `image_extractor.py` | Parameter |
| النقاط/الفواصل اختفت | `image_preprocessor.py` | Parameter |
| خطوط الجدول غير مكتشفة | `bordered_table_detector.py` | Parameter |
| الصفوف مدمجة/مقسمة | `borderless_table_detector.py`, `row_detector.py` | Parameter |
| الأعمدة خاطئة | `borderless_table_detector.py`, `column_detector.py` | Parameter ثم Code عند Layout جديد |
| Crop يقطع النص | `crop_generator.py` | Parameter |
| Crop صحيح والنص خطأ | `ocr_engine.py` | Parameter/Engine |
| النص صحيح لكن الرقم None | `data_reconstructor.py` | Format ثم Code |
| القيم صحيحة لكن Review | `validator.py` | Validation Parameter |
| Excel غير مناسب | `exporter.py` | Code |
| ترتيب Fallback غير مناسب | `pipeline.py` | Code |

---

# 26. القاعدة النهائية قبل تعديل Python

اسأل بالترتيب:

1. هل الصفحة الأصلية واضحة؟
2. هل Variant المعالجة حافظت على الرموز؟
3. هل Table region صحيح؟
4. هل Row boxes صحيحة؟
5. هل Column boundaries صحيحة؟
6. هل Crop صحيح؟
7. هل OCR وحده هو المخطئ؟
8. هل Normalization فقط هي المخطئة؟
9. هل Validation convention هو المخطئ؟

لا تعدل Python إلا إذا وصلت إلى خطوة محددة ووجدت أن الـParameter المطلوب غير موجود أو أن الخوارزمية نفسها غير قادرة على تمثيل الحالة.
