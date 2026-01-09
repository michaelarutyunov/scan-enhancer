"""Configuration Constants

Constants for PDF processing pipeline configuration.
"""

# File Processing Limits
MAX_FILE_SIZE_MB = 200  # MinerU API limit

# Progress Steps (for UI progress tracking)
PROGRESS_STEPS = {
    "VALIDATE": 0.02,
    "PREPROCESS_START": 0.05,
    "PREPROCESS_END": 0.15,
    "SUBMIT_API": 0.20,
    "OCR_CHECK": 0.85,
    "PDF_BUILD": 0.85,
    "COMPLETE": 1.0,
}

# Default Font Buckets (line height thresholds in points)
DEFAULT_FONT_BUCKETS = {
    "bucket_9": 17.0,   # 8pt → 9pt threshold
    "bucket_10": 22.0,  # 9pt → 10pt threshold
    "bucket_11": 28.0,  # 10pt → 11pt threshold
    "bucket_12": 30.0,  # 11pt → 12pt threshold
    "bucket_14": 32.0,  # 12pt → 14pt threshold
}

# Binarization Defaults
DEFAULT_BINARIZE_BLOCK_SIZE = 31  # Odd number between 11-51
DEFAULT_BINARIZE_C_CONSTANT = 25  # Between 0-51

# OCR Quality Control Defaults
DEFAULT_QUALITY_CUTOFF = 0.9  # Confidence threshold (0.0-1.0)

# Line Calibration Defaults
DEFAULT_TARGET_LINE_HEIGHT = 34.0  # Maximum line height in pixels before overlap fixing
DEFAULT_OVERLAP_THRESHOLD = -10.0  # Maximum negative gap to ignore for overlap fixing

# Output Format
DEFAULT_OUTPUT_FORMAT = "json"  # Hardcoded for best structure preservation

# Language Options
SUPPORTED_LANGUAGES = {
    "ru": "Russian",
    "ch": "Chinese",
    "en": "English",
    "japan": "Japanese",
    "korean": "Korean",
    "german": "German",
    "french": "French",
    "spanish": "Spanish",
}
