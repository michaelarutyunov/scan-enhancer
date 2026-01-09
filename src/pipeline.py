"""PDF Processing Pipeline

Main orchestration logic for PDF processing workflow.
"""
import os
import tempfile
import shutil
from datetime import datetime
from typing import Optional, Callable
import pandas as pd

from .processing_options import ProcessingOptions
from .processing_result import ProcessingResult
from .config import PROGRESS_STEPS, DEFAULT_OUTPUT_FORMAT, MAX_FILE_SIZE_MB
from .utils import validate_pdf_path, check_file_size_limit, clean_filename
from .mineru_processor import MinerUAPIProcessor
from .pdf_preprocessor import preprocess_pdf, is_available
from .document_builder import (
    DocumentBuilder,
    LayoutAnalyzer,
    create_pdf_from_mineru,
    create_pdf_from_layout,
    create_pdf_from_layout_flow,
    calculate_margins_from_layout,
)
from .ocr_postprocessor import OCRPostProcessor
from .exceptions import (
    ScanEnhancerError,
    ValidationError,
    InvalidFileError,
    FileSizeLimitExceededError,
    PreprocessingError,
    BinarizationError,
    MinerUError,
    TaskFailedError,
    RenderingError,
    PipelineStepError,
)


class PDFProcessingPipeline:
    """PDF processing pipeline orchestrator.

    This class orchestrates the complete PDF processing workflow:
    1. Validation - validate file exists, has correct extension, and size
    2. Preprocessing - optional binarization for noise reduction
    3. MinerU API - submit to MinerU for OCR and layout extraction
    4. OCR Correction - optional manual correction of low-confidence items
    5. PDF Generation - build final PDF from MinerU output

    The pipeline maintains all error handling and business logic from the original
    process_pdf() function while providing a clean, reusable interface.

    Attributes:
        mineru: MinerU API processor instance
        progress_callback: Optional callback for progress updates (progress, desc)
    """

    def __init__(
        self,
        mineru_processor: MinerUAPIProcessor,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ):
        """Initialize pipeline with MinerU processor and optional progress callback.

        Args:
            mineru_processor: Configured MinerU API processor instance
            progress_callback: Optional function(progress: float, desc: str) for progress updates
        """
        self.mineru = mineru_processor
        self.progress = progress_callback or (lambda p, d: None)

        # Internal state for cleanup
        self._temp_pdf_to_cleanup: Optional[str] = None

    def process(self, options: ProcessingOptions) -> ProcessingResult:
        """Execute complete PDF processing pipeline.

        Args:
            options: Processing configuration options

        Returns:
            ProcessingResult with outputs and status

        Raises:
            Does not raise - all errors are captured in ProcessingResult.error
        """
        try:
            # Step 1: Validation
            self.progress(PROGRESS_STEPS["VALIDATE"], "Validating PDF file...")
            self._validate_file(options.pdf_path)

            # Step 2: Optional Preprocessing
            pdf_path, binarized_pdf_path = self._preprocess_if_enabled(options)

            # Step 3: Submit to MinerU API
            self.progress(PROGRESS_STEPS["SUBMIT_API"], "Submitting to MinerU API...")
            result = self.mineru.process_pdf(
                pdf_path,
                output_format=DEFAULT_OUTPUT_FORMAT,
                language=options.language,
                enable_formula=options.enable_formula
            )

            # Step 4: Check result status
            task_id = result.get("task_id")
            status = result.get("status")
            result_data = result.get("result", {})

            if status != "completed":
                # Extract error message
                error_msg = result_data.get("error", status)
                return ProcessingResult(
                    status="failed",
                    status_message=f"Processing failed: {error_msg}",
                    error=error_msg,
                    binarized_pdf_path=binarized_pdf_path,
                )

            # Step 5: Extract results
            temp_dir = result.get("temp_dir")
            zip_path = result.get("zip_path")
            layout_data = result.get("layout_data")

            # Step 6: OCR Quality Check and Correction
            if options.enable_ocr_correction and layout_data:
                ocr_result = self._check_ocr_quality(
                    layout_data=layout_data,
                    temp_dir=temp_dir,
                    pdf_path=pdf_path,
                    options=options,
                    binarized_pdf_path=binarized_pdf_path,
                    zip_path=zip_path,
                )
                if ocr_result:
                    # Needs correction - return early
                    return ocr_result

            # Step 7: Generate final PDF
            self.progress(PROGRESS_STEPS["PDF_BUILD"], "Parsing complete! Building PDF...")
            output_pdf_path = self._generate_pdf(
                layout_data=layout_data,
                result_data=result_data,
                temp_dir=temp_dir,
                options=options,
            )

            self.progress(PROGRESS_STEPS["COMPLETE"], "Complete!")

            # Cleanup
            self._cleanup_temp_files()

            # Return success
            return ProcessingResult(
                status="completed",
                status_message="✅ Processing complete!",
                output_pdf_path=output_pdf_path,
                binarized_pdf_path=binarized_pdf_path,
                mineru_zip_path=zip_path if (options.download_raw and zip_path and os.path.exists(zip_path)) else None,
            )

        except Exception as e:
            # Cleanup on error
            self._cleanup_temp_files()

            return ProcessingResult(
                status="failed",
                status_message=f"Processing failed: {str(e)}",
                error=str(e),
            )

    def _validate_file(self, pdf_path: str) -> float:
        """Validate PDF file exists, has correct extension, and is within size limit.

        Args:
            pdf_path: Path to PDF file

        Returns:
            File size in MB

        Raises:
            InvalidFileError: If file doesn't exist or has wrong extension
            FileSizeLimitExceededError: If file exceeds size limit
        """
        # Check file extension and existence
        validate_pdf_path(pdf_path)

        # Check file size (MinerU API limit)
        size_mb = check_file_size_limit(pdf_path, max_mb=MAX_FILE_SIZE_MB)

        return size_mb

    def _preprocess_if_enabled(self, options: ProcessingOptions) -> tuple[str, Optional[str]]:
        """Preprocess PDF with binarization if enabled.

        Args:
            options: Processing options

        Returns:
            Tuple of (pdf_path_to_use, binarized_pdf_path_or_none)

        Raises:
            ValueError: If binarization enabled but not available
        """
        if not options.binarize_enabled:
            return options.pdf_path, None

        # Check if binarization is available
        if not is_available():
            raise ValueError(
                "Binarization preprocessing is not available. "
                "Required dependencies may not be installed."
            )

        self.progress(PROGRESS_STEPS["PREPROCESS_START"], "Preprocessing PDF (binarization)...")

        # Create output filename with timestamp
        base_name = clean_filename(os.path.basename(options.pdf_path))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        binarized_filename = f"{base_name}_binarized_{timestamp}.pdf"
        temp_pdf_path = os.path.join(tempfile.gettempdir(), binarized_filename)

        # Store for cleanup
        self._temp_pdf_to_cleanup = temp_pdf_path

        # Progress callback wrapper
        def progress_cb(page, total, msg):
            if total > 0:
                progress_val = PROGRESS_STEPS["PREPROCESS_START"] + (
                    (PROGRESS_STEPS["PREPROCESS_END"] - PROGRESS_STEPS["PREPROCESS_START"]) * page / total
                )
                self.progress(progress_val, msg)
            else:
                self.progress(PROGRESS_STEPS["PREPROCESS_START"], msg)

        # Run preprocessing
        processed_pdf_path = preprocess_pdf(
            input_path=options.pdf_path,
            output_path=temp_pdf_path,
            block_size=options.binarize_block_size,
            c_constant=options.binarize_c_constant,
            progress_callback=progress_cb
        )

        # Copy to current directory for download
        binarized_output_path = binarized_filename
        shutil.copy2(temp_pdf_path, binarized_output_path)

        return processed_pdf_path, binarized_output_path

    def _check_ocr_quality(
        self,
        layout_data: dict,
        temp_dir: str,
        pdf_path: str,
        options: ProcessingOptions,
        binarized_pdf_path: Optional[str],
        zip_path: Optional[str],
    ) -> Optional[ProcessingResult]:
        """Check OCR quality and return result if correction needed.

        Args:
            layout_data: Layout data from MinerU
            temp_dir: Temporary directory with extracted files
            pdf_path: Path to processed PDF
            options: Processing options
            binarized_pdf_path: Path to binarized PDF (if any)
            zip_path: Path to MinerU ZIP output

        Returns:
            ProcessingResult if correction needed, None otherwise
        """
        self.progress(PROGRESS_STEPS["OCR_CHECK"], "Checking OCR quality...")

        # Extract low-confidence items from layout.json
        layout_json_path = os.path.join(temp_dir, "layout.json")
        processor = OCRPostProcessor(layout_json_path, options.quality_cutoff)
        processor.load_layout()
        low_conf_items = processor.extract_low_confidence_items()

        if not low_conf_items:
            # No correction needed
            return None

        # Found low-confidence items - prepare for user correction
        df = processor.to_dataframe()

        # Debug logging
        print(f"DEBUG: Created DataFrame with shape: {df.shape}")
        print(f"DEBUG: DataFrame columns: {df.columns.tolist()}")
        print(f"DEBUG: DataFrame head:\n{df.head()}")

        # Store state for later use when Apply Corrections is clicked
        state_data = {
            "processor": processor,
            "temp_dir": temp_dir,
            "pdf_path": pdf_path,
            "original_base_name": options.original_filename or clean_filename(os.path.basename(pdf_path)),
            "keep_original_margins": options.keep_original_margins,
            "enable_footnote_detection": options.enable_footnote_detection,
            "font_buckets": options.font_buckets.copy(),
        }

        status_msg = f"✅ MinerU completed. Found {len(low_conf_items)} low-confidence items. Please review and correct below."

        return ProcessingResult(
            status="needs_correction",
            status_message=status_msg,
            binarized_pdf_path=binarized_pdf_path,
            mineru_zip_path=zip_path if options.download_raw else None,
            needs_correction=True,
            corrections_dataframe=df,
            correction_state=state_data,
        )

    def _generate_pdf(
        self,
        layout_data: Optional[dict],
        result_data: dict,
        temp_dir: str,
        options: ProcessingOptions,
    ) -> str:
        """Generate final PDF from MinerU output.

        Args:
            layout_data: Layout data from MinerU (if available)
            result_data: Result data from MinerU API
            temp_dir: Temporary directory with extracted files
            options: Processing options

        Returns:
            Path to generated PDF
        """
        # Create output filename with timestamp
        base_name = options.original_filename or clean_filename(os.path.basename(options.pdf_path))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"{base_name}_final_{timestamp}.pdf"

        # DEBUG: Trace code path
        print("=" * 80)
        print("DEBUG: PDF RENDERING DECISION")
        print(f"DEBUG: layout_data is None: {layout_data is None}")
        print(f"DEBUG: layout_data type: {type(layout_data)}")
        if layout_data:
            print(f"DEBUG: pdf_info count: {len(layout_data.get('pdf_info', []))}")
            if layout_data.get('pdf_info'):
                print(f"DEBUG: First page has preproc_blocks: {'preproc_blocks' in layout_data.get('pdf_info', [{}])[0]}")
        print(f"DEBUG: result_data type: {type(result_data)}")
        print("=" * 80)

        # Choose rendering method based on available data
        if layout_data:
            if options.keep_original_margins:
                # Use layout.json for exact positioning with original margins
                print("DEBUG: Using layout.json for exact positioning (original margins)")
                create_pdf_from_layout(
                    output_path=output_path,
                    layout_data=layout_data,
                    temp_dir=temp_dir,
                    use_consistent_margins=False,
                    font_buckets=options.font_buckets,
                    enable_footnote_detection=options.enable_footnote_detection
                )
            else:
                # Use layout.json with flow-based rendering and dynamic spacing
                print("DEBUG: Using layout.json for flow-based rendering with original margins")

                # Calculate DPI from page size for margin calculation
                pdf_info = layout_data.get("pdf_info", [])
                if pdf_info:
                    first_page_size = pdf_info[0].get("page_size", [612, 792])
                    # Use the same DPI calculation as DocumentBuilder
                    analyzer = LayoutAnalyzer()
                    dpi = analyzer.calculate_dpi_from_page_size(first_page_size)
                    # Calculate margins from layout
                    calculated_margin = calculate_margins_from_layout(layout_data, dpi)
                else:
                    calculated_margin = None

                create_pdf_from_layout_flow(
                    output_path=output_path,
                    layout_data=layout_data,
                    temp_dir=temp_dir,
                    margin=calculated_margin,
                    enable_footnote_detection=options.enable_footnote_detection
                )
        else:
            # Fallback to content_list.json for flow-based rendering
            print("DEBUG: layout.json not available, using content_list.json for flow-based rendering")
            create_pdf_from_mineru(
                output_path=output_path,
                content=result_data,
                content_type=DEFAULT_OUTPUT_FORMAT,
                temp_dir=temp_dir,
                use_consistent_margins=not options.keep_original_margins
            )

        return output_path

    def _cleanup_temp_files(self):
        """Clean up temporary files created during processing."""
        if self._temp_pdf_to_cleanup and os.path.exists(self._temp_pdf_to_cleanup):
            try:
                os.remove(self._temp_pdf_to_cleanup)
                self._temp_pdf_to_cleanup = None
            except Exception:
                pass  # Ignore cleanup errors


def apply_corrections_and_generate_pdf(
    corrections_df,
    state_data: dict
) -> tuple[Optional[str], str]:
    """Apply user corrections and generate final PDF.

    This is a standalone function (not part of the pipeline class) because it's
    called separately from the main processing flow, after user edits corrections.

    Args:
        corrections_df: Edited DataFrame from corrections_table (can be list or DataFrame)
        state_data: Dict with keys: processor, temp_dir, pdf_path,
                    keep_original_margins, font_buckets, original_base_name, enable_footnote_detection

    Returns:
        Tuple of (final_pdf_path, status_message)
    """
    try:
        if state_data is None:
            return None, "❌ Error: No state data available. Please run OCR processing first."

        processor = state_data.get("processor")
        temp_dir = state_data.get("temp_dir")
        pdf_path = state_data.get("pdf_path")
        keep_original_margins = state_data.get("keep_original_margins", True)
        enable_footnote_detection = state_data.get("enable_footnote_detection", False)
        font_buckets = state_data.get("font_buckets", {})

        if processor is None:
            return None, "❌ Error: OCR processor not found in state."

        # Convert corrections data to DataFrame if it's a list
        if isinstance(corrections_df, list):
            # Data comes as rows only (headers defined in component)
            if len(corrections_df) > 0:
                headers = ["Page", "Score", "Type", "Original", "Correction"]
                corrections_df = pd.DataFrame(corrections_df, columns=headers)
            else:
                return None, "❌ Error: No corrections data provided."

        # Apply corrections to layout.json
        processor.from_dataframe(corrections_df)
        status_msg, num_changes = processor.apply_corrections(backup=True)

        # Load corrected layout
        layout_data = processor.load_layout()

        # Generate PDF from corrected layout with proper filename using original base name
        original_base_name = state_data.get("original_base_name", clean_filename(os.path.basename(pdf_path)))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_pdf = f"{original_base_name}_final_{timestamp}.pdf"

        if keep_original_margins:
            # Use exact positioning with original margins
            create_pdf_from_layout(
                output_path=output_pdf,
                layout_data=layout_data,
                temp_dir=temp_dir,
                use_consistent_margins=False,
                font_buckets=font_buckets,
                enable_footnote_detection=enable_footnote_detection
            )
        else:
            # Use flow-based rendering with dynamic spacing
            # Calculate margins from layout
            pdf_info = layout_data.get("pdf_info", [])
            if pdf_info:
                first_page_size = pdf_info[0].get("page_size", [612, 792])
                # Use the same DPI calculation as DocumentBuilder
                analyzer = LayoutAnalyzer()
                dpi = analyzer.calculate_dpi_from_page_size(first_page_size)
                # Calculate margins from layout
                calculated_margin = calculate_margins_from_layout(layout_data, dpi)
            else:
                calculated_margin = None

            create_pdf_from_layout_flow(
                output_path=output_pdf,
                layout_data=layout_data,
                temp_dir=temp_dir,
                margin=calculated_margin,
                enable_footnote_detection=enable_footnote_detection
            )

        final_status = f"{status_msg}\n✅ Final PDF generated successfully!"
        return output_pdf, final_status

    except Exception as e:
        return None, f"❌ Error applying corrections: {str(e)}"
