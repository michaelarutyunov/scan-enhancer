# Fix Margin Calculation for Flow Mode

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the margin calculation in flow mode to preserve content width from original PDF, preventing text overflow when converting between Letter and A4 page sizes.

**Architecture:** The `calculate_margins_from_layout()` function currently calculates margins based on the original PDF's page size (Letter or A4), but flow mode always outputs A4. This causes content width mismatch when original is Letter. The fix calculates the original content width and computes the A4 margin needed to preserve that content width.

**Tech Stack:** Python, ReportLab, existing document_builder.py module

---

## Context

**Current behavior:**
- Original PDF: Letter (612pt wide), content width 547.6pt, margin 32.2pt
- Flow mode: A4 (595.27pt wide), margin 32.2pt → content width 530.9pt
- **Problem:** 16.7pt less space → text overflows

**Desired behavior:**
- Calculate original content width in points
- Compute A4 margin to preserve that content width
- Formula: `margin = (A4_width - original_content_width_pt) / 2`

---

### Task 1: Refactor `calculate_margins_from_layout()` to preserve content width

**Files:**
- Modify: `src/document_builder.py:1511-1559` (calculate_margins_from_layout function)

**Step 1: Read the current implementation**

Read: `src/document_builder.py` lines 1511-1559
Understand: Current algorithm finds min_left and max_right, converts each to points separately

**Step 2: Rewrite to calculate content width first**

Replace the margin calculation logic:

```python
def calculate_margins_from_layout(layout_data: Dict, dpi: float, target_page_width: float = None) -> float:
    """
    Calculate document margins from layout.json bbox data.

    Finds the leftmost and rightmost content across all pages to determine
    the content width. Then calculates the margin needed for the target page
    to preserve this content width.

    Args:
        layout_data: Parsed layout.json content with pdf_info array
        dpi: DPI for pixel-to-point conversion
        target_page_width: Target page width in points (default: A4 width)

    Returns:
        Margin in points (clamped between 0.5cm and 2cm)
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm

    pdf_info = layout_data.get("pdf_info", [])
    if not pdf_info:
        return 0.5 * cm  # Default fallback

    # Default to A4 if not specified
    if target_page_width is None:
        target_page_width = A4[0]

    # Find the content bounds (leftmost and rightmost content) across all pages
    min_left = float('inf')
    max_right = 0

    for page_data in pdf_info:
        preproc_blocks = page_data.get("preproc_blocks", [])
        for block in preproc_blocks:
            bbox = block.get("bbox", [0, 0, 100, 100])
            # bbox is [x0, y0, x1, y1] where x0 is left, x1 is right
            left = bbox[0]
            right = bbox[2]
            min_left = min(min_left, left)
            max_right = max(max_right, right)

    # Calculate original content width in pixels, then convert to points
    content_width_px = max_right - min_left
    content_width_pt = content_width_px / dpi * 72

    # Calculate margin needed to preserve content width on target page
    # margin = (target_page_width - content_width_pt) / 2
    margin = (target_page_width - content_width_pt) / 2

    # Ensure minimum margin of 0.5cm and maximum of 2cm
    margin = max(0.5 * cm, min(margin, 2 * cm))

    print(f"DEBUG: Content width preservation:")
    print(f"  Original content width: {content_width_pt:.1f}pt ({content_width_px:.0f}px)")
    print(f"  Target page width: {target_page_width:.1f}pt")
    print(f"  Calculated margin: {margin:.1f}pt")

    return margin
```

**Step 3: Verify syntax**

Run: `python3 -m py_compile src/document_builder.py`
Expected: No errors

**Step 4: Commit**

```bash
git add src/document_builder.py
git commit -m "Refactor: Calculate margins to preserve content width

Instead of calculating margins separately from left/right edges,
calculate the content width first, then compute the margin needed
to preserve that content width on the target page.

This ensures text that fit on single lines in original PDF
will also fit in flow mode, preventing overflow when converting
between Letter and A4 page sizes.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Update call sites to pass target page width

**Files:**
- Modify: `app.py:275-292` (process_pdf function)
- Modify: `app.py:415-433` (apply_corrections_and_generate_pdf function)

**Step 1: Add A4 import**

At the top of the relevant call sites, ensure A4 is available:

In `process_pdf()` around line 275:
```python
from reportlab.lib.pagesizes import A4

pdf_info = layout_data.get("pdf_info", [])
if pdf_info:
    first_page_size = pdf_info[0].get("page_size", [612, 792])
    temp_builder = DocumentBuilder.__new__(DocumentBuilder)
    dpi = temp_builder._calculate_dpi_from_page_size(first_page_size)
    calculated_margin = calculate_margins_from_layout(layout_data, dpi, target_page_width=A4[0])
else:
    calculated_margin = None
```

**Step 2: Update second call site**

In `apply_corrections_and_generate_pdf()` around line 415:
```python
from reportlab.lib.pagesizes import A4

pdf_info = layout_data.get("pdf_info", [])
if pdf_info:
    first_page_size = pdf_info[0].get("page_size", [612, 792])
    temp_builder = DocumentBuilder.__new__(DocumentBuilder)
    dpi = temp_builder._calculate_dpi_from_page_size(first_page_size)
    calculated_margin = calculate_margins_from_layout(layout_data, dpi, target_page_width=A4[0])
else:
    calculated_margin = None
```

**Step 3: Verify syntax**

Run: `python3 -m py_compile app.py`
Expected: No errors

**Step 4: Commit**

```bash
git add app.py
git commit -m "Pass target page width to margin calculation

Explicitly pass A4[0] as target_page_width to ensure
margins are calculated for the correct output page size.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Test with a Letter-sized PDF

**Step 1: Deploy to HuggingFace Spaces**

Push changes and wait for rebuild

**Step 2: Upload test PDF**

Use a Letter-sized PDF (1275×1650 pixels at 150 DPI)

**Step 3: Verify debug output**

Expected debug output:
```
DEBUG: Content width preservation:
  Original content width: 547.6pt (1141px)
  Target page width: 595.3pt
  Calculated margin: 23.8pt
```

**Step 4: Check output PDF**

Verify: Lines that fit on single lines in original also fit in flow mode output
No text should overflow

**Step 5: Commit any adjustments**

If needed, make small tweaks to margin clamping or calculation

---

## Summary

This plan refactors the margin calculation to:
1. Calculate the original content width (max_right - min_left)
2. Convert to points
3. Compute margin needed to preserve that width on A4
4. Result: Text that fit before will also fit in flow mode

**Key insight:** Preserve content width, not margin ratio.
