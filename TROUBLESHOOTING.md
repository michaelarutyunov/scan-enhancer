# Troubleshooting Guide

This document covers common errors and their solutions when using the PDF Document Cleaner.

## Common Errors

### 1. "Task not found or expire" (Repeated warnings)

**Symptoms:**
```
Warning: API returned error: task not found or expire
Warning: API returned error: task not found or expire
...
TimeoutError: Task xxx did not complete within 600 seconds
```

**Cause:** Using wrong polling endpoint for batch upload workflow.

**Solution:** This should be fixed in the latest code. The batch API requires:
- Upload endpoint: `/file-urls/batch`
- Polling endpoint: `/extract-results/batch/{batch_id}` (NOT `/extract/task/{task_id}`)

---

### 2. "Processing failed: Invalid JSON in content file"

**Symptoms:**
```
Processing failed: Invalid JSON in content file: Expecting value: line 1 column 1 (char 0)
```

**Cause:** Selecting wrong content file from ZIP. The ZIP contains multiple files:
- `full.md` - Markdown content
- `*_content_list.json` - Structured JSON
- `layout.json`, `*_model.json` - Metadata

**Solution:** Use the correct file based on requested format:
- For JSON format: Use `*_content_list.json`
- For Markdown format: Use `full.md`

---

### 3. Empty PDF (no pages)

**Symptoms:** PDF downloads but has 0 pages when opened.

**Cause:** Not downloading/extracting the actual content from MinerU's ZIP file. Only the metadata was passed to the document builder.

**Solution:**
1. Download ZIP from `full_zip_url`
2. Extract all files to temporary directory
3. Parse the actual content file (not just metadata)

---

### 4. "Processing failed: failed" (No error details)

**Symptoms:** Generic error with no useful information.

**Cause:** Error message not being extracted from API response.

**Solution:** Extract `err_msg` field from `extract_result`:
```python
error_msg = first_result.get("err_msg", "Unknown error")
```

---

### 5. Images not appearing in PDF

**Symptoms:** Text renders correctly but images are missing.

**Causes:**
- Field name mismatch: MinerU uses `img_path`, code expects `image`
- Images not extracted from ZIP file
- `temp_dir` not passed to document builder

**Solution:**
1. Extract images folder from ZIP to temp directory
2. Handle both `img_path` (MinerU) and `image` (fallback) fields
3. Pass `temp_dir` to `DocumentBuilder` and `create_pdf_from_mineru()`

---

### 6. Wrong/incorrect characters in OCR

**Symptoms:** Characters don't match the document (garbled text).

**Cause:** Language parameter not set or incorrect.

**Solution:** Specify correct language in API call:
```python
batch_data = {
    "language": "ru",  # Russian
    # or "en", "ch", "japan", "korean", etc.
}
```

---

### 7. "No content file found in ZIP"

**Symptoms:**
```
Processing failed: No content file found in ZIP
```

**Cause:** ZIP structure different than expected, or wrong file selection logic.

**Solution:** Check ZIP contents with debug logging:
```python
print(f"DEBUG: ZIP files: {zip_files}")
```

---

### 8. File size exceeded errors

**Symptoms:**
```
PDF file too large: XX.XMB. API limit is 20MB.
```

**Cause:** Outdated file size limit.

**Solution:** Update limits to current API specifications:
- File size: 200 MB (not 20 MB)
- Pages: 600 pages

---

### 9. Multipage document processing fails

**Symptoms:** Single pages work, multipage documents fail.

**Possible Causes:**
- File exceeds 200 MB limit
- More than 600 pages
- Corrupted pages in PDF
- API timeout (10 minutes)

**Solution:** Check actual error message (after fixes) for specific cause.

---

### 10. "NameError: name 'TA_CENTER' is not defined"

**Symptoms:**
```
NameError: name 'TA_CENTER' is not defined
```

**Cause:** Missing import from ReportLab.

**Solution:** Add to imports:
```python
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
```

---

## Debugging Tips

### Enable Debug Logging

The code includes `print()` statements for debugging. View logs in:
- **Local:** Console output
- **HuggingFace Spaces:** "Logs" tab in Space UI

### Check ZIP Contents

When ZIP-related errors occur, enable debug output to see file structure:
```
DEBUG: ZIP files: ['full.md', 'content_list.json', 'images/...']
DEBUG: Content file: full.md
DEBUG: Content size: 10032 bytes
```

### Verify API Response Structure

Check what the API actually returns:
```python
import json
print(json.dumps(result, indent=2))
```

### Test with Single Page First

Always test with a simple single-page document before debugging multipage issues.

---

## Getting Help

If you encounter an error not listed here:

1. **Check the logs** - Full error messages and stack traces are shown
2. **Review learnings.md** - Contains insights from debugging sessions
3. **Check MinerU API docs** - https://mineru.net/apiManage/docs
4. **Search GitHub issues** - https://github.com/opendatalab/MinerU/issues

When reporting issues, include:
- Full error message
- File size and page count
- Selected output format (JSON/Markdown)
- Selected language
