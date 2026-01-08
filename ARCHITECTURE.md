# Architecture Documentation

This document describes the system architecture, data flow, design decisions, and implementation details for the PDF Document Cleaner.

## Table of Contents

1. [System Overview](#system-overview)
2. [Component Architecture](#component-architecture)
3. [Data Flow](#data-flow)
4. [Design Decisions and Rationale](#design-decisions-and-rationale)
5. [Key Implementation Details](#key-implementation-details)
6. [Dependencies](#dependencies)

---

## System Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Gradio     │     │   Optional   │     │    MinerU    │     │     OCR      │     │   Document   │
│     UI       │────▶│  Binarize    │────▶│     API      │────▶│ Postprocess  │────▶│   Builder    │
│  (app.py)    │     │(pdf_preproc) │     │  (External)  │     │  (Manual)    │     │(document_    │
│              │     │              │     │              │     │(ocr_postproc)│     │  builder.py) │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │                                                                 │
       │                                                          User corrections
       │                                                          (interactive)
       │
       └────────────────────────────────────────────────────────────────────▶
                                                          Output PDF
                                                  (<name>_final_<timestamp>.pdf)
```

### Core Problem Solved

The application processes scanned PDF documents to:
1. **Extract text** via OCR while preserving document structure
2. **Remove visual noise** from scans (binarization preprocessing)
3. **Generate clean, searchable PDFs** with properly sized fonts
4. **Enable manual correction** of low-confidence OCR results

---

## Component Architecture

### 1. Gradio UI (`app.py`)

**File:** `app.py` (700+ lines)

**Responsibilities:**
- User interface for file upload and settings
- Input validation (file type, size)
- Progress tracking and error display
- Orchestration of the processing pipeline
- State management for OCR correction workflow

**Key Functions:**
- `process_pdf()`: Main processing pipeline
- `apply_corrections_and_generate_pdf()`: Applies user corrections and generates final PDF

**UI Organization:**
- **Left Column (Setup)**: Settings organized into sections
  - Document Language (dropdown: ru, ch, en, japan, korean, german, french, spanish)
  - De-noising (binarize toggle, block size slider, C constant slider)
  - Additional Settings (diagnostics, margins, formula detection)
  - OCR Quality Control (manual correction toggle, quality cutoff slider, **line calibration toggle**)
    - **Line Calibration** (opt-in): Fix overlapping text by adjusting line heights
      - Target Line Height slider (0-50px): Maximum line height before fixing is triggered
      - Overlap Threshold slider (-50 to 0px): Optional secondary filter for overlap severity
  - Font Size Buckets (5 configurable thresholds)
- **Right Column (Workflow)**: Processing interface
  - Tips (file size, orientation)
  - PDF upload
  - Process button
  - Output files and correction interface

**Key Parameters:**
- `language`: Document language for OCR accuracy (default: "ru")
- `binarize_enabled`: Whether to apply binarization preprocessing (default: True)
- `binarize_block_size`: Adaptive thresholding neighborhood size, 11-51, odd (default: 31)
- `binarize_c_constant`: Threshold constant subtracted from mean, 0-51 (default: 25)
- `enable_formula`: Enable/disable MinerU formula detection (default: False)
- `keep_original_margins`: Use exact page positioning or consistent 1.5cm margins (default: True)
- `download_raw`: Download MinerU ZIP for diagnostics (default: True)
- `enable_ocr_correction`: Enable manual OCR correction workflow (default: True)
- `quality_cutoff`: Confidence threshold for flagging items, 0.0-1.0 (default: 0.9)
- `enable_line_calibration`: Enable line calibration to fix overlapping text (default: False)
- `target_line_height`: Maximum line height in pixels before overlap fixing (default: 34.0)
- `overlap_threshold`: Maximum negative gap in pixels to ignore for overlap fixing (default: -10.0)
- `font_bucket_*`: Thresholds for mapping bbox heights to font sizes (default: 17, 22, 28, 30, 32)

---

### 2. PDF Preprocessor (`src/pdf_preprocessor.py`)

**File:** `src/pdf_preprocessor.py` (290+ lines)

**Responsibilities:**
- Convert PDF pages to images using pdf2image
- Apply OpenCV adaptive thresholding for binarization
- Rebuild PDF from binarized images
- Fix overlapping text by adjusting bbox heights

**Key Functions:**
- `preprocess_pdf()`: Main preprocessing pipeline with progress callback
- `fix_overlapping_blocks()`: Fix text overlap by reducing line heights
- `_adaptive_threshold()`: Gaussian-weighted local thresholding
- `_morphological_cleanup()`: Remove small noise artifacts
- `is_available()`: Check if dependencies are installed

**Line Calibration Logic:**
```python
# Problem: MinerU bbox data has overlapping lines (negative gaps)
# Solution: Reduce bbox heights to trigger smaller fonts

def fix_overlapping_blocks(layout_data, target_line_height=34, overlap_threshold=-10):
    for block in layout_data['pdf_info']:
        median_height = calculate_median(bbox_heights)

        # Primary filter: is line height too large?
        if median_height > target_line_height:
            # Secondary filter (optional): is overlap severe enough?
            if overlap_threshold < 0:
                max_overlap = find_max_negative_gap(lines)
                if max_overlap >= overlap_threshold:
                    continue  # Skip if overlap isn't severe enough

            # Reduce all bbox heights proportionally
            reduction_factor = target_line_height / median_height
            for line in block['lines']:
                line['bbox'][3] = line['bbox'][1] + (height * reduction_factor)
```

**Rationale:**
Scanned documents often have:
- Background noise (speckles, dots)
- Uneven lighting
- Low contrast
- Overlapping text from tight original line spacing

Binarization converts each pixel to pure black or white based on local neighborhood analysis, dramatically improving OCR accuracy.

Line calibration fixes visual text overlap by:
- Detecting blocks with line heights exceeding target
- Reducing bbox heights proportionally
- Triggering smaller font sizes via bucket mapping
- Preserving readability while eliminating overlap

**Parameters:**
- `block_size`: Size of neighborhood for local threshold calculation (odd, 11-51)
  - Higher = smoother results, less sensitive to local variations
  - Lower = more detail, but may amplify noise
- `c_constant`: Subtracted from local mean to determine threshold (0-51)
  - **Higher = more black pixels** (lower threshold)
  - **Lower = more white pixels** (higher threshold)
- `target_line_height`: Maximum line height before fixing (0-50px, default 34px)
  - Lower = more aggressive (fix more blocks)
  - Higher = more conservative (fix fewer blocks)
- `overlap_threshold`: Negative gap threshold (-50 to 0px, default -10px)
  - More negative = more selective (only fix severe overlaps)
  - 0 = disable this filter, use target_line_height only

---

### 3. MinerU API Processor (`src/mineru_processor.py`)

**File:** `src/mineru_processor.py` (420 lines)

**Responsibilities:**
- Communicate with MinerU batch API
- Handle two-step file upload workflow
- Poll for task completion
- Download and extract ZIP results

**Key Functions:**
- `submit_task()`: Initiate batch upload with presigned URL
- `poll_task()`: Wait for completion with timeout
- `process_pdf()`: Complete workflow from upload to download

**API Workflow:**
```python
# Step 1: Get presigned URL
POST /file-urls/batch
→ {"batch_id": "uuid", "file_urls": ["https://..."]}

# Step 2: Upload file
PUT {presigned_url}
→ File uploaded

# Step 3: Poll for completion
GET /extract-results/batch/{batch_id}
→ {"state": "done" | "running" | "failed"}

# Step 4: Download results
GET {full_zip_url}
→ ZIP with layout.json, content_list.json, full.md, images/
```

**Rationale for Batch Upload:**
The single-file endpoint only accepts URLs, not file uploads. Therefore, a two-step process is required:
1. Obtain presigned URL for direct upload
2. Upload file to S3-compatible storage
3. Poll batch endpoint for results

---

### 4. Document Builder (`src/document_builder.py`)

**File:** `src/document_builder.py` (1,082 lines)

**Responsibilities:**
- Parse MinerU JSON/Markdown output
- Calculate DPI from page dimensions
- Convert pixel coordinates to points
- Render PDF with ReportLab using exact positioning

**Key Classes:**
- `DocumentBuilder`: Main PDF building class with DPI-aware coordinate conversion

**Rendering Methods:**
1. **Layout-based rendering** (`add_from_layout_json`): Primary method using canvas-based absolute positioning with exact layout preservation
2. **Flow-based rendering** (`add_from_layout_json_flow`): Alternative using ReportLab flowables (Paragraph, Spacer) with dynamic spacing adjustment

**Critical Functions:**
- `add_from_layout_json()`: Canvas-based rendering with exact positioning
- `add_from_layout_json_flow()`: Flow-based rendering with dynamic spacing and custom styling
  - Titles: 12pt bold, centered, 0.4cm spacing before/after
  - Body text: 10.5pt, 12pt leading (1.14x), justified
  - Page numbers: 8pt, right-aligned
  - Footnotes: 8pt, left-aligned
  - Dynamic spacing: Automatically reduces spacing to fit content on each page
  - Gap detection: Adds 0.4cm spacer for gaps >30px between blocks
- `finalize()`: Creates SimpleDocTemplate and builds the document
  - Uses `self._flow_margin` if set by flow mode, otherwise uses 1cm or 2cm defaults
  - This ensures content wrapping matches PDF page margins
- `_calculate_dpi_from_page_size()`: Detect scan DPI by comparing to paper sizes
- `_convert_bbox()`: Convert pixels to points for all coordinates
- `_render_text_block()`: Map bbox heights to appropriate font sizes

**Font Size Mapping Logic:**
```python
# MinerU returns bbox heights in pixels at scan DPI
# We convert to points, then map to font size using thresholds

bbox_height_px = 43  # From layout.json
dpi = 150  # Calculated from page size
bbox_height_pt = bbox_height_px / dpi * 72  # = 20.6 points

# Block type determines sizing strategy:
# - TITLES: fixed at 12pt (for consistency)
# - DISCARDED (page numbers, footnotes): fixed at 8pt
# - TEXT: threshold-based mapping

# Map text blocks to font size using buckets (default thresholds):
if bbox_height_pt < 18.0:   font_size = 8pt
elif bbox_height_pt < 17.0:  font_size = 9pt
elif bbox_height_pt < 22.0:  font_size = 10pt
elif bbox_height_pt < 28.0:  font_size = 11pt
elif bbox_height_pt < 30.0:  font_size = 12pt
elif bbox_height_pt < 32.0:  font_size = 13pt
else: font_size = 14pt
```

**Font Handling:**
- DejaVu Sans (bundled) → System fonts → Helvetica (last resort)
- Helvetica does NOT support Cyrillic characters
- Font registration happens per-document to ensure availability

**Flow-Based Rendering Architecture:**

Flow mode provides an alternative to canvas-based exact positioning, using ReportLab's flowable system:

```python
# Content organization
content_items = [
    {'type': 'title', 'content': 'Chapter 1', 'spacing': 0.4*cm, ...},
    {'type': 'text', 'content': 'Body text...', 'spacing': 0.1*cm, ...},
    {'type': 'spacer', 'content': 0.4*cm, ...},  # For gap detection
    {'type': 'image', 'content': (path, width, height), ...},
]

# Dynamic spacing calculation
total_height = calculate_content_height(content_items, available_width, available_height)
if total_height > available_height:
    multiplier = available_height / total_height  # Reduce spacing
    multiplier = max(multiplier, 0.4)  # Minimum 40% reduction

# Render with adjusted spacing
for item in content_items:
    style = ParagraphStyle(..., spaceAfter=item['spacing'] * multiplier)
    story.append(Paragraph(item['content'], style))
```

**Margin Calculation and Usage:**

A critical bug was fixed where flow mode calculated content width using one margin, but `finalize()` used a different margin:

```python
# BEFORE (bug):
# In add_from_layout_json_flow():
available_width = page_width_pt - (2 * margin)  # margin = 32.2pt
# Paragraphs wrapped to: 595.27 - 64.4 = 530.87pt

# In finalize():
margin = 2 * cm  # 56.7pt, NOT the 32.2pt!
doc = SimpleDocTemplate(..., rightMargin=margin, leftMargin=margin, ...)
# PDF content area: 595.27 - 113.4 = 481.87pt
# Result: 530.87pt paragraphs don't fit in 481.87pt → overflow!

# AFTER (fixed):
# In add_from_layout_json_flow():
self._flow_margin = margin  # Store for finalize() to use

# In finalize():
if hasattr(self, '_flow_margin'):
    margin = self._flow_margin  # Use same margin as content wrapping
else:
    margin = 1 * cm if self.use_consistent_margins else 2 * cm
```

This ensures paragraphs are wrapped for the same width as the PDF page content area.

---

### 5. OCR Post-Processor (`src/ocr_postprocessor.py`)

**File:** `src/ocr_postprocessor.py` (235 lines)

**Responsibilities:**
- Extract low-confidence OCR results from MinerU layout.json
- Present them to user for manual review/correction
- Apply user corrections back to layout.json
- Create backup before modifying

**Key Functions:**
- `extract_low_confidence_items()`: Filter text spans by confidence score threshold
- `to_dataframe()`: Convert to Gradio-compatible DataFrame for UI
- `from_dataframe()`: Update corrections from user-edited table
- `apply_corrections()`: Patch layout.json with corrections (creates backup)

**Key Parameters:**
- `quality_threshold`: Confidence score cutoff (0.0-1.0, default: 0.9)
  - Spans with score < threshold are flagged for review
  - Lower threshold = more items to review
  - Higher threshold = fewer items

**Rationale:**
MinerU provides confidence scores for each text span. Low-confidence text often contains:
- OCR errors (misread characters)
- Fragments (partial words)
- Artifacts (page numbers, punctuation)

Manual correction is more reliable than automated grammar checking because:
- User understands context and intent
- No false positives (grammar checkers can introduce errors)
- Works for any language without configuration
- Zero processing overhead

---

### 6. Utilities (`src/utils.py`)

**File:** `src/utils.py` (102 lines)

**Responsibilities:**
- File validation (extension, size)
- Filename sanitization for safe downloads
- File size formatting for user display

**Key Functions:**
- `validate_pdf_path()`: Check file extension
- `check_file_size_limit()`: Verify size constraints
- `clean_filename()`: Sanitize output filenames

---

## Data Flow

### Complete Request Flow

```
1. USER UPLOAD
   ├── Gradio receives file object
   ├── Validate PDF extension (.pdf)
   └── Check file size (< 200MB)

2. OPTIONAL BINARIZATION
   ├── Convert PDF to images (200 DPI)
   ├── Apply adaptive thresholding per page
   ├── Rebuild PDF from binarized images
   └── Return binarized PDF for API processing

3. SUBMIT TO MINERU
   ├── POST /file-urls/batch
   │   └── Get presigned upload URL + batch_id
   ├── PUT file to presigned URL (S3-compatible)
   └── Return batch_id for polling

4. POLL FOR COMPLETION
   ├── GET /extract-results/batch/{batch_id}
   ├── Check state: waiting-file → pending → running → done
   ├── Repeat every 5 seconds (max 600 seconds)
   └── Extract error message if failed

5. DOWNLOAD RESULTS
   ├── GET full_zip_url
   ├── Extract ZIP to temp directory:
   │   ├── layout.json (bbox coordinates in pixels)
   │   ├── content_list.json (structured content)
   │   ├── full.md (markdown content)
   │   ├── images/*.jpg (extracted images)
   │   └── *_origin.pdf (original file)
   └── Parse layout.json for page dimensions

5A. EXTRACT LOW-CONFIDENCE ITEMS (if OCR correction enabled)
    ├── Load layout.json from temp directory
    ├── Scan all text spans for confidence scores
    ├── Filter spans where score < quality_cutoff
    ├── Store location data (page, block, line, span indices)
    └── Return DataFrame to UI for user review

5B. USER MANUAL CORRECTION (if low-conf items found)
    ├── Display editable table in Gradio UI
    ├── User edits "Correction" column
    │   ├── Fix mistakes in "Original" text
    │   └── Leave blank to delete the span
    ├── Click "Apply Corrections"
    └── Continue to step 6 with corrected layout

5C. APPLY CORRECTIONS
    ├── Create backup: layout_uncorrected.json
    ├── Navigate to each span using stored location data
    ├── Update span["content"] with user correction
    ├── Save modified layout.json
    └── Proceed to PDF generation with corrected data

5D. LINE CALIBRATION (if enabled)
    ├── For each page in layout.pdf_info:
    │   ├── For each block in preproc_blocks:
    │   │   ├── Get median bbox height (pixels)
    │   │   ├── Skip if median height <= target_line_height (e.g., 34px)
    │   │   ├── (Optional) Skip if max_overlap >= overlap_threshold (e.g., -10px)
    │   │   ├── Calculate reduction factor: target_line_height / median_height
    │   │   ├── Apply reduction to all lines in block
    │   │   │   ├── Keep y1 (top position)
    │   │   │   └── Reduce y2: new_y2 = y1 + (old_height × reduction_factor)
    │   │   ├── Update block bbox to contain modified lines
    │   │   └── Increment blocks_fixed counter
    │   └── Print summary: "Fixed X blocks with line height > Ypx"
    └── Return modified layout_data with reduced bbox heights
        └── Result: Reduced bbox heights map to smaller font buckets

6. BUILD PDF
   ├── Calculate DPI from page size (Letter/A4 detection)
   ├── Convert page size from pixels to points
   ├── For each content block:
   │   ├── Convert bbox from pixels to points
   │   ├── Calculate median bbox height for block
   │   ├── Convert to points using DPI
   │   ├── Map to font size using thresholds
   │   └── Render at exact position with exact font
   ├── Embed images with proper scaling
   └── Save to output path with format: <name>_final_<timestamp>.pdf

7. RETURN TO USER
   ├── Main output: OCR-processed PDF (always shown when generated)
   ├── Optional: Binarized PDF (shown only if "Pre-process PDF" checkbox is checked)
   └── Optional: Raw MinerU ZIP (shown only if "Download raw MinerU output" checkbox is checked)
```

---

## Design Decisions and Rationale

### 1. DPI Calculation from Page Size

**Problem:** MinerU returns bbox coordinates in pixels, but ReportLab requires points. We need to know the scan DPI to convert correctly.

**Solution:** Detect paper size by comparing pixel dimensions to known standards:
```python
# US Letter: 8.5 × 11 inches
# A4: 8.27 × 11.69 inches

dpi_width = page_width_px / 8.5  # For Letter
dpi_height = page_height_px / 11  # For Letter
avg_dpi = (dpi_width + dpi_height) / 2
```

**Rationale:**
- Scanned documents are almost always standard paper sizes
- DPI is consistent across width and height for proper scans
- Using average improves accuracy
- Letter vs A4 detection handles both common sizes
- Chooses the paper size with more consistent width/height DPI ratio

**Alternatives Considered:**
- **Assume 72 DPI**: Too low, would give tiny fonts
- **Assume 300 DPI**: Too high for typical scans
- **Use EXIF metadata**: Not available in PDF
- **Ask user**: Adds friction, error-prone

---

### 2. Pixel-to-Point Conversion

**Problem:** ReportLab interprets all coordinates and sizes in points (1/72 inch). MinerU provides pixel coordinates.

**Solution:** Convert all measurements:
```python
def pixels_to_points(value_px, dpi):
    return value_px / dpi * 72

# Apply to:
- Page dimensions
- Bbox coordinates (x, y, width, height)
- Font size calculations
```

**Rationale:**
- Ensures consistent units throughout rendering pipeline
- Prevents scaling errors (everything was ~50% too small before)
- Matches ReportLab's internal coordinate system

**Bug Encountered:**
Initially set canvas size to pixel dimensions directly, causing ReportLab to interpret 1275 pixels as 1275 points (nearly 18 inches) instead of 612 points (8.5 inches). This made fonts appear tiny because the canvas was oversized.

---

### 3. Font Size Bucket Mapping

**Problem:** Need to map bbox heights to appropriate font sizes. Bbox height includes the font size plus line spacing (leading).

**Solution:** Use threshold-based buckets with configurable defaults:
```python
# Line height ≈ font_size × 1.2
# 9pt font → ~11pt line height
# 10pt font → ~12pt line height
# etc.

# Map text blocks to font size using buckets (default thresholds):
if bbox_height_pt < 18.0:   font_size = 8pt
elif bbox_height_pt < 17.0:  font_size = 9pt
elif bbox_height_pt < 22.0:  font_size = 10pt
elif bbox_height_pt < 28.0:  font_size = 11pt
elif bbox_height_pt < 30.0:  font_size = 12pt
elif bbox_height_pt < 32.0:  font_size = 13pt
else: font_size = 14pt
```

**Rationale:**
- Median bbox height is stable measure for block
- Thresholds account for leading (typically 1.2x font size)
- User-adjustable for different documents via UI sliders
- Balances precision (discrete steps) vs flexibility

**Alternatives Considered:**
- **Direct mapping** (`font_size = bbox_height / 1.2`): Too precise, causes visual inconsistency
- **ML-based prediction**: Overkill, requires training data
- **Fixed font sizes**: Loses original hierarchy information

---

### 4. Binarization Preprocessing

**Problem:** Scanned documents often have noise that reduces OCR accuracy.

**Solution:** Optional OpenCV adaptive thresholding pipeline:
1. Convert PDF to images at 200 DPI
2. Apply Gaussian-weighted adaptive threshold per pixel
3. Remove small noise with morphological opening
4. Rebuild PDF from processed images

**Rationale:**
- **Adaptive thresholding** handles uneven lighting better than global threshold
- **Gaussian weighting** gives smooth results
- **Morphological cleanup** removes isolated noise pixels
- User-adjustable parameters for different document types

**Parameter Guidance:**
- `block_size=31, c=25`: Good for typical text documents (default)
- `block_size=51, c=30`: Better for low-contrast scans
- `block_size=15, c=15`: Preserves more detail but may keep noise

---

### 5. Page Size Options

**Problem:** Should output PDF use original page size or standard size (A4)?

**Solution:** User choice via checkbox:
- **Keep original margins**: Use exact page size from scan
- **Use consistent margins**: Force A4 with 1.5cm margins

**Rationale:**
- Original size preserves exact layout but may vary
- A4 ensures consistency but may crop content
- Some users want exact reproduction, others want standard documents
- Providing choice serves both use cases

---

### 6. Font Handling for Cyrillic

**Problem:** Standard ReportLab fonts don't support Russian/Cyrillic characters.

**Solution:** Multi-tier font registration:
```python
font_paths = [
    'fonts/DejaVuSans.ttf',           # Bundled (highest priority)
    '/usr/share/fonts/.../DejaVu...', # System fonts
    'C:\\Windows\\Fonts\\arial.ttf',  # Windows
    # ... more fallbacks
]
```

**Rationale:**
- DejaVu Sans has excellent Cyrillic coverage
- Bundling font ensures it works on HF Spaces
- System fonts provide fallback for local dev
- Graceful degradation to Helvetica (with warning)

---

### 7. Two-Stage Coordinate Conversion

**Problem:** MinerU uses top-left origin (like images), ReportLab uses bottom-left origin (like PDF).

**Solution:** Explicit coordinate transformation:
```python
# MinerU: y=0 is top, y increases downward
# ReportLab: y=0 is bottom, y increases upward

rl_y = page_height - y2  # Flip Y coordinate
```

**Rationale:**
- Explicit conversion makes logic clear
- Prevents off-by-one errors
- Documented for future maintenance

---

### 8. Standardized Output Filename Format

**Problem:** Output filenames need to be predictable and include timestamps to prevent overwrites.

**Solution:** Always use consistent format with preserved original filename:
```python
# Save original filename BEFORE any preprocessing (binarization, etc.)
original_base_name = clean_filename(os.path.basename(pdf_path))
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = f"{original_base_name}_final_{timestamp}.pdf"
```

**Applied to:**
- Normal processing (no OCR corrections needed)
- OCR correction workflow (after user applies corrections)
- Both code paths use the same original filename to ensure consistency

**Rationale:**
- Predictable naming helps users find output files
- Timestamp prevents overwrites
- Original filename is preserved regardless of preprocessing (e.g., binarization)
- **Example:** `extract_2.pdf` → `extract_2_final_20260108_105805.pdf` (NOT `extract_2_binarized_20260108_105746_final_...`)
- "_final" suffix clearly indicates this is the end product
- Consistency improves UX

---

### 9. Interactive OCR Correction Workflow

**Problem:** OCR is not perfect and users need a way to fix errors before final PDF generation.

**Solution:** Two-stage workflow with interactive DataFrame:
1. Extract low-confidence items based on quality threshold
2. Display editable table with Page, Score, Type, Original, Correction columns
3. User edits corrections and clicks "Apply Corrections"
4. Apply corrections to layout.json and generate final PDF

**Rationale:**
- Preserves exact positioning information for applying corrections
- User sees context (page, score, type) for each item
- Can delete items by leaving correction blank
- Creates backup before modifications
- State management allows corrections to be applied after initial processing

---

## Key Implementation Details

### Challenge 1: Tiny Font Sizes

**Root Cause:** Unit mismatch between MinerU (pixels) and ReportLab (points):
- Page size: `[1275, 1650]` pixels (US Letter at 150 DPI)
- Canvas set to 1275×1650 points → nearly 18×23 inches!
- Fonts positioned correctly but on oversized canvas

**Solution:**
1. Calculate DPI from page size (detecting Letter/A4)
2. Convert page dimensions to points before setting canvas
3. Convert all bbox coordinates to points

**Code:**
```python
page_width_pt = original_page_width_px / dpi * 72  # 1275 → 612
page_height_pt = original_page_height_px / dpi * 72  # 1650 → 792
canvas.setPageSize((page_width_pt, page_height_pt))
```

---

### Challenge 2: Font Size Still Wrong After DPI Fix

**Root Cause:** Bbox heights from MinerU were in pixels, but being used directly for font size mapping without conversion.

**Solution:**
```python
# Before: Used pixels directly
font_size = get_font_size_from_bbox(bbox_height_px)  # Wrong!

# After: Convert to points first
bbox_height_pt = bbox_height_px / dpi * 72
font_size = get_font_size_from_bbox(bbox_height_pt)  # Correct!
```

---

### Challenge 3: Images Not Rendering

**Root Cause:** MinerU extracts images to `images/` subfolder in ZIP. DocumentBuilder couldn't find them.

**Solution:**
1. Always extract ZIP to temp directory preserving structure
2. Pass temp_dir to DocumentBuilder
3. Resolve image paths relative to temp_dir

**Code:**
```python
# MinerU provides: "images/abc123.jpg"
# Need: "/tmp/mineru_xyz/images/abc123.jpg"
img_path = os.path.join(self.temp_dir, img_rel_path)
```

---

### Challenge 4: Binarization TypeError

**Root Cause:** img2pdf expects file-like objects, but was receiving PIL Image objects directly.

**Solution:**
```python
# Convert PIL Images to BytesIO buffers
buf = io.BytesIO()
img.save(buf, format='PNG')
buf.seek(0)
image_buffers.append(buf)

# Pass buffers to img2pdf
pdf_bytes = img2pdf.convert(image_buffers)
```

---

### Challenge 5: Gradio 6.0.0 DataFrame Not Displaying Data

**Root Cause:** Gradio 6.0.0 had rendering issues with DataFrame components initialized with `visible=False` that were later updated to `visible=True` with data.

**Solution:**
1. Upgraded to Gradio 6.2.0
2. Updated `requirements.txt`: `gradio>=6.2.0`
3. Updated `README.md` metadata: `sdk_version: 6.2.0`

---

## Dependencies

### Python Dependencies

```
gradio>=6.2.0          # UI framework (upgraded for DataFrame fix)
reportlab>=4.0.0       # PDF generation
requests>=2.31.0       # HTTP client
python-dotenv>=1.0.0   # Environment config
Pillow>=10.0.0         # Image processing
pandas>=2.0.0          # DataFrame operations for OCR corrections
opencv-python>=4.8.0   # Binarization
pdf2image>=1.16.0      # PDF to images
img2pdf>=0.4.4         # Images to PDF
numpy>=1.24.0          # Array operations
```

**Core dependencies:**
- gradio>=6.2.0: UI framework with DataFrame bug fixes
- pandas>=2.0.0: Required for OCR correction table handling
- reportlab>=4.0.0: PDF generation

**Optional dependencies** (required for binarization):
- opencv-python>=4.8.0
- pdf2image>=1.16.0
- img2pdf>=0.4.4
- numpy>=1.24.0

The app gracefully handles missing optional dependencies by disabling binarization feature.

### System Dependencies

```
fonts-dejavu-core    # Cyrillic font support
fonts-dejavu-extra   # Extended font variants
poppler-utils        # PDF to image conversion
```

---

## References

- [MinerU API Documentation](https://mineru.net/)
- [ReportLab User Guide](https://www.reportlab.com/docs/reportlab-userguide.pdf)
- [OpenCV Documentation](https://docs.opencv.org/)
- [Gradio Documentation](https://gradio.app/docs/)
