"""Processing Result Dataclass

Result outputs from PDF processing pipeline.
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
import pandas as pd


@dataclass
class ProcessingResult:
    """Result from PDF processing pipeline.

    This dataclass encapsulates all outputs from the PDF processing pipeline,
    including generated files, intermediate results, and state for OCR correction workflow.

    Attributes:
        status: Processing status ("completed", "needs_correction", "failed")
        status_message: Human-readable status message

        # Output Files
        output_pdf_path: Path to final processed PDF (None if OCR correction needed)
        binarized_pdf_path: Path to binarized PDF (if preprocessing enabled, None otherwise)
        mineru_zip_path: Path to raw MinerU output ZIP (if download_raw enabled, None otherwise)

        # OCR Correction Workflow
        needs_correction: True if low-confidence OCR items found and correction enabled
        corrections_dataframe: DataFrame with low-confidence items for user review
        correction_state: Internal state for apply_corrections workflow

        # Error Handling
        error: Error message if processing failed (None otherwise)
    """

    # Status
    status: str  # "completed", "needs_correction", "failed"
    status_message: str

    # Output Files
    output_pdf_path: Optional[str] = None
    binarized_pdf_path: Optional[str] = None
    mineru_zip_path: Optional[str] = None

    # OCR Correction Workflow
    needs_correction: bool = False
    corrections_dataframe: Optional[pd.DataFrame] = None
    correction_state: Optional[Dict[str, Any]] = None

    # Error Handling
    error: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        """True if processing completed successfully without needing correction."""
        return self.status == "completed" and self.output_pdf_path is not None

    @property
    def is_failed(self) -> bool:
        """True if processing failed with an error."""
        return self.status == "failed"

    def to_gradio_outputs(self) -> tuple:
        """Convert to Gradio UI outputs format.

        Returns:
            Tuple of (output_file, binarized_file, mineru_zip, corrections_table,
                     correction_panel_visible, state, status, correction_status_visible)
        """
        import gradio as gr

        if self.is_failed:
            # Return error state
            return (
                None,  # output_file
                self.binarized_pdf_path,
                self.mineru_zip_path,
                gr.update(visible=False),  # corrections_table
                gr.update(visible=False),  # apply_corrections_btn
                None,  # processor_state
                self.status_message,  # main_status
                gr.update(visible=False),  # correction_status
            )

        if self.needs_correction:
            # Return state for OCR correction
            # Convert DataFrame to list of lists format WITHOUT headers
            table_data = self.corrections_dataframe.values.tolist() if self.corrections_dataframe is not None else []

            return (
                None,  # No final PDF yet
                self.binarized_pdf_path,
                self.mineru_zip_path,
                gr.update(value=table_data, visible=True),  # Set BOTH value AND visibility
                gr.update(visible=True),  # Show apply button
                self.correction_state,  # Store for apply_corrections
                self.status_message,
                gr.update(visible=False),  # Hide correction status initially
            )

        # Processing complete
        return (
            self.output_pdf_path,  # Final PDF
            self.binarized_pdf_path,
            self.mineru_zip_path,
            gr.update(visible=False),  # Hide corrections table
            gr.update(visible=False),  # Hide apply button
            None,  # No state needed
            self.status_message,
            gr.update(visible=False),  # Hide correction status
        )
