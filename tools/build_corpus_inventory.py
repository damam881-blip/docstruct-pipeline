from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pymupdf as fitz


def inspect_pdf(path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    doc = fitz.open(str(path))
    pages: list[dict[str, Any]] = []
    dimensions: Counter[str] = Counter()
    text_pages = image_pages = drawing_pages = 0
    for index, page in enumerate(doc):
        text = page.get_text("text") or ""
        images = page.get_images(full=True)
        drawings = page.get_drawings()
        chars = len(text.strip())
        if chars:
            text_pages += 1
        if images:
            image_pages += 1
        if drawings:
            drawing_pages += 1
        dim = f"{page.rect.width:.2f}x{page.rect.height:.2f}@{page.rotation}"
        dimensions[dim] += 1
        pages.append(
            {
                "page_number": index + 1,
                "width_pt": round(page.rect.width, 3),
                "height_pt": round(page.rect.height, 3),
                "rotation": page.rotation,
                "text_char_count": chars,
                "image_count": len(images),
                "drawing_count": len(drawings),
                "coarse_page_type": "hybrid" if chars and images else "digital" if chars else "scanned",
            }
        )
    return {
        "file_name": path.name,
        "path": str(path),
        "page_count": len(doc),
        "pages_with_text": text_pages,
        "pages_with_images": image_pages,
        "pages_with_drawings": drawing_pages,
        "coarse_document_type": "hybrid" if text_pages and image_pages else "digital" if text_pages else "scanned",
        "dimension_signatures": dict(dimensions),
        "processing_seconds": round(time.perf_counter() - started, 3),
        "pages": pages,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    records = [inspect_pdf(Path(item)) for item in args.files]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = [{k: record[k] for k in ("file_name", "page_count", "pages_with_text", "pages_with_images", "pages_with_drawings", "coarse_document_type", "processing_seconds")} for record in records]
    output.with_name(output.stem + "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
