from __future__ import annotations

import pymupdf as fitz

from pipeline.pdf_analyzer import PDFAnalyzer


def base_config():
    return {
        "analysis": {"thumbnail_dpi": 72},
        "classification": {
            "digital_min_characters": 10,
            "scan_image_coverage_threshold": 0.70,
            "horizontal_line_density_min": 0.002,
            "vertical_line_density_min": 0.001,
            "alignment_score_min": 0.35,
        },
        "digital_text": {"quality_min": 0.7},
    }


def test_digital_page_classification(tmp_path):
    path = tmp_path / "digital.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "A digital table page with selectable text 123.45")
    doc.save(path)
    doc.close()
    analysis = next(PDFAnalyzer(base_config()).analyze_pdf(path, render_layout=False))
    assert analysis.page_type.value == "digital"
    assert analysis.word_count > 3


def test_scanned_page_classification(tmp_path):
    source = fitz.open()
    page = source.new_page()
    page.insert_text((72, 72), "Rendered scan content")
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    target = fitz.open()
    tpage = target.new_page(width=page.rect.width, height=page.rect.height)
    tpage.insert_image(tpage.rect, stream=pix.tobytes("png"))
    path = tmp_path / "scan.pdf"
    target.save(path)
    source.close(); target.close()
    analysis = next(PDFAnalyzer(base_config()).analyze_pdf(path, render_layout=False))
    assert analysis.page_type.value == "scanned"
    assert analysis.image_count >= 1


def test_hybrid_page_classification(tmp_path):
    path = tmp_path / "hybrid.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Selectable hybrid text layer with enough characters")
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 400), 0)
    pix.clear_with(240)
    page.insert_image(page.rect, pixmap=pix, overlay=False)
    doc.save(path)
    doc.close()
    analysis = next(PDFAnalyzer(base_config()).analyze_pdf(path, render_layout=False))
    assert analysis.page_type.value == "hybrid"
