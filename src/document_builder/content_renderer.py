"""Content Renderer Module

Handles rendering of non-text content elements (images, tables, equations)
for PDF document generation.
"""
import os
import base64
import tempfile
from typing import Dict, Tuple, Optional
from reportlab.lib.units import cm
from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


class ContentRenderer:
    """Handles rendering of images, tables, and equations for PDF documents."""

    def __init__(self, temp_dir: str = None, font_name: str = 'Helvetica'):
        """
        Initialize content renderer.

        Args:
            temp_dir: Optional temporary directory containing extracted images
            font_name: Font name to use for rendering (must support Cyrillic if needed)
        """
        self.temp_dir = temp_dir
        self.font_name = font_name
        self.temp_files = []  # Track temporary files for cleanup
        self.styles = getSampleStyleSheet()

    def add_image(self, item: Dict, story: list, caption_style: ParagraphStyle = None):
        """
        Add an image from MinerU output to the document story.

        Handles multiple image formats:
        - img_path: Relative path to image in temp_dir (MinerU batch format)
        - image: Base64 data URI or HTTP URL (fallback)

        Supports both caption and image_caption fields.

        Args:
            item: Dictionary containing image data with keys:
                - img_path: Relative path like "images/xxx.jpg"
                - image: Base64 or URL (fallback)
                - image_caption/caption: Optional caption text
            story: ReportLab story list to append elements to
            caption_style: Optional ParagraphStyle for caption text
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
            story.append(rl_image)
            story.append(Spacer(1, 0.3 * cm))

            # Add caption if present
            if caption:
                # Use provided caption style or create default
                if caption_style is None:
                    caption_style = ParagraphStyle(
                        'Caption',
                        parent=self.styles['Normal'],
                        fontName=self.font_name,
                        fontSize=9,
                        alignment=TA_CENTER,
                        spaceAfter=6,
                    )
                story.append(Paragraph(caption, caption_style))
                story.append(Spacer(1, 0.3 * cm))

        except Exception as e:
            print(f"Warning: Could not add image: {e}")
            # Add placeholder text
            body_style = self.styles['Normal']
            story.append(Paragraph(f"[Image: {caption or 'No caption'}]", body_style))

    def render_image_block(self, block: Dict, canvas, x: float, y: float, width: float, height: float):
        """
        Render an image block at exact position on canvas.

        Args:
            block: Block data with image path in lines/spans or blocks/lines/spans
            canvas: ReportLab Canvas object for drawing
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
                    canvas.drawImage(full_path, x, y, width=width, height=height,
                                    preserveAspectRatio=True, anchor='sw')
                except Exception as e:
                    print(f"Warning: Could not draw image {full_path}: {e}")
            else:
                print(f"Warning: Image file not found: {full_path}")

    def add_table(self, item: Dict, story: list):
        """
        Add a table from MinerU output to the document story.

        Creates a ReportLab Table with styling including borders
        and header formatting.

        Args:
            item: Dictionary containing table data with key:
                - content: List of lists representing table rows
            story: ReportLab story list to append elements to
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

            story.append(table)
            story.append(Spacer(1, 0.5 * cm))

        except Exception as e:
            print(f"Warning: Could not add table: {e}")

    def add_equation(self, equation_text: str, story: list):
        """
        Add a mathematical equation to the document story.

        Currently renders equations as monospace text. Full LaTeX
        rendering would require additional dependencies.

        Args:
            equation_text: LaTeX or plain text equation
            story: ReportLab story list to append elements to
        """
        if not equation_text:
            return

        # For LaTeX equations, we'd need a LaTeX renderer
        # For now, render as monospace text
        try:
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

            story.append(Paragraph(equation_text, eq_style))
            story.append(Spacer(1, 0.3 * cm))

        except Exception as e:
            print(f"Warning: Could not add equation: {e}")
            body_style = self.styles['Normal']
            story.append(Paragraph(equation_text, body_style))

    def cleanup_temp_files(self):
        """
        Clean up temporary image files created during rendering.

        Should be called after document generation is complete.
        """
        for tmp_file in self.temp_files:
            try:
                if os.path.exists(tmp_file):
                    os.unlink(tmp_file)
            except Exception as e:
                print(f"Warning: Could not delete temp file {tmp_file}: {e}")

        self.temp_files = []
