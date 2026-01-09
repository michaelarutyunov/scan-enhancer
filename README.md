---
title: PDF Document Cleaner
emoji: 📚
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 6.2.0
app_file: app.py
pinned: false
python_version: "3.10"
---

# PDF Document Cleaner 📚

A HuggingFace Spaces application that processes scanned PDF documents using **MinerU API** to extract text while preserving images, tables, and document structure.

## Features

- **Multi-Language OCR**: Supports 109 languages including Russian, powered by MinerU
- **Structure Preservation**: Extracts and preserves headings, paragraphs, lists, tables, and images
- **Binarization Preprocessing**: Enabled by default for improved OCR accuracy on noisy scans
- **Line Calibration**: Optional feature to fix overlapping text by adjusting line heights (opt-in)
- **OCR Manual Correction**: Review and fix low-confidence text before generating PDF
- **Smart Font Sizing**: DPI-aware coordinate conversion for properly sized fonts
- **Flow-Based Mode**: Alternative rendering mode with custom styling and dynamic spacing
- **PDF Output**: Generates clean, searchable PDFs with predictable filenames
- **Cloud Processing**: Uses MinerU cloud API - no local ML models needed

## How It Works

```
┌────────────────┐
│  Upload PDF    │
│  (max 200MB)   │
└────────┬───────┘
         │
         ▼
┌─────────────────────────────┐
│  Binarization (default ON)  │
│  - Remove noise & speckles  │
│  - Improve contrast         │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  MinerU Cloud API           │
│  - OCR with language model  │
│  - Extract layout/structure │
│  - Confidence scores        │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  OCR Quality Check          │
│  IF confidence < 0.9:       │
│  → Manual correction table  │
│  ELSE: Skip to PDF          │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  PDF Builder                │
│  - DPI detection            │
│  - Coordinate conversion    │
│  - Font size mapping        │
│  - ReportLab rendering      │
└────────┬────────────────────┘
         │
         ▼
┌────────────────────────────┐
│  Clean PDF                 │
│  + Searchable              │
│  + Proper fonts            │
│  + <name>_final_<time>.pdf │
└────────────────────────────┘
```

### Why This Tool?

Scanned PDFs often have:
- ❌ No selectable/searchable text
- ❌ Visual noise (speckles, dots)
- ❌ Inconsistent or tiny fonts
- ❌ Overlapping text (tight line spacing)
- ❌ Poor OCR accuracy

This tool produces:
- ✅ Fully searchable text
- ✅ Clean, noise-free documents
- ✅ Properly sized fonts (DPI-aware)
- ✅ Fixed overlapping text (with line calibration)
- ✅ High OCR accuracy
- ✅ Flow-based mode option for custom styling

## Usage

### Quick Start

1. Upload a scanned PDF document (max 200 MB, 600 pages)
2. **Optional**: Adjust "Pre-process PDF" settings for noisy scans
3. Select document language (Russian, English, Chinese, etc.) for better OCR accuracy
4. **Optional**: Uncheck "Keep original page margins" for flow-based mode with custom styling
5. **Optional**: Enable "Line Calibration" if text appears overlapping in output
6. **Optional**: Adjust font size buckets if automatic sizing needs tuning
7. Click "🔍 Process the document"
8. **If low-confidence items found**: Review and correct in the table, then click "✅ Apply Corrections"
9. Download the cleaned PDF

### Advanced Settings

#### Binarization (Noise Reduction)

Enable this for documents with:
- Background noise or speckles
- Uneven lighting
- Low contrast

**Parameters:**
- **Block size** (11-51, odd): Neighborhood size for local thresholding
  - Higher = smoother, less sensitive to noise
  - Lower = more detail, may amplify noise
  - Default: 31 (good for most documents)

- **C constant** (0-51): Threshold adjustment
  - **Higher = more black** (lower threshold)
  - **Lower = more white** (higher threshold)
  - Default: 25 (cleaner results)

#### OCR Quality Control

- **Manual Correction**: Enable to review low-confidence OCR results
- **Quality Cut-off** (0.0-1.0): Confidence threshold for flagging items
  - Lower = more items to review
  - Higher = fewer items
  - Default: 0.9

#### Line Calibration (Overlap Fixing)

Enable this to fix overlapping text by reducing line heights in blocks with excessive spacing.

**When to use:**
- Text appears vertically overlapping in the output PDF
- Lines are too close together or touching
- Some fonts appear too large for their content

**Parameters:**
- **Target Line Height** (0-50px, default 34px): Maximum line height before fixing is triggered
  - Blocks with median height > this value will be reduced
  - Lower = more aggressive (fixes more blocks)
  - Higher = more conservative (fixes fewer blocks)
  - Set based on visual appearance of overlapping text

- **Overlap Threshold** (-50 to 0px, default -10px): Optional secondary filter
  - Only fixes blocks with overlap worse than this value
  - More negative = more severe overlap required
  - Set to 0 to disable this filter (use only Target Line Height)

**How it works:**
1. Analyzes each text block in layout.json
2. Calculates median bbox height (in pixels)
3. If height exceeds Target Line Height (and optionally, Overlap Threshold):
   - Reduces bbox heights proportionally to map to smaller font sizes
   - Keeps text positions intact, only reduces vertical spacing
4. Result: Smaller fonts that don't overlap

**Note:** This feature is opt-in (disabled by default) to preserve original fonts for documents without overlap issues.

#### Flow-Based Rendering Mode (Uncheck "Keep original page margins")

When unchecked, switches from exact layout positioning to flow-based rendering with custom styling.

**When to use:**
- You want more readable, reformatted documents
- You don't need to preserve the exact original layout
- You prefer consistent styling over exact positioning

**Styling in flow mode:**
- **Titles**: 12pt bold, centered, 0.4cm spacing before/after
- **Body text**: 10.5pt, 12pt leading (1.14x), justified alignment
- **Page numbers**: 8pt, right-aligned
- **Footnotes**: 8pt, left-aligned
- **Gap detection**: Automatically adds 0.4cm spacer for gaps >30px between blocks
- **Dynamic spacing**: Reduces spacing (to 40% minimum) to fit content on each page

**How it works:**
1. Uncheck "Keep original page margins"
2. Content is organized into flowable items (titles, text, images, spacers)
3. Calculates total height and adjusts spacing multiplier if needed
4. Renders with ReportLab's Paragraph and Spacer flowables
5. Result: Clean, readable document with consistent styling

**Note:** Flow mode uses margins calculated from the original PDF layout to ensure text that fit on single lines in the original also fits in the output.

#### Font Size Buckets

Adjust these if fonts appear too small/large:

| Slider | Default | Description |
|--------|---------|-------------|
| 8pt → 9pt | 17.0pt | Footnotes, page numbers |
| 9pt → 10pt | 22.0pt | Small text |
| 10pt → 11pt | 28.0pt | Body text |
| 11pt → 12pt | 30.0pt | Section headers |
| 12pt → 14pt | 32.0pt | Main titles |

## Technical Overview

### Architecture

```
app.py (Gradio UI - 472 lines)
    │
    └─→ pipeline.py (PDFProcessingPipeline - 505 lines)
        ├─→ processing_options.py (ProcessingOptions dataclass)
        ├─→ processing_result.py (ProcessingResult dataclass)
        ├─→ config.py (Configuration constants)
        ├─→ exceptions.py (Custom exception hierarchy - 18 types)
        │
        ├─→ pdf_preprocessor.py (Optional binarization)
        │   └─→ pdf2image + OpenCV
        │
        ├─→ mineru_processor.py (API client)
        │   └─→ MinerU Cloud API
        │
        ├─→ ocr_postprocessor.py (Manual correction)
        │   └─→ pandas DataFrame
        │
        └─→ document_builder/ (Modular package - 7 modules)
            ├─→ builder.py (DocumentBuilder orchestrator)
            ├─→ font_manager.py (Font registration & Cyrillic)
            ├─→ coordinate_utils.py (DPI & conversion utilities)
            ├─→ text_extractor.py (Text & footnote extraction)
            ├─→ layout_analyzer.py (Font sizing & layout)
            ├─→ content_renderer.py (Images, tables, equations)
            └─→ __init__.py (Public API exports)
```

### Key Technical Challenges Solved

#### 1. DPI Detection

**Problem:** MinerU returns coordinates in pixels, but PDF rendering requires points. We need to know the scan DPI to convert correctly.

**Solution:** Detect paper size by comparing pixel dimensions to standard sizes:
- US Letter: 8.5 × 11 inches
- A4: 8.27 × 11.69 inches

Example: A 1275×1650 pixel PDF → detected as US Letter at 150 DPI.

#### 2. Coordinate Conversion

**Problem:** Multiple coordinate systems:
- MinerU: pixels, top-left origin
- ReportLab: points, bottom-left origin

**Solution:** Two-stage conversion:
```python
# 1. Pixels to points
points = pixels / dpi * 72

# 2. Top-left to bottom-left
y_reportlab = page_height - y_mineru
```

#### 3. Font Size Mapping

**Problem:** Bbox height includes line spacing (leading), not just font size.

**Solution:** Use threshold buckets based on typical line heights:
- 9pt font → ~17pt line height
- 10pt font → ~22pt line height
- etc.

User-adjustable for different documents.

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| Use MinerU API | Best OCR accuracy, no local compute |
| Canvas-based rendering | Exact positioning, preserves layout |
| Threshold buckets | Transparent, user-adjustable |
| Optional binarization | Not all documents need it |
| DPI detection | Automatic, no user input |

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed technical documentation.

## Setup

### HuggingFace Spaces Deployment

1. Create a new Space on HuggingFace
2. Set `MINERU_API_KEY` as a Space secret (get your key at https://mineru.net/)
3. Upload all files from this repository
4. The Space will start automatically

### Local Development

```bash
# Clone repository
git clone <repo-url>
cd scan-enhancer

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and add your API key
cp .env.example .env
# Edit .env and add your MINERU_API_KEY

# Run application
python app.py
```

The app will be available at `http://localhost:7860`

### Dependencies

**Core:**
- `gradio>=6.2.0` - UI framework
- `reportlab>=4.0.0` - PDF generation
- `requests>=2.31.0` - HTTP client
- `python-dotenv>=1.0.0` - Environment config
- `Pillow>=10.0.0` - Image processing
- `pandas>=2.0.0` - DataFrame operations

**Optional (for binarization):**
- `opencv-python>=4.8.0` - Image processing
- `pdf2image>=1.16.0` - PDF to images
- `img2pdf>=0.4.4` - Images to PDF
- `numpy>=1.24.0` - Array operations

## Project Structure

```
scan-enhancer/
├── src/
│   ├── pipeline.py              # PDFProcessingPipeline orchestrator
│   ├── processing_options.py    # ProcessingOptions dataclass
│   ├── processing_result.py     # ProcessingResult dataclass
│   ├── config.py                # Configuration constants
│   ├── exceptions.py            # Custom exception hierarchy
│   │
│   ├── mineru_processor.py      # MinerU API client
│   ├── pdf_preprocessor.py      # Optional binarization
│   ├── ocr_postprocessor.py     # OCR quality control
│   ├── utils.py                 # Helper functions
│   │
│   └── document_builder/        # Modular PDF generation package
│       ├── __init__.py          # Public API exports
│       ├── builder.py           # DocumentBuilder orchestrator
│       ├── font_manager.py      # Font registration & Cyrillic
│       ├── coordinate_utils.py  # DPI & coordinate conversion
│       ├── text_extractor.py    # Text & footnote extraction
│       ├── layout_analyzer.py   # Font sizing & layout analysis
│       └── content_renderer.py  # Images, tables, equations
│
├── fonts/
│   ├── DejaVuSans.ttf           # Bundled Cyrillic font
│   └── DejaVuSans-Bold.ttf      # Bundled bold font
│
├── docs/
│   ├── plans/                   # Planning documents
│   └── USER_GUIDE.md            # User guide (usage & settings)
│
├── app.py                       # Main Gradio application
├── requirements.txt             # Python dependencies
├── packages.txt                 # System dependencies
├── .env.example                 # Environment variables template
├── README.md                    # This file
└── ARCHITECTURE.md              # Technical documentation
```

## API Limits

| Limit | Value |
|-------|-------|
| File size | 200 MB per file |
| Pages per file | 600 pages |
| Daily quota | Varies by API plan |
| Processing timeout | 10 minutes |

*Get your API key at https://mineru.net/*

## Troubleshooting

### Fonts appear too small/large

The automatic DPI detection may be incorrect for your document. Try:
1. Check the debug output for detected DPI
2. Manually adjust font size buckets in the UI
3. For unusual paper sizes, you may need to tweak thresholds

### Poor OCR accuracy

1. Enable binarization preprocessing
2. Adjust binarization parameters (try C=20-30)
3. Ensure correct document language is selected
4. For very old documents, try increasing block size to 41-51

### Binarization not available

The binarization feature requires OpenCV. If disabled:
- Check that opencv-python is installed
- Verify pdf2image can find Poppler (system dependency)
- See dependencies section above

### Images missing in output

This is rare but can happen if:
- MinerU failed to extract images (check raw ZIP)
- Image paths in layout.json are incorrect
- File a bug with the document attached

## Contributing

Bug reports and feature requests are welcome! Please:

1. Check [ARCHITECTURE.md](ARCHITECTURE.md) for technical context
2. Search existing issues first
3. Include:
   - Steps to reproduce
   - Expected vs actual behavior
   - Sample document (if possible, remove sensitive content)

## License

See [LICENSE](LICENSE) file for details.

## Acknowledgments

- [MinerU](https://mineru.net/) for the document parsing API
- [Gradio](https://gradio.app/) for the UI framework
- [ReportLab](https://www.reportlab.com/) for PDF generation
- [OpenCV](https://opencv.org/) for image processing
- [DejaVu fonts](https://dejavu-fonts.github.io/) for Cyrillic support

---

**For detailed technical documentation, design decisions, and implementation notes, see [ARCHITECTURE.md](ARCHITECTURE.md).**
