"""Utilities Module

Helper functions for the PDF processing application.
"""
import os
import re
from typing import Tuple

from .exceptions import InvalidFileError, FileSizeLimitExceededError


def validate_pdf_path(pdf_path: str) -> None:
    """
    Validate PDF file exists and has correct extension.

    Args:
        pdf_path: Path to PDF file

    Raises:
        InvalidFileError: If file doesn't exist or has wrong extension
    """
    if not pdf_path:
        raise InvalidFileError("PDF path cannot be empty")

    if not os.path.exists(pdf_path):
        raise InvalidFileError(f"File does not exist: {pdf_path}")

    if not pdf_path.lower().endswith('.pdf'):
        raise InvalidFileError(f"File must have .pdf extension: {pdf_path}")


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


def check_file_size_limit(file_path: str, max_mb: int = 200) -> float:
    """
    Check if file is within size limit.

    Args:
        file_path: Path to file
        max_mb: Maximum size in MB (default 200 for MinerU API)

    Returns:
        File size in MB

    Raises:
        FileSizeLimitExceededError: If file exceeds size limit
        InvalidFileError: If file size cannot be determined
    """
    try:
        size_bytes = os.path.getsize(file_path)
        size_mb = size_bytes / (1024 * 1024)

        if size_mb > max_mb:
            raise FileSizeLimitExceededError(size_mb, max_mb)

        return size_mb
    except FileSizeLimitExceededError:
        raise
    except Exception as e:
        raise InvalidFileError(f"Error checking file size: {str(e)}")
