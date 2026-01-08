"""Document Builder Module

Renders MinerU JSON/Markdown output to PDF document.
"""
import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.pdfgen import canvas as pdfcanvas
from typing import Dict, List, Any, Tuple
import os
import tempfile


class DocumentBuilder:
    """Build PDF document from MinerU structured output."""

    def __init__(self, output_path: str, temp_dir: str = None, use_consistent_margins: bool = False, font_buckets: dict = None, enable_footnote_detection: bool = False):
        """
        Initialize document builder.

        Args:
            output_path: Where to save the final PDF
            temp_dir: Optional temporary directory containing extracted images
            use_consistent_margins: If True, use 1cm margins; otherwise use 2cm default
            font_buckets: Optional dict with custom bbox height thresholds for font sizing
                         Keys: "bucket_9", "bucket_10", "bucket_11", "bucket_12", "bucket_14"
            enable_footnote_detection: If True, detect footnotes by position and content pattern
        """
        self.output_path = output_path
        self.temp_dir = temp_dir
        self.use_consistent_margins = use_consistent_margins
        self.enable_footnote_detection = enable_footnote_detection
        self.story = []
        self.styles = getSampleStyleSheet()
        self.temp_files = []

        # Font bucket thresholds (default values in POINTS, not pixels!)
        # These thresholds work with bbox heights converted to points
        # TITLES are fixed at 12pt, DISCARDED at 8pt
        # TEXT only: 18-27pt range → 10-12pt fonts
        # 9pt font → ~11pt line height, 10pt → ~12pt, 11pt → ~13pt, 12pt → ~14pt, 14pt → ~17pt
        self.font_bucket_9 = font_buckets.get("bucket_9", 17.0) if font_buckets else 17.0
        self.font_bucket_10 = font_buckets.get("bucket_10", 22.0) if font_buckets else 22.0
        self.font_bucket_11 = font_buckets.get("bucket_11", 28.0) if font_buckets else 28.0
        self.font_bucket_12 = font_buckets.get("bucket_12", 30.0) if font_buckets else 30.0
        self.font_bucket_14 = font_buckets.get("bucket_14", 32.0) if font_buckets else 32.0

        # DEBUG: Print font bucket thresholds
        print("=" * 80)
        print("DEBUG: Font bucket thresholds being used (in points):")
        print(f"  TITLES: fixed at 12pt")
        print(f"  DISCARDED: fixed at 8pt")
        print(f"  TEXT thresholds:")
        print(f"    bucket_9 (< {self.font_bucket_9}) → 9pt")
        print(f"    bucket_10 (< {self.font_bucket_10}) → 10pt")
        print(f"    bucket_11 (< {self.font_bucket_11}) → 11pt")
        print(f"    bucket_12 (< {self.font_bucket_12}) → 12pt")
        print(f"    bucket_14 (< {self.font_bucket_14}) → 13pt")
        print(f"    ≥ {self.font_bucket_14} → 14pt")
        print("=" * 80)

        # Setup fonts for Cyrillic support
        self._setup_fonts()

    def _setup_fonts(self):
        """
        Register fonts that support Cyrillic characters.

        Tries multiple font paths in order of preference:
        1. Bundled DejaVu Sans (in fonts/ directory)
        2. DejaVu Sans (Linux system paths)
        3. Liberation Sans (Linux)
        4. Arial Unicode (macOS)
        5. Arial (Windows)

        Falls back to Helvetica if no fonts are found.
        WARNING: Helvetica does NOT support Cyrillic characters!

        Also registers bold variant if available.
        """
        # Bundled font path (highest priority)
        bundled_font = os.path.join(os.path.dirname(__file__), '..', 'fonts', 'DejaVuSans.ttf')
        bundled_bold_font = os.path.join(os.path.dirname(__file__), '..', 'fonts', 'DejaVuSans-Bold.ttf')

        # Try to register DejaVu Sans (common on Linux)
        font_paths = [
            bundled_font,  # Bundled font (failsafe)
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',  # macOS
            'C:\\Windows\\Fonts\\arial.ttf',  # Windows
        ]

        # Bold font paths
        bold_font_paths = [
            bundled_bold_font,
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
        ]

        self.font_name = 'Helvetica'  # Default fallback
        self.font_name_bold = 'Helvetica-Bold'  # Bold fallback
        font_found = False

        print("DEBUG: Setting up fonts for Cyrillic support...")
        for font_path in font_paths:
            print(f"DEBUG: Checking font path: {font_path}")
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
                    self.font_name = 'DejaVuSans'
                    font_found = True
                    print(f"DEBUG: Successfully registered font from: {font_path}")
                    break
                except Exception as e:
                    print(f"DEBUG: Failed to register font {font_path}: {e}")
                    continue

        # Try to register bold font
        bold_font_found = False
        if font_found:
            for bold_font_path in bold_font_paths:
                print(f"DEBUG: Checking bold font path: {bold_font_path}")
                if os.path.exists(bold_font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', bold_font_path))
                        self.font_name_bold = 'DejaVuSans-Bold'
                        bold_font_found = True
                        print(f"DEBUG: Successfully registered bold font from: {bold_font_path}")
                        break
                    except Exception as e:
                        print(f"DEBUG: Failed to register bold font {bold_font_path}: {e}")
                        continue

        if not font_found:
            print("=" * 60)
            print("WARNING: No Cyrillic-compatible font found!")
            print("WARNING: Using Helvetica fallback - Cyrillic text will NOT render correctly!")
            print("WARNING: Install fonts-dejavu-core or add DejaVuSans.ttf to fonts/ directory")
            print("=" * 60)
        elif not bold_font_found:
            print("=" * 60)
            print("WARNING: Bold font not found, using regular font for bold text")
            print("=" * 60)
            self.font_name_bold = self.font_name

        # Create custom styles
        self.body_style = ParagraphStyle(
            'Body',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=11,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        )

        # Use the registered bold font for bold text
        self.body_style_bold = ParagraphStyle(
            'BodyBold',
            parent=self.body_style,
            fontName=self.font_name_bold,
            fontSize=11,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        )

        self.heading_style = ParagraphStyle(
            'Heading',
            parent=self.styles['Heading1'],
            fontName=self.font_name,
            fontSize=14,
            spaceAfter=12,
        )

        self.caption_style = ParagraphStyle(
            'Caption',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=9,
            fontStyle='Italic',
            alignment=TA_CENTER,
            spaceAfter=6,
        )

        # Flow mode styles (used when keep_original_margins=False)
        # Titles: 12pt bold, centered, larger spacing after
        self.flow_title_style = ParagraphStyle(
            'FlowTitle',
            parent=self.styles['Normal'],
            fontName=self.font_name_bold,
            fontSize=12,
            leading=15,  # ~1.25x for titles
            alignment=TA_CENTER,
            spaceAfter=0.4 * cm,  # Larger interval after titles (base value, will be adjusted dynamically)
        )

        # Body text: 10.5pt, narrower line spacing (1.14x)
        self.flow_body_style = ParagraphStyle(
            'FlowBody',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=10.5,
            leading=12,  # Narrower line spacing (1.14x)
            alignment=TA_JUSTIFY,
            spaceAfter=0.1 * cm,  # Base spacing (will be adjusted dynamically)
        )

        # Page numbers: small, right-aligned
        self.flow_page_number_style = ParagraphStyle(
            'FlowPageNumber',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=8,
            leading=10,
            alignment=TA_RIGHT,
            spaceAfter=0,
        )

        # Footnotes: small, left-aligned
        self.flow_footnote_style = ParagraphStyle(
            'FlowFootnote',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
            spaceAfter=0,
        )

    def add_from_mineru_json(self, content: Any):
        """
        Build PDF from MinerU JSON output.

        Args:
            content: MinerU JSON response with structured content.
                     Can be a list of items directly, or a dict with "content" key.

        Handles:
            - Page breaks via page_idx field (groups content by page)
            - Bold styling via text_level field (text_level=1 is bold)
        """
        # MinerU JSON structure can be:
        # 1. A list of content items directly: [{'type': 'text', ...}, ...]
        # 2. A dict with "content" key: {"content": [{'type': 'text', ...}, ...]}

        # Handle if content is already a list
        if isinstance(content, list):
            items = content
        elif isinstance(content, dict) and "content" in content:
            items = content["content"]
        else:
            # Fallback: try as markdown
            text_content = content.get("text", "") if isinstance(content, dict) else str(content)
            self._add_markdown_text(text_content)
            return

        # Group items by page_idx to handle page breaks correctly
        # This ensures page numbers stay on their correct pages
        from collections import defaultdict
        pages = defaultdict(list)

        for item in items:
            page_idx = item.get('page_idx', 0)
            pages[page_idx].append(item)

        # Process each page's content together
        for page_idx in sorted(pages.keys()):
            page_items = pages[page_idx]

            # Skip first page's page break
            if page_idx > 0:
                self.story.append(PageBreak())

            # Add all items for this page
            for item in page_items:
                item_type = item.get("type", "")

                if item_type == "text":
                    text = item.get("text", "")
                    text_level = item.get("text_level")

                    # Smart spacing based on content type
                    if text_level == 1:
                        # Section header - normal spacing
                        self._add_text_block(text, style=self.body_style_bold, spacer_after=0.15)
                    else:
                        # Body text/proverbs - minimal spacing
                        self._add_text_block(text, style=self.body_style, spacer_after=0.05)
                elif item_type == "image":
                    self._add_image(item)
                elif item_type == "header":
                    self._add_header(item.get("text", ""))
                elif item_type == "table":
                    self._add_table(item)
                elif item_type == "equation":
                    self._add_equation(item.get("text", ""))
                elif item_type in ("page_footnote", "page_number"):
                    # Skip page-level metadata
                    continue
                elif item_type == "discarded":
                    # Add discarded items (includes page numbers) as text
                    text = item.get("text", "")
                    if text and text.strip():
                        # Page numbers - add without spacing
                        self._add_text_block(text, style=self.body_style, spacer_after=0)
                else:
                    # Unknown type, try to add as text
                    text = item.get("text", "")
                    text_level = item.get("text_level")
                    if text_level == 1:
                        self._add_text_block(text, style=self.body_style_bold, spacer_after=0.15)
                    else:
                        self._add_text_block(text, style=self.body_style, spacer_after=0.05)

    def add_from_mineru_markdown(self, markdown_text: str):
        """
        Build PDF from MinerU Markdown output.

        Args:
            markdown_text: Markdown content from MinerU
        """
        self._add_markdown_text(markdown_text)

    def add_from_layout_json(self, layout_data: Dict, use_consistent_margins: bool = False):
        """
        Build PDF from MinerU layout.json with exact positioning.

        Uses canvas-based rendering to place elements at their exact
        bbox coordinates, matching the original PDF layout precisely.

        Args:
            layout_data: Parsed layout.json content with pdf_info array
            use_consistent_margins: If True, use 1.5cm margins with A4 page size;
                                   otherwise use original page size and margins
        """
        pdf_info = layout_data.get("pdf_info", [])
        if not pdf_info:
            print("Warning: No pdf_info in layout data")
            return

        # Store consistent margins setting for coordinate conversion
        self._use_consistent_margins_layout = use_consistent_margins

        # Calculate DPI from page size (needed for pixel-to-point conversion)
        # Get page size from first page
        first_page_size = pdf_info[0].get("page_size", [612, 792])
        self._dpi = self._calculate_dpi_from_page_size(first_page_size)
        print(f"DEBUG: Calculated DPI from page size {first_page_size}: {self._dpi:.1f}")

        # Create canvas for direct drawing
        self._canvas = pdfcanvas.Canvas(self.output_path)

        # Determine page size and margin offset
        if use_consistent_margins:
            # Use A4 with 1cm margins
            page_width, page_height = A4
            margin = 1 * cm
            self._margin_offset_x = margin
            self._margin_offset_y = margin
        else:
            # Use original page size from layout.json
            # Will be set per page below
            self._margin_offset_x = 0
            self._margin_offset_y = 0

        # Process each page
        for page_data in pdf_info:
            page_idx = page_data.get("page_idx", 0)

            # Get original page size in pixels from MinerU
            original_page_size_px = page_data.get("page_size", [612, 792])

            if use_consistent_margins:
                # Use A4 page size (in points)
                self._canvas.setPageSize(A4)
                current_page_width, current_page_height = A4
                # Original page size in pixels (for DPI-based conversion)
                original_page_width_px, original_page_height_px = original_page_size_px
            else:
                # Convert original page size from pixels to points
                # This ensures the canvas is sized correctly for ReportLab
                original_page_width_px, original_page_height_px = original_page_size_px
                page_width_pt = original_page_width_px / self._dpi * 72
                page_height_pt = original_page_height_px / self._dpi * 72
                self._canvas.setPageSize((page_width_pt, page_height_pt))
                current_page_width, current_page_height = page_width_pt, page_height_pt

            # Process content blocks (preproc_blocks)
            preproc_blocks = page_data.get("preproc_blocks", [])
            for block in preproc_blocks:
                self._render_block(block, current_page_height, original_page_height_px)

            # Process discarded blocks (page numbers, etc.)
            discarded_blocks = page_data.get("discarded_blocks", [])
            for block in discarded_blocks:
                self._render_block(block, current_page_height, original_page_height_px, is_discarded=True)

            # Move to next page
            self._canvas.showPage()

        # Save the document
        self._canvas.save()
        self._canvas = None

    def _render_block(self, block: Dict, page_height: float, original_page_height_px: float = None, is_discarded: bool = False):
        """
        Render a single block at its exact position.

        Args:
            block: Block data with type, bbox, and lines
            page_height: Height of the page in points for coordinate conversion
            original_page_height_px: Original page height in pixels from layout.json
            is_discarded: Whether this is a discarded block (page number)
        """
        block_type = block.get("type", "text")
        bbox = block.get("bbox", [0, 0, 100, 20])

        # Convert bbox coordinates from MinerU (pixels, top-left origin) to ReportLab (points, bottom-left origin)
        # _convert_bbox handles pixel-to-point conversion internally using self._dpi
        x, y, width, height = self._convert_bbox(bbox, page_height)

        # Apply margin offset if using consistent margins
        if hasattr(self, '_use_consistent_margins_layout') and self._use_consistent_margins_layout:
            x += self._margin_offset_x
            y += self._margin_offset_y

        if block_type == "image":
            self._render_image_block(block, x, y, width, height)
        else:
            # Text, title, or discarded - pass page_height for line positioning
            self._render_text_block(block, x, y, width, height, block_type, is_discarded, page_height, original_page_height_px)

    def _calculate_dpi_from_page_size(self, page_size: List[float]) -> float:
        """
        Calculate DPI from page size by comparing to standard paper dimensions.

        MinerU stores bbox coordinates in pixels. We need to determine the DPI
        to convert pixel heights to points for font sizing.

        Args:
            page_size: [width, height] in pixels from layout.json

        Returns:
            DPI as a float (typically 72, 96, 150, 200, or 300)
        """
        # Standard paper sizes in inches
        # US Letter: 8.5 x 11 inches
        # A4: 8.27 x 11.69 inches
        letter_w, letter_h = 8.5, 11.0
        a4_w, a4_h = 8.27, 11.69

        px_w, px_h = page_size

        # Calculate DPI based on US Letter (most common for scanned documents)
        dpi_w_letter = px_w / letter_w
        dpi_h_letter = px_h / letter_h
        avg_dpi_letter = (dpi_w_letter + dpi_h_letter) / 2

        # Calculate DPI based on A4
        dpi_w_a4 = px_w / a4_w
        dpi_h_a4 = px_h / a4_h
        avg_dpi_a4 = (dpi_w_a4 + dpi_h_a4) / 2

        # Use the DPI that gives more consistent width/height ratio
        # (i.e., the one where width and height DPI are closer together)
        if abs(dpi_w_letter - dpi_h_letter) < abs(dpi_w_a4 - dpi_h_a4):
            # US Letter is a better match
            return avg_dpi_letter
        else:
            # A4 is a better match
            return avg_dpi_a4

    def _convert_bbox(self, bbox: List[float], page_height: float) -> Tuple[float, float, float, float]:
        """
        Convert MinerU bbox from pixels to ReportLab coordinates in points.

        MinerU bbox: [x1, y1, x2, y2] in pixels with origin at top-left
        ReportLab: points with origin at bottom-left

        Args:
            bbox: [x1, y1, x2, y2] coordinates in pixels
            page_height: Height of the page in points

        Returns:
            (x, y, width, height) in ReportLab coordinates (points)
        """
        x1, y1, x2, y2 = bbox

        # Convert from pixels to points
        x1_pt = x1 / self._dpi * 72
        y1_pt = y1 / self._dpi * 72
        x2_pt = x2 / self._dpi * 72
        y2_pt = y2 / self._dpi * 72

        width = x2_pt - x1_pt
        height = y2_pt - y1_pt

        # Convert y coordinate: ReportLab y = page_height - MinerU y2 (bottom of block)
        rl_y = page_height - y2_pt

        return x1_pt, rl_y, width, height

    def _get_font_size_from_bbox(self, bbox_height: float) -> int:
        """
        Direct mapping from bbox height to font size using universal standard buckets.

        Thresholds (dynamic, set via font_buckets parameter):
        - < 18 units         → 8pt  (smallest footnotes)
        - 18 - bucket_9     → 9pt  (footnotes, page numbers)
        - bucket_9 - bucket_10  → 10pt (main body text, questions, proverbs)
        - bucket_10 - bucket_11 → 11pt (section headers like "Литовские", "Немецкие")
        - bucket_11 - bucket_12 → 12pt (main title or large headers)
        - bucket_12 - bucket_14 → 13pt (very large headers)
        - > bucket_14       → 14pt (extra large headers)

        Args:
            bbox_height: Raw bbox height from layout.json (y2 - y1)

        Returns:
            Font size in points
        """
        if bbox_height < 18:
            return 8
        elif bbox_height < self.font_bucket_9:
            return 9
        elif bbox_height < self.font_bucket_10:
            return 10
        elif bbox_height < self.font_bucket_11:
            return 11
        elif bbox_height < self.font_bucket_12:
            return 12
        elif bbox_height < self.font_bucket_14:
            return 13
        else:
            return 14

    def _is_footnote_block(self, block: Dict, page_height: float) -> bool:
        """
        Detect if block is a footnote based on position and content pattern.

        Requires BOTH:
        - Position in bottom 20% of page
        - First line starts with number + space + letter (e.g., "1 Литературовед")

        Args:
            block: Block data with bbox and lines
            page_height: Page height in pixels

        Returns:
            True if block appears to be a footnote
        """
        import re

        bbox = block.get("bbox", [0, 0, 0, 0])
        y_top = bbox[1]

        # Signal 1: Position - bottom 20% of page
        is_at_bottom = y_top > page_height * 0.80
        if not is_at_bottom:
            return False

        # Signal 2: Content pattern - starts with number + space + letter
        # Footnotes: "1 Литературовед" (digit + space + letter)
        # vs Lists: "1. Расскажите" (digit + period + space)
        first_line_content = ""
        lines = block.get("lines", [])
        if lines:
            spans = lines[0].get("spans", [])
            if spans:
                first_line_content = spans[0].get("content", "")

        has_footnote_pattern = bool(re.match(r'^\d+\s+[A-ZА-Яa-zа-я]', first_line_content))

        # Require BOTH signals to reduce false positives
        return has_footnote_pattern

    def _render_text_block(self, block: Dict, x: float, y: float, width: float, height: float,
                           block_type: str, is_discarded: bool, page_height: float, original_page_height_px: float = None):
        """
        Render a text block at exact position, preserving line breaks and original spacing.

        Font sizing strategy (universal buckets with median):
        1. Get bbox heights for all lines in the block
        2. Find the median bbox height (more stable than mode for small samples)
        3. Map directly to font size using fixed thresholds
        4. Apply same font size to all lines in block

        Args:
            block: Block data with lines containing spans
            x, y, width, height: Position and size in ReportLab coordinates
            block_type: "text", "title", or "discarded"
            is_discarded: Whether this is a discarded block
            page_height: Height of the page for coordinate conversion (in points)
            original_page_height_px: Original page height in pixels (for footnote detection)
        """
        # Extract text lines preserving structure
        text_lines = self._extract_text_lines_from_block(block)
        if not text_lines:
            return

        # Get line data for font sizing
        lines_data = block.get("lines", [])

        # Fixed line height for consistent spacing
        FIXED_LINE_HEIGHT = 14

        # Step 1: Collect bbox heights for all lines in this block
        bbox_heights = []
        for line_data in lines_data:
            line_bbox = line_data.get("bbox", [0, 0, 0, 0])
            if len(line_bbox) >= 4:
                bbox_height = line_bbox[3] - line_bbox[1]
                bbox_heights.append(bbox_height)

        # Step 2 & 3: Determine font size using universal buckets
        # TITLES: Always use 12pt regardless of bbox height
        # DISCARDED: Always use 8pt (page numbers, footnotes)
        # FOOTNOTES: Use 8pt if detected (position + content pattern)
        # TEXT: Use bucket thresholds based on median line height
        if block_type == "title":
            # Force titles to 12pt font for consistency
            font_size = 12
        elif block_type == "discarded":
            # Page numbers, footnotes already marked as discarded → 8pt
            font_size = 8
        elif self.enable_footnote_detection and original_page_height_px and self._is_footnote_block(block, original_page_height_px):
            # Detected footnote (not marked as discarded by MinerU) → 8pt
            font_size = 8
        elif bbox_heights:
            # Use median (middle value) instead of mode
            # More stable for small samples and handles outliers better
            sorted_heights = sorted(bbox_heights)
            mid = len(sorted_heights) // 2
            if len(sorted_heights) % 2 == 0:
                # Even number of items: average the two middle values
                median_bbox_height_px = (sorted_heights[mid - 1] + sorted_heights[mid]) / 2
            else:
                # Odd number of items: take the middle value
                median_bbox_height_px = sorted_heights[mid]

            # Convert pixels to points using DPI
            # Formula: points = pixels / DPI * 72
            median_bbox_height_pt = median_bbox_height_px / self._dpi * 72

            # Map point height to font size
            font_size = self._get_font_size_from_bbox(median_bbox_height_pt)

            # DEBUG: Print first 10 blocks for verification
            if not hasattr(self, '_debug_blocks_printed'):
                self._debug_blocks_printed = 0
            if self._debug_blocks_printed < 10:
                self._debug_blocks_printed += 1
                print(f"DEBUG Block {self._debug_blocks_printed}: type={block_type}, median_bbox={median_bbox_height_px:.1f}px ({median_bbox_height_pt:.1f}pt) → font_size={font_size}pt | lines={len(text_lines)} | text='{text_lines[0][:40] if text_lines else ''}...'")
        else:
            # Fallback to default sizes
            if block_type == "title":
                font_size = 12  # Titles always 12pt
            elif block_type == "discarded":
                font_size = 8  # Discarded always 8pt
            else:
                font_size = 11  # Default text

        # Determine font name (bold for titles)
        font_name = self.font_name_bold if block_type == "title" else self.font_name

        try:
            for i, text_line in enumerate(text_lines):
                # Clean text for ReportLab
                clean_text = text_line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

                # Create style with the font size (same for all lines in block)
                line_style = ParagraphStyle(
                    'Dynamic',
                    parent=self.styles['Normal'],
                    fontName=font_name,
                    fontSize=font_size,
                    leading=font_size * 1.2,  # Leading is typically 1.2x font size
                    alignment=TA_JUSTIFY,
                )

                # Position line using fixed line height from top of block
                line_y = y + height - ((i + 1) * FIXED_LINE_HEIGHT)

                # Create paragraph and wrap it
                para = Paragraph(clean_text, line_style)
                para_width, para_height = para.wrap(width, height)

                # Draw at calculated position
                para.drawOn(self._canvas, x, line_y)

        except Exception as e:
            # Fallback to simple text rendering
            print(f"Warning: Paragraph failed for '{text_lines[0][:50] if text_lines else ''}...': {e}")
            self._canvas.setFont(self.font_name, 11)
            # Render all lines as fallback using same fixed line height
            for i, text_line in enumerate(text_lines):
                line_y = y + height - ((i + 1) * FIXED_LINE_HEIGHT)
                self._canvas.drawString(x, line_y, text_line[:80])

    def _extract_text_lines_from_block(self, block: Dict) -> list:
        """
        Extract text lines from block's lines/spans structure, preserving line breaks.

        Args:
            block: Block with lines array containing spans

        Returns:
            List of text strings, one per line
        """
        lines = block.get("lines", [])
        text_lines = []

        for line in lines:
            spans = line.get("spans", [])
            line_text_parts = []
            for span in spans:
                content = span.get("content", "")
                if content:
                    line_text_parts.append(content)

            # Join spans within a line with spaces, but keep lines separate
            if line_text_parts:
                text_lines.append(" ".join(line_text_parts))

        return text_lines

    def _render_image_block(self, block: Dict, x: float, y: float, width: float, height: float):
        """
        Render an image block at exact position.

        Args:
            block: Block data with image path in lines/spans or blocks/lines/spans
            x, y, width, height: Position and size in ReportLab coordinates
        """
        # Find image path in the block structure
        # Image blocks can have structure: blocks[] -> lines[] -> spans[] -> image_path
        # OR directly: lines[] -> spans[] -> image_path
        image_path = None

        # Try nested blocks structure first (for image blocks)
        blocks = block.get("blocks", [])
        if blocks:
            for sub_block in blocks:
                lines = sub_block.get("lines", [])
                for line in lines:
                    spans = line.get("spans", [])
                    for span in spans:
                        if span.get("type") == "image":
                            image_path = span.get("image_path")
                            break
                    if image_path:
                        break
                if image_path:
                    break

        # Try direct lines structure (fallback)
        if not image_path:
            lines = block.get("lines", [])
            for line in lines:
                spans = line.get("spans", [])
                for span in spans:
                    if span.get("type") == "image":
                        image_path = span.get("image_path")
                        break
                if image_path:
                    break

        if not image_path:
            print(f"Warning: Image block has no image_path")
            return

        # Construct full path
        if self.temp_dir:
            full_path = os.path.join(self.temp_dir, "images", image_path)
            if not os.path.exists(full_path):
                # Try without images/ prefix
                full_path = os.path.join(self.temp_dir, image_path)

            if os.path.exists(full_path):
                try:
                    print(f"DEBUG: Drawing image at ({x}, {y}) size ({width}x{height}): {image_path}")
                    self._canvas.drawImage(full_path, x, y, width=width, height=height,
                                          preserveAspectRatio=True, anchor='sw')
                except Exception as e:
                    print(f"Warning: Could not draw image {full_path}: {e}")
            else:
                print(f"Warning: Image file not found: {full_path}")

    def _calculate_content_height_with_spacing(
        self,
        content_items: List[Tuple[str, Any, float]],
        page_width: float,
        available_height: float
    ) -> Tuple[float, float]:
        """
        Calculate total height of content items with their spacing.

        Args:
            content_items: List of (item_type, content, base_spacing) tuples
                          item_type: 'text', 'title', 'discarded', 'image'
                          content: text string for text items, or (path, width, height) for images
                          base_spacing: spaceAfter value in points
            page_width: Available page width in points
            available_height: Available page height in points

        Returns:
            Tuple of (total_height, spacing_sum) in points
        """
        total_height = 0
        spacing_sum = 0

        for item_type, content, base_spacing in content_items:
            if item_type in ('text', 'title', 'discarded'):
                # Determine appropriate style
                if item_type == 'title':
                    style = self.flow_title_style
                elif item_type == 'discarded':
                    style = self.flow_discarded_style
                else:
                    style = self.flow_body_style

                # Create temporary paragraph and measure its height
                # Clean text for ReportLab
                clean_text = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                temp_para = Paragraph(clean_text, style)
                _, text_height = temp_para.wrap(page_width, available_height)
                total_height += text_height
                spacing_sum += base_spacing
            elif item_type == 'image':
                # Images have fixed height (path, width, height in points)
                _, _, height = content
                total_height += height
                spacing_sum += base_spacing

        return total_height, spacing_sum

    def add_from_layout_json_flow(self, layout_data: Dict, margin: float = None):
        """
        Build PDF from layout.json using flow-based rendering with dynamic spacing.

        This method processes layout.json structure but uses ReportLab flowables
        (Paragraph, Spacer) instead of exact canvas positioning. Spacing is
        dynamically adjusted to fit content on each page.

        Features:
        - Titles: 12pt bold, centered, first line gets 0.4cm space before, last gets 0.4cm after
        - Multi-line titles: middle lines get 0.1cm spacing (tighter)
        - Gap detection: blocks separated by >30px get 0.4cm spacer
        - Discarded blocks: page numbers (right-aligned), footnotes (left-aligned)

        Args:
            layout_data: Parsed layout.json content with pdf_info array
            margin: Optional margin in points. If None, calculated from layout data.
        """
        pdf_info = layout_data.get("pdf_info", [])
        if not pdf_info:
            print("Warning: No pdf_info in layout data")
            return

        # Calculate DPI from page size (needed for image height conversion)
        first_page_size = pdf_info[0].get("page_size", [612, 792])
        self._dpi = self._calculate_dpi_from_page_size(first_page_size)
        print(f"DEBUG: Flow mode - Calculated DPI from page size {first_page_size}: {self._dpi:.1f}")

        # Calculate or use provided margin
        if margin is None:
            # Calculate margins from original PDF layout
            margin = calculate_margins_from_layout(layout_data, self._dpi)
        else:
            print(f"DEBUG: Flow mode - Using provided margin: {margin:.1f}pt")

        # Store margin for finalize() to use
        self._flow_margin = margin

        # Page dimensions with calculated/provided margins
        page_width_pt, page_height_pt = A4
        available_width = page_width_pt - (2 * margin)
        available_height = page_height_pt - (2 * margin)

        # Gap detection threshold (30 pixels)
        GAP_THRESHOLD_PX = 30
        # Spacer for detected gaps (0.4cm - same as title spacing)
        LARGE_SPACER = 0.4 * cm

        # Group blocks by page_idx
        from collections import defaultdict
        pages = defaultdict(list)

        for page_data in pdf_info:
            page_idx = page_data.get("page_idx", 0)
            page_size_px = page_data.get("page_size", first_page_size)
            page_height_px = page_size_px[1]

            # Track last block position for gap detection
            last_block_bottom = None

            # Process content blocks (preproc_blocks) in order
            preproc_blocks = page_data.get("preproc_blocks", [])
            for block in preproc_blocks:
                block_type = block.get("type", "text")
                bbox = block.get("bbox", [0, 0, 100, 100])
                block_top = bbox[1]

                # Check for gap between blocks
                if last_block_bottom is not None:
                    gap = block_top - last_block_bottom
                    if gap > GAP_THRESHOLD_PX:
                        # Use different spacer sizes: 0.4cm before titles, 2.5cm for other gaps
                        if block_type == 'title':
                            spacer_size = 0.4 * cm  # Same as title's space after
                        else:
                            spacer_size = LARGE_SPACER  # 2.5cm for content gaps

                        pages[page_idx].append({
                            'type': 'spacer',
                            'content': spacer_size,
                            'spacing': 0,
                            'is_first_in_group': False,
                            'is_last_in_group': False
                        })

                # Extract text lines from block
                text_lines = self._extract_text_lines_from_block(block)

                if block_type == "image":
                    # Extract image dimensions
                    # Find image path
                    blocks = block.get("blocks", [])
                    image_path = None
                    for sub_block in blocks:
                        lines = sub_block.get("lines", [])
                        for line in lines:
                            spans = line.get("spans", [])
                            for span in spans:
                                if span.get("type") == "image":
                                    image_path = span.get("image_path")
                                    break
                            if image_path:
                                break
                        if image_path:
                            break

                    # Calculate image height in points
                    bbox_height = bbox[3] - bbox[1]
                    image_height_pt = bbox_height / self._dpi * 72

                    # Store image with metadata for multi-line title tracking
                    pages[page_idx].append({
                        'type': 'image',
                        'content': (image_path, available_width, image_height_pt),
                        'spacing': 0.1 * cm,
                        'is_first_in_group': False,
                        'is_last_in_group': False
                    })

                    # Update last block position
                    last_block_bottom = bbox[3]

                elif text_lines:
                    # Check for footnote detection
                    is_footnote = False
                    if self.enable_footnote_detection and block_type == "text":
                        is_footnote = self._is_footnote_block(block, page_height_px)

                    # For titles, we need to track first/last line for proper spacing
                    if block_type == "title":
                        # First title line gets special treatment (space before)
                        for i, line in enumerate(text_lines):
                            is_first = (i == 0)
                            is_last = (i == len(text_lines) - 1)
                            # Spacing: first gets 0.4cm before (handled in render), middle get 0.1cm, last gets 0.4cm
                            spacing = 0.4 * cm if is_last else 0.1 * cm
                            pages[page_idx].append({
                                'type': 'title',
                                'content': line,
                                'spacing': spacing,
                                'is_first_in_group': is_first,
                                'is_last_in_group': is_last
                            })
                    elif is_footnote:
                        # Detected footnote - treat like discarded block (8pt font)
                        for line in text_lines:
                            pages[page_idx].append({
                                'type': 'footnote',
                                'content': line,
                                'spacing': 0,
                                'is_first_in_group': False,
                                'is_last_in_group': False,
                            })
                    else:
                        # Regular text - add each line as a separate paragraph
                        for line in text_lines:
                            pages[page_idx].append({
                                'type': 'text',
                                'content': line,
                                'spacing': 0.1 * cm,
                                'is_first_in_group': False,
                                'is_last_in_group': False,
                            })

                    # Update last block position
                    last_block_bottom = bbox[3]

            # Process discarded blocks (page numbers, footnotes) - add at end
            discarded_blocks = page_data.get("discarded_blocks", [])
            for block in discarded_blocks:
                text_lines = self._extract_text_lines_from_block(block)
                if not text_lines:
                    continue

                # Determine if page number or footnote based on content
                # Page numbers are typically numeric (with optional dashes/spaces)
                # Footnotes contain actual text content
                for line in text_lines:
                    # Check if line is purely numeric (with optional dashes, spaces, roman numerals)
                    # Remove common formatting and check if only numbers remain
                    cleaned = line.strip().replace('-', '').replace('—', '').replace(' ', '').replace('.', '')
                    # Check if it's a number (arabic or roman) or very short numeric-like string
                    is_numeric = cleaned.isdigit() or len(cleaned) <= 3

                    if is_numeric and len(line.strip()) < 20:
                        # Short numeric/string → page number (right-aligned)
                        block_type = 'page_number'
                    else:
                        # Contains actual text → footnote (left-aligned)
                        block_type = 'footnote'

                    pages[page_idx].append({
                        'type': block_type,
                        'content': line,
                        'spacing': 0,
                        'is_first_in_group': False,
                        'is_last_in_group': False
                    })

        # Process each page
        for page_idx in sorted(pages.keys()):
            content_items = pages[page_idx]

            # Skip first page's page break
            if page_idx > 0:
                self.story.append(PageBreak())

            # Calculate total height with base spacing
            total_text_height, total_spacing = self._calculate_content_height_with_spacing_dict(
                content_items, available_width, available_height
            )
            total_height = total_text_height + total_spacing

            # Calculate spacing multiplier if overflow
            multiplier = 1.0
            if total_height > available_height:
                multiplier = available_height / total_height

                # Apply limits
                if multiplier < 0.4:
                    print(f"Warning: Page {page_idx + 1} content too large. Spacing reduced to 40% minimum.")
                    multiplier = 0.4
                else:
                    print(f"Info: Page {page_idx + 1} spacing adjusted to {multiplier * 100:.1f}% to fit content.")

            # Render content with adjusted spacing
            for item in content_items:
                item_type = item['type']

                if item_type == 'spacer':
                    # Gap spacer - also gets scaled
                    adjusted_spacing = item['content'] * multiplier
                    if adjusted_spacing < 0.1 * cm:
                        adjusted_spacing = 0.1 * cm
                    self.story.append(Spacer(1, adjusted_spacing))

                elif item_type in ('text', 'title', 'page_number', 'footnote'):
                    # Select base style
                    if item_type == 'title':
                        base_style = self.flow_title_style
                    elif item_type == 'page_number':
                        base_style = self.flow_page_number_style
                    elif item_type == 'footnote':
                        base_style = self.flow_footnote_style
                    else:
                        base_style = self.flow_body_style

                    # Adjust spacing
                    base_spacing = item['spacing']
                    adjusted_spacing = base_spacing * multiplier
                    if adjusted_spacing < 0.1 * cm:
                        adjusted_spacing = 0.1 * cm  # Minimum threshold

                    # For first title line, add space before
                    if item_type == 'title' and item['is_first_in_group']:
                        space_before = 0.4 * cm * multiplier
                        if space_before < 0.1 * cm:
                            space_before = 0.1 * cm
                        self.story.append(Spacer(1, space_before))

                    # Create style with adjusted spacing
                    style = ParagraphStyle(
                        f'Adjusted_{item_type}',
                        parent=base_style,
                        spaceAfter=adjusted_spacing,
                    )

                    # Clean text and add paragraph
                    clean_text = item['content'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    self.story.append(Paragraph(clean_text, style))

                elif item_type == 'image':
                    # Add image with original size
                    image_path, img_width, img_height = item['content']

                    if image_path and self.temp_dir:
                        # Construct full path
                        full_path = os.path.join(self.temp_dir, "images", image_path)
                        if not os.path.exists(full_path):
                            full_path = os.path.join(self.temp_dir, image_path)

                        if os.path.exists(full_path):
                            try:
                                from reportlab.platypus import Image as RLImage
                                rl_image = RLImage(full_path, width=img_width, height=img_height)
                                # Adjust spacing after image
                                base_spacing = item['spacing']
                                adjusted_spacing = base_spacing * multiplier
                                if adjusted_spacing < 0.1 * cm:
                                    adjusted_spacing = 0.1 * cm
                                self.story.append(rl_image)
                                self.story.append(Spacer(1, adjusted_spacing))
                            except Exception as e:
                                print(f"Warning: Could not add image {full_path}: {e}")

    def _calculate_content_height_with_spacing_dict(
        self,
        content_items: List[Dict],
        page_width: float,
        available_height: float
    ) -> Tuple[float, float]:
        """
        Calculate total height of content items (dict format) with their spacing.

        Args:
            content_items: List of dicts with 'type', 'content', 'spacing' keys
            page_width: Available page width in points
            available_height: Available page height in points

        Returns:
            Tuple of (total_height, spacing_sum) in points
        """
        total_height = 0
        spacing_sum = 0

        for item in content_items:
            item_type = item['type']

            if item_type == 'spacer':
                # Gap spacer
                spacing_sum += item['content']

            elif item_type in ('text', 'title', 'page_number', 'footnote'):
                # Determine appropriate style
                if item_type == 'title':
                    style = self.flow_title_style
                elif item_type == 'page_number':
                    style = self.flow_page_number_style
                elif item_type == 'footnote':
                    style = self.flow_footnote_style
                else:
                    style = self.flow_body_style

                # Create temporary paragraph and measure its height
                clean_text = item['content'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                temp_para = Paragraph(clean_text, style)
                _, text_height = temp_para.wrap(page_width, available_height)
                total_height += text_height
                spacing_sum += item['spacing']

                # Add space before for first title line
                if item_type == 'title' and item['is_first_in_group']:
                    spacing_sum += 0.4 * cm

            elif item_type == 'image':
                # Images have fixed height (path, width, height in points)
                _, _, height = item['content']
                total_height += height
                spacing_sum += item['spacing']

        return total_height, spacing_sum

    def finalize_layout(self):
        """
        Finalize document when using layout-based rendering.

        Note: For layout.json rendering, the document is saved in add_from_layout_json().
        This method is kept for compatibility but does nothing when canvas rendering is used.
        """
        # Layout rendering saves in add_from_layout_json()
        pass

    def _add_text_block(self, text: str, style=None, spacer_after=0.2):
        """
        Add a text paragraph to the document.

        Splits text by newlines and creates a separate Paragraph
        for each line with the specified style.

        Args:
            text: The text content to add
            style: Optional ParagraphStyle to use (defaults to body_style)
            spacer_after: Height of spacer to add after this block in cm (0 for no spacer)
        """
        if not text or not text.strip():
            return

        if style is None:
            style = self.body_style

        # Split by lines and add each as a paragraph
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        for line in lines:
            self.story.append(Paragraph(line, style))

        if spacer_after > 0:
            self.story.append(Spacer(1, spacer_after * cm))

    def _add_header(self, text: str):
        """
        Add a header/title paragraph to the document.

        Uses heading style (larger, centered text) for section titles.

        Args:
            text: The header text to add
        """
        if not text or not text.strip():
            return

        self.story.append(Paragraph(text, self.heading_style))
        self.story.append(Spacer(1, 0.3 * cm))

    def _add_markdown_text(self, markdown_text: str):
        """
        Add markdown-formatted text to the document.

        Parses simple markdown syntax:
        - `# Heading` → heading style
        - `## Subheading` → heading style
        - Plain text → body style

        Args:
            markdown_text: Markdown content to render
        """
        if not markdown_text:
            return

        # Simple markdown rendering
        lines = markdown_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Headings
            if line.startswith("# "):
                self.story.append(Paragraph(line[2:], self.heading_style))
            elif line.startswith("## "):
                self.story.append(Paragraph(line[3:], self.heading_style))
            # Images: ![alt](url)
            elif line.startswith("!["):
                # Would need to extract URL and download
                # For now, add as text placeholder
                self.story.append(Paragraph(line, self.body_style))
            else:
                self.story.append(Paragraph(line, self.body_style))

            self.story.append(Spacer(1, 0.2 * cm))

    def _add_image(self, item: Dict):
        """
        Add an image from MinerU output to the document.

        Handles multiple image formats:
        - img_path: Relative path to image in temp_dir (MinerU batch format)
        - image: Base64 data URI or HTTP URL (fallback)

        Supports both caption and image_caption fields.

        Args:
            item: Dictionary containing image data with keys:
                - img_path: Relative path like "images/xxx.jpg"
                - image: Base64 or URL (fallback)
                - image_caption/caption: Optional caption text
        """
        # MinerU may provide: img_path (relative path in temp_dir) or image (base64/URL)
        img_path = item.get("img_path")
        img_data = item.get("image")
        # Handle both caption and image_caption fields
        caption = item.get("image_caption") or item.get("caption", "")

        tmp_path = None

        try:
            # Prefer img_path if available (MinerU batch format)
            if img_path and self.temp_dir:
                # img_path is relative like "images/xxx.jpg"
                full_path = os.path.join(self.temp_dir, img_path)
                if os.path.exists(full_path):
                    tmp_path = full_path
                else:
                    print(f"Warning: Image not found at {full_path}")
                    return
            elif img_data:
                # Fallback to original image field (base64 or URL)
                # If image is base64 encoded
                if isinstance(img_data, str) and img_data.startswith("data:image"):
                    import base64
                    header, data = img_data.split(",", 1)
                    img_bytes = base64.b64decode(data)

                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        tmp.write(img_bytes)
                        tmp_path = tmp.name
                # If image is a path/URL
                else:
                    import requests
                    response = requests.get(img_data, timeout=30)
                    response.raise_for_status()

                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        tmp.write(response.content)
                        tmp_path = tmp.name

                self.temp_files.append(tmp_path)
            else:
                return

            if not tmp_path:
                return

            # Add image to PDF (scale to fit)
            from reportlab.platypus import Image as RLImage
            from PIL import Image as PILImage

            with PILImage.open(tmp_path) as img:
                img_width, img_height = img.size
                aspect = img_height / img_width

            max_width = 15 * cm
            max_height = 12 * cm

            if aspect > max_height / max_width:
                height = max_height
                width = height / aspect
            else:
                width = max_width
                height = width * aspect

            rl_image = RLImage(tmp_path, width=width, height=height)
            self.story.append(rl_image)
            self.story.append(Spacer(1, 0.3 * cm))

            # Add caption if present
            if caption:
                self.story.append(Paragraph(caption, self.caption_style))
                self.story.append(Spacer(1, 0.3 * cm))

        except Exception as e:
            print(f"Warning: Could not add image: {e}")
            # Add placeholder text
            self.story.append(Paragraph(f"[Image: {caption or 'No caption'}]", self.body_style))

    def _add_table(self, item: Dict):
        """
        Add a table from MinerU output to the document.

        Creates a ReportLab Table with styling including borders
        and header formatting.

        Args:
            item: Dictionary containing table data with key:
                - content: List of lists representing table rows
        """
        table_data = item.get("content", [])
        if not table_data:
            return

        try:
            # Convert table data to ReportLab Table
            # table_data should be a list of lists (rows x columns)
            if not isinstance(table_data[0], list):
                table_data = [[cell] for cell in table_data]

            # Clean cell text
            cleaned_data = []
            for row in table_data:
                cleaned_row = [
                    str(cell).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    for cell in row
                ]
                cleaned_data.append(cleaned_row)

            # Create table
            table = Table(cleaned_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), self.font_name),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))

            self.story.append(table)
            self.story.append(Spacer(1, 0.5 * cm))

        except Exception as e:
            print(f"Warning: Could not add table: {e}")

    def _add_equation(self, equation_text: str):
        """
        Add a mathematical equation to the document.

        Currently renders equations as monospace text. Full LaTeX
        rendering would require additional dependencies.

        Args:
            equation_text: LaTeX or plain text equation
        """
        if not equation_text:
            return

        # For LaTeX equations, we'd need a LaTeX renderer
        # For now, render as monospace text
        try:
            from reportlab.pdfbase.pdfmetrics import registerFont
            from reportlab.pdfbase.ttfonts import TTFont

            # Try to find a monospace font
            mono_fonts = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
                '/usr/share/fonts/dejavu/DejaVuSansMono.ttf',
            ]

            mono_font = 'Courier'
            for font_path in mono_fonts:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('Mono', font_path))
                        mono_font = 'Mono'
                        break
                    except Exception:
                        continue

            eq_style = ParagraphStyle(
                'Equation',
                parent=self.styles['Normal'],
                fontName=mono_font,
                fontSize=10,
                alignment=TA_CENTER,
                spaceAfter=10,
            )

            self.story.append(Paragraph(equation_text, eq_style))
            self.story.append(Spacer(1, 0.3 * cm))

        except Exception as e:
            print(f"Warning: Could not add equation: {e}")
            self.story.append(Paragraph(equation_text, self.body_style))

    def finalize(self):
        """
        Save completed document to output path.
        """
        # Use flow margin if set (from flow mode), otherwise use consistent 1cm or default 2cm
        if hasattr(self, '_flow_margin'):
            margin = self._flow_margin
            print(f"DEBUG: finalize() - Using flow margin: {margin:.1f}pt")
        else:
            margin = 1 * cm if self.use_consistent_margins else 2 * cm
            print(f"DEBUG: finalize() - Using standard margin: {margin:.1f}pt")

        doc = SimpleDocTemplate(
            self.output_path,
            pagesize=A4,
            rightMargin=margin,
            leftMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
        )

        doc.build(self.story)

        # Clean up temporary image files
        for tmp_file in self.temp_files:
            try:
                if os.path.exists(tmp_file):
                    os.unlink(tmp_file)
            except Exception as e:
                print(f"Warning: Could not delete temp file {tmp_file}: {e}")


def create_pdf_from_mineru(
    output_path: str,
    content: Any,
    content_type: str = "json",
    temp_dir: str = None,
    use_consistent_margins: bool = False
) -> str:
    """
    Helper function to create PDF from MinerU output.

    Args:
        output_path: Where to save the PDF
        content: MinerU JSON or Markdown content
        content_type: "json" or "markdown"
        temp_dir: Optional temporary directory containing extracted images
        use_consistent_margins: If True, use 1.5cm margins on all sides

    Returns:
        Path to created document
    """
    builder = DocumentBuilder(output_path, temp_dir=temp_dir, use_consistent_margins=use_consistent_margins)

    if content_type == "json":
        builder.add_from_mineru_json(content)
    else:
        if isinstance(content, str):
            builder.add_from_mineru_markdown(content)
        else:
            # Try to extract text if it's a dict
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            builder.add_from_mineru_markdown(text)

    builder.finalize()
    return output_path


def create_pdf_from_layout(
    output_path: str,
    layout_data: Dict,
    temp_dir: str = None,
    use_consistent_margins: bool = False,
    font_buckets: dict = None,
    enable_footnote_detection: bool = False
) -> str:
    """
    Create PDF from MinerU layout.json with exact positioning.

    This method uses canvas-based rendering to place elements at their
    exact bbox coordinates, matching the original PDF layout precisely.

    Args:
        output_path: Where to save the PDF
        layout_data: Parsed layout.json content with pdf_info array
        temp_dir: Temporary directory containing extracted images
        use_consistent_margins: If True, use 1.5cm margins with A4 page size
        font_buckets: Optional dict with custom bbox height thresholds for font sizing
                     Keys: "bucket_10", "bucket_11", "bucket_12"
        enable_footnote_detection: If True, detect footnotes by position and content pattern

    Returns:
        Path to created document
    """
    builder = DocumentBuilder(output_path, temp_dir=temp_dir, font_buckets=font_buckets, enable_footnote_detection=enable_footnote_detection)
    builder.add_from_layout_json(layout_data, use_consistent_margins=use_consistent_margins)
    # Note: add_from_layout_json() saves the document directly
    return output_path


def calculate_margins_from_layout(layout_data: Dict, dpi: float) -> float:
    """
    Calculate document margins from layout.json bbox data.

    Finds the leftmost and rightmost content across all pages to determine
    the original PDF's margins.

    Args:
        layout_data: Parsed layout.json content with pdf_info array
        dpi: DPI for pixel-to-point conversion

    Returns:
        Margin in points (clamped between 0.5cm and 2cm)
    """
    from reportlab.lib.units import cm

    pdf_info = layout_data.get("pdf_info", [])
    if not pdf_info:
        return 0.5 * cm  # Default fallback

    first_page_size = pdf_info[0].get("page_size", [612, 792])
    page_width_px, _ = first_page_size

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

    # Calculate margins in points (convert from pixels)
    left_margin_pt = min_left / dpi * 72
    right_margin_pt = (page_width_px - max_right) / dpi * 72

    # Use the larger of the two margins for consistency
    margin = max(left_margin_pt, right_margin_pt)

    # Ensure minimum margin of 0.5cm and maximum of 2cm
    margin = max(0.5 * cm, min(margin, 2 * cm))

    print(f"DEBUG: Calculated margins from layout: left={left_margin_pt:.1f}pt, right={right_margin_pt:.1f}pt, using={margin:.1f}pt")

    return margin


def create_pdf_from_layout_flow(
    output_path: str,
    layout_data: Dict,
    temp_dir: str = None,
    font_buckets: dict = None,
    margin: float = None,
    enable_footnote_detection: bool = False
) -> str:
    """
    Create PDF from MinerU layout.json using flow-based rendering with dynamic spacing.

    This method uses ReportLab flowables (Paragraph, Spacer) instead of exact
    canvas positioning. Spacing is dynamically adjusted to fit content on each page.

    Styling:
    - Titles: 12pt bold, centered, larger spacing after
    - Body text: 10.5pt, narrower line spacing (12pt leading = 1.14x)
    - Discarded: Page numbers (right-aligned), footnotes (left-aligned)
    - Images: Fixed size (not scaled)

    Args:
        output_path: Where to save the PDF
        layout_data: Parsed layout.json content with pdf_info array
        temp_dir: Temporary directory containing extracted images
        font_buckets: Optional dict with custom bbox height thresholds (not used in flow mode)
        margin: Optional margin in points. If None, calculated from layout data.
        enable_footnote_detection: If True, detect footnotes by position and content pattern

    Returns:
        Path to created document
    """
    builder = DocumentBuilder(output_path, temp_dir=temp_dir, font_buckets=font_buckets, enable_footnote_detection=enable_footnote_detection)
    builder.add_from_layout_json_flow(layout_data, margin=margin)
    builder.finalize()
    return output_path
