"""PDF Preprocessing Module

Provides image preprocessing for PDF documents before OCR/Layout analysis.
Includes binarization to improve text clarity and reduce noise.
"""
import os
import tempfile
from typing import Optional

try:
    import cv2
    import numpy as np
    from pdf2image import convert_from_path
    import img2pdf
    CV2_AVAILABLE = True
except ImportError as e:
    CV2_AVAILABLE = False
    IMPORT_ERROR = str(e)


def preprocess_pdf(
    input_path: str,
    output_path: Optional[str] = None,
    method: str = "adaptive",
    morph_cleanup: bool = True,
    block_size: int = 31,
    c_constant: int = 10,
    progress_callback=None
) -> str:
    """
    Preprocess PDF by converting each page to image, applying binarization,
    and rebuilding as PDF.

    Args:
        input_path: Path to input PDF file
        output_path: Path for output PDF (if None, creates temp file)
        method: Binarization method - "adaptive", "otsu", or "global"
        morph_cleanup: Whether to apply morphological cleanup (remove small noise)
        block_size: Block size for adaptive thresholding (must be odd)
        c_constant: Constant subtracted from mean for adaptive thresholding
        progress_callback: Optional callback(page_num, total_pages, message) for progress

    Returns:
        Path to binarized PDF file

    Raises:
        ImportError: If OpenCV or pdf2image not available
        ValueError: If input file doesn't exist
    """
    if not CV2_AVAILABLE:
        raise ImportError(
            f"PDF preprocessing requires opencv-python, pdf2image, and img2pdf. "
            f"Missing: {IMPORT_ERROR}"
        )

    if not os.path.exists(input_path):
        raise ValueError(f"Input file not found: {input_path}")

    # Create output path if not provided
    if output_path is None:
        output_path = tempfile.mktemp(suffix="_binarized.pdf")

    # Convert PDF to images
    if progress_callback:
        progress_callback(0, 0, "Converting PDF to images...")

    try:
        images = convert_from_path(input_path, dpi=200)
    except Exception as e:
        raise RuntimeError(f"Failed to convert PDF to images: {e}")

    total_pages = len(images)

    # Process each page
    binarized_images = []

    for i, pil_image in enumerate(images):
        if progress_callback:
            progress_callback(i + 1, total_pages, f"Binarizing page {i + 1}/{total_pages}...")

        # Convert PIL image to numpy array (OpenCV format)
        img_array = np.array(pil_image)

        # Convert to grayscale if needed
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        # Apply binarization
        if method == "adaptive":
            binary = _adaptive_threshold(gray, block_size, c_constant)
        elif method == "otsu":
            binary = _otsu_threshold(gray)
        elif method == "global":
            binary = _global_threshold(gray)
        else:
            raise ValueError(f"Unknown binarization method: {method}")

        # Optional morphological cleanup
        if morph_cleanup:
            binary = _morphological_cleanup(binary)

        # Convert back to PIL Image for img2pdf
        from PIL import Image
        binary_pil = Image.fromarray(binary)
        binarized_images.append(binary_pil)

    # Save binarized images as PDF
    if progress_callback:
        progress_callback(total_pages, total_pages, "Building binarized PDF...")

    try:
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert(binarized_images))
    except Exception as e:
        raise RuntimeError(f"Failed to create binarized PDF: {e}")

    return output_path


def _adaptive_threshold(gray: np.ndarray, block_size: int, c_constant: int) -> np.ndarray:
    """Apply adaptive thresholding using Gaussian-weighted local mean."""
    # Ensure block_size is odd
    if block_size % 2 == 0:
        block_size += 1

    # Ensure block_size is at least 3
    if block_size < 3:
        block_size = 3

    # Apply adaptive threshold
    binary = cv2.adaptiveThreshold(
        gray,
        255,  # Max value
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        c_constant
    )
    return binary


def _otsu_threshold(gray: np.ndarray) -> np.ndarray:
    """Apply Otsu's method for automatic global thresholding."""
    _, binary = cv2.threshold(
        gray,
        0,  # Threshold (ignored for Otsu)
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return binary


def _global_threshold(gray: np.ndarray, threshold: int = 127) -> np.ndarray:
    """Apply simple global thresholding."""
    _, binary = cv2.threshold(
        gray,
        threshold,
        255,
        cv2.THRESH_BINARY
    )
    return binary


def _morphological_cleanup(binary: np.ndarray) -> np.ndarray:
    """Apply morphological operations to remove small noise artifacts."""
    # Create small kernel for noise removal
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))

    # Opening operation (erosion followed by dilation) removes small white spots
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    return cleaned


def is_available() -> bool:
    """Check if preprocessing dependencies are available."""
    return CV2_AVAILABLE


def get_missing_dependencies() -> list:
    """Return list of missing dependencies."""
    missing = []
    try:
        import cv2
    except ImportError:
        missing.append("opencv-python")
    try:
        from pdf2image import convert_from_path
    except ImportError:
        missing.append("pdf2image")
    try:
        import img2pdf
    except ImportError:
        missing.append("img2pdf")
    return missing
