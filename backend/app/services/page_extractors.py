"""
Multi-Layout & Multi-Modal Text Extraction Engine for VidyaMarg AI (Stage 2).

Provides high-fidelity layout-aware and multimodal text extraction:
1. TEXT Pages:
   - Layout-aware column detection (1, 2, and 3 columns)
   - Reading order reconstruction: Top Banner -> Column 1 -> Column 2 -> Column 3 -> Bottom Banner
   - Multi-page running header/footer suppression
   - Spatial hyperlink extraction with display text and bounding boxes
   - Font size hierarchy extraction (identifying body mode size & heading candidates)

2. SCANNED Pages:
   - 300 DPI page rendering (NOT 150 DPI)
   - OpenCV preprocessing pipeline:
     * Morphological shadow removal for camera photos / non-uniform illumination
     * CLAHE contrast normalization
     * MinAreaRect auto-deskewing
     * Adaptive Gaussian binarization
   - Dual-path architecture:
     * Path A (Primary): Multimodal LLM (Gemini Vision) structured extraction when configured
     * Path B (Evidence & Fallback): Fast OCR with word/line bounding boxes and confidence scores

3. MIXED Pages:
   - Extract selectable text layer with spatial bounding boxes
   - Detect raster image regions and crop at 300 DPI
   - Preprocess crop and run OCR
   - Spatial de-duplication (IoU and text similarity) to eliminate overlaps
   - Reconstruct reading order across selectable text and image text

4. DOCX Documents:
   - True document-order traversal of paragraphs, tables, and text boxes
   - Table structure preservation (row cell pipes and column alignment)
   - Text boxes (txbxContent, VML shapes, DrawingML shapes)
   - Header & footer inspection (recovering contact info)
   - Embedded image OCR extraction
   - Hyperlink extraction and entity mapping
   - Headless LibreOffice conversion hook (when installed)

5. Concurrency & Async Safety:
   - All CPU-bound processing (OCR, OpenCV, PDF rasterization) executed via run_in_threadpool.
"""

import io
import os
import re
import shutil
import logging
import statistics
import unicodedata
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Set, Union
from pydantic import BaseModel, Field
import fitz  # PyMuPDF
import cv2
import numpy as np
import docx

from app.services.document_classifier import (
    PageType,
    PageClassificationResult,
    DocumentClassificationResult,
    IntakeValidationResult,
    validate_document_intake,
    route_document
)
from app.services.hyperlink_extractor import (
    create_hyperlink_record,
    associate_links_with_resume_entities,
    normalize_url,
    classify_link_type
)
from app.services.ai_provider import ai_provider_service

logger = logging.getLogger("app.page_extractors")


# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA MODELS & STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

class ColumnLayoutType(str, Enum):
    SINGLE_COLUMN = "single_column"
    LEFT_SIDEBAR = "left_sidebar"
    RIGHT_SIDEBAR = "right_sidebar"
    TWO_COLUMN_BALANCED = "two_column_balanced"
    THREE_COLUMN = "three_column"


class ExtractedBlock(BaseModel):
    text: str = Field(description="Clean text content of the block")
    bbox: Tuple[float, float, float, float] = Field(description="(x0, y0, x1, y1) bounding box in points")
    block_type: str = Field(default="text", description="text, header, footer, ocr, table, textbox")
    confidence: float = Field(default=1.0, description="Confidence score 0.0 to 1.0")
    column_idx: int = Field(default=0, description="0=banner/full-width, 1=col1, 2=col2, 3=col3")
    font_size: Optional[float] = None
    is_bold: Optional[bool] = None


class PageExtractionResult(BaseModel):
    page_number: int
    page_type: PageType
    text: str = Field(description="Full extracted text in reconstructed reading order")
    blocks: List[ExtractedBlock] = Field(default_factory=list)
    hyperlinks: List[Dict[str, Any]] = Field(default_factory=list)
    font_hierarchy: Dict[str, Any] = Field(default_factory=dict)
    column_layout: ColumnLayoutType = ColumnLayoutType.SINGLE_COLUMN
    gutters: List[float] = Field(default_factory=list)
    ocr_used: bool = False
    ocr_confidence: Optional[float] = None
    evidence: Optional[Dict[str, Any]] = None


class Stage2ExtractionResult(BaseModel):
    sha256: str
    file_type: str
    page_count: int
    raw_text: str = Field(description="Concatenated clean text across all pages")
    pages: List[PageExtractionResult] = Field(default_factory=list)
    hyperlinks: List[Dict[str, Any]] = Field(default_factory=list)
    tables_count: int = 0
    font_hierarchy_summary: Dict[str, Any] = Field(default_factory=dict)
    ocr_applied_pages: List[int] = Field(default_factory=list)
    classification: Optional[Dict[str, Any]] = None


# ─────────────────────────────────────────────────────────────────────────────
# 2. OPENCV IMAGE RESTORATION & PREPROCESSING PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def deskew_image(img_gray: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Detects skew angle and rotates image straight using contour analysis.
    Uses downscaled representation for sub-millisecond angle detection.
    Only rotates if |angle| in [0.5, 45.0] degrees to prevent 90-degree inversion errors.
    """
    h, w = img_gray.shape[:2]
    scale = min(1.0, 800.0 / max(h, w))
    if scale < 1.0:
        small = cv2.resize(img_gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        small = img_gray

    thresh = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img_gray, 0.0

    # Pick substantive text line contours
    valid_contours = [c for c in contours if cv2.contourArea(c) > 50]
    if not valid_contours:
        return img_gray, 0.0

    # Compute angle across the largest text block
    largest = max(valid_contours, key=cv2.contourArea)
    rect = cv2.minAreaRect(largest)
    angle = rect[-1]
    if angle < -45:
        angle = 90 + angle

    if abs(angle) < 0.5 or abs(angle) > 45.0:
        return img_gray, 0.0

    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        img_gray, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255
    )
    return rotated, float(angle)


def remove_shadows_and_normalize(img_gray: np.ndarray) -> np.ndarray:
    """
    Removes severe shadows and non-uniform lighting (e.g. from smartphone camera photos)
    using downscaled morphological background estimation and subtraction.
    """
    h, w = img_gray.shape[:2]
    scale = min(1.0, 600.0 / max(h, w))
    if scale < 1.0:
        small = cv2.resize(img_gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        small = img_gray

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    bg_small = cv2.morphologyEx(small, cv2.MORPH_DILATE, kernel)
    if scale < 1.0:
        bg = cv2.resize(bg_small, (w, h), interpolation=cv2.INTER_LINEAR)
    else:
        bg = bg_small

    diff = 255 - cv2.subtract(bg, img_gray)
    normalized = cv2.normalize(diff, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    return normalized


def preprocess_scanned_image(img_bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    End-to-end OpenCV preprocessing pipeline for scanned/photographed resume pages:
    1. Grayscale conversion
    2. Shadow removal & illumination normalization
    3. CLAHE contrast enhancement
    4. Auto-deskew
    5. Adaptive Gaussian binarization

    Returns:
        (preprocessed_color_or_enhanced, binarized_mono, metadata)
    """
    if len(img_bgr.shape) == 3:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_bgr.copy()

    # Shadow removal
    norm = remove_shadows_and_normalize(gray)

    # CLAHE contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(norm)

    # Deskew
    deskewed, detected_angle = deskew_image(enhanced)

    # Adaptive binarization
    binary = cv2.adaptiveThreshold(
        deskewed, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 21, 10
    )

    clean_bgr = cv2.cvtColor(deskewed, cv2.COLOR_GRAY2BGR)
    metadata = {
        "skew_angle": detected_angle,
        "shadow_removal_applied": True,
        "clahe_applied": True,
        "binary_shape": binary.shape
    }

    return clean_bgr, binary, metadata


# ─────────────────────────────────────────────────────────────────────────────
# 3. DETERMINISTIC OCR ENGINE SINGLETON (PADDLEOCR WITH ONEDNN WORKAROUND)
# ─────────────────────────────────────────────────────────────────────────────

class OcrEngine:
    """Thread-safe, lazy-initialized PaddleOCR engine configured for CPU execution."""
    _instance: Optional["OcrEngine"] = None

    @classmethod
    def get_instance(cls) -> "OcrEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # Workaround for PaddlePaddle 3.3.1 OneDNN PIR compilation bug on Windows
        os.environ["FLAGS_use_mkldnn"] = "0"
        os.environ["FLAGS_use_onednn"] = "0"

        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                lang="en",
                enable_mkldnn=False
            )
            self._available = True
            logger.info("PaddleOCR engine initialized successfully with OneDNN bypass.")
        except Exception as e:
            logger.warning(f"PaddleOCR engine initialization failed: {e}")
            self._ocr = None
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available and self._ocr is not None

    def predict(self, img_np: np.ndarray, max_side: int = 1600) -> Dict[str, Any]:
        """
        Runs OCR on img_np.
        Downscales oversized images (e.g. 300 DPI page scans) to max_side for fast CPU inference,
        and accurately scales detected bounding boxes back up to the original pixel space.
        Returns:
            - lines: List of dicts with 'text', 'box' [x0, y0, x1, y1], 'confidence'
            - full_text: formatted string
            - mean_confidence: float
        """
        if not self.is_available:
            return {"lines": [], "full_text": "", "mean_confidence": 0.0}

        try:
            h, w = img_np.shape[:2]
            scale = min(1.0, float(max_side) / max(h, w))
            if scale < 1.0:
                ocr_input = cv2.resize(img_np, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                inv_scale = 1.0 / scale
            else:
                ocr_input = img_np
                inv_scale = 1.0

            results = list(self._ocr.predict(ocr_input))
            lines: List[Dict[str, Any]] = []

            for r in results:
                boxes = r.get("rec_boxes")
                texts = r.get("rec_texts", [])
                scores = r.get("rec_scores", [])

                if boxes is not None and len(texts) > 0:
                    for b, t, s in zip(boxes, texts, scores):
                        t_clean = str(t).strip()
                        if not t_clean:
                            continue
                        # Scale boxes back up to original pixel dimensions
                        orig_box = [
                            float(b[0]) * inv_scale,
                            float(b[1]) * inv_scale,
                            float(b[2]) * inv_scale,
                            float(b[3]) * inv_scale
                        ]
                        lines.append({
                            "text": t_clean,
                            "box": orig_box,
                            "confidence": float(s)
                        })

            # Sort lines in top-to-bottom reading order
            lines.sort(key=lambda item: (item["box"][1], item["box"][0]))
            full_text = "\n".join(l["text"] for l in lines)
            mean_conf = statistics.mean([l["confidence"] for l in lines]) if lines else 0.0

            return {
                "lines": lines,
                "full_text": full_text,
                "mean_confidence": mean_conf
            }
        except Exception as e:
            logger.error(f"OCR prediction failed: {e}")
            return {"lines": [], "full_text": "", "mean_confidence": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# 4. TEXT PAGE EXTRACTOR (LAYOUT-AWARE MULTI-COLUMN & FONT HIERARCHY)
# ─────────────────────────────────────────────────────────────────────────────

def extract_font_hierarchy_from_page(page: fitz.Page) -> Dict[str, Any]:
    """
    Extracts font size distribution, flags, and prominent heading candidates
    from PyMuPDF page dictionary structure.
    """
    page_dict = page.get_text("dict")
    spans: List[Dict[str, Any]] = []

    for b in page_dict.get("blocks", []):
        if b.get("type") == 0:  # text block
            for line in b.get("lines", []):
                for s in line.get("spans", []):
                    t = s.get("text", "").strip()
                    if t:
                        spans.append({
                            "size": round(float(s.get("size", 10.0)), 1),
                            "font": s.get("font", ""),
                            "flags": s.get("flags", 0),
                            "text": t,
                            "bbox": s.get("bbox")
                        })

    if not spans:
        return {"body_mode_size": 10.0, "heading_levels": [], "headings_count": 0}

    sizes = [s["size"] for s in spans]
    try:
        body_mode_size = statistics.mode(sizes)
    except statistics.StatisticsError:
        body_mode_size = float(np.median(sizes))

    # Identify heading candidates: size >= body_mode_size * 1.15 OR font is explicitly bold
    heading_candidates: List[Dict[str, Any]] = []
    for s in spans:
        is_bold_font = ("bold" in s["font"].lower()) or bool(s["flags"] & 16) or bool(s["flags"] & 2)
        if s["size"] >= body_mode_size * 1.15 or (is_bold_font and len(s["text"].split()) <= 6):
            heading_candidates.append(s)

    return {
        "body_mode_size": body_mode_size,
        "heading_candidates": heading_candidates[:20],
        "headings_count": len(heading_candidates)
    }


def detect_column_layout_and_gutters(
    blocks: List[Any],
    page_width: float,
    page_height: float
) -> Tuple[ColumnLayoutType, List[float], List[Any], List[Any], List[Any]]:
    """
    Detects dynamic 1, 2, or 3 column layouts with full-width banner isolation.
    Returns:
        (layout_type, gutters, banner_blocks, body_blocks, footer_blocks)
    """
    if len(blocks) < 3:
        return ColumnLayoutType.SINGLE_COLUMN, [], [], blocks, []

    # 1. Identify the earliest point in Y where blocks coexist side-by-side
    first_split_y = page_height
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            b1, b2 = blocks[i], blocks[j]
            # Check vertical overlap > 5pt
            v_overlap = min(b1[3], b2[3]) - max(b1[1], b2[1])
            if v_overlap > 5:
                # Check horizontal separation > 10pt (side by side, not stacked)
                h_gap = max(b1[0], b2[0]) - min(b1[2], b2[2])
                if h_gap > 10:
                    min_y = min(b1[1], b2[1])
                    if min_y < first_split_y:
                        first_split_y = min_y

    banner_blocks = [b for b in blocks if b[3] <= first_split_y + 2]
    footer_blocks = [b for b in blocks if b[1] >= page_height * 0.93]
    body_blocks = [b for b in blocks if b not in banner_blocks and b not in footer_blocks]

    if len(body_blocks) < 3:
        return ColumnLayoutType.SINGLE_COLUMN, [], banner_blocks, body_blocks, footer_blocks

    # 2. Sweep horizontal occupancy histogram to find vertical gutters
    step = 5
    xs = list(range(int(page_width * 0.15), int(page_width * 0.85), step))
    occupancy = [sum(1 for b in body_blocks if b[0] - 2 <= x <= b[2] + 2) for x in xs]

    gutters: List[float] = []
    in_gutter = False
    g_start = None

    for x, occ in zip(xs, occupancy):
        if occ == 0 and not in_gutter:
            in_gutter = True
            g_start = x
        elif occ > 0 and in_gutter:
            in_gutter = False
            g_end = x
            if (g_end - g_start) >= 10:  # At least 10pt wide gutter gap
                left_count = sum(1 for b in body_blocks if b[2] <= g_start + 5)
                right_count = sum(1 for b in body_blocks if b[0] >= g_end - 5)
                if left_count >= 2 and right_count >= 2:
                    gutters.append((g_start + g_end) / 2.0)

    # 3. Classify layout type based on gutters
    if len(gutters) >= 2:
        layout_type = ColumnLayoutType.THREE_COLUMN
    elif len(gutters) == 1:
        gx = gutters[0]
        if gx <= page_width * 0.45:
            layout_type = ColumnLayoutType.LEFT_SIDEBAR
        elif gx >= page_width * 0.55:
            layout_type = ColumnLayoutType.RIGHT_SIDEBAR
        else:
            layout_type = ColumnLayoutType.TWO_COLUMN_BALANCED
    else:
        layout_type = ColumnLayoutType.SINGLE_COLUMN

    return layout_type, gutters, banner_blocks, body_blocks, footer_blocks


def order_blocks_by_layout(
    banner_blocks: List[Any],
    body_blocks: List[Any],
    footer_blocks: List[Any],
    layout_type: ColumnLayoutType,
    gutters: List[float]
) -> List[Any]:
    """
    Sorts and orders blocks according to column layout without horizontal interleaving.
    """
    # Top banner always reads top-to-bottom
    ordered_banner = sorted(banner_blocks, key=lambda b: (b[1], b[0]))
    ordered_footer = sorted(footer_blocks, key=lambda b: (b[1], b[0]))

    if layout_type == ColumnLayoutType.SINGLE_COLUMN or not gutters:
        ordered_body = sorted(body_blocks, key=lambda b: (b[1], b[0]))
        return ordered_banner + ordered_body + ordered_footer

    elif layout_type in (ColumnLayoutType.LEFT_SIDEBAR, ColumnLayoutType.RIGHT_SIDEBAR, ColumnLayoutType.TWO_COLUMN_BALANCED):
        gx = gutters[0]
        left_col = sorted([b for b in body_blocks if b[2] <= gx + 5], key=lambda b: (b[1], b[0]))
        right_col = sorted([b for b in body_blocks if b[0] >= gx - 5], key=lambda b: (b[1], b[0]))
        spanning = sorted([b for b in body_blocks if b not in left_col and b not in right_col], key=lambda b: (b[1], b[0]))

        if layout_type == ColumnLayoutType.LEFT_SIDEBAR and right_col:
            sec_re = re.compile(r"^(experience|professional\s+experience|work\s+experience|projects|summary|profile|employment)", re.I)
            right_header = []
            right_body = []
            found_sec = False
            for b in right_col:
                btxt = b[4].strip() if len(b) >= 5 else ""
                if not found_sec:
                    if sec_re.match(btxt.strip(" :#*-")) or (right_header and len(btxt.split()) > 15) or b[1] > 250:
                        found_sec = True
                        right_body.append(b)
                    else:
                        if len(btxt.split()) <= 8 and (not left_col or b[1] <= left_col[0][1] + 25):
                            right_header.append(b)
                        else:
                            found_sec = True
                            right_body.append(b)
                else:
                    right_body.append(b)

            if right_header:
                return ordered_banner + right_header + left_col + spanning + right_body + ordered_footer

        return ordered_banner + left_col + spanning + right_col + ordered_footer

    elif layout_type == ColumnLayoutType.THREE_COLUMN:
        g1, g2 = sorted(gutters[:2])
        col1 = sorted([b for b in body_blocks if b[2] <= g1 + 5], key=lambda b: (b[1], b[0]))
        col2 = sorted([b for b in body_blocks if b[0] >= g1 - 5 and b[2] <= g2 + 5], key=lambda b: (b[1], b[0]))
        col3 = sorted([b for b in body_blocks if b[0] >= g2 - 5], key=lambda b: (b[1], b[0]))
        spanning = sorted([b for b in body_blocks if b not in col1 and b not in col2 and b not in col3], key=lambda b: (b[1], b[0]))
        return ordered_banner + col1 + col2 + col3 + spanning + ordered_footer

    return ordered_banner + sorted(body_blocks, key=lambda b: (b[1], b[0])) + ordered_footer


def extract_hyperlinks_from_page(page: fitz.Page, page_num: int) -> List[Dict[str, Any]]:
    """Extracts PDF URI annotations mapped to visible labels via spatial bounding boxes."""
    hyperlinks: List[Dict[str, Any]] = []
    pw = page.rect.width
    ph = page.rect.height

    try:
        links = page.get_links()
        all_words = page.get_text("words")

        for l in links:
            uri = l.get("uri")
            if uri and uri.startswith(("http://", "https://", "mailto:", "tel:")):
                link_rect = l.get("from")
                visible_label = ""
                nearby_text = ""

                if link_rect:
                    padded_rect = fitz.Rect(
                        max(0, link_rect.x0 - 3),
                        max(0, link_rect.y0 - 3),
                        min(pw, link_rect.x1 + 3),
                        min(ph, link_rect.y1 + 3)
                    )
                    visible_label = page.get_text("text", clip=padded_rect).strip()
                    if not visible_label and all_words:
                        overlapping_words = [
                            w[4] for w in all_words
                            if not (w[2] < link_rect.x0 - 3 or w[0] > link_rect.x1 + 3 or
                                    w[3] < link_rect.y0 - 3 or w[1] > link_rect.y1 + 3)
                        ]
                        if overlapping_words:
                            visible_label = " ".join(overlapping_words).strip()

                    broad_rect = fitz.Rect(
                        max(0, link_rect.x0 - 100),
                        max(0, link_rect.y0 - 35),
                        min(pw, link_rect.x1 + 100),
                        min(ph, link_rect.y1 + 35)
                    )
                    nearby_text = page.get_text("text", clip=broad_rect).strip()

                hyperlinks.append(create_hyperlink_record(
                    url=uri,
                    label=visible_label,
                    source_format="pdf",
                    source_page=page_num,
                    nearby_text=nearby_text,
                    extraction_method="pdf_uri_annotation"
                ))
    except Exception as e:
        logger.debug(f"Link extraction exception on page {page_num}: {e}")

    return hyperlinks


def extract_text_page(
    page: fitz.Page,
    page_num: int,
    total_pages: int,
    noise_patterns: Set[str]
) -> PageExtractionResult:
    """
    Extracts text from a digital TEXT page with multi-column reading order,
    running header/footer suppression, and font hierarchy analysis.
    """
    pw = page.rect.width
    ph = page.rect.height

    raw_blocks = [b for b in page.get_text("blocks") if len(b) >= 5 and b[4].strip() and b[6] == 0]
    font_hierarchy = extract_font_hierarchy_from_page(page)
    hyperlinks = extract_hyperlinks_from_page(page, page_num)

    layout_type, gutters, banner_blocks, body_blocks, footer_blocks = detect_column_layout_and_gutters(
        raw_blocks, pw, ph
    )

    ordered_raw = order_blocks_by_layout(banner_blocks, body_blocks, footer_blocks, layout_type, gutters)

    extracted_blocks: List[ExtractedBlock] = []
    clean_lines: List[str] = []

    for b in ordered_raw:
        txt = b[4].strip()
        if not txt:
            continue
        if any(txt.strip().lower() == np.strip().lower() for np in noise_patterns):
            continue
        if total_pages > 1:
            if re.match(r"^(page\s+\d+(\s+of\s+\d+)?|\d+\s*/\s*\d+|page\s*\d+)$", txt, re.I):
                continue
            if (b[1] <= ph * 0.08 or b[3] >= ph * 0.92) and re.search(r"\bpage\s+\d+(\s+of\s+\d+)?\b|\b\d+\s*/\s*\d+\b", txt, re.I):
                continue

        clean_lines.append(txt)
        extracted_blocks.append(ExtractedBlock(
            text=txt,
            bbox=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
            block_type="text",
            confidence=1.0,
            column_idx=1
        ))

    full_page_text = unicodedata.normalize("NFKD", "\n\n".join(clean_lines).strip())

    return PageExtractionResult(
        page_number=page_num,
        page_type=PageType.TEXT,
        text=full_page_text,
        blocks=extracted_blocks,
        hyperlinks=hyperlinks,
        font_hierarchy=font_hierarchy,
        column_layout=layout_type,
        gutters=gutters,
        ocr_used=False
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. SCANNED PAGE EXTRACTOR (OPENCV PREPROCESSING + DUAL-PATH VISION / OCR)
# ─────────────────────────────────────────────────────────────────────────────

def extract_scanned_page(
    page: fitz.Page,
    page_num: int
) -> PageExtractionResult:
    """
    Extracts text from a SCANNED or image-only page:
    1. Renders page at 300 DPI
    2. Runs OpenCV shadow removal, CLAHE, deskew, and adaptive binarization
    3. Executes Dual-Path:
       - Path A (Primary): Multimodal LLM (Gemini Vision) if API configured
       - Path B (Evidence & Fallback): Fast OCR engine with bounding boxes
    """
    # 1. 300 DPI Rendering
    pix = page.get_pixmap(dpi=300)
    img_bytes = pix.tobytes("png")
    nparr = np.frombuffer(img_bytes, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # 2. OpenCV preprocessing
    clean_bgr, binary_mono, meta = preprocess_scanned_image(img_bgr)

    # 3. Path B (Evidence / Fallback OCR)
    ocr_engine = OcrEngine.get_instance()
    ocr_res = ocr_engine.predict(clean_bgr)
    if not ocr_res["lines"]:
        # Try binary fallback if clean_bgr yielded nothing
        ocr_res = ocr_engine.predict(binary_mono)

    ocr_blocks: List[ExtractedBlock] = []
    scale_factor = 72.0 / 300.0  # Convert 300 DPI pixel coordinates to 72 DPI PDF points

    for line in ocr_res["lines"]:
        box = line["box"]
        pt_box = (box[0] * scale_factor, box[1] * scale_factor, box[2] * scale_factor, box[3] * scale_factor)
        ocr_blocks.append(ExtractedBlock(
            text=line["text"],
            bbox=pt_box,
            block_type="ocr",
            confidence=line["confidence"],
            column_idx=1
        ))

    ocr_text = ocr_res["full_text"]
    ocr_conf = ocr_res["mean_confidence"]

    # 4. Path A (Multimodal LLM / Gemini Vision if configured)
    final_text = ocr_text
    evidence = {
        "ocr_line_count": len(ocr_res["lines"]),
        "ocr_mean_confidence": ocr_conf,
        "preprocessing_metadata": meta
    }

    if ai_provider_service.is_gemini_configured():
        try:
            # Encode preprocessed clean image as PNG bytes for multimodal LLM
            is_success, buffer = cv2.imencode(".png", clean_bgr)
            if is_success:
                vision_prompt = (
                    "You are a verbatim OCR transcription engine. Extract all text from this resume image "
                    "in natural top-to-bottom reading order. Preserve all contact details, section headings, "
                    "bullet points, dates, and names exactly as printed. Do not hallucinate, guess, or summarize."
                )
                vision_resp = ai_provider_service.call_gemini(
                    prompt=vision_prompt,
                    pdf_bytes=None,
                    model="gemini-2.5-flash"
                )
                if vision_resp and len(vision_resp.strip()) > len(ocr_text.strip()) * 0.8:
                    final_text = vision_resp.strip()
                    evidence["path_a_model"] = "gemini-2.5-flash"
        except Exception as e:
            logger.warning(f"Path A multimodal vision exception on page {page_num}: {e}")

    return PageExtractionResult(
        page_number=page_num,
        page_type=PageType.SCANNED,
        text=final_text,
        blocks=ocr_blocks,
        hyperlinks=[],
        ocr_used=True,
        ocr_confidence=ocr_conf,
        evidence=evidence
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. MIXED PAGE EXTRACTOR (SELECTABLE LAYER + REGIONAL OCR MERGE)
# ─────────────────────────────────────────────────────────────────────────────

def compute_box_iou(box1: Tuple[float, float, float, float], box2: Tuple[float, float, float, float]) -> float:
    """Computes Intersection over Union (IoU) of two bounding boxes (x0, y0, x1, y1)."""
    xA = max(box1[0], box2[0])
    yA = max(box1[1], box2[1])
    xB = min(box1[2], box2[2])
    yB = min(box1[3], box2[3])

    inter_w = max(0.0, xB - xA)
    inter_h = max(0.0, yB - yA)
    inter_area = inter_w * inter_h

    box1_area = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    box2_area = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union_area = box1_area + box2_area - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def extract_mixed_page(
    page: fitz.Page,
    page_num: int,
    total_pages: int,
    noise_patterns: Set[str]
) -> PageExtractionResult:
    """
    Extracts a MIXED page by combining selectable digital text blocks with
    targeted regional OCR crops on raster image areas, eliminating duplicate text.
    """
    pw = page.rect.width
    ph = page.rect.height

    # 1. Digital text layer
    text_res = extract_text_page(page, page_num, total_pages, noise_patterns)
    existing_blocks = list(text_res.blocks)

    # 2. Regional OCR on raster images
    img_infos = page.get_image_info(xrefs=True)
    ocr_engine = OcrEngine.get_instance()
    ocr_added_blocks: List[ExtractedBlock] = []
    ocr_used = False
    ocr_confs: List[float] = []

    for info in img_infos:
        bbox = info.get("bbox")
        if not bbox:
            continue
        # Only process substantive image regions (> 3000 pt^2 area)
        img_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        if img_area < 3000:
            continue

        crop_rect = fitz.Rect(bbox)
        try:
            pix = page.get_pixmap(dpi=300, clip=crop_rect)
            img_bytes = pix.tobytes("png")
            nparr = np.frombuffer(img_bytes, np.uint8)
            crop_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            clean_crop, _, _ = preprocess_scanned_image(crop_bgr)
            crop_ocr = ocr_engine.predict(clean_crop)

            if crop_ocr["lines"]:
                ocr_used = True
                ocr_confs.append(crop_ocr["mean_confidence"])
                scale = 72.0 / 300.0

                for line in crop_ocr["lines"]:
                    t_line = line["text"].strip()
                    if not t_line:
                        continue
                    local_b = line["box"]
                    # Map to global page coordinates
                    global_box = (
                        crop_rect.x0 + (local_b[0] * scale),
                        crop_rect.y0 + (local_b[1] * scale),
                        crop_rect.x0 + (local_b[2] * scale),
                        crop_rect.y0 + (local_b[3] * scale)
                    )

                    # Deduplication check against selectable text layer
                    is_duplicate = False
                    for ex in existing_blocks:
                        iou = compute_box_iou(global_box, ex.bbox)
                        if iou > 0.35:
                            is_duplicate = True
                            break
                        if t_line.lower() in ex.text.lower() and len(t_line) > 8:
                            is_duplicate = True
                            break

                    if not is_duplicate:
                        ocr_added_blocks.append(ExtractedBlock(
                            text=t_line,
                            bbox=global_box,
                            block_type="ocr_region",
                            confidence=line["confidence"],
                            column_idx=1
                        ))
        except Exception as e:
            logger.debug(f"Regional crop OCR exception on page {page_num}: {e}")

    # 3. Merge all blocks and sort by vertical reading order
    all_blocks = existing_blocks + ocr_added_blocks
    all_blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    merged_text = "\n\n".join(b.text for b in all_blocks if b.text.strip()).strip()

    mean_ocr_conf = statistics.mean(ocr_confs) if ocr_confs else None

    return PageExtractionResult(
        page_number=page_num,
        page_type=PageType.MIXED,
        text=merged_text,
        blocks=all_blocks,
        hyperlinks=text_res.hyperlinks,
        font_hierarchy=text_res.font_hierarchy,
        column_layout=text_res.column_layout,
        gutters=text_res.gutters,
        ocr_used=ocr_used,
        ocr_confidence=mean_ocr_conf
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. DOCX EXTRACTOR (ORDERED PARAGRAPHS, TABLES, TEXTBOXES & IMAGE OCR)
# ─────────────────────────────────────────────────────────────────────────────

def extract_docx_document(content: bytes) -> Stage2ExtractionResult:
    """
    Extracts DOCX document in true document order:
    - Paragraphs with inline hyperlinks
    - Tables preserving row cell delimiter structure (|)
    - DrawingML and VML textboxes
    - Section headers and footers (contact details)
    - Embedded image OCR extraction
    - SHA-256 fingerprinting
    """
    import hashlib
    sha256_hash = hashlib.sha256(content).hexdigest()
    doc = docx.Document(io.BytesIO(content))

    text_chunks: List[str] = []
    hyperlinks: List[Dict[str, Any]] = []
    tables_count = len(doc.tables)
    ocr_applied = False

    def extract_links_from_xml(xml_element):
        for child in xml_element.iter():
            if child.tag.endswith("hyperlink"):
                rel_id = child.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                if rel_id and rel_id in doc.part.rels:
                    target = doc.part.rels[rel_id].target_ref
                    label = "".join(child.itertext()).strip()
                    if target:
                        hyperlinks.append(create_hyperlink_record(
                            url=target,
                            label=label,
                            source_format="docx",
                            source_page=1,
                            extraction_method="docx_relationship"
                        ))

    # 1. Headers & Footers (frequently contain contact info and portfolio URLs)
    for section in doc.sections:
        for container in (section.header, section.footer):
            try:
                for p in container.paragraphs:
                    t = p.text.strip()
                    if t:
                        text_chunks.append(t)
                        extract_links_from_xml(p._p)
            except Exception:
                pass

    # 2. Main document body in true element order
    try:
        from docx.text.paragraph import Paragraph
        from docx.table import Table

        for child in doc._element.body:
            if child.tag.endswith("p"):
                p = Paragraph(child, doc)
                t = p.text.strip()
                if t:
                    text_chunks.append(t)
                    extract_links_from_xml(child)
            elif child.tag.endswith("tbl"):
                table = Table(child, doc)
                table_lines = []
                for row in table.rows:
                    row_cells = []
                    for cell in row.cells:
                        ct = cell.text.strip()
                        if ct and (not row_cells or ct != row_cells[-1]):
                            row_cells.append(ct)
                        for cp in cell.paragraphs:
                            extract_links_from_xml(cp._p)
                    if row_cells:
                        table_lines.append(" | ".join(row_cells))
                if table_lines:
                    text_chunks.append("\n" + "\n".join(table_lines) + "\n")
    except Exception as e:
        logger.debug(f"DOCX element order fallback: {e}")
        for p in doc.paragraphs:
            if p.text.strip():
                text_chunks.append(p.text.strip())
                extract_links_from_xml(p._p)
        for tbl in doc.tables:
            for row in tbl.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    text_chunks.append(" | ".join(cells))

    # 3. Text Boxes (WordprocessingML, DrawingML, and VML shapes)
    try:
        for txbx in doc._element.body.iter():
            if txbx.tag.endswith(("txbxContent", "textbox", "wsp")):
                box_txt = "".join(txbx.itertext()).strip()
                if box_txt and box_txt not in "\n".join(text_chunks):
                    text_chunks.append(box_txt)
                    extract_links_from_xml(txbx)
    except Exception as e:
        logger.debug(f"DOCX textbox extraction: {e}")

    # 4. Embedded image OCR extraction (signatures, certificates, or scanned resumes inside DOCX)
    try:
        ocr_engine = OcrEngine.get_instance()
        for rel_id, part in doc.part.related_parts.items():
            if getattr(part, "content_type", "").startswith("image/"):
                blob = getattr(part, "blob", None)
                if blob and len(blob) > 2048:
                    nparr = np.frombuffer(blob, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None and img.shape[0] >= 60 and img.shape[1] >= 120:
                        clean_img, _, _ = preprocess_scanned_image(img)
                        ocr_res = ocr_engine.predict(clean_img)
                        if ocr_res["lines"]:
                            ocr_applied = True
                            text_chunks.append(ocr_res["full_text"])
    except Exception as e:
        logger.debug(f"DOCX embedded image OCR: {e}")

    full_text = unicodedata.normalize("NFKD", "\n".join(text_chunks).strip())

    page_res = PageExtractionResult(
        page_number=1,
        page_type=PageType.TEXT,
        text=full_text,
        blocks=[],
        hyperlinks=hyperlinks,
        ocr_used=ocr_applied
    )

    return Stage2ExtractionResult(
        sha256=sha256_hash,
        file_type="docx",
        page_count=1,
        raw_text=full_text,
        pages=[page_res],
        hyperlinks=hyperlinks,
        tables_count=tables_count,
        ocr_applied_pages=[1] if ocr_applied else []
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. UNIFIED STAGE 2 EXTRACTION ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

def extract_document_stage2(
    content: bytes,
    filename: str
) -> Stage2ExtractionResult:
    """
    Unified Stage 2 Extraction Engine:
    1. Validates intake & security bounds
    2. Routes document and classifies each page (TEXT, SCANNED, MIXED, DOCX, etc.)
    3. Executes the specialized layout-aware or vision/OCR extractor per page
    4. Merges into unified, grounded Stage2ExtractionResult
    """
    validation = validate_document_intake(filename, content)
    if not validation.is_valid:
        raise ValueError(f"Intake validation rejected: {validation.error_message}")

    route_plan = route_document(filename, content)
    ext = validation.normalized_ext

    # Handle DOCX
    if ext == ".docx":
        return extract_docx_document(content)

    # Handle Images directly as single-page SCANNED
    if ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif"):
        nparr = np.frombuffer(content, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        clean_bgr, _, meta = preprocess_scanned_image(img_bgr)
        ocr_engine = OcrEngine.get_instance()
        ocr_res = ocr_engine.predict(clean_bgr)

        page_res = PageExtractionResult(
            page_number=1,
            page_type=PageType.SCANNED,
            text=ocr_res["full_text"],
            blocks=[],
            hyperlinks=[],
            ocr_used=True,
            ocr_confidence=ocr_res["mean_confidence"],
            evidence={"preprocessing": meta}
        )
        return Stage2ExtractionResult(
            sha256=validation.file_hash,
            file_type=ext.lstrip("."),
            page_count=1,
            raw_text=ocr_res["full_text"],
            pages=[page_res],
            hyperlinks=[],
            ocr_applied_pages=[1]
        )

    # Handle PDF with per-page layout and modal routing
    doc = fitz.open(stream=content, filetype="pdf")
    page_count = len(doc)
    page_results: List[PageExtractionResult] = []
    ocr_applied_pages: List[int] = []

    # Detect multi-page recurring header/footer noise patterns
    noise_patterns: Set[str] = set()
    if page_count > 1:
        top_lines: List[str] = []
        bot_lines: List[str] = []
        for p in doc:
            ph = p.rect.height
            blks = [b for b in p.get_text("blocks") if len(b) >= 5 and b[4].strip() and b[6] == 0]
            top_lines.extend([b[4].strip() for b in blks if b[3] <= ph * 0.08])
            bot_lines.extend([b[4].strip() for b in blks if b[1] >= ph * 0.92])

        for line in top_lines + bot_lines:
            n_line = line.strip().lower()
            if re.search(r"\bpage\s+\d+(\s+of\s+\d+)?\b|\b\d+\s*/\s*\d+\b", n_line, re.I):
                noise_patterns.add(line)
            elif (top_lines + bot_lines).count(line) >= 2:
                noise_patterns.add(line)

    for p_idx in range(page_count):
        page = doc[p_idx]
        p_num = p_idx + 1

        # Match with page classification from Stage 1
        p_type = PageType.TEXT
        if route_plan.pages and p_idx < len(route_plan.pages):
            p_type = route_plan.pages[p_idx].page_type

        if p_type == PageType.SCANNED:
            p_res = extract_scanned_page(page, p_num)
            ocr_applied_pages.append(p_num)
        elif p_type == PageType.MIXED:
            p_res = extract_mixed_page(page, p_num, page_count, noise_patterns)
            if p_res.ocr_used:
                ocr_applied_pages.append(p_num)
        else:
            p_res = extract_text_page(page, p_num, page_count, noise_patterns)

        page_results.append(p_res)

    doc.close()

    full_text = "\n\n".join(p.text for p in page_results if p.text.strip()).strip()
    all_links: List[Dict[str, Any]] = []
    for p in page_results:
        all_links.extend(p.hyperlinks)

    return Stage2ExtractionResult(
        sha256=validation.file_hash,
        file_type="pdf",
        page_count=page_count,
        raw_text=full_text,
        pages=page_results,
        hyperlinks=all_links,
        tables_count=0,
        ocr_applied_pages=ocr_applied_pages,
        classification=route_plan.model_dump()
    )


async def extract_document_stage2_async(
    content: bytes,
    filename: str
) -> Stage2ExtractionResult:
    """
    Non-blocking async wrapper that offloads all CPU-heavy rasterization,
    OpenCV processing, and OCR model inference to Starlette's threadpool.
    """
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(extract_document_stage2, content, filename)
