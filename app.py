"""Textbook PDF Cleaner - Main Application

HuggingFace Spaces application for processing scanned PDFs using MinerU API.
"""
import sys
import os
from pathlib import Path

# Add current directory to path for imports (for HuggingFace Spaces)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import gradio as gr
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.mineru_processor import MinerUAPIProcessor
from src.document_builder import create_pdf_from_mineru, create_pdf_from_layout, create_pdf_from_layout_flow, calculate_margins_from_layout
from src.utils import validate_pdf_path, check_file_size_limit, clean_filename
from src.pdf_preprocessor import preprocess_pdf, is_available, fix_overlapping_blocks

# Initialize MinerU API processor
# API key should be set in HF Space secrets as MINERU_API_KEY
try:
    mineru = MinerUAPIProcessor()
    print("MinerU API processor initialized successfully!")
except ValueError as e:
    print(f"Warning: {e}")
    print("Please set MINERU_API_KEY in your .env file or HuggingFace Space secrets.")
    mineru = None


def process_pdf(
    pdf_file,
    language: str,
    download_raw: bool,
    keep_original_margins: bool,
    binarize_enabled: bool,
    binarize_block_size: int,
    binarize_c_constant: int,
    enable_formula: bool,
    font_bucket_9: float,
    font_bucket_10: float,
    font_bucket_11: float,
    font_bucket_12: float,
    font_bucket_14: float,
    enable_ocr_correction: bool,
    quality_cutoff: float,
    enable_line_calibration: bool,
    target_line_height: float,
    overlap_threshold: float,
    progress=gr.Progress()
) -> tuple:
    """
    Main processing pipeline using MinerU API.

    Args:
        pdf_file: Uploaded PDF file object
        language: Language code for OCR (e.g., "ru" for Russian)
        download_raw: If True, also return raw MinerU output ZIP
        keep_original_margins: If True, use exact positioning; if False, use consistent 1cm margins
        binarize_enabled: If True, preprocess PDF with binarization before sending to MinerU
        binarize_block_size: Block size for adaptive thresholding (odd number, 11-51)
        binarize_c_constant: C constant subtracted from mean for adaptive thresholding (0-30)
        enable_formula: If True, enable MinerU formula recognition; if False, treat as text
        font_bucket_9: Line height threshold in points for 9pt font (default 8.0)
        font_bucket_10: Line height threshold in points for 10pt font (default 18.0)
        font_bucket_11: Line height threshold in points for 11pt font (default 21.0)
        font_bucket_12: Line height threshold in points for 12pt font (default 25.0)
        font_bucket_14: Line height threshold in points for 14pt font (default 27.0)
        enable_line_calibration: If True, apply line calibration to fix overlapping text (default False)
        target_line_height: Maximum line height in pixels before overlap fixing is triggered (default 34.0)
        overlap_threshold: Optional maximum negative gap to ignore for overlap fixing (default -10.0)
        progress: Gradio progress tracker

    Returns:
        Tuple of (output PDF path, binarized PDF path or None, MinerU ZIP path or None)
    """
    if pdf_file is None:
        raise gr.Error("Please upload a PDF file")

    if mineru is None:
        raise gr.Error(
            "MinerU API not configured. "
            "Please set MINERU_API_KEY environment variable."
        )

    from datetime import datetime

    pdf_path = pdf_file.name
    temp_pdf_to_cleanup = None
    binarized_pdf_path = None
    # Save original filename for final output naming (before any preprocessing)
    original_base_name = clean_filename(os.path.basename(pdf_path))

    try:
        # Validate file
        progress(0.02, desc="Validating PDF file...")

        # Check file extension
        if not validate_pdf_path(pdf_path):
            raise gr.Error("Invalid file. Please upload a PDF file.")

        # Check file size (MinerU API limit is 200MB)
        is_valid, size_mb, msg = check_file_size_limit(pdf_path, max_mb=200)
        if not is_valid:
            raise gr.Error(msg)

        # Optionally preprocess PDF with binarization
        if binarize_enabled:
            if not is_available():
                raise gr.Error(
                    "Binarization preprocessing is not available. "
                    "Required dependencies may not be installed."
                )

            progress(0.05, desc="Preprocessing PDF (binarization)...")
            import tempfile

            # Create output filename with timestamp
            base_name = clean_filename(os.path.basename(pdf_path))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            binarized_filename = f"{base_name}_binarized_{timestamp}.pdf"
            temp_pdf_to_cleanup = os.path.join(tempfile.gettempdir(), binarized_filename)

            def progress_cb(page, total, msg):
                if total > 0:
                    progress(0.05 + (0.1 * page / total), desc=msg)
                else:
                    progress(0.05, desc=msg)

            pdf_path = preprocess_pdf(
                input_path=pdf_path,
                output_path=temp_pdf_to_cleanup,
                block_size=binarize_block_size,
                c_constant=binarize_c_constant,
                progress_callback=progress_cb
            )
            # Also save to current directory for download
            binarized_pdf_path = binarized_filename
            import shutil
            shutil.copy2(temp_pdf_to_cleanup, binarized_pdf_path)
        else:
            pdf_path = pdf_file.name

        progress(0.15, desc=f"Processing PDF ({size_mb:.1f} MB)...")

        # Submit to MinerU API
        progress(0.2, desc="Submitting to MinerU API...")
        # Hardcoded to JSON format for best structure preservation
        output_format = "json"
        result = mineru.process_pdf(pdf_path, output_format=output_format, language=language, enable_formula=enable_formula)

        task_id = result.get("task_id")
        status = result.get("status")
        result_data = result.get("result", {})

        if status == "completed":
            # Get the parsed content
            temp_dir = result.get("temp_dir")
            zip_path = result.get("zip_path")
            layout_data = result.get("layout_data")  # For exact positioning

            # Check for low-confidence items if OCR correction enabled
            if enable_ocr_correction and layout_data:
                progress(0.85, desc="Checking OCR quality...")

                from src.ocr_postprocessor import OCRPostProcessor

                # Extract low-confidence items from layout.json
                layout_json_path = os.path.join(temp_dir, "layout.json")
                processor = OCRPostProcessor(layout_json_path, quality_cutoff)
                processor.load_layout()
                low_conf_items = processor.extract_low_confidence_items()

                if low_conf_items:
                    # Found low-confidence items - pause for user correction
                    df = processor.to_dataframe()

                    # Debug logging
                    print(f"DEBUG: Created DataFrame with shape: {df.shape}")
                    print(f"DEBUG: DataFrame columns: {df.columns.tolist()}")
                    print(f"DEBUG: DataFrame head:\n{df.head()}")
                    print(f"DEBUG: DataFrame as dict:\n{df.to_dict('records')[:3]}")

                    # Store state for later use when Apply Corrections is clicked
                    state_data = {
                        "processor": processor,
                        "temp_dir": temp_dir,
                        "pdf_path": pdf_path,
                        "original_base_name": original_base_name,  # Store original filename for final output
                        "keep_original_margins": keep_original_margins,
                        "enable_line_calibration": enable_line_calibration,
                        "target_line_height": target_line_height,
                        "overlap_threshold": overlap_threshold,
                        "font_buckets": {
                            "bucket_9": font_bucket_9,
                            "bucket_10": font_bucket_10,
                            "bucket_11": font_bucket_11,
                            "bucket_12": font_bucket_12,
                            "bucket_14": font_bucket_14,
                        }
                    }

                    status_msg = f"✅ MinerU completed. Found {len(low_conf_items)} low-confidence items. Please review and correct below."

                    # Return early - don't generate PDF yet
                    # Convert DataFrame to list of lists format WITHOUT headers
                    # (Headers are defined in the component itself)
                    table_data = df.values.tolist()
                    print(f"DEBUG: Returning data with {len(df)} rows")
                    print(f"DEBUG: Table data (no headers): {len(table_data)} rows")
                    print(f"DEBUG: First 3 data rows: {table_data[:3]}")

                    # Return: (output_file, binarized, mineru_zip, corrections_table, correction_panel_visible, state, status, correction_status_visible)
                    return (
                        None,  # No final PDF yet
                        binarized_pdf_path,
                        zip_path if download_raw else None,
                        gr.update(value=table_data, visible=True),  # Set BOTH value AND visibility
                        gr.update(visible=True),  # Show apply button (correction_panel is now dummy)
                        state_data,  # Store for apply_corrections
                        status_msg,
                        gr.update(visible=False)  # Hide correction status initially
                    )

            # No OCR correction needed - proceed directly to PDF generation
            progress(0.85, desc="Parsing complete! Building PDF...")

            # Create output filename with timestamp using original filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"{original_base_name}_final_{timestamp}.pdf"

            # DEBUG: Trace code path
            print("=" * 80)
            print("DEBUG: PDF RENDERING DECISION")
            print(f"DEBUG: layout_data is None: {layout_data is None}")
            print(f"DEBUG: layout_data type: {type(layout_data)}")
            if layout_data:
                print(f"DEBUG: pdf_info count: {len(layout_data.get('pdf_info', []))}")
                print(f"DEBUG: First page has preproc_blocks: {'preproc_blocks' in layout_data.get('pdf_info', [{}])[0]}")
            print(f"DEBUG: result_data type: {type(result_data)}")
            print("=" * 80)

            # Build PDF from MinerU output
            # Choose rendering method based on margin preference
            if layout_data:
                # Fix any overlapping text blocks before rendering (if enabled)
                if enable_line_calibration:
                    layout_data = fix_overlapping_blocks(layout_data, target_line_height=target_line_height, overlap_threshold=overlap_threshold)

                if keep_original_margins:
                    # Use layout.json for exact positioning with original margins
                    print("DEBUG: Using layout.json for exact positioning (original margins)")
                    create_pdf_from_layout(
                        output_path=output_path,
                        layout_data=layout_data,
                        temp_dir=temp_dir,
                        use_consistent_margins=False,
                        font_buckets={
                            "bucket_9": font_bucket_9,
                            "bucket_10": font_bucket_10,
                            "bucket_11": font_bucket_11,
                            "bucket_12": font_bucket_12,
                            "bucket_14": font_bucket_14,
                        }
                    )
                else:
                    # Use layout.json with flow-based rendering and dynamic spacing
                    print("DEBUG: Using layout.json for flow-based rendering with original margins")

                    # Calculate DPI from page size for margin calculation
                    pdf_info = layout_data.get("pdf_info", [])
                    if pdf_info:
                        first_page_size = pdf_info[0].get("page_size", [612, 792])
                        # Use the same DPI calculation as DocumentBuilder
                        temp_builder = DocumentBuilder.__new__(DocumentBuilder)
                        dpi = temp_builder._calculate_dpi_from_page_size(first_page_size)
                        # Calculate margins from layout
                        calculated_margin = calculate_margins_from_layout(layout_data, dpi)
                    else:
                        calculated_margin = None

                    create_pdf_from_layout_flow(
                        output_path=output_path,
                        layout_data=layout_data,
                        temp_dir=temp_dir,
                        margin=calculated_margin,
                    )
            else:
                # Fallback to content_list.json for flow-based rendering
                print("DEBUG: layout.json not available, using content_list.json for flow-based rendering")
                create_pdf_from_mineru(
                    output_path=output_path,
                    content=result_data,
                    content_type=output_format,
                    temp_dir=temp_dir,
                    use_consistent_margins=not keep_original_margins
                )

            progress(1.0, desc="Complete!")

            # Clean up temporary binarized PDF if it was created
            if temp_pdf_to_cleanup and os.path.exists(temp_pdf_to_cleanup):
                try:
                    os.remove(temp_pdf_to_cleanup)
                except:
                    pass

            # Return (output PDF, binarized PDF, ZIP, corrections_table, apply_btn, state, status, correction_status)
            return (
                output_path,  # Final PDF (as plain string, .then() will set visibility)
                binarized_pdf_path,
                zip_path if (download_raw and zip_path and os.path.exists(zip_path)) else None,
                gr.update(visible=False),  # Hide corrections table
                gr.update(visible=False),  # Hide apply button
                None,  # No state needed
                "✅ Processing complete!",
                gr.update(visible=False)  # Hide correction status
            )
        else:
            # Extract error message if available
            error_msg = result_data.get("error", status)
            raise gr.Error(f"Processing failed: {error_msg}")

    except gr.Error:
        # Clean up on error
        if temp_pdf_to_cleanup and os.path.exists(temp_pdf_to_cleanup):
            try:
                os.remove(temp_pdf_to_cleanup)
            except:
                pass
        raise
    except Exception as e:
        # Clean up on error
        if temp_pdf_to_cleanup and os.path.exists(temp_pdf_to_cleanup):
            try:
                os.remove(temp_pdf_to_cleanup)
            except:
                pass
        raise gr.Error(f"Processing failed: {str(e)}")


def apply_corrections_and_generate_pdf(
    corrections_df,
    state_data
):
    """
    Apply user corrections and generate final PDF.

    Args:
        corrections_df: Edited DataFrame from corrections_table
        state_data: Dict with keys: processor, temp_dir, pdf_path,
                    keep_original_margins, enable_line_calibration, target_line_height,
                    overlap_threshold, font_buckets

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
        enable_line_calibration = state_data.get("enable_line_calibration", False)
        target_line_height = state_data.get("target_line_height", 34.0)
        overlap_threshold = state_data.get("overlap_threshold", -10.0)
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

        # Fix any overlapping text blocks before rendering (if enabled)
        if enable_line_calibration:
            layout_data = fix_overlapping_blocks(layout_data, target_line_height=target_line_height, overlap_threshold=overlap_threshold)

        # Generate PDF from corrected layout with proper filename using original base name
        from datetime import datetime
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
                font_buckets=font_buckets
            )
        else:
            # Use flow-based rendering with dynamic spacing
            # Calculate margins from layout
            pdf_info = layout_data.get("pdf_info", [])
            if pdf_info:
                first_page_size = pdf_info[0].get("page_size", [612, 792])
                # Use the same DPI calculation as DocumentBuilder
                temp_builder = DocumentBuilder.__new__(DocumentBuilder)
                dpi = temp_builder._calculate_dpi_from_page_size(first_page_size)
                # Calculate margins from layout
                calculated_margin = calculate_margins_from_layout(layout_data, dpi)
            else:
                calculated_margin = None

            create_pdf_from_layout_flow(
                output_path=output_pdf,
                layout_data=layout_data,
                temp_dir=temp_dir,
                margin=calculated_margin,
            )

        final_status = f"{status_msg}\n✅ Final PDF generated successfully!"
        return output_pdf, final_status

    except Exception as e:
        return None, f"❌ Error applying corrections: {str(e)}"


# Create Gradio interface
with gr.Blocks(title="PDF Document Cleaner") as app:
    gr.Markdown("# 📚 PDF Document Cleaner")

    gr.Markdown("""
    Powered by [MinerU](https://mineru.net/) - An open-source document parsing solution.
    """)

    with gr.Row():
        with gr.Column():
            gr.Markdown("## Setup")
            gr.Markdown("### Document Language")
            language = gr.Dropdown(
                choices=[
                    ("Russian", "ru"),
                    ("Chinese", "ch"),
                    ("English", "en"),
                    ("Japanese", "japan"),
                    ("Korean", "korean"),
                    ("German", "german"),
                    ("French", "french"),
                    ("Spanish", "spanish"),
                ],
                value="ru",
                info="Select the primary language for better OCR accuracy"
            )

            gr.Markdown("---")
            gr.Markdown("### De-noising")

            binarize_enabled = gr.Checkbox(
                label="Pre-process PDF (binarize before sending to API)",
                value=True,
                info="Improves text clarity for noisy scans. Adds ~10-20 seconds."
            )

            binarize_block_size = gr.Slider(
                minimum=11,
                maximum=51,
                value=31,
                step=2,
                label="Binarization block size",
                info="Neighborhood size for local thresholding. Higher=smoother, lower=more local detail. (odd, default: 31)"
            )

            binarize_c_constant = gr.Slider(
                minimum=0,
                maximum=51,
                value=25,
                step=1,
                label="Binarization C constant",
                info="Subtracted from local mean. Lower=more white (fewer dots), Higher=more black. (default: 25)"
            )

            gr.Markdown("---")
            gr.Markdown("### ⚙️ Additional Settings")

            download_raw = gr.Checkbox(
                label="Download raw MinerU output (for diagnostics)",
                value=True,
                info="Enable to also download the raw MinerU ZIP file for debugging"
            )

            keep_original_margins = gr.Checkbox(
                label="Keep original page margins",
                value=True,
                info="When unchecked, uses consistent 1cm margins on all sides"
            )

            enable_formula = gr.Checkbox(
                label="Enable formula detection",
                value=False,
                info="Disable if text is being misclassified as equations (e.g., single letters or special characters)"
            )

            gr.Markdown("---")
            gr.Markdown("### OCR Quality Control")

            enable_ocr_correction = gr.Checkbox(
                label="OCR Manual Correction",
                value=True,
                info="Review and correct low-confidence OCR results before generating PDF"
            )

            quality_cutoff = gr.Slider(
                minimum=0.0,
                maximum=1.0,
                value=0.9,
                step=0.01,
                label="Quality Cut-off",
                info="Confidence threshold (lower = more items to review). Recommended: 0.85-0.95",
                interactive=True
            )

            enable_line_calibration = gr.Checkbox(
                label="Line Calibration",
                value=False,
                info="Fix overlapping text by adjusting line heights. Disable to preserve original fonts."
            )

            target_line_height = gr.Slider(
                minimum=0.0,
                maximum=50.0,
                value=34.0,
                step=0.5,
                label="Target Line Height",
                info="Maximum line height (px) before overlap fixing is triggered. Blocks taller than this will be reduced. Default: 34.0",
                interactive=False
            )

            overlap_threshold = gr.Slider(
                minimum=-50.0,
                maximum=0.0,
                value=-10.0,
                step=0.5,
                label="Overlap Threshold",
                info="Fix text blocks with overlap worse than this (pixels). Lower = more aggressive, Higher = more conservative. Default: -10.0",
                interactive=False
            )

            gr.Markdown("---")
            gr.Markdown("### Font Size Buckets (line height thresholds in points)")

            font_bucket_9 = gr.Slider(
                minimum=5,
                maximum=50,
                value=17.0,
                step=0.5,
                label="8pt → 9pt threshold",
                info="Line height below this → 8pt, above → 9pt (default: 17.0pt)"
            )

            font_bucket_10 = gr.Slider(
                minimum=5,
                maximum=50,
                value=22.0,
                step=0.5,
                label="9pt → 10pt threshold",
                info="Line height below this → 9pt, above → 10pt (default: 22.0pt)"
            )

            font_bucket_11 = gr.Slider(
                minimum=5,
                maximum=50,
                value=28.0,
                step=0.5,
                label="10pt → 11pt threshold",
                info="Line height below this → 10pt, above → 11pt (default: 28.0pt)"
            )

            font_bucket_12 = gr.Slider(
                minimum=5,
                maximum=50,
                value=30.0,
                step=0.5,
                label="11pt → 12pt threshold",
                info="Line height below this → 11pt, above → 12pt (default: 30.0pt)"
            )

            font_bucket_14 = gr.Slider(
                minimum=5,
                maximum=50,
                value=32.0,
                step=0.5,
                label="12pt → 14pt threshold",
                info="Line height below this → 12pt, above → 14pt (default: 32.0pt)"
            )

        with gr.Column():
            gr.Markdown("## Workflow")
            gr.Markdown("**Tips:** 1) Maximum file size: 200 MB, 2) Vertical page orientation")

            pdf_input = gr.File(
                label="Upload PDF Document",
                file_types=[".pdf"],
                type="filepath"
            )

            process_btn = gr.Button(
                "🔍 Process the document",
                variant="primary",
                size="lg"
            )

            binarized_file = gr.File(
                label="📄 Download Binarized PDF (Pre-processed)",
                type="filepath",
                visible=False
            )

            mineru_output = gr.File(
                label="🔧 Download Raw MinerU Output (ZIP)",
                type="filepath",
                visible=False
            )

            # State storage for OCR correction workflow
            processor_state = gr.State()

            # Main status message
            main_status = gr.Textbox(
                label="Status",
                interactive=False,
                visible=True
            )

            # Low Confidence Text correction panel
            # NOTE: DataFrame moved outside hidden container due to Gradio rendering bug
            correction_header = gr.Markdown("### Low Confidence Text", visible=False)
            correction_instructions = gr.Markdown("Review and correct OCR errors below. Edit the 'Correction' column.", visible=False)

            corrections_table = gr.DataFrame(
                headers=["Page", "Score", "Type", "Original", "Correction"],
                interactive=True,
                wrap=True,
                label="Corrections Table",
                visible=False  # Start hidden, show when data available
            )

            apply_corrections_btn = gr.Button(
                "✅ Apply Corrections",
                variant="primary",
                visible=False  # Start hidden
            )

            correction_status = gr.Textbox(
                label="Correction Status",
                interactive=False,
                visible=False
            )

            # Dummy component to replace correction_panel in outputs
            correction_panel = gr.Column(visible=False)

            output_file = gr.File(
                label="📥 Download Final PDF",
                type="filepath",
                visible=False
            )

    # Toggle MinerU output visibility when checkbox changes
    download_raw.change(
        fn=lambda x: gr.update(visible=x),
        inputs=[download_raw],
        outputs=[mineru_output]
    )

    # Toggle binarized output visibility when checkbox changes
    binarize_enabled.change(
        fn=lambda x: gr.update(visible=x),
        inputs=[binarize_enabled],
        outputs=[binarized_file]
    )

    # Grey out quality_cutoff when OCR correction is disabled
    enable_ocr_correction.change(
        fn=lambda enabled: gr.update(interactive=enabled),
        inputs=[enable_ocr_correction],
        outputs=[quality_cutoff]
    )

    # Grey out line calibration sliders when line calibration is disabled
    enable_line_calibration.change(
        fn=lambda enabled: (
            gr.update(interactive=enabled),
            gr.update(interactive=enabled)
        ),
        inputs=[enable_line_calibration],
        outputs=[target_line_height, overlap_threshold]
    )

    # Connect processing function
    process_btn.click(
        fn=process_pdf,
        inputs=[pdf_input, language, download_raw, keep_original_margins, binarize_enabled,
                binarize_block_size, binarize_c_constant, enable_formula,
                font_bucket_9, font_bucket_10, font_bucket_11, font_bucket_12, font_bucket_14,
                enable_ocr_correction, quality_cutoff, enable_line_calibration, target_line_height, overlap_threshold],
        outputs=[
            output_file,           # Final PDF (None if corrections needed)
            binarized_file,        # Binarized PDF
            mineru_output,         # MinerU ZIP
            corrections_table,     # DataFrame for corrections (now also controls visibility)
            apply_corrections_btn, # Show/hide apply button
            processor_state,       # Store processor instance
            main_status,           # Status message
            correction_status      # Correction results
        ]
    ).then(
        # Show output files when they have values AND checkbox is enabled
        fn=lambda final, binarized, mineru, binarize_checked, mineru_checked: (
            gr.update(visible=final is not None),  # output_file (always show if available)
            gr.update(visible=binarized is not None and binarize_checked),  # binarized_file (only if checkbox checked)
            gr.update(visible=mineru is not None and mineru_checked),  # mineru_output (only if checkbox checked)
        ),
        inputs=[output_file, binarized_file, mineru_output, binarize_enabled, download_raw],
        outputs=[output_file, binarized_file, mineru_output]
    )

    # Connect correction apply function
    apply_corrections_btn.click(
        fn=apply_corrections_and_generate_pdf,
        inputs=[
            corrections_table,
            processor_state
        ],
        outputs=[
            output_file,
            correction_status
        ]
    ).then(
        fn=lambda: gr.update(visible=True),
        outputs=output_file
    )


if __name__ == "__main__":
    app.launch(ssr_mode=False)  # Disable SSR to fix DataFrame rendering issues
