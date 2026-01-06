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
*_content_list.json              # Flattened sequential list of all items
layout.json                      # Page-level structure with bbox coordinates
*_model.json                     # Model metadata
images/*.jpg                     # Extracted images
*_origin.pdf                     # Original PDF
```

**Critical:** `content_list.json` is flattened (loses page boundaries) while `layout.json` preserves page structure!

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

## 11. ReportLab Page Flow Nuances

### The Fundamental Issue
ReportLab's **natural page flow** operates independently of logical `PageBreak` insertions. When content fills a page, ReportLab automatically flows remaining content to the next page **during the build phase**, regardless of where `PageBreak()` is placed in the story list.

### Why Page Numbers Get Pushed
1. **Sequential processing**: Items are added to story list in order
2. **Cumulative overflow**: Multiple items (paragraphs, spacers) fill the page
3. **Natural flow kicks in**: ReportLab flows excess content to next page
4. **PageBreak comes too late**: Logical PageBreak happens after natural flow already occurred

### Attempted Solutions (and why they didn't work)

#### keepWithNext Attribute
```python
para.keepWithNext = True  # Only keeps THIS paragraph with next element
```
**Problem**: Only applies to individual flowables. Earlier paragraphs in the same text block can still flow independently. Setting it on the last paragraph doesn't prevent earlier paragraphs from flowing.

#### Smart Spacing
```python
# Reduced spacers: headers 0.15cm, body text 0.05cm
```
**Problem**: Helps reduce overflow but doesn't solve the fundamental issue. With enough content, page still overflows.

#### Grouping by Page Index
```python
# Group items by page_idx, add PageBreak between pages
pages = defaultdict(list)
for item in items:
    pages[item['page_idx']].append(item)
```
**Problem**: Still adds all flowables to story list sequentially. ReportLab's flow algorithm doesn't respect our logical grouping - it flows based on available space during build.

### The Real Solution
Switch to `layout.json` which has:
- **Page-level structure**: `pdf_info` array with one entry per page
- **Positional data**: `bbox` coordinates for each element
- **Proper grouping**: Each page has `preproc_blocks` (content) and `discarded_blocks` (page numbers)

Example structure:
```json
{
  "pdf_info": [
    {
      "page_idx": 0,
      "preproc_blocks": [...],      // Content for page 0
      "discarded_blocks": [...]     // Page numbers for page 0
    },
    {
      "page_idx": 1,
      "preproc_blocks": [...],      // Content for page 1
      "discarded_blocks": [...]     // Page numbers for page 1
    }
  ]
}
```

### Key Insight
`content_list.json` is **flattened** and loses page boundaries. `layout.json` preserves the page-level structure that MinerU extracted. Using `layout.json` would allow processing each page as a unit, keeping page numbers with their correct pages.

### ReportLab Build Process
1. **Layout phase**: ReportLab calculates positions and decides where content fits
2. **Flow algorithm**: Automatically flows content to next page when space runs out
3. **Rendering phase**: Actually draws the content

Our `PageBreak()` insertions happen during story construction, but ReportLab's flow algorithm makes final decisions during the layout phase.

### Content Overflow Example
Page 0 contains:
- 7 bold headers (text_level=1)
- 31 paragraphs (from splitting multi-proverb items by `\n`)
- 14 spacers × 0.2cm = 2.8cm of blank space
- Page number "62" at the end

Even with reduced spacers (1.4cm total), the cumulative content height can exceed available page space, causing ReportLab to flow the page number to page 1.

### Discarded Items
MinerU marks page numbers as `type="discarded"` with the page number as text content (e.g., "62", "63"). These appear at the end of each page's content in the sequence, and their `bbox` coordinates show they're positioned at the bottom of the page.

## 12. Solution: Exact Positioning with layout.json

### The Fix
Instead of using `content_list.json` (flattened) with ReportLab's flowable-based rendering, use `layout.json` with **canvas-based absolute positioning**:

1. **Switch data source**: `layout.json` has explicit page-level structure with `pdf_info` array
2. **Use canvas rendering**: Replace `SimpleDocTemplate` with `pdfgen.Canvas` for direct drawing
3. **Exact coordinates**: Use `Paragraph.drawOn(canvas, x, y)` to place text at bbox positions

### Coordinate Conversion
MinerU bbox uses top-left origin; ReportLab uses bottom-left:
```python
def _convert_bbox(bbox, page_height):
    x1, y1, x2, y2 = bbox
    width = x2 - x1
    height = y2 - y1
    # ReportLab y = page_height - MinerU y2 (bottom of block)
    rl_y = page_height - y2
    return x1, rl_y, width, height
```

### Implementation Files
- **document_builder.py**: Added `add_from_layout_json()` method with canvas rendering
- **mineru_processor.py**: Now returns `layout_data` in result when `layout.json` exists
- **app.py**: Uses `create_pdf_from_layout()` when `layout_data` is available

### Key Methods Added
- `add_from_layout_json(layout_data)`: Main entry point for layout-based rendering
- `_render_block(block, page_height)`: Renders individual blocks at exact positions
- `_convert_bbox(bbox, page_height)`: Converts MinerU to ReportLab coordinates
- `_render_text_block()`: Renders text using `Paragraph.drawOn()`
- `_render_image_block()`: Renders images using `canvas.drawImage()`
- `_extract_text_from_block()`: Extracts text from lines/spans structure

## 13. Deployment and Verification

### Debugging the Layout Method
Added debug logging to `app.py` to trace which rendering path is used:
```python
print("=" * 80)
print("DEBUG: PDF RENDERING DECISION")
print(f"DEBUG: layout_data is None: {layout_data is None}")
print(f"DEBUG: layout_data type: {type(layout_data)}")
if layout_data:
    print(f"DEBUG: pdf_info count: {len(layout_data.get('pdf_info', []))}")
```

This confirmed the layout method was working after deployment to HuggingFace Spaces.

### Results Achieved
✅ **Page alignment fixed**: Page "62" now appears at bottom of page 1 (not top of page 2)
✅ **Page breaks correct**: Page 2 starts with "Холодной осенью..." (matches original)
✅ **Layout-based rendering active**: Using exact bbox coordinates from layout.json

## 14. Image Rendering in Layout Blocks

### The Problem
Images weren't rendering even though:
- Image file exists in `interim/images/8e7034b3420ebc113675f3f69d23572e97a6ca30e0b27e3f38f4fb2c0e040cb4.jpg`
- layout.json contains image block with correct path
- Block type is "image"

### Root Cause
Image blocks have **nested structure** different from text blocks:
```json
{
  "type": "image",
  "bbox": [...],
  "blocks": [                    // ← Extra nesting!
    {
      "type": "image_body",
      "lines": [
        {
          "spans": [
            {
              "type": "image",
              "image_path": "8e7034...jpg"  // ← Path is here
            }
          ]
        }
      ]
    }
  ]
}
```

Original code only checked `block.get("lines")` directly, missing the nested `blocks[]` array.

### The Fix
Updated `_render_image_block()` to check both structures:
1. **Try nested first**: `blocks[] → lines[] → spans[] → image_path`
2. **Fallback to direct**: `lines[] → spans[] → image_path`

```python
# Try nested blocks structure first (for image blocks)
blocks = block.get("blocks", [])
if blocks:
    for sub_block in blocks:
        lines = sub_block.get("lines", [])
        # ... find image_path in spans
```

### Lesson Learned
MinerU's layout.json structure varies by block type. Always inspect the actual JSON structure when implementing parsers, don't assume uniform structure across all block types.
