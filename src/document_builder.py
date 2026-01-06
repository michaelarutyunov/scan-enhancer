"""Document Builder Module

Renders MinerU JSON/Markdown output to PDF document.
"""
import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from typing import Dict, List, Any
import os
import tempfile


class DocumentBuilder:
    """Build PDF document from MinerU structured output."""

    def __init__(self, output_path: str):
        """
        Initialize document builder.

        Args:
            output_path: Where to save the final PDF
        """
        self.output_path = output_path
        self.story = []
        self.styles = getSampleStyleSheet()
        self.temp_files = []

        # Setup fonts for Cyrillic support
        self._setup_fonts()

    def _setup_fonts(self):
        """Register fonts that support Cyrillic characters."""
        # Try to register DejaVu Sans (common on Linux)
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',  # macOS
            'C:\\Windows\\Fonts\\arial.ttf',  # Windows
        ]

        self.font_name = 'Helvetica'  # Default fallback

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
                    self.font_name = 'DejaVuSans'
                    break
                except Exception:
                    continue

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

    def add_from_mineru_json(self, content: Dict):
        """
        Build PDF from MinerU JSON output.

        Args:
            content: MinerU JSON response with structured content
        """
        # MinerU JSON structure typically has:
        # - content: list of content items in reading order
        # - Each item has type: text, image, table, equation, etc.

        if not content or "content" not in content:
            # Fallback: try as markdown
            text_content = content.get("text", "") if isinstance(content, dict) else str(content)
            self._add_markdown_text(text_content)
            return

        items = content["content"]

        for item in items:
            item_type = item.get("type", "")

            if item_type == "text":
                self._add_text_block(item.get("text", ""))
            elif item_type == "image":
                self._add_image(item)
            elif item_type == "table":
                self._add_table(item)
            elif item_type == "equation":
                self._add_equation(item.get("text", ""))
            else:
                # Unknown type, try to add as text
                self._add_text_block(item.get("text", ""))

    def add_from_mineru_markdown(self, markdown_text: str):
        """
        Build PDF from MinerU Markdown output.

        Args:
            markdown_text: Markdown content from MinerU
        """
        self._add_markdown_text(markdown_text)

    def _add_text_block(self, text: str):
        """Add a text paragraph."""
        if not text or not text.strip():
            return

        # Escape XML special characters for ReportLab
        clean_text = (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )

        # Split into paragraphs
        paragraphs = clean_text.split("\n\n")

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Handle headings
            if para.startswith("# "):
                self.story.append(Paragraph(para[2:], self.heading_style))
            elif para.startswith("## "):
                self.story.append(Paragraph(para[3:], self.heading_style))
            else:
                # Regular paragraph
                # Preserve line breaks within paragraphs
                lines = para.split("\n")
                for line in lines:
                    line = line.strip()
                    if line:
                        self.story.append(Paragraph(line, self.body_style))

            self.story.append(Spacer(1, 0.3 * cm))

    def _add_markdown_text(self, markdown_text: str):
        """Add markdown-formatted text."""
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
        """Add an image from MinerU output."""
        # MinerU may provide image data or path
        img_data = item.get("image")
        caption = item.get("caption", "")

        if not img_data:
            return

        try:
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
        """Add a table from MinerU output."""
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
        """Add a mathematical equation."""
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
    content_type: str = "json"
) -> str:
    """
    Helper function to create PDF from MinerU output.

    Args:
        output_path: Where to save the PDF
        content: MinerU JSON or Markdown content
        content_type: "json" or "markdown"

    Returns:
        Path to created document
    """
    builder = DocumentBuilder(output_path)

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
