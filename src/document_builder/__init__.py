"""Document Builder Package

This package provides components for building PDF documents from MinerU output:

Core Classes:
- DocumentBuilder: Main orchestrator class (from builder.py)
- FontManager: Font registration and Cyrillic support
- TextExtractor: Text extraction from MinerU structures
- LayoutAnalyzer: Font sizing and layout analysis
- ContentRenderer: Image, table, and equation rendering

Utilities:
- coordinate_utils: Coordinate conversion functions

Helper Functions:
- create_pdf_from_mineru: Create PDF from MinerU JSON/Markdown
- create_pdf_from_layout: Create PDF with exact positioning
- create_pdf_from_layout_flow: Create PDF with flow-based rendering
"""

# Import core classes
from .builder import (
    DocumentBuilder,
    create_pdf_from_mineru,
    create_pdf_from_layout,
    create_pdf_from_layout_flow,
)
from .font_manager import FontManager
from .text_extractor import TextExtractor
from .layout_analyzer import LayoutAnalyzer, calculate_margins_from_layout
from .content_renderer import ContentRenderer
from . import coordinate_utils

# Expose public API
__all__ = [
    # Main builder class
    'DocumentBuilder',

    # Helper functions
    'create_pdf_from_mineru',
    'create_pdf_from_layout',
    'create_pdf_from_layout_flow',
    'calculate_margins_from_layout',

    # Component classes
    'FontManager',
    'TextExtractor',
    'LayoutAnalyzer',
    'ContentRenderer',

    # Utilities module
    'coordinate_utils',
]
