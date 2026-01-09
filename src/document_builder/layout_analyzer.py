"""Layout Analyzer Module

Handles all layout analysis logic for PDF rendering:
- Font sizing based on bbox height thresholds
- Median font size calculations
- Gap detection between content blocks
- Spacing calculations with dynamic multipliers
- DPI calculations from page dimensions
- Margin calculations from layout data
"""
from typing import Dict, List, Tuple, Any
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
import re


class LayoutAnalyzer:
    """Analyzes layout data to determine font sizing, spacing, and margins."""

    # Gap detection threshold (30 pixels)
    GAP_THRESHOLD_PX = 30
    # Spacer for detected gaps (0.4cm - same as title spacing)
    LARGE_SPACER = 0.4 * cm

    def __init__(self, font_buckets: dict = None, dpi: float = None):
        """
        Initialize layout analyzer.

        Args:
            font_buckets: Optional dict with custom bbox height thresholds for font sizing
                         Keys: "bucket_9", "bucket_10", "bucket_11", "bucket_12", "bucket_14"
            dpi: Optional DPI for pixel-to-point conversion. If None, will be calculated later.
        """
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

        # Store DPI if provided
        self._dpi = dpi

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

    @property
    def dpi(self) -> float:
        """Get the current DPI value."""
        return self._dpi

    @dpi.setter
    def dpi(self, value: float):
        """Set the DPI value."""
        self._dpi = value

    def calculate_dpi_from_page_size(self, page_size: List[float]) -> float:
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
            calculated_dpi = avg_dpi_letter
        else:
            # A4 is a better match
            calculated_dpi = avg_dpi_a4

        # Store for later use
        self._dpi = calculated_dpi
        return calculated_dpi

    def get_font_size_from_bbox(self, bbox_height: float) -> int:
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

    def calculate_median_bbox_height(self, bbox_heights: List[float]) -> float:
        """
        Calculate median bbox height from a list of heights.

        Uses median (middle value) instead of mode for stability with small samples
        and better handling of outliers.

        Args:
            bbox_heights: List of bbox heights in pixels

        Returns:
            Median bbox height in pixels
        """
        if not bbox_heights:
            return 0

        sorted_heights = sorted(bbox_heights)
        mid = len(sorted_heights) // 2

        if len(sorted_heights) % 2 == 0:
            # Even number of items: average the two middle values
            median_bbox_height = (sorted_heights[mid - 1] + sorted_heights[mid]) / 2
        else:
            # Odd number of items: take the middle value
            median_bbox_height = sorted_heights[mid]

        return median_bbox_height

    def convert_pixels_to_points(self, pixels: float) -> float:
        """
        Convert pixels to points using stored DPI.

        Formula: points = pixels / DPI * 72

        Args:
            pixels: Value in pixels

        Returns:
            Value in points

        Raises:
            ValueError: If DPI has not been set
        """
        if self._dpi is None:
            raise ValueError("DPI must be set before converting pixels to points")

        return pixels / self._dpi * 72

    def is_footnote_block(self, block: Dict, page_height: float) -> bool:
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

    def detect_gap_between_blocks(self, last_block_bottom: float, current_block_top: float) -> bool:
        """
        Detect if there's a significant gap between two blocks.

        Args:
            last_block_bottom: Bottom Y coordinate of previous block (pixels)
            current_block_top: Top Y coordinate of current block (pixels)

        Returns:
            True if gap exceeds threshold
        """
        gap = current_block_top - last_block_bottom
        return gap > self.GAP_THRESHOLD_PX

    def calculate_content_height_with_spacing(
        self,
        content_items: List[Tuple[str, Any, float]],
        page_width: float,
        available_height: float,
        styles: Dict[str, ParagraphStyle]
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
            styles: Dict mapping item types to ParagraphStyle objects
                   Keys: 'title', 'discarded', 'body' (default for text)

        Returns:
            Tuple of (total_height, spacing_sum) in points
        """
        total_height = 0
        spacing_sum = 0

        for item_type, content, base_spacing in content_items:
            if item_type in ('text', 'title', 'discarded'):
                # Determine appropriate style
                if item_type == 'title':
                    style = styles.get('title')
                elif item_type == 'discarded':
                    style = styles.get('discarded')
                else:
                    style = styles.get('body')

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

    def calculate_content_height_with_spacing_dict(
        self,
        content_items: List[Dict],
        page_width: float,
        available_height: float,
        styles: Dict[str, ParagraphStyle]
    ) -> Tuple[float, float]:
        """
        Calculate total height of content items (dict format) with their spacing.

        Args:
            content_items: List of dicts with 'type', 'content', 'spacing' keys
            page_width: Available page width in points
            available_height: Available page height in points
            styles: Dict mapping item types to ParagraphStyle objects
                   Keys: 'title', 'page_number', 'footnote', 'body' (default for text)

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
                    style = styles.get('title')
                elif item_type == 'page_number':
                    style = styles.get('page_number')
                elif item_type == 'footnote':
                    style = styles.get('footnote')
                else:
                    style = styles.get('body')

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

    def calculate_spacing_multiplier(
        self,
        total_content_height: float,
        total_spacing: float,
        available_height: float,
        page_idx: int = 0
    ) -> float:
        """
        Calculate spacing multiplier to fit content on page.

        If content overflows, spacing is reduced proportionally.
        Applies limits to ensure minimum readability (40% of original spacing).

        Args:
            total_content_height: Total height of content without spacing (points)
            total_spacing: Total spacing between content items (points)
            available_height: Available page height (points)
            page_idx: Page number (0-indexed) for debug messages

        Returns:
            Spacing multiplier (1.0 = no adjustment, <1.0 = reduced spacing)
        """
        total_height = total_content_height + total_spacing

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

        return multiplier

    def calculate_margins_from_layout(self, layout_data: Dict) -> float:
        """
        Calculate document margins from layout.json bbox data.

        Finds the leftmost and rightmost content across all pages to determine
        the original PDF's margins.

        Args:
            layout_data: Parsed layout.json content with pdf_info array

        Returns:
            Margin in points (clamped between 0.5cm and 2cm)

        Raises:
            ValueError: If DPI has not been set or layout data is empty
        """
        if self._dpi is None:
            raise ValueError("DPI must be set before calculating margins")

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
        left_margin_pt = self.convert_pixels_to_points(min_left)
        right_margin_pt = self.convert_pixels_to_points(page_width_px - max_right)

        # Use the larger of the two margins for consistency
        margin = max(left_margin_pt, right_margin_pt)

        # Ensure minimum margin of 0.5cm and maximum of 2cm
        margin = max(0.5 * cm, min(margin, 2 * cm))

        print(f"DEBUG: Calculated margins from layout: left={left_margin_pt:.1f}pt, right={right_margin_pt:.1f}pt, using={margin:.1f}pt")

        return margin


def calculate_margins_from_layout(layout_data: Dict, dpi: float) -> float:
    """
    Calculate document margins from layout.json bbox data.

    This is a standalone function for backward compatibility.
    Creates a temporary LayoutAnalyzer instance to perform the calculation.

    Args:
        layout_data: Parsed layout.json content with pdf_info array
        dpi: DPI for pixel-to-point conversion

    Returns:
        Margin in points (clamped between 0.5cm and 2cm)
    """
    analyzer = LayoutAnalyzer(dpi=dpi)
    return analyzer.calculate_margins_from_layout(layout_data)
