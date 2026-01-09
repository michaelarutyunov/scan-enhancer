# PDF Document Cleaner - User Guide

Complete guide to using the PDF Document Cleaner application.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Understanding the Process](#understanding-the-process)
3. [Settings Explained](#settings-explained)
4. [Common Scenarios](#common-scenarios)
5. [Troubleshooting](#troubleshooting)
6. [Tips & Best Practices](#tips--best-practices)

---

## Quick Start

### Basic Workflow (3 Steps)

1. **Upload your PDF** - Click "Upload Scanned PDF Document"
2. **Select language** - Choose the document's language (Russian, English, etc.)
3. **Click Process** - Press "🔍 Process the document"

That's it! The app will use default settings optimized for most scanned documents.

### When to Adjust Settings

You may need to adjust settings if:
- Text appears overlapping or too large/small in output
- OCR quality is poor (enable binarization)
- You want to review and fix OCR errors manually
- You prefer reflowed text instead of exact layout preservation

---

## Understanding the Process

### What Happens When You Click "Process"

```
1. VALIDATION (1-2 seconds)
   ✓ Checks PDF is valid and under 200MB

2. BINARIZATION (if enabled, 10-30 seconds)
   ✓ Cleans up noise and improves scan quality
   ✓ Creates cleaner image for better OCR

3. MINERU API PROCESSING (30-120 seconds)
   ✓ Sends to MinerU cloud for OCR
   ✓ Extracts text, layout, images, tables
   ✓ Returns structured JSON data

4. OCR QUALITY CHECK (if enabled, instant)
   ✓ Finds low-confidence OCR results
   ✓ Shows editable table for manual correction
   ✓ Waits for you to fix errors

5. PDF GENERATION (5-15 seconds)
   ✓ Builds clean searchable PDF
   ✓ Applies proper fonts and sizing
   ✓ Embeds images and tables

6. DOWNLOAD
   ✓ Final PDF: <filename>_final_<timestamp>.pdf
   ✓ Optional: Binarized PDF (if preprocessing enabled)
   ✓ Optional: Raw MinerU ZIP (if diagnostics enabled)
```

### PDF Rendering Modes

The app offers two distinct rendering modes for generating the output PDF:

#### Exact Layout Mode (Default)
**How to select:** Choose "Exact Layout - Preserves original positioning and spacing"

**What it does:**
- Preserves exact X/Y coordinates from the scanned document
- Uses original document margins (may be uneven)
- Analyzes line heights to determine appropriate font sizes
- Font sizes are customizable via Font Size Buckets sliders
- Original page layout preserved exactly

**Best for:** Documents with specific layouts, tables, diagrams, forms, certificates

**Font Customization:** Fully customizable - adjust the 5 font bucket thresholds to control how line heights map to font sizes (8pt through 14pt)

---

#### Flow Layout Mode
**How to select:** Choose "Flow Layout - Reformats with consistent margins"

**What it does:**
- Reformats content with dynamic spacing
- Calculates consistent margins (0.5-2cm) from layout analysis
- Uses standardized fonts: titles (12pt bold), body (10.5pt), footnotes (8pt)
- Dynamic spacing adjustment to fit content on pages

**Best for:** Text-heavy documents, books, articles, long documents you'll read on screen

**Font Customization:** Limited - uses standard typography (Font Size Buckets are hidden and ignored)

---

#### Choosing the Right Mode

**💡 Tip:** Try **Exact Layout** first. If margins look uneven or fonts are inconsistent, switch to **Flow Layout**.

| Feature | Exact Layout | Flow Layout |
|---------|-------------|-------------|
| **Positioning** | Preserves exact X/Y coordinates | Reformats with dynamic spacing |
| **Margins** | Uses original (may vary) | Consistent (0.5-2cm) |
| **Font Sizing** | Customizable buckets | Standard sizes |
| **Use Case** | Specific layouts, tables | Text-heavy documents |

---

## Settings Explained

### Document Language

**Location:** First dropdown at top of settings

**What it does:** Tells MinerU which language model to use for OCR

**Options:**
- Russian (ru) - Default
- English (en)
- Chinese (ch)
- Japanese (japan)
- Korean (korean)
- German (german)
- French (french)
- Spanish (spanish)

**When to adjust:**
- Always set this to match your document's primary language
- OCR accuracy drops significantly with wrong language
- For mixed-language documents, choose the predominant language

**Example:**
- English textbook → Select "English"
- Russian legal document → Select "Russian"

---

### Pre-process PDF with Binarization

**Location:** Checkbox + two sliders in "De-noising" section

**What it does:** Converts scanned image to pure black/white before OCR

**Default:** ✓ Enabled (block size: 31, C constant: 25)

**When to enable:**
- ✓ Scanned documents with background noise
- ✓ Photocopies with speckles or dots
- ✓ Low-contrast scans
- ✓ Uneven lighting or shadows
- ☐ High-quality digital PDFs (already clean)

**How it works:**
1. Converts PDF pages to images
2. Analyzes each pixel's neighborhood
3. Decides: black or white based on local contrast
4. Removes tiny noise specks
5. Rebuilds PDF from cleaned images

#### Block Size (11-51, must be odd)

**What it controls:** Size of neighborhood analyzed for each pixel

**Lower values (11-21):**
- More detail preserved
- May keep more noise
- Better for high-resolution scans
- Use for: Very clean documents with fine print

**Default (31):**
- Balanced approach
- Good for most documents
- Recommended starting point

**Higher values (41-51):**
- Smoother results
- More aggressive noise removal
- Better for low-contrast scans
- Use for: Old photocopies, faded documents

**Example:**
- Modern scanner, clear text → Try 21-31
- Old photocopy with noise → Try 41-51

#### C Constant (0-51)

**What it controls:** Threshold adjustment - how much to favor black vs white

**Lower values (5-15):**
- More white pixels (higher threshold)
- Cleaner background
- May lose thin lines
- Use for: Documents with heavy background

**Default (25):**
- Balanced black/white
- Good for typical documents
- Recommended starting point

**Higher values (35-51):**
- More black pixels (lower threshold)
- Preserves detail better
- May keep more noise
- Use for: Faded text, light scans

**Visual guide:**
```
C=10: ░░░TEXT░░░  (very clean, may lose detail)
C=25: ▒▒▒TEXT▒▒▒  (balanced, default)
C=40: ▓▓▓TEXT▓▓▓  (preserve detail, may keep noise)
```

**Common adjustments:**
- Too much noise in output? → Increase block size to 41
- Text looks too thin? → Increase C to 30-35
- Background not clean? → Decrease C to 15-20

---

### Keep Original Page Margins

**Location:** Checkbox in "Additional Settings"

**Default:** ✓ Checked (exact layout mode)

**What it does:**
- ✓ Checked = Canvas-based exact positioning
- ☐ Unchecked = Flow-based reflowing with custom styling

**Exact Layout Mode (Checked):**
- Preserves pixel-perfect positioning
- Original font sizes maintained
- Page layout identical to source
- Best for: Forms, tables, official documents

**Flow-Based Mode (Unchecked):**
- Reformats for readability
- Titles: 12pt bold, centered
- Body: 10.5pt, justified
- Dynamic spacing adjustment
- Best for: Reading-heavy documents

**When to use Flow Mode:**
- Long documents you'll read on screen
- Want consistent, modern styling
- Don't need exact layout preservation
- Original has weird spacing

---

### Download Raw MinerU Output

**Location:** Checkbox in "Additional Settings"

**Default:** ✓ Checked

**What it does:** Downloads ZIP with MinerU's original output

**ZIP Contents:**
- `layout.json` - Bounding box coordinates
- `content_list.json` - Structured content
- `full.md` - Markdown version
- `images/` - Extracted images
- `*_origin.pdf` - Your original file

**When to enable:**
- ✓ Debugging font size issues
- ✓ Want to see raw OCR data
- ✓ Need extracted images separately
- ☐ Just want final PDF (save space)

---

### Enable Formula Detection

**Location:** Checkbox in "Additional Settings"

**Default:** ☐ Unchecked

**What it does:** Tells MinerU to detect mathematical formulas

**When to enable:**
- ✓ Math textbooks
- ✓ Scientific papers with equations
- ✓ Technical manuals with formulas
- ☐ Regular text documents (slower processing)

**Note:** Formulas are rendered as monospace text in output PDF

---

### Enable Footnote Detection

**Location:** Checkbox in "Additional Settings"

**Default:** ☐ Unchecked

**What it does:** Detects footnotes by position and content pattern

**Detection criteria (both required):**
1. Block in bottom 20% of page
2. First line starts with: `digit + space + letter` (e.g., "1 Footnote text")

**When to enable:**
- ✓ Academic papers with footnotes
- ✓ Legal documents with citations
- ☐ Documents without footnotes (false positives)

**Note:** Detected footnotes are styled smaller (8pt) and left-aligned

---

### Manual Correction of Low-Confidence Items

**Location:** Checkbox + slider in "OCR Quality Control" section

**Default:** ✓ Enabled, cutoff: 0.9 (90%)

**What it does:** Pauses processing to let you review and fix OCR errors

**Workflow:**
1. OCR completes
2. App finds all text with confidence < cutoff
3. Shows editable table with Page, Score, Type, Original, Correction
4. You edit "Correction" column
5. Click "Apply Corrections"
6. Final PDF generated with your fixes

**When to enable:**
- ✓ Important documents (contracts, legal)
- ✓ Want to ensure 100% accuracy
- ✓ Have time to review
- ☐ Quick processing needed

#### Quality Cut-off (0.0-1.0)

**What it controls:** Confidence threshold for flagging items

**Lower values (0.5-0.8):**
- More items flagged
- More work to review
- Catches more potential errors
- Use for: Very important documents

**Default (0.9):**
- Balanced approach
- Flags genuinely questionable text
- Reasonable review workload

**Higher values (0.95-0.99):**
- Fewer items flagged
- Less work to review
- May miss some errors
- Use for: Quick processing

**How to use the correction table:**
- **Original:** Text as OCR read it (read-only)
- **Correction:** Your fixed version (editable)
- **Leave blank to delete** the span entirely
- **No changes needed?** Leave as-is

---

### Line Calibration

**Location:** Checkbox + two sliders in "OCR Quality Control"

**Default:** ☐ Unchecked (opt-in feature)

**What it does:** Fixes overlapping text by reducing line heights

**When to enable:**
- Lines touching or overlapping in output
- Text appears too cramped vertically
- Some fonts too large for content

**How it works:**
1. Analyzes median line height per block
2. If height > Target Line Height → reduce proportionally
3. Optionally checks overlap severity
4. Smaller heights → smaller font bucket → readable text

#### Target Line Height (0-50 pixels)

**What it controls:** Maximum acceptable line height before fixing

**Lower values (20-30 px):**
- More aggressive fixing
- Fixes more blocks
- Smaller fonts overall
- Use for: Very cramped originals

**Default (34 px):**
- Conservative approach
- Only fixes obviously large text
- Recommended starting point

**Higher values (40-50 px):**
- Very conservative
- Only fixes extreme cases
- Preserves original sizing more

**When to adjust:**
- Still overlapping after default? → Lower to 28-30
- Too much changed? → Raise to 40

#### Overlap Threshold (-50 to 0 pixels)

**What it controls:** Secondary filter based on actual overlap severity

**Default (-10 px):**
- Only fixes if lines overlap by ≥10 pixels
- More selective
- Prevents over-correction

**Set to 0:**
- Disables this filter entirely
- Uses only Target Line Height
- More aggressive

**More negative (-20 to -50):**
- Only fixes severe overlaps
- Very selective
- May miss some issues

**Best practice:**
- Start with default (-10 px)
- If output still has overlap → Set to 0
- If over-corrected → Set to -20

---

### Font Size Buckets

**Location:** 5 sliders at bottom of settings

**What they do:** Map line heights to font sizes

**How it works:**
```
Line height from scan → Convert to points → Map to font size bucket

Example:
Scanned at 150 DPI
Line height: 43 pixels
Convert: 43 / 150 × 72 = 20.6 points
Map: 20.6 < 22.0 threshold → Use 10pt font
```

**Bucket thresholds:**

| Slider | Default | Meaning |
|--------|---------|---------|
| 8pt → 9pt | 17.0pt | Line heights < 17pt use 8pt font |
| 9pt → 10pt | 22.0pt | 17-22pt line heights use 9pt font |
| 10pt → 11pt | 28.0pt | 22-28pt line heights use 10pt font |
| 11pt → 12pt | 30.0pt | 28-30pt line heights use 11pt font |
| 12pt → 14pt | 32.0pt | >32pt line heights use 14pt font |

**When to adjust:**
- All fonts too small → Raise all thresholds by 2-4pt
- All fonts too large → Lower all thresholds by 2-4pt
- Only body text wrong → Adjust 10pt→11pt threshold
- Only titles wrong → Adjust 12pt→14pt threshold

**Example adjustment:**
```
Problem: Body text (should be 11pt) is 10pt
Current: 10pt→11pt threshold at 28.0pt
Solution: Lower threshold to 26.0pt
Result: More text maps to 11pt bucket
```

---

## Common Scenarios

### Scenario 1: Simple Scanned Book

**Goal:** Quick, readable output

**Settings:**
- Pre-process PDF: ✓ (use defaults)
- Keep original margins: ☐ (flow mode)
- Manual correction: ☐ (disable for speed)
- Line calibration: ☐ (not needed for books)
- Language: Match book language

**Expected time:** 1-2 minutes

---

### Scenario 2: Important Legal Document

**Goal:** 100% accuracy, exact layout

**Settings:**
- Pre-process PDF: ✓ (clean scan)
- Keep original margins: ✓ (exact layout)
- Manual correction: ✓ (review everything)
- Quality cutoff: 0.95 (catch more errors)
- Download raw output: ✓ (for records)
- Language: Match document language

**Expected time:** 3-5 minutes + manual review

---

### Scenario 3: Old Photocopy with Noise

**Goal:** Clean up poor quality scan

**Settings:**
- Pre-process PDF: ✓
- Block size: 41-51 (aggressive cleanup)
- C constant: 20 (cleaner background)
- Keep original margins: ☐ (flow for readability)
- Manual correction: ✓ (OCR likely imperfect)
- Language: Match document

**Expected time:** 2-4 minutes + review

---

### Scenario 4: Math Textbook

**Goal:** Preserve equations and formatting

**Settings:**
- Pre-process PDF: ✓ (if scanned)
- Enable formula detection: ✓
- Keep original margins: ✓ (exact layout)
- Manual correction: ✓ (math is precise)
- Language: Match textbook language

**Expected time:** 2-4 minutes + review

---

### Scenario 5: Text Overlapping in Output

**Goal:** Fix cramped, overlapping lines

**Settings:**
- Enable line calibration: ✓
- Target line height: 34px (default)
- Overlap threshold: -10px (default)
- If still overlapping:
  - Lower target to 28-30px
  - Or set threshold to 0

**Expected time:** Same as normal + calibration step

---

## Troubleshooting

### Problem: Fonts are too small

**Likely cause:** DPI detection incorrect or bucket thresholds too high

**Solutions:**
1. Check debug output for detected DPI
2. Lower all font bucket thresholds by 3-4 points
3. Example: Change "10pt→11pt" from 28.0 to 24.0

---

### Problem: Fonts are too large

**Likely cause:** Bucket thresholds too low

**Solutions:**
1. Raise all font bucket thresholds by 3-4 points
2. Or enable line calibration to reduce line heights

---

### Problem: Text is overlapping

**Likely cause:** Original scan has tight line spacing

**Solutions:**
1. Enable "Line Calibration"
2. Start with defaults (target: 34px, threshold: -10px)
3. If still overlapping, lower target to 28-30px
4. Or set threshold to 0 for more aggressive fixing

---

### Problem: Poor OCR accuracy

**Likely causes:**
- Wrong language selected
- Binarization disabled on noisy scan
- Binarization too aggressive

**Solutions:**
1. Verify language setting matches document
2. Enable "Pre-process PDF" if disabled
3. Try different binarization parameters:
   - More noise? Increase block size to 41-51
   - Text too thin? Increase C constant to 30-35
   - Background too gray? Decrease C to 15-20

---

### Problem: Too many items to correct

**Likely cause:** Quality cutoff too low

**Solutions:**
1. Raise cutoff from 0.9 to 0.95
2. Or disable manual correction for quicker results
3. For critical documents, consider improving source scan quality first

---

### Problem: Images missing in output

**Rare issue, possible causes:**
- MinerU extraction failed
- Image paths incorrect

**Solutions:**
1. Enable "Download raw MinerU output"
2. Check if images exist in ZIP's `images/` folder
3. If images in ZIP but not in PDF, report as bug

---

### Problem: Processing very slow

**Likely causes:**
- Large file size (50-200MB)
- Many pages (200-600)
- MinerU API overload

**Solutions:**
1. Check file size (displayed in UI tip)
2. Split large PDFs into smaller chunks
3. Try again during off-peak hours
4. Disable binarization to save 10-30 seconds

---

## Tips & Best Practices

### Before You Start

✓ **Check file size** - Maximum 200MB, displayed in UI tip
✓ **Verify orientation** - Portrait works best
✓ **Select correct language** - Critical for OCR accuracy
✓ **Clean physical scan** - Garbage in = garbage out

### For Best Results

✓ **Use binarization** for scanned documents (default: on)
✓ **Disable binarization** for digital PDFs (already clean)
✓ **Enable manual correction** for important documents
✓ **Start with defaults** - only adjust if output has issues
✓ **Download raw output** first time - helps debug issues

### When Adjusting Settings

✓ **Change one thing at a time** - easier to identify what helps
✓ **Note what works** - same settings likely work for similar documents
✓ **Start conservative** - can always process again with different settings

### Understanding Limitations

✗ Scanned handwriting - OCR works on printed text only
✗ Very complex layouts - may need manual touch-up
✗ Multiple columns - may not preserve perfectly in flow mode
✗ Very faint text - even binarization has limits

### File Management

✓ **Output naming:** `<original>_final_<timestamp>.pdf`
✓ **Example:** `extract_2.pdf` → `extract_2_final_20260109_143052.pdf`
✓ **Note:** Timestamp prevents overwrites if you reprocess

---

## Need More Help?

- **Technical details:** See [ARCHITECTURE.md](../ARCHITECTURE.md)
- **Setup instructions:** See [README.md](../README.md)
- **Bug reports:** File an issue on GitHub
- **MinerU API:** https://mineru.net/

---

**Last updated:** January 2026
