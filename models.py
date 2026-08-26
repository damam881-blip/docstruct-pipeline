from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class PageType(str, Enum):
    DIGITAL = "digital"
    SCANNED = "scanned"
    HYBRID = "hybrid"


class LayoutType(str, Enum):
    BORDERED_TABLE = "bordered_table"
    BORDERLESS_TABLE = "borderless_table"
    MIXED = "mixed"
    FREE_TEXT = "free_text"


class Strategy(str, Enum):
    DIGITAL_TEXT = "digital_text"
    CELL_OCR = "cell_ocr"
    ROW_OCR = "row_ocr"
    FULL_PAGE_OCR = "full_page_ocr"
    DIGITAL_WITH_OCR_FALLBACK = "digital_with_ocr_fallback"


@dataclass(slots=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def intersection(self, other: "BBox") -> "BBox | None":
        x0, y0 = max(self.x0, other.x0), max(self.y0, other.y0)
        x1, y1 = min(self.x1, other.x1), min(self.y1, other.y1)
        if x1 <= x0 or y1 <= y0:
            return None
        return BBox(x0, y0, x1, y1)

    def intersection_ratio(self, other: "BBox", denominator: str = "self") -> float:
        inter = self.intersection(other)
        if not inter:
            return 0.0
        base = self.area if denominator == "self" else other.area
        return inter.area / base if base else 0.0

    def expanded(self, left: float, top: float, right: float, bottom: float) -> "BBox":
        return BBox(self.x0 - left, self.y0 - top, self.x1 + right, self.y1 + bottom)

    def clamped(self, width: float, height: float) -> "BBox":
        return BBox(max(0.0, self.x0), max(0.0, self.y0), min(width, self.x1), min(height, self.y1))

    def to_int(self) -> tuple[int, int, int, int]:
        return tuple(int(round(v)) for v in (self.x0, self.y0, self.x1, self.y1))

    def to_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass(slots=True)
class WordBox:
    text: str
    bbox: BBox
    confidence: float = 1.0
    source: str = "digital"
    block_no: int | None = None
    line_no: int | None = None
    word_no: int | None = None
    language: str | None = None


@dataclass(slots=True)
class TableRegion:
    table_id: str
    bbox: BBox
    layout_type: LayoutType
    confidence: float
    row_boundaries: list[float] = field(default_factory=list)
    column_boundaries: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PageAnalysis:
    page_number: int
    page_type: PageType
    layout_type: LayoutType
    has_horizontal_lines: bool
    has_vertical_lines: bool
    table_regions: list[TableRegion]
    rotation: float
    recommended_strategy: Strategy
    width_pt: float
    height_pt: float
    estimated_dpi: float | None
    text_char_count: int
    word_count: int
    image_count: int
    drawing_count: int
    text_density: float
    image_coverage: float
    horizontal_line_density: float
    vertical_line_density: float
    alignment_score: float
    digital_text_quality: float
    requires_ocr: bool
    layout_signature: str
    measurements: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExtractedCell:
    file_name: str
    page_number: int
    table_id: str
    row_index: int
    column_index: int
    bbox: BBox
    crop_path: str | None
    engine: str
    confidence: float
    raw_value: str
    normalized_value: Any
    validation_status: str = "unvalidated"
    validation_errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExtractedRow:
    file_name: str
    page_number: int
    table_id: str
    row_index: int
    cells: list[ExtractedCell]
    bbox: BBox | None = None
    row_confidence: float = 0.0
    normalized: dict[str, Any] = field(default_factory=dict)
    validation_status: str = "unvalidated"
    validation_errors: list[str] = field(default_factory=list)
    source_crop: str | None = None
    is_header: bool = False
    is_total: bool = False

    def raw_values(self) -> list[str]:
        return [cell.raw_value for cell in self.cells]


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "warning"
    page_number: int | None = None
    table_id: str | None = None
    row_index: int | None = None
    column_index: int | None = None


@dataclass(slots=True)
class PageExtractionResult:
    analysis: PageAnalysis
    rows: list[ExtractedRow]
    free_text: str = ""
    issues: list[ValidationIssue] = field(default_factory=list)
    debug_dir: str | None = None
    processing_seconds: float = 0.0
    fallback_chain: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None


@dataclass(slots=True)
class TransformChain:
    pdf_width_pt: float
    pdf_height_pt: float
    image_width_px: int
    image_height_px: int
    deskew_angle_deg: float = 0.0
    crop_origin_px: tuple[float, float] = (0.0, 0.0)

    @property
    def scale_x(self) -> float:
        return self.image_width_px / self.pdf_width_pt if self.pdf_width_pt else 1.0

    @property
    def scale_y(self) -> float:
        return self.image_height_px / self.pdf_height_pt if self.pdf_height_pt else 1.0

    def pdf_to_image(self, bbox: BBox) -> BBox:
        return BBox(bbox.x0 * self.scale_x, bbox.y0 * self.scale_y, bbox.x1 * self.scale_x, bbox.y1 * self.scale_y)

    def image_to_pdf(self, bbox: BBox) -> BBox:
        return BBox(bbox.x0 / self.scale_x, bbox.y0 / self.scale_y, bbox.x1 / self.scale_x, bbox.y1 / self.scale_y)

    def page_to_crop(self, bbox: BBox) -> BBox:
        ox, oy = self.crop_origin_px
        return BBox(bbox.x0 - ox, bbox.y0 - oy, bbox.x1 - ox, bbox.y1 - oy)

    def crop_to_page(self, bbox: BBox) -> BBox:
        ox, oy = self.crop_origin_px
        return BBox(bbox.x0 + ox, bbox.y0 + oy, bbox.x1 + ox, bbox.y1 + oy)


def dataclass_to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        result = asdict(value)
        return _enum_to_value(result)
    if isinstance(value, list):
        return [dataclass_to_dict(v) for v in value]
    return value


def _enum_to_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _enum_to_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_enum_to_value(v) for v in value]
    if isinstance(value, tuple):
        return [_enum_to_value(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def union_bbox(boxes: Iterable[BBox]) -> BBox | None:
    boxes = list(boxes)
    if not boxes:
        return None
    return BBox(
        min(b.x0 for b in boxes),
        min(b.y0 for b in boxes),
        max(b.x1 for b in boxes),
        max(b.y1 for b in boxes),
    )
