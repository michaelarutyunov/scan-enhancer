"""Coordinate Conversion Utilities

This module provides pure utility functions for converting between different
coordinate systems used in PDF processing:

- MinerU coordinates: Pixels with origin at top-left
- ReportLab coordinates: Points with origin at bottom-left
- DPI calculation from page dimensions
- Margin calculation from layout data

All coordinate conversion functions are pure (no side effects) and can be
easily tested in isolation.
"""

from typing import Dict, List, Tuple


def calculate_dpi_from_page_size(page_size: List[float]) -> float:
    """
    Calculate DPI from page size by comparing to standard paper dimensions.

    MinerU stores bbox coordinates in pixels. We need to determine the DPI
    to convert pixel heights to points for font sizing and coordinate conversion.

    This function compares the pixel dimensions against standard paper sizes
    (US Letter and A4) to determine which standard size provides the most
    consistent DPI calculation across width and height.

    Args:
        page_size: [width, height] in pixels from layout.json

    Returns:
        DPI as a float (typically 72, 96, 150, 200, or 300)

    Examples:
        >>> calculate_dpi_from_page_size([612, 792])  # 72 DPI Letter
        72.0
        >>> calculate_dpi_from_page_size([1700, 2200])  # 200 DPI Letter
        200.0
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


def convert_bbox_to_points(
    bbox: List[float],
    page_height: float,
    dpi: float
) -> Tuple[float, float, float, float]:
    """
    Convert MinerU bbox from pixels to ReportLab coordinates in points.

    This function handles three transformations:
    1. Convert from pixels to points using DPI
    2. Flip Y-axis origin from top-left to bottom-left
    3. Calculate width and height

    Coordinate Systems:
    - MinerU bbox: [x1, y1, x2, y2] in pixels with origin at top-left
    - ReportLab: (x, y, width, height) in points with origin at bottom-left

    Args:
        bbox: [x1, y1, x2, y2] coordinates in pixels from MinerU
        page_height: Height of the page in points (for Y-axis flipping)
        dpi: Dots per inch for pixel-to-point conversion

    Returns:
        Tuple of (x, y, width, height) in ReportLab coordinates (points)
        where (x, y) is the bottom-left corner of the box

    Examples:
        >>> # Box at top-left corner, 100x50 pixels at 72 DPI
        >>> convert_bbox_to_points([0, 0, 100, 50], 792, 72)
        (0.0, 742.0, 100.0, 50.0)

    Notes:
        - Points = Pixels / DPI * 72
        - Y-coordinate flip: ReportLab Y = page_height - MinerU Y2 (bottom of block)
    """
    x1, y1, x2, y2 = bbox

    # Convert from pixels to points
    # Formula: points = pixels / DPI * 72
    x1_pt = x1 / dpi * 72
    y1_pt = y1 / dpi * 72
    x2_pt = x2 / dpi * 72
    y2_pt = y2 / dpi * 72

    width = x2_pt - x1_pt
    height = y2_pt - y1_pt

    # Convert y coordinate: ReportLab y = page_height - MinerU y2 (bottom of block)
    # MinerU y2 is the bottom edge in top-left origin system
    # ReportLab expects bottom-left origin, so we flip it
    rl_y = page_height - y2_pt

    return x1_pt, rl_y, width, height


def pixels_to_points(pixels: float, dpi: float) -> float:
    """
    Convert pixel measurement to points.

    Args:
        pixels: Measurement in pixels
        dpi: Dots per inch

    Returns:
        Measurement in points (1 point = 1/72 inch)

    Examples:
        >>> pixels_to_points(72, 72)
        72.0
        >>> pixels_to_points(150, 150)
        72.0
    """
    return pixels / dpi * 72


def points_to_pixels(points: float, dpi: float) -> float:
    """
    Convert point measurement to pixels.

    Args:
        points: Measurement in points (1 point = 1/72 inch)
        dpi: Dots per inch

    Returns:
        Measurement in pixels

    Examples:
        >>> points_to_pixels(72, 72)
        72.0
        >>> points_to_pixels(72, 150)
        150.0
    """
    return points * dpi / 72


def flip_y_coordinate(y: float, page_height: float) -> float:
    """
    Flip Y coordinate between top-left and bottom-left origin systems.

    This function converts between:
    - Top-left origin (used by MinerU, common in image processing)
    - Bottom-left origin (used by ReportLab/PDF, PostScript standard)

    Args:
        y: Y coordinate in source system
        page_height: Height of the page (in same units as y)

    Returns:
        Y coordinate in flipped system

    Examples:
        >>> flip_y_coordinate(0, 792)  # Top becomes bottom
        792.0
        >>> flip_y_coordinate(792, 792)  # Bottom becomes top
        0.0

    Notes:
        This function is its own inverse:
        flip_y_coordinate(flip_y_coordinate(y, h), h) == y
    """
    return page_height - y


def calculate_margins_from_layout(layout_data: Dict, dpi: float) -> float:
    """
    Calculate document margins from layout.json bbox data.

    Analyzes all content blocks across all pages to find the leftmost and
    rightmost content positions, then calculates margins from the page edges.
    Uses the larger of left/right margins for consistency.

    Args:
        layout_data: Parsed layout.json content with pdf_info array
        dpi: DPI for pixel-to-point conversion

    Returns:
        Margin in points (clamped between 0.5cm and 2cm for safety)

    Examples:
        If content spans from x=50px to x=562px on a 612px wide page at 72 DPI:
        - Left margin: 50px = 50pt
        - Right margin: (612-562)px = 50pt
        - Result: 50pt (≈ 1.76cm)

    Notes:
        - Returns 0.5cm (≈ 14.2pt) as fallback if no pdf_info
        - Clamps result between 0.5cm and 2cm to prevent extreme values
        - Prints debug info showing calculated margins
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
