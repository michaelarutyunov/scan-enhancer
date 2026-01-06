# Key Learnings from Debugging Session

## 1. MinerU Batch API Workflow
The batch upload workflow has specific requirements:
- **Two-step upload**: Get presigned URL → Upload file via PUT
- **Different polling endpoint**: `/extract-results/batch/{batch_id}` NOT `/extract/task/{task_id}`
- **Returns ZIP file**: Contains actual content + images in a structured format
- **State values**: `done`, `waiting-file`, `pending`, `running`, `failed`, `converting`

## 2. ZIP File Structure
MinerU returns multiple files in the ZIP:
```
full.md                          # Markdown content
*_content_list.json              # Structured JSON with layout
layout.json                      # Layout metadata
*_model.json                     # Model metadata
images/*.jpg                     # Extracted images
*_origin.pdf                     # Original PDF
```

**Critical:** Must select the right file based on requested format!

## 3. Content Format Mismatch
The document builder expected:
```python
{"content": [{"type": "text", ...}, ...]}
```
But MinerU returns a **list directly**:
```python
[{"type": "text", ...}, ...]
```

## 4. Field Name Differences
MinerU uses different field names than expected:
- `img_path` vs `image`
- `image_caption` vs `caption`
- `header` type elements need special handling

## 5. Error Reporting Matters
**Before:** `"Processing failed: failed"`
**After:** Shows actual error with context (ZIP contents, file selected, JSON parse errors)

Better error messages = faster debugging

## 6. Debugging Techniques
- Add `print()` statements to trace data flow
- Show ZIP file contents to understand structure
- Display first N bytes of content to diagnose format issues
- Use file extensions to determine parsing strategy

## 7. API Parameter Defaults
- Added `language` parameter (default "ru" for Russian)
- This significantly improves OCR accuracy for specific languages

## 8. HuggingFace Spaces Workflow
- Push to GitHub → Auto-sync to HF Spaces
- Logs visible in HF Space "Logs" tab
- No need to manually redeploy

## 9. Common Multipage PDF Failures
- File size > 200MB
- Page count > 600 pages
- Corrupted pages
- API timeout (600 second limit)

## 10. Data Flow Chain
```
Gradio Upload → Validate → Submit to MinerU → Poll → Download ZIP → Extract → Parse → Build PDF
```

Each step can fail; need proper error handling at each stage.
