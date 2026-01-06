"""Utilities Module

Helper functions for the PDF processing application.
"""
import os
import re
from typing import Tuple


def validate_pdf_path(pdf_path: str) -> bool:
    """
    Validate PDF file exists and has correct extension.

    Args:
        pdf_path: Path to PDF file

    Returns:
        True if valid, False otherwise
    """
    if not pdf_path:
        return False

    if not os.path.exists(pdf_path):
        return False

    if not pdf_path.lower().endswith('.pdf'):
        return False

    return True


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "45.3 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def clean_filename(filename: str) -> str:
    """
    Clean filename for safe saving.

    Args:
        filename: Original filename

    Returns:
        Cleaned filename
    """
    # Remove path components
    filename = os.path.basename(filename)

    # Remove extension
    name, _ = os.path.splitext(filename)

    # Replace invalid characters
    name = re.sub(r'[^\w\s-]', '', name)

    # Replace spaces with underscores
    name = re.sub(r'\s+', '_', name)

    # Limit length
    if len(name) > 50:
        name = name[:50]

    return name or 'document'


def check_file_size_limit(file_path: str, max_mb: int = 200) -> Tuple[bool, float, str]:
    """
    Check if file is within size limit.

    Args:
        file_path: Path to file
        max_mb: Maximum size in MB (default 200 for MinerU API)

    Returns:
        (is_valid, size_mb, message)
    """
    try:
        size_bytes = os.path.getsize(file_path)
        size_mb = size_bytes / (1024 * 1024)

        if size_mb > max_mb:
            return False, size_mb, f"File size ({size_mb:.1f} MB) exceeds limit of {max_mb} MB"

        return True, size_mb, "OK"
    except Exception as e:
        return False, 0, f"Error checking file size: {str(e)}"
