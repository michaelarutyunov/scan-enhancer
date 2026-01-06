"""Document Builder Module

Renders MinerU JSON/Markdown output to PDF document.
"""
import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from typing import Dict, List, Any
import os
import tempfile


class DocumentBuilder:
    """Build PDF document from MinerU structured output."""

    def __init__(self, output_path: str, temp_dir: str = None):
        """
        Initialize document builder.

        Args:
            output_path: Where to save the final PDF
            temp_dir: Optional temporary directory containing extracted images
        """
        self.output_path = output_path
        self.temp_dir = temp_dir
        self.story = []
        self.styles = getSampleStyleSheet()
        self.temp_files = []

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
            - Page breaks via page_idx field
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

        # Track current page for page breaks
        current_page_idx = None

        for i, item in enumerate(items):
            item_type = item.get("type", "")
            page_idx = item.get("page_idx")

            # Check for page break using page_idx field
            # Insert break BEFORE processing first item of new page
            # This ensures page numbers (discarded items) stay on their original page
            if page_idx is not None and current_page_idx is not None and page_idx != current_page_idx:
                # Page changed, insert a page break before adding this item
                self.story.append(PageBreak())

            # Update current page tracker
            if page_idx is not None:
                current_page_idx = page_idx

            if item_type == "text":
                text = item.get("text", "")
                text_level = item.get("text_level")
                # Look ahead to check if next items are page numbers on same page
                # If so, don't add trailing spacer to save space
                next_item_has_page_number = False
                if i + 1 < len(items):
                    next_item = items[i + 1]
                    if (next_item.get("type") == "discarded" and
                        next_item.get("page_idx") == page_idx and
                        next_item.get("text", "").strip().isdigit()):
                        next_item_has_page_number = True

                # text_level=1 indicates section headers (bold styling)
                if text_level == 1:
                    self._add_text_block(text, style=self.body_style_bold, skip_trailing_space=next_item_has_page_number)
                else:
                    self._add_text_block(text, style=self.body_style, skip_trailing_space=next_item_has_page_number)
            elif item_type == "image":
                self._add_image(item)
            elif item_type == "header":
                # Headers are like text but with different styling
                self._add_header(item.get("text", ""))
            elif item_type == "table":
                self._add_table(item)
            elif item_type == "equation":
                self._add_equation(item.get("text", ""))
            elif item_type in ("page_footnote", "page_number"):
                # Skip page-level metadata
                continue
            else:
                # Unknown type, try to add as text
                text = item.get("text", "")
                text_level = item.get("text_level")

                # Look ahead for page number
                next_item_has_page_number = False
                if i + 1 < len(items):
                    next_item = items[i + 1]
                    if (next_item.get("type") == "discarded" and
                        next_item.get("page_idx") == page_idx and
                        next_item.get("text", "").strip().isdigit()):
                        next_item_has_page_number = True

                if text_level == 1:
                    self._add_text_block(text, style=self.body_style_bold, skip_trailing_space=next_item_has_page_number)
                else:
                    self._add_text_block(text, style=self.body_style, skip_trailing_space=next_item_has_page_number)

    def add_from_mineru_markdown(self, markdown_text: str):
        """
        Build PDF from MinerU Markdown output.

        Args:
            markdown_text: Markdown content from MinerU
        """
        self._add_markdown_text(markdown_text)

    def _add_text_block(self, text: str, style=None, skip_trailing_space=False):
        """
        Add a text paragraph to the document.

        Splits text by newlines and creates a separate Paragraph
        for each line with the specified style.

        Args:
            text: The text content to add
            style: Optional ParagraphStyle to use (defaults to body_style)
            skip_trailing_space: If True, don't add trailing spacer (saves space before page numbers)
        """
        if not text or not text.strip():
            return

        if style is None:
            style = self.body_style

        # Split by lines and add each as a paragraph
        for line in text.split('\n'):
            line = line.strip()
            if line:
                self.story.append(Paragraph(line, style))

        if not skip_trailing_space:
            self.story.append(Spacer(1, 0.2 * cm))

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
        doc = SimpleDocTemplate(
            self.output_path,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
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
    temp_dir: str = None
) -> str:
    """
    Helper function to create PDF from MinerU output.

    Args:
        output_path: Where to save the PDF
        content: MinerU JSON or Markdown content
        content_type: "json" or "markdown"
        temp_dir: Optional temporary directory containing extracted images

    Returns:
        Path to created document
    """
    builder = DocumentBuilder(output_path, temp_dir=temp_dir)

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
