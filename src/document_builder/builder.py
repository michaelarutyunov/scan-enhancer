"""Document Builder Module - Refactored

Orchestrates PDF rendering by coordinating specialized components:
- FontManager: Font registration and Cyrillic support
- TextExtractor: Text extraction from MinerU structures
- LayoutAnalyzer: Font sizing and layout analysis
- ContentRenderer: Image, table, and equation rendering
- coordinate_utils: Coordinate system conversions

This refactored version delegates work to focused classes while maintaining
the same public API as the original DocumentBuilder.
"""
import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas as pdfcanvas
from typing import Dict, List, Any, Tuple
import os
import tempfile
from collections import defaultdict

# Import extracted classes
from .font_manager import FontManager
from .text_extractor import TextExtractor
from .layout_analyzer import LayoutAnalyzer
from .content_renderer import ContentRenderer
from . import coordinate_utils


class DocumentBuilder:
    """Build PDF document from MinerU structured output.

    This refactored version delegates to specialized components:
    - font_manager: Handles all font operations
    - text_extractor: Extracts and processes text from MinerU structures
    - layout_analyzer: Analyzes layout for font sizing and spacing
    - content_renderer: Renders images, tables, and equations
    - coordinate_utils: Pure utility functions for coordinate conversion
    """

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

        # Initialize specialized components
        self.font_manager = FontManager()
        self.text_extractor = TextExtractor(enable_footnote_detection=enable_footnote_detection)
        self.layout_analyzer = LayoutAnalyzer(font_buckets=font_buckets)
        self.content_renderer = ContentRenderer(temp_dir=temp_dir, font_name=self.font_manager.font_name)

        # Create custom styles using font manager
        self._setup_styles()

    def _setup_styles(self):
        """Create custom paragraph styles using registered fonts."""
        # Body style with regular font
        self.body_style = ParagraphStyle(
            'Body',
            parent=self.styles['Normal'],
            fontName=self.font_manager.get_font_name(bold=False),
            fontSize=11,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        )

        # Body style with bold font
        self.body_style_bold = ParagraphStyle(
            'BodyBold',
            parent=self.body_style,
            fontName=self.font_manager.get_font_name(bold=True),
            fontSize=11,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        )

        # Heading style
        self.heading_style = ParagraphStyle(
            'Heading',
            parent=self.styles['Heading1'],
            fontName=self.font_manager.get_font_name(bold=False),
            fontSize=14,
            spaceAfter=12,
        )

        # Caption style
        self.caption_style = ParagraphStyle(
            'Caption',
            parent=self.styles['Normal'],
            fontName=self.font_manager.get_font_name(bold=False),
            fontSize=9,
            alignment=TA_CENTER,
            spaceAfter=6,
        )

        # Flow mode styles (used when keep_original_margins=False)
        # Titles: 12pt bold, centered, larger spacing after
        self.flow_title_style = ParagraphStyle(
            'FlowTitle',
            parent=self.styles['Normal'],
            fontName=self.font_manager.get_font_name(bold=True),
            fontSize=12,
            leading=15,  # ~1.25x for titles
            alignment=TA_CENTER,
            spaceAfter=0.4 * cm,  # Larger interval after titles
        )

        # Body text: 10.5pt, narrower line spacing (1.14x)
        self.flow_body_style = ParagraphStyle(
            'FlowBody',
            parent=self.styles['Normal'],
            fontName=self.font_manager.get_font_name(bold=False),
            fontSize=10.5,
            leading=12,  # Narrower line spacing (1.14x)
            alignment=TA_JUSTIFY,
            spaceAfter=0.1 * cm,  # Base spacing
        )

        # Page numbers: small, right-aligned
        self.flow_page_number_style = ParagraphStyle(
            'FlowPageNumber',
            parent=self.styles['Normal'],
            fontName=self.font_manager.get_font_name(bold=False),
            fontSize=8,
            leading=10,
            alignment=TA_RIGHT,
            spaceAfter=0,
        )

        # Footnotes: small, left-aligned
        self.flow_footnote_style = ParagraphStyle(
            'FlowFootnote',
            parent=self.styles['Normal'],
            fontName=self.font_manager.get_font_name(bold=False),
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
                    self.content_renderer.add_image(item, self.story, self.caption_style)
                elif item_type == "header":
                    self._add_header(item.get("text", ""))
                elif item_type == "table":
                    self.content_renderer.add_table(item, self.story)
                elif item_type == "equation":
                    self.content_renderer.add_equation(item.get("text", ""), self.story)
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
        first_page_size = pdf_info[0].get("page_size", [612, 792])
        dpi = self.layout_analyzer.calculate_dpi_from_page_size(first_page_size)
        print(f"DEBUG: Calculated DPI from page size {first_page_size}: {dpi:.1f}")

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
            else:
                # Convert original page size from pixels to points
                original_page_width_px, original_page_height_px = original_page_size_px
                page_width_pt = coordinate_utils.pixels_to_points(original_page_width_px, dpi)
                page_height_pt = coordinate_utils.pixels_to_points(original_page_height_px, dpi)
                self._canvas.setPageSize((page_width_pt, page_height_pt))
                current_page_width, current_page_height = page_width_pt, page_height_pt

            # Process content blocks (preproc_blocks)
            preproc_blocks = page_data.get("preproc_blocks", [])
            for block in preproc_blocks:
                self._render_block(block, current_page_height, original_page_size_px[1], dpi)

            # Process discarded blocks (page numbers, etc.)
            discarded_blocks = page_data.get("discarded_blocks", [])
            for block in discarded_blocks:
                self._render_block(block, current_page_height, original_page_size_px[1], dpi, is_discarded=True)

            # Move to next page
            self._canvas.showPage()

        # Save the document
        self._canvas.save()
        self._canvas = None

    def _render_block(self, block: Dict, page_height: float, original_page_height_px: float, dpi: float, is_discarded: bool = False):
        """
        Render a single block at its exact position.

        Args:
            block: Block data with type, bbox, and lines
            page_height: Height of the page in points for coordinate conversion
            original_page_height_px: Original page height in pixels from layout.json
            dpi: DPI for pixel-to-point conversion
            is_discarded: Whether this is a discarded block (page number)
        """
        block_type = block.get("type", "text")
        bbox = block.get("bbox", [0, 0, 100, 20])

        # Convert bbox coordinates using coordinate_utils
        x, y, width, height = coordinate_utils.convert_bbox_to_points(bbox, page_height, dpi)

        # Apply margin offset if using consistent margins
        if hasattr(self, '_use_consistent_margins_layout') and self._use_consistent_margins_layout:
            x += self._margin_offset_x
            y += self._margin_offset_y

        if block_type == "image":
            self.content_renderer.render_image_block(block, self._canvas, x, y, width, height)
        else:
            # Text, title, or discarded - pass page_height for line positioning
            self._render_text_block(block, x, y, width, height, block_type, is_discarded, page_height, original_page_height_px, dpi)

    def _render_text_block(self, block: Dict, x: float, y: float, width: float, height: float,
                           block_type: str, is_discarded: bool, page_height: float, original_page_height_px: float, dpi: float):
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
            dpi: DPI for pixel-to-point conversion
        """
        # Extract text lines using text_extractor
        text_lines = self.text_extractor.extract_text_lines_from_block(block)
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

        # Step 2 & 3: Determine font size using layout_analyzer
        if block_type == "title":
            # Force titles to 12pt font for consistency
            font_size = 12
        elif block_type == "discarded":
            # Page numbers, footnotes already marked as discarded → 8pt
            font_size = 8
        elif self.enable_footnote_detection and self.text_extractor.is_footnote_block(block, original_page_height_px):
            # Detected footnote (not marked as discarded by MinerU) → 8pt
            font_size = 8
        elif bbox_heights:
            # Calculate median bbox height
            median_bbox_height_px = self.layout_analyzer.calculate_median_bbox_height(bbox_heights)

            # Convert pixels to points using DPI
            median_bbox_height_pt = coordinate_utils.pixels_to_points(median_bbox_height_px, dpi)

            # Map point height to font size
            font_size = self.layout_analyzer.get_font_size_from_bbox(median_bbox_height_pt)

            # DEBUG: Print first 10 blocks for verification
            if not hasattr(self, '_debug_blocks_printed'):
                self._debug_blocks_printed = 0
            if self._debug_blocks_printed < 10:
                self._debug_blocks_printed += 1
                print(f"DEBUG Block {self._debug_blocks_printed}: type={block_type}, median_bbox={median_bbox_height_px:.1f}px ({median_bbox_height_pt:.1f}pt) → font_size={font_size}pt | lines={len(text_lines)} | text='{text_lines[0][:40] if text_lines else ''}...'")
        else:
            # Fallback to default sizes
            if block_type == "title":
                font_size = 12
            elif block_type == "discarded":
                font_size = 8
            else:
                font_size = 11

        # Determine font name (bold for titles)
        font_name = self.font_manager.get_font_name(bold=(block_type == "title"))

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
            self._canvas.setFont(self.font_manager.get_font_name(), 11)
            # Render all lines as fallback using same fixed line height
            for i, text_line in enumerate(text_lines):
                line_y = y + height - ((i + 1) * FIXED_LINE_HEIGHT)
                self._canvas.drawString(x, line_y, text_line[:80])

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

        # Calculate DPI from page size
        first_page_size = pdf_info[0].get("page_size", [612, 792])
        dpi = self.layout_analyzer.calculate_dpi_from_page_size(first_page_size)
        print(f"DEBUG: Flow mode - Calculated DPI from page size {first_page_size}: {dpi:.1f}")

        # Calculate or use provided margin
        if margin is None:
            # Calculate margins from original PDF layout using coordinate_utils
            margin = coordinate_utils.calculate_margins_from_layout(layout_data, dpi)
        else:
            print(f"DEBUG: Flow mode - Using provided margin: {margin:.1f}pt")

        # Store margin for finalize() to use
        self._flow_margin = margin

        # Page dimensions with calculated/provided margins
        page_width_pt, page_height_pt = A4
        available_width = page_width_pt - (2 * margin)
        available_height = page_height_pt - (2 * margin)

        # Group blocks by page_idx
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

                # Check for gap between blocks using layout_analyzer
                if last_block_bottom is not None and self.layout_analyzer.detect_gap_between_blocks(last_block_bottom, block_top):
                    # Use different spacer sizes: 0.4cm before titles, 2.5cm for other gaps
                    if block_type == 'title':
                        spacer_size = 0.4 * cm
                    else:
                        spacer_size = self.layout_analyzer.LARGE_SPACER

                    pages[page_idx].append({
                        'type': 'spacer',
                        'content': spacer_size,
                        'spacing': 0,
                        'is_first_in_group': False,
                        'is_last_in_group': False
                    })

                # Extract text lines using text_extractor
                text_lines = self.text_extractor.extract_text_lines_from_block(block)

                if block_type == "image":
                    # Calculate image height in points
                    bbox_height = bbox[3] - bbox[1]
                    image_height_pt = coordinate_utils.pixels_to_points(bbox_height, dpi)

                    # Extract image path
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

                    # Store image with metadata
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
                    # Check for footnote detection using text_extractor
                    is_footnote = False
                    if self.enable_footnote_detection and block_type == "text":
                        is_footnote = self.text_extractor.is_footnote_block(block, page_height_px)

                    # For titles, track first/last line for proper spacing
                    if block_type == "title":
                        for i, line in enumerate(text_lines):
                            is_first = (i == 0)
                            is_last = (i == len(text_lines) - 1)
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
                text_lines = self.text_extractor.extract_text_lines_from_block(block)
                if not text_lines:
                    continue

                # Determine if page number or footnote based on content
                for line in text_lines:
                    # Check if line is purely numeric
                    cleaned = line.strip().replace('-', '').replace('—', '').replace(' ', '').replace('.', '')
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

            # Calculate total height with base spacing using layout_analyzer
            styles_dict = {
                'title': self.flow_title_style,
                'page_number': self.flow_page_number_style,
                'footnote': self.flow_footnote_style,
                'body': self.flow_body_style
            }
            total_text_height, total_spacing = self.layout_analyzer.calculate_content_height_with_spacing_dict(
                content_items, available_width, available_height, styles_dict
            )

            # Calculate spacing multiplier using layout_analyzer
            multiplier = self.layout_analyzer.calculate_spacing_multiplier(
                total_text_height, total_spacing, available_height, page_idx
            )

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
                        adjusted_spacing = 0.1 * cm

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

        # Clean up temporary image files using content_renderer
        self.content_renderer.cleanup_temp_files()


# Helper functions (kept for backward compatibility)

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
