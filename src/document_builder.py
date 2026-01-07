"""Document Builder Module

Renders MinerU JSON/Markdown output to PDF document.
"""
import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
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

    def __init__(self, output_path: str, temp_dir: str = None, use_consistent_margins: bool = False, font_buckets: dict = None):
        """
        Initialize document builder.

        Args:
            output_path: Where to save the final PDF
            temp_dir: Optional temporary directory containing extracted images
            use_consistent_margins: If True, use 1cm margins; otherwise use 2cm default
            font_buckets: Optional dict with custom bbox height thresholds for font sizing
                         Keys: "bucket_9", "bucket_10", "bucket_11", "bucket_12", "bucket_14"
        """
        self.output_path = output_path
        self.temp_dir = temp_dir
        self.use_consistent_margins = use_consistent_margins
        self.story = []
        self.styles = getSampleStyleSheet()
        self.temp_files = []

        # Font bucket thresholds (default values in POINTS, not pixels!)
        # These thresholds work with bbox heights converted to points
        # Typical line heights are ~1.2x the font size
        # 9pt font → ~11pt line height, 10pt → ~12pt, 11pt → ~13pt, 12pt → ~14pt, 14pt → ~17pt
        self.font_bucket_9 = font_buckets.get("bucket_9", 11.5) if font_buckets else 11.5
        self.font_bucket_10 = font_buckets.get("bucket_10", 12.5) if font_buckets else 12.5
        self.font_bucket_11 = font_buckets.get("bucket_11", 14.0) if font_buckets else 14.0
        self.font_bucket_12 = font_buckets.get("bucket_12", 16.0) if font_buckets else 16.0
        self.font_bucket_14 = font_buckets.get("bucket_14", 18.5) if font_buckets else 18.5

        # DEBUG: Print font bucket thresholds
        print("=" * 80)
        print("DEBUG: Font bucket thresholds being used (in points):")
        print(f"  bucket_9 (< {self.font_bucket_9}) → 9pt")
        print(f"  bucket_10 (< {self.font_bucket_10}) → 10pt")
        print(f"  bucket_11 (< {self.font_bucket_11}) → 11pt")
        print(f"  bucket_12 (< {self.font_bucket_12}) → 12pt")
        print(f"  bucket_14 (< {self.font_bucket_14}) → 13pt")
        print(f"  ≥ {self.font_bucket_14} → 14pt")
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
            self._render_text_block(block, x, y, width, height, block_type, is_discarded, page_height)

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

    def _render_text_block(self, block: Dict, x: float, y: float, width: float, height: float,
                           block_type: str, is_discarded: bool, page_height: float):
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
            page_height: Height of the page for coordinate conversion
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
        if bbox_heights:
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
                print(f"DEBUG Block {self._debug_blocks_printed}: median_bbox={median_bbox_height_px:.1f}px ({median_bbox_height_pt:.1f}pt) → font_size={font_size}pt | lines={len(text_lines)} | text='{text_lines[0][:40] if text_lines else ''}...'")
        else:
            # Fallback to default sizes
            font_size = 14 if block_type == "title" else 11

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
        # Use consistent 1cm margins if requested, otherwise use default 2cm
        margin = 1 * cm if self.use_consistent_margins else 2 * cm

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
    font_buckets: dict = None
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

    Returns:
        Path to created document
    """
    builder = DocumentBuilder(output_path, temp_dir=temp_dir, font_buckets=font_buckets)
    builder.add_from_layout_json(layout_data, use_consistent_margins=use_consistent_margins)
    # Note: add_from_layout_json() saves the document directly
    return output_path
