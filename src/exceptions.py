"""Custom Exception Hierarchy

Exception hierarchy for scan-enhancer application providing better error handling
and more granular exception types for different failure scenarios.
"""


class ScanEnhancerError(Exception):
    """Base exception for all scan-enhancer errors.

    This is the root of the exception hierarchy. Catching this exception
    will catch all custom exceptions from the scan-enhancer application.
    """
    pass


# Validation Errors
class ValidationError(ScanEnhancerError):
    """Raised when input validation fails."""
    pass


class InvalidFileError(ValidationError):
    """Raised when file validation fails (doesn't exist, wrong extension, etc.)."""
    pass


class FileSizeLimitExceededError(ValidationError):
    """Raised when file exceeds size limits (e.g., MinerU 200MB limit)."""

    def __init__(self, file_size: float, max_size: float):
        self.file_size = file_size
        self.max_size = max_size
        super().__init__(
            f"File size {file_size:.1f} MB exceeds maximum allowed size {max_size:.1f} MB"
        )


class InvalidConfigurationError(ValidationError):
    """Raised when configuration parameters are invalid."""
    pass


# Preprocessing Errors
class PreprocessingError(ScanEnhancerError):
    """Base class for preprocessing-related errors."""
    pass


class BinarizationError(PreprocessingError):
    """Raised when PDF binarization fails."""
    pass


class LineCalibrationError(PreprocessingError):
    """Raised when line calibration fails."""
    pass


class MissingDependencyError(PreprocessingError):
    """Raised when required preprocessing dependencies are missing."""

    def __init__(self, missing_packages: list):
        self.missing_packages = missing_packages
        super().__init__(
            f"Missing required packages: {', '.join(missing_packages)}. "
            f"Install with: pip install {' '.join(missing_packages)}"
        )


# MinerU API Errors
class MinerUError(ScanEnhancerError):
    """Base class for MinerU API-related errors."""
    pass


class MinerUAPIError(MinerUError):
    """Raised when MinerU API request fails."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"MinerU API error ({status_code}): {message}")


class MinerUAuthenticationError(MinerUError):
    """Raised when MinerU API authentication fails."""

    def __init__(self):
        super().__init__(
            "MinerU API authentication failed. Please check your API key in the UI."
        )


class TaskNotFoundError(MinerUError):
    """Raised when MinerU task ID is not found."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task ID '{task_id}' not found in MinerU API")


class TaskFailedError(MinerUError):
    """Raised when MinerU task processing fails."""

    def __init__(self, task_id: str, error_message: str):
        self.task_id = task_id
        self.error_message = error_message
        super().__init__(f"MinerU task {task_id} failed: {error_message}")


class TaskTimeoutError(MinerUError):
    """Raised when MinerU task times out."""

    def __init__(self, task_id: str, timeout_seconds: int):
        self.task_id = task_id
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"MinerU task {task_id} timed out after {timeout_seconds} seconds"
        )


# PDF Rendering Errors
class RenderingError(ScanEnhancerError):
    """Base class for PDF rendering errors."""
    pass


class FontError(RenderingError):
    """Raised when font setup or registration fails."""
    pass


class ImageRenderingError(RenderingError):
    """Raised when image rendering fails."""

    def __init__(self, image_path: str, reason: str):
        self.image_path = image_path
        super().__init__(f"Failed to render image '{image_path}': {reason}")


class TableRenderingError(RenderingError):
    """Raised when table rendering fails."""
    pass


class EquationRenderingError(RenderingError):
    """Raised when equation rendering fails."""
    pass


class LayoutParsingError(RenderingError):
    """Raised when layout JSON parsing fails."""

    def __init__(self, field: str, reason: str):
        self.field = field
        super().__init__(f"Failed to parse layout field '{field}': {reason}")


# OCR Post-Processing Errors
class OCRPostProcessingError(ScanEnhancerError):
    """Base class for OCR post-processing errors."""
    pass


class LayoutLoadError(OCRPostProcessingError):
    """Raised when loading layout.json fails."""
    pass


class CorrectionApplicationError(OCRPostProcessingError):
    """Raised when applying OCR corrections fails."""
    pass


# Pipeline Errors
class PipelineError(ScanEnhancerError):
    """Base class for pipeline orchestration errors."""
    pass


class PipelineStepError(PipelineError):
    """Raised when a specific pipeline step fails.

    This wraps the underlying exception while preserving the pipeline context.
    """

    def __init__(self, step_name: str, original_exception: Exception):
        self.step_name = step_name
        self.original_exception = original_exception
        super().__init__(
            f"Pipeline step '{step_name}' failed: {str(original_exception)}"
        )
