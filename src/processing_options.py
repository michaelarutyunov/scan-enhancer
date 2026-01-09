"""Processing Options Dataclass

Configuration options for PDF processing pipeline.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional

from .config import (
    DEFAULT_FONT_BUCKETS,
    DEFAULT_BINARIZE_BLOCK_SIZE,
    DEFAULT_BINARIZE_C_CONSTANT,
    DEFAULT_QUALITY_CUTOFF,
)


@dataclass
class ProcessingOptions:
    """Configuration options for PDF processing pipeline.

    This dataclass encapsulates all configuration parameters needed for the
    PDF processing pipeline, including preprocessing, API settings, OCR correction,
    and PDF generation options.

    Attributes:
        pdf_path: Path to the input PDF file to process
        language: Language code for OCR (e.g., "ru" for Russian, "en" for English)

        # Output Options
        download_raw: If True, save and return raw MinerU output ZIP
        keep_original_margins: If True, use exact positioning (Exact Layout mode); if False, use flow-based rendering (Flow Layout mode)

        # Preprocessing Options
        binarize_enabled: If True, preprocess PDF with binarization before sending to MinerU
        binarize_block_size: Block size for adaptive thresholding (odd number, 11-51)
        binarize_c_constant: C constant subtracted from mean for adaptive thresholding (0-51)

        # MinerU API Options
        enable_formula: If True, enable MinerU formula recognition; if False, treat as text

        # PDF Generation Options
        enable_footnote_detection: If True, detect footnotes by position and content pattern (works in both modes)
        font_buckets: Dict of line height thresholds for font size classification (only applies to Exact Layout mode)

        # OCR Quality Control
        enable_ocr_correction: If True, pause for manual OCR correction of low-confidence items
        quality_cutoff: Confidence threshold for flagging items for review (0.0-1.0)

        # Internal State (populated by caller)
        original_filename: Original filename for final output naming (before preprocessing)
    """

    # Required
    pdf_path: str
    language: str = "ru"

    # Output Options
    download_raw: bool = True
    keep_original_margins: bool = True

    # Preprocessing Options
    binarize_enabled: bool = True
    binarize_block_size: int = DEFAULT_BINARIZE_BLOCK_SIZE
    binarize_c_constant: int = DEFAULT_BINARIZE_C_CONSTANT

    # MinerU API Options
    enable_formula: bool = False

    # PDF Generation Options
    enable_footnote_detection: bool = False
    font_buckets: Dict[str, float] = field(default_factory=lambda: DEFAULT_FONT_BUCKETS.copy())

    # OCR Quality Control
    enable_ocr_correction: bool = True
    quality_cutoff: float = DEFAULT_QUALITY_CUTOFF

    # Internal State
    original_filename: Optional[str] = None

    def __post_init__(self):
        """Validate configuration options after initialization."""
        # Validate binarize_block_size is odd
        if self.binarize_enabled:
            if self.binarize_block_size % 2 == 0:
                raise ValueError(
                    f"binarize_block_size must be odd, got {self.binarize_block_size}"
                )
            if not (11 <= self.binarize_block_size <= 51):
                raise ValueError(
                    f"binarize_block_size must be between 11-51, got {self.binarize_block_size}"
                )
            if not (0 <= self.binarize_c_constant <= 51):
                raise ValueError(
                    f"binarize_c_constant must be between 0-51, got {self.binarize_c_constant}"
                )

        # Validate quality_cutoff
        if not (0.0 <= self.quality_cutoff <= 1.0):
            raise ValueError(
                f"quality_cutoff must be between 0.0-1.0, got {self.quality_cutoff}"
            )
