# Architecture Documentation

This document describes the system architecture, data flow, and design decisions for the PDF Document Cleaner.

## System Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Gradio     │     │   MinerU     │     │    MinerU    │     │   Document   │
│     UI       │────▶│   Processor  │────▶│     API      │────▶│   Builder    │
│  (app.py)    │     │(mineru_      │     │  (External)  │     │(document_    │
│              │     │ processor.py)│     │              │     │  builder.py) │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │                                                                 │
       │                            ┌──────────────┐                        │
       └───────────────────────────▶│  Output PDF  │◀───────────────────────┘
                                    │  (.pdf file)  │
                                    └──────────────┘
```

## Component Architecture

### 1. Gradio UI (`app.py`)

**Responsibilities:**
- User interface for file upload and settings
- Input validation (file type, size)
- Progress tracking
- Error display

**Key Functions:**
- `process_pdf()`: Main processing pipeline

**Dependencies:**
- `MinerUAPIProcessor` - API communication
- `create_pdf_from_mineru()` - PDF generation
- `validate_pdf_path()`, `check_file_size_limit()` - Validation

---

### 2. MinerU API Processor (`src/mineru_processor.py`)

**Responsibilities:**
- Communicate with MinerU batch API
- Handle file upload workflow
- Poll for task completion
- Download and extract ZIP results

**Key Functions:**
- `submit_task()`: Initiate batch upload
- `poll_task()`: Wait for completion
- `get_task_status()`: Check task state
- `process_pdf()`: Complete workflow

**Data Structures:**
```python
# Request format (batch upload)
{
    "model_version": "vlm",
    "language": "ru",
    "files": [{"name": "file.pdf", "data_id": "file"}]
}

# Response format (batch result)
{
    "code": 0,
    "data": {
        "batch_id": "uuid",
        "extract_result": [{
            "state": "done",  # or: waiting-file, pending, running, failed, converting
            "full_zip_url": "https://...",
            "err_msg": ""
        }]
    }
}
```

---

### 3. Document Builder (`src/document_builder.py`)

**Responsibilities:**
- Parse MinerU JSON/Markdown output
- Render PDF with ReportLab
- Handle fonts, images, tables, equations

**Key Classes:**
- `DocumentBuilder`: Main PDF building class

**Key Functions:**
- `add_from_mineru_json()`: Parse structured content
- `add_from_mineru_markdown()`: Parse markdown
- `_add_image()`, `_add_table()`, `_add_equation()`: Render elements
- `finalize()`: Save PDF

**Content Types Handled:**
```python
# MinerU JSON content items
{
    "type": "text",          # Plain text paragraph
    "text": "Content here"
}

{
    "type": "image",         # Image with caption
    "img_path": "images/xxx.jpg",
    "image_caption": ["Caption text"]
}

{
    "type": "table",         # Table data
    "content": [[row1_col1, row1_col2], ...]
}

{
    "type": "equation",      # Math equation
    "text": "E = mc^2"
}

{
    "type": "header",        # Section heading
    "text": "Chapter Title"
}
```

---

### 4. Utilities (`src/utils.py`)

**Responsibilities:**
- File validation
- Filename sanitization
- File size formatting

**Key Functions:**
- `validate_pdf_path()`: Check file extension
- `check_file_size_limit()`: Verify size constraints
- `clean_filename()`: Sanitize output filenames

---

## Data Flow

### Complete Request Flow

```
1. USER UPLOAD
   ├── Gradio receives file
   ├── Validate PDF extension
   └── Check file size (< 200MB)

2. SUBMIT TO MINERU
   ├── POST /file-urls/batch
   │   └── Get presigned upload URL + batch_id
   ├── PUT file to presigned URL
   └── Return batch_id for polling

3. POLL FOR COMPLETION
   ├── GET /extract-results/batch/{batch_id}
   ├── Check state (waiting-file → pending → running → done)
   └── Repeat every 5 seconds (max 600 seconds)

4. DOWNLOAD RESULTS
   ├── GET full_zip_url (ZIP file contains:)
   │   ├── full.md or *_content_list.json (content)
   │   ├── layout.json (metadata)
   │   ├── *_model.json (model info)
   │   ├── images/*.jpg (extracted images)
   │   └── *_origin.pdf (original)
   ├── Extract to temp directory
   └── Select correct content file based on format

5. BUILD PDF
   ├── Parse content (JSON or Markdown)
   ├── Download/load images from temp_dir
   ├── Render with ReportLab:
   │   ├── Headers → Heading style
   │   ├── Text → Body style
   │   ├── Images → Scaled and placed
   │   ├── Tables → Styled with borders
   │   └── Equations → Monospace text
   └── Save to output path

6. RETURN TO USER
   └── Gradio serves PDF for download
```

---

## Design Decisions

### 1. Batch Upload Workflow

**Why:** Single-file endpoint only accepts URLs, not file uploads.

**Implication:** Must use two-step process:
1. Get presigned URL from `/file-urls/batch`
2. Upload file via PUT to presigned URL
3. Poll `/extract-results/batch/{batch_id}` for results

### 2. ZIP File Extraction

**Why:** MinerU returns content + images in a ZIP file.

**Implication:** Must:
- Extract entire ZIP to temp directory
- Preserve `images/` folder structure
- Select correct content file based on format

### 3. Temporary Directory Management

**Why:** Images need to be accessible during PDF building.

**Implication:**
- Pass `temp_dir` through entire chain
- `DocumentBuilder` needs access to image files
- Cleanup happens after PDF generation

### 4. Format Detection

**Why:** ZIP contains multiple files (`.md`, `.json`, metadata).

**Implication:** Smart file selection:
- JSON format → Look for `*_content_list.json`
- Markdown format → Look for `full.md`
- Fallback → First non-image file

### 5. Font Handling

**Why:** Cyrillic characters require specific fonts.

**Implication:**
- Try multiple font paths (DejaVu Sans, Liberation Sans, Arial)
- Fall back to Helvetica if none found
- Per-page font registration

---

## Error Handling Strategy

### 1. API Errors

```python
# Extract meaningful error from response
error_msg = first_result.get("err_msg", "Unknown error")
return {
    "status": "failed",
    "result": {"error": error_msg}
}
```

### 2. File Not Found

```python
# Check file exists before processing
if not pdf_file.exists():
    raise FileNotFoundError(f"PDF file not found: {pdf_path}")
```

### 3. Size Limits

```python
# Check before uploading
if file_size_mb > 200:
    raise ValueError(f"PDF file too large: {file_size_mb:.1f}MB")
```

### 4. Timeout

```python
# Poll with timeout
if time.time() - start_time > max_wait_seconds:
    raise TimeoutError(f"Task {task_id} did not complete in time")
```

---

## State Management

### Processing States

| State | Description | Action |
|-------|-------------|--------|
| `waiting-file` | File uploaded, waiting to process | Continue polling |
| `pending` | Queued for processing | Continue polling |
| `running` | Currently processing | Continue polling |
| `converting` | Format conversion in progress | Continue polling |
| `done` | Complete | Download ZIP |
| `failed` | Error occurred | Show error message |

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MINERU_API_KEY` | Yes | MinerU API authentication token |

### API Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_version` | `vlm` | MinerU model version |
| `language` | `ru` | Document language for OCR |
| `output_format` | `json` | JSON or Markdown output |

---

## Performance Considerations

### File Size Limits

- **Upload:** 200 MB per file
- **Processing:** 10 minute timeout
- **Pages:** 600 pages max

### Optimization

- **Parallel requests:** Not supported (sequential processing)
- **Caching:** Not implemented (fresh processing each time)
- **Polling interval:** 5 seconds (balances responsiveness vs API load)

---

## Security

### API Key Management

- Stored in environment variable (`MINERU_API_KEY`)
- Never logged or exposed
- Passed via `Authorization: Bearer {token}` header

### File Handling

- Temporary files cleaned up after processing
- No persistent storage of user uploads
- Input validation on file type and size

---

## Dependencies

```
gradio>=6.0.0          # UI framework
reportlab>=4.0.0      # PDF generation
requests>=2.31.0      # HTTP client
python-dotenv>=1.0.0  # Environment config
Pillow>=10.0.0        # Image processing
```

---

## Future Improvements

### Potential Enhancements

1. **Batch Processing**
   - Process multiple files in parallel
   - Progress tracking for multiple files

2. **Caching**
   - Cache results for same file
   - Reduce API calls

3. **Additional Formats**
   - DOCX output
   - HTML output
   - LaTeX rendering for equations

4. **Enhanced Error Recovery**
   - Retry failed tasks
   - Partial result extraction
   - Graceful degradation

5. **Performance**
   - Streaming PDF generation
   - Incremental rendering
   - Progress indicators for long documents
