# Architecture Documentation

This document describes the system architecture, data flow, design decisions, and challenges encountered for the PDF Document Cleaner.

## Table of Contents

1. [System Overview](#system-overview)
2. [Component Architecture](#component-architecture)
3. [Data Flow](#data-flow)
4. [Design Decisions and Rationale](#design-decisions-and-rationale)
5. [Key Challenges and Solutions](#key-challenges-and-solutions)
6. [Options Considered But Not Implemented](#options-considered-but-not-implemented)
7. [Error Handling Strategy](#error-handling-strategy)
8. [Performance Considerations](#performance-considerations)

---

## System Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Gradio     │     │   Optional   │     │    MinerU    │     │   Document   │
│     UI       │────▶│  Binarize    │────▶│     API      │────▶│   Builder    │
│  (app.py)    │     │(pdf_preproc) │     │  (External)  │     │(document_    │
│              │     │              │     │              │     │  builder.py) │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │                                                                 │
       │                            ┌──────────────┐                        │
       └───────────────────────────▶│  Output PDF  │◀───────────────────────┘
                                    │  (.pdf file)  │
                                    └──────────────┘
```

### Core Problem Solved

The application processes scanned PDF documents to:
1. **Extract text** via OCR while preserving document structure
2. **Remove visual noise** from scans (binarization preprocessing)
3. **Generate clean, searchable PDFs** with properly sized fonts

---

## Component Architecture

### 1. Gradio UI (`app.py`)

**Responsibilities:**
- User interface for file upload and settings
- Input validation (file type, size)
- Progress tracking and error display
- Orchestration of the processing pipeline

**Key Functions:**
- `process_pdf()`: Main processing pipeline that coordinates all components

**Key Parameters:**
- `output_format`: "json" (structured) or "markdown" (simple)
- `language`: Document language for OCR accuracy
- `binarize_enabled`: Whether to apply binarization preprocessing
- `binarize_block_size`: Adaptive thresholding neighborhood size (11-51, odd)
- `binarize_c_constant`: Threshold constant subtracted from mean (0-30)
- `font_bucket_*`: Thresholds for mapping bbox heights to font sizes

---

### 2. PDF Preprocessor (`src/pdf_preprocessor.py`)

**Responsibilities:**
- Convert PDF pages to images using pdf2image
- Apply OpenCV adaptive thresholding for binarization
- Rebuild PDF from binarized images

**Key Functions:**
- `preprocess_pdf()`: Main preprocessing pipeline with progress callback
- `_adaptive_threshold()`: Gaussian-weighted local thresholding
- `_morphological_cleanup()`: Remove small noise artifacts

**Rationale:**
Scanned documents often have:
- Background noise (speckles, dots)
- Uneven lighting
- Low contrast

Binarization converts each pixel to pure black or white based on local neighborhood analysis, dramatically improving OCR accuracy.

**Parameters Explained:**
- `block_size`: Size of neighborhood for local threshold calculation
  - Higher = smoother results, less sensitive to local variations
  - Lower = more detail, but may amplify noise
- `c_constant`: Subtracted from local mean to determine threshold
  - **Higher = more black pixels** (lower threshold)
  - **Lower = more white pixels** (higher threshold)

---

### 3. MinerU API Processor (`src/mineru_processor.py`)

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
→ {"batch_id": "uuid", "url": "https://..."}

# Step 2: Upload file
PUT {presigned_url}
→ File uploaded

# Step 3: Poll for completion
GET /extract-results/batch/{batch_id}
→ {"state": "done" | "running" | "failed"}

# Step 4: Download results
GET {full_zip_url}
→ ZIP with content, layout.json, images/
```

**Rationale for Batch Upload:**
The single-file endpoint only accepts URLs, not file uploads. Therefore, a two-step process is required:
1. Obtain presigned URL for direct upload
2. Upload file to S3-compatible storage
3. Poll batch endpoint for results

---

### 4. Document Builder (`src/document_builder.py`)

**Responsibilities:**
- Parse MinerU JSON/Markdown output
- Calculate DPI from page dimensions
- Convert pixel coordinates to points
- Render PDF with ReportLab using exact positioning

**Key Classes:**
- `DocumentBuilder`: Main PDF building class with DPI-aware coordinate conversion

**Critical Functions:**
- `add_from_layout_json()`: Canvas-based rendering with exact positioning
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

# Map to font size using buckets
if bbox_height_pt < 11.5:  font_size = 9pt
elif bbox_height_pt < 12.5: font_size = 10pt
elif bbox_height_pt < 14.0: font_size = 11pt
elif bbox_height_pt < 16.0: font_size = 12pt
elif bbox_height_pt < 18.5: font_size = 13pt
else: font_size = 14pt
```

**Font Handling:**
- DejaVu Sans (bundled) → Fallback to system fonts → Helvetica (last resort)
- Helvetica does NOT support Cyrillic characters
- Font registration happens per-document to ensure availability

---

### 5. Utilities (`src/utils.py`)

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
   │   ├── *_content_list.json (structured content)
   │   ├── full.md (markdown content)
   │   ├── images/*.jpg (extracted images)
   │   └── *_origin.pdf (original file)
   └── Parse layout.json for page dimensions

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
   └── Save to output path

7. RETURN TO USER
   ├── Main output: OCR-processed PDF
   ├── Optional: Binarized PDF (if preprocessing enabled)
   └── Optional: Raw MinerU ZIP (for diagnostics)
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

**Solution:** Use threshold-based buckets:
```python
# Line height ≈ font_size × 1.2
# 9pt font → ~11pt line height
# 10pt font → ~12pt line height
# etc.

if bbox_height_pt < 11.5:  return 9pt
elif bbox_height_pt < 12.5: return 10pt
# ... etc
```

**Rationale:**
- Median bbox height is stable measure for block
- Thresholds account for leading (typically 1.2x font size)
- User-adjustable for different documents
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
- `block_size=31, c=20`: Good for typical text documents
- `block_size=51, c=25`: Better for low-contrast scans
- `block_size=15, c=10`: Preserves more detail but may keep noise

---

### 5. Page Size Options

**Problem:** Should output PDF use original page size or standard size (A4)?

**Solution:** User choice via checkbox:
- **Keep original margins**: Use exact page size from scan
- **Use consistent margins**: Force A4 with 1cm margins

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

## Key Challenges and Solutions

### Challenge 1: Tiny Font Sizes

**Symptom:** All text appeared at ~50% of expected size, despite correct font size calculations.

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

**Symptom:** Fonts still appeared small after fixing DPI calculation.

**Root Cause:** Bbox heights from MinerU were in pixels, but being used directly for font size mapping without conversion.

**Solution:**
```python
# Before: Used pixels directly
font_size = get_font_size_from_bbox(bbox_height_px)  # Wrong!

# After: Convert to points first
bbox_height_pt = bbox_height_px / dpi * 72
font_size = get_font_size_from_bbox(bbox_height_pt)  # Correct!
```

**Example:**
- Bbox height: 43 pixels
- At 150 DPI: 43 / 150 × 72 = 20.6 points
- 20.6pt line height → 14pt font (using 1.2x leading ratio)

---

### Challenge 3: Images Not Rendering

**Symptom:** Images appeared as broken or missing.

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

**Symptom:** `TypeError: Neither read(), read_bytes() nor is str or bytes` when calling `img2pdf.convert()`.

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

### Challenge 5: Progress Callback Division by Zero

**Symptom:** `ZeroDivisionError` in binarization progress callback.

**Root Cause:** Progress callback called before page count was determined (total=0).

**Solution:**
```python
def progress_cb(page, total, msg):
    if total > 0:
        progress(0.05 + (0.1 * page / total), desc=msg)
    else:
        progress(0.05, desc=msg)
```

---

### Challenge 6: Poppler Not Installed on HF Spaces

**Symptom:** `FileNotFoundError: pdfinfo not found` when using pdf2image.

**Root Cause:** pdf2image requires Poppler utilities, but HF Spaces uses `packages.txt` not `apt.txt`.

**Solution:**
```bash
# Wrong: apt.txt (not read by HF Spaces)
poppler-utils

# Correct: packages.txt (read by HF Spaces)
poppler-utils
```

Required factory reset of Space to install system packages.

---

### Challenge 7: C Constant Direction Confusion

**Symptom:** Initial documentation had C constant effect backwards.

**Root Cause:** Misunderstanding of adaptive threshold formula:
```python
threshold = mean neighborhood - C
# Higher C → lower threshold → more pixels classified as black
```

**Solution:**
- Corrected documentation and info text
- Updated default C from 10 to 20 (fewer black dots)
- Clarified: "Lower=more white, Higher=more black"

---

## Options Considered But Not Implemented

### 1. Local OCR Processing

**Considered:** Running Tesseract or similar locally instead of using MinerU API.

**Rejected because:**
- Requires heavy ML models and dependencies
- Computationally expensive (need GPU for good performance)
- Language support requires installing language packs
- Accuracy generally lower than commercial APIs

**Trade-off:** API dependency vs local processing complexity

---

### 2. Direct PDF Modification

**Considered:** Modify original PDF directly (replace text layers) instead of rebuilding.

**Rejected because:**
- PDF structure is complex and fragile
- Text extraction may be inaccurate or incomplete
- Hard to preserve images and formatting
- Limited control over output quality

**Trade-off:** Full rebuild vs incremental modification

---

### 3. Markdown-Only Processing

**Considered:** Only support Markdown output, not JSON.

**Rejected because:**
- JSON preserves more structure (tables, images, layout)
- Markdown loses positional information
- Can't do exact positioning with Markdown
- Users want clean PDFs that match original layout

**Trade-off:** Simplicity vs feature richness

---

### 4. Automatic Font Size Detection

**Considered:** Use machine learning to predict optimal font sizes from bbox dimensions.

**Rejected because:**
- Requires training dataset
- Overfitting risk to specific document types
- User may want different sizing for accessibility
- Threshold buckets are simpler and more transparent

**Trade-off:** ML sophistication vs user control

---

### 5. Batch Processing Multiple Files

**Considered:** Allow uploading and processing multiple files at once.

**Rejected because:**
- Gradio UI complexity increases significantly
- Progress tracking becomes more complex
- API rate limiting concerns
- Most users process one document at a time

**Trade-off:** Feature richness vs UI simplicity

**Future enhancement:** Could be added if there's demand

---

### 6. Caching Processed Documents

**Considered:** Cache results to avoid reprocessing same file.

**Rejected because:**
- Storage costs on HF Spaces
- Cache invalidation complexity
- Privacy concerns (storing user documents)
- Most documents are unique

**Trade-off:** Performance vs privacy/cost

---

### 7. Advanced Image Enhancement

**Considered:** Add deskewing, perspective correction, or other image preprocessing.

**Rejected because:**
- Increases dependency count significantly
- May introduce artifacts
- MinerU API handles some of this
- Binarization is sufficient for most cases

**Trade-off:** Feature completeness vs simplicity

---

## Error Handling Strategy

### API Errors

```python
# Extract meaningful error from MinerU response
error_msg = first_result.get("err_msg", "Unknown error")
if state == "failed":
    return {
        "status": "failed",
        "result": {"error": error_msg}
    }
```

### File Validation

```python
# Multi-layer validation
if not validate_pdf_path(pdf_path):
    raise gr.Error("Invalid file. Please upload a PDF file.")

is_valid, size_mb, msg = check_file_size_limit(pdf_path, max_mb=200)
if not is_valid:
    raise gr.Error(msg)
```

### Timeout Handling

```python
# Poll with configurable timeout
if time.time() - start_time > max_wait_seconds:
    raise TimeoutError(f"Task {task_id} did not complete in {max_wait_seconds}s")
```

### Graceful Degradation

```python
# Font registration fallback
try:
    pdfmetrics.registerFont(TTFont(font_path, font_path))
except:
    # Try next font path
    try:
        pdfmetrics.registerFont(TTFont(system_font_path, font_path))
    except:
        # Last resort
        font_name = 'Helvetica'  # May not support Cyrillic
```

---

## Performance Considerations

### File Size Limits

| Metric | Limit | Rationale |
|--------|-------|-----------|
| Upload | 200 MB | MinerU API constraint |
| Processing | 10 min | API timeout |
| Pages | 600 | API constraint |
| Polling interval | 5 sec | Balance responsiveness vs load |

### Optimization Opportunities

1. **Streaming PDF generation**: Currently builds entire PDF in memory. Could stream for large documents.

2. **Parallel page processing**: Binarization and some rendering could be parallelized.

3. **Incremental rendering**: Render pages as they're processed rather than waiting for all.

4. **Result caching**: Cache by file hash for repeated processing.

**Current stance:** Optimization not critical yet. Profile before optimizing.

---

## Security Considerations

### API Key Management

- Stored in HF Spaces secret (`MINERU_API_KEY`)
- Never logged or exposed in error messages
- Passed via `Authorization: Bearer {token}` header

### File Handling

- Temporary files cleaned up after processing
- No persistent storage of user uploads
- Input validation on file type and size
- Sanitized filenames for downloads

### Dependency Security

- Use pinned versions in requirements.txt
- Regular updates for security patches
- Minimal dependencies to reduce attack surface

---

## Future Improvements

### High Priority

1. **Additional paper sizes**: Support Legal, A3, etc.
2. **Custom font paths**: Allow users to upload custom fonts
3. **Advanced binarization**: Add Otsu, Sauvola methods

### Medium Priority

1. **DOCX output**: Export to Word format
2. **Batch processing**: Handle multiple files
3. **Quality presets**: Pre-configured parameter sets

### Low Priority

1. **LaTeX rendering**: Native equation rendering
2. **Table extraction**: Preserve table structure better
3. **Language detection**: Auto-detect document language

---

## Dependencies

```
gradio>=6.0.0          # UI framework
reportlab>=4.0.0      # PDF generation
requests>=2.31.0      # HTTP client
python-dotenv>=1.0.0  # Environment config
Pillow>=10.0.0        # Image processing
opencv-python>=4.8.0  # Binarization (optional)
pdf2image>=1.16.0     # PDF to images (optional)
img2pdf>=0.4.4        # Images to PDF (optional)
numpy>=1.24.0         # Array operations (optional)
```

**Optional dependencies** (required only if binarization is enabled):
- opencv-python
- pdf2image
- img2pdf
- numpy

The app gracefully handles missing optional dependencies by disabling binarization feature.

---

## References

- [MinerU API Documentation](https://mineru.net/)
- [ReportLab User Guide](https://www.reportlab.com/docs/reportlab-userguide.pdf)
- [OpenCV Documentation](https://docs.opencv.org/)
- [Gradio Documentation](https://gradio.app/docs/)
