"""Russian Textbook PDF Cleaner - Main Application

HuggingFace Spaces application for processing scanned PDFs using MinerU API.
"""
import sys
import os
from pathlib import Path

# Add current directory to path for imports (for HuggingFace Spaces)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import gradio as gr
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.mineru_processor import MinerUAPIProcessor
from src.document_builder import create_pdf_from_mineru, create_pdf_from_layout
from src.utils import validate_pdf_path, check_file_size_limit, clean_filename
from src.pdf_preprocessor import preprocess_pdf, is_available

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
    output_format: str,
    language: str,
    download_raw: bool,
    keep_original_margins: bool,
    binarize_enabled: bool,
    font_bucket_9: float,
    font_bucket_10: float,
    font_bucket_11: float,
    font_bucket_12: float,
    font_bucket_14: float,
    progress=gr.Progress()
) -> tuple:
    """
    Main processing pipeline using MinerU API.

    Args:
        pdf_file: Uploaded PDF file object
        output_format: "json" or "markdown" - MinerU output format
        language: Language code for OCR (e.g., "ru" for Russian)
        download_raw: If True, also return raw MinerU output ZIP
        keep_original_margins: If True, use exact positioning; if False, use consistent 1cm margins
        binarize_enabled: If True, preprocess PDF with binarization before sending to MinerU
        font_bucket_9: Bbox height threshold for 9pt font (default 23)
        font_bucket_10: Bbox height threshold for 10pt font (default 28)
        font_bucket_11: Bbox height threshold for 11pt font (default 33)
        font_bucket_12: Bbox height threshold for 12pt font (default 41)
        font_bucket_14: Bbox height threshold for 14pt font (default 50)
        progress: Gradio progress tracker

    Returns:
        Tuple of (output PDF path, MinerU ZIP path or None)
    """
    if pdf_file is None:
        raise gr.Error("Please upload a PDF file")

    if mineru is None:
        raise gr.Error(
            "MinerU API not configured. "
            "Please set MINERU_API_KEY environment variable."
        )

    pdf_path = pdf_file.name
    temp_pdf_to_cleanup = None

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
            temp_pdf_to_cleanup = tempfile.mktemp(suffix="_binarized.pdf")

            def progress_cb(page, total, msg):
                progress(0.05 + (0.1 * page / total), desc=msg)

            pdf_path = preprocess_pdf(
                input_path=pdf_path,
                output_path=temp_pdf_to_cleanup,
                progress_callback=progress_cb
            )
        else:
            pdf_path = pdf_file.name

        progress(0.15, desc=f"Processing PDF ({size_mb:.1f} MB)...")

        # Submit to MinerU API
        progress(0.2, desc="Submitting to MinerU API...")
        result = mineru.process_pdf(pdf_path, output_format=output_format, language=language)

        task_id = result.get("task_id")
        status = result.get("status")
        result_data = result.get("result", {})

        if status == "completed":
            progress(0.85, desc="Parsing complete! Building PDF...")

            # Get the parsed content
            temp_dir = result.get("temp_dir")
            zip_path = result.get("zip_path")
            layout_data = result.get("layout_data")  # For exact positioning

            # Create output filename
            base_name = clean_filename(os.path.basename(pdf_path))
            output_path = f"{base_name}_cleaned.pdf"

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
                # Use layout.json for exact positioning
                # Apply consistent margins if user requested them
                use_consistent_margins = not keep_original_margins
                if keep_original_margins:
                    print("DEBUG: Using layout.json for exact positioning (original margins)")
                else:
                    print("DEBUG: Using layout.json for exact positioning (1.5cm margins)")
                create_pdf_from_layout(
                    output_path=output_path,
                    layout_data=layout_data,
                    temp_dir=temp_dir,
                    use_consistent_margins=use_consistent_margins,
                    font_buckets={
                        "bucket_9": font_bucket_9,
                        "bucket_10": font_bucket_10,
                        "bucket_11": font_bucket_11,
                        "bucket_12": font_bucket_12,
                        "bucket_14": font_bucket_14,
                    }
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

            # Return both PDF and optionally the ZIP file
            if download_raw and zip_path and os.path.exists(zip_path):
                return output_path, zip_path
            else:
                return output_path, None
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


# Create Gradio interface
with gr.Blocks(title="PDF Document Cleaner") as app:
    gr.Markdown("# 📚 PDF Document Cleaner")

    with gr.Row():
        with gr.Column():
            gr.Markdown("""
            **Features:**
            - Multi-language OCR support
            - Preserves document structure
            - Outputs searchable PDF
            """)
        with gr.Column():
            gr.Markdown("""
            **Tips:**
            - Maximum file size: 200 MB
            - Ensure pages are properly oriented
            """)
        with gr.Column():
            gr.Markdown("""
            Powered by [MinerU](https://mineru.net/) - An open-source document parsing solution.
            """)

    with gr.Row():
        with gr.Column():
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

            gr.Markdown("### Output Format")
            output_format = gr.Radio(
                choices=[
                    ("JSON → PDF (Structured, preserves tables/images)", "json"),
                    ("Markdown → PDF (Simple text-focused)", "markdown")
                ],
                value="json",
                info="JSON preserves more structure, Markdown is simpler"
            )

            gr.Markdown("---")
            gr.Markdown("### Font Size Buckets (bbox height thresholds)")

            font_bucket_9 = gr.Slider(
                minimum=15,
                maximum=50,
                value=23,
                step=0.5,
                label="8pt → 9pt threshold",
                info="Bbox height below this → 8pt, above → 9pt (default: 23)"
            )

            font_bucket_10 = gr.Slider(
                minimum=15,
                maximum=50,
                value=28,
                step=0.5,
                label="9pt → 10pt threshold",
                info="Bbox height below this → 9pt, above → 10pt (default: 28)"
            )

            font_bucket_11 = gr.Slider(
                minimum=15,
                maximum=50,
                value=33,
                step=0.5,
                label="10pt → 11pt threshold",
                info="Bbox height below this → 10pt, above → 11pt (default: 33)"
            )

            font_bucket_12 = gr.Slider(
                minimum=15,
                maximum=50,
                value=41,
                step=0.5,
                label="11pt → 12pt threshold",
                info="Bbox height below this → 11pt, above → 12pt (default: 41)"
            )

            font_bucket_14 = gr.Slider(
                minimum=15,
                maximum=50,
                value=50,
                step=0.5,
                label="12pt → 14pt threshold",
                info="Bbox height below this → 12pt, above → 14pt (default: 50)"
            )

            gr.Markdown("---")
            gr.Markdown("### ⚙️ Additional Settings")

            download_raw = gr.Checkbox(
                label="Download raw MinerU output (for diagnostics)",
                value=False,
                info="Enable to also download the raw MinerU ZIP file for debugging"
            )

            keep_original_margins = gr.Checkbox(
                label="Keep original page margins",
                value=True,
                info="When unchecked, uses consistent 1cm margins on all sides"
            )

            binarize_enabled = gr.Checkbox(
                label="Pre-process PDF (binarize before sending to API)",
                value=False,
                info="Improves text clarity for noisy scans. Adds ~10-20 seconds."
            )

        with gr.Column():
            pdf_input = gr.File(
                label="Upload PDF Document",
                file_types=[".pdf"],
                type="filepath"
            )

            process_btn = gr.Button(
                "🚀 Process Document",
                variant="primary",
                size="lg"
            )

            output_file = gr.File(
                label="📥 Download Cleaned Document",
                type="filepath"
            )

            mineru_output = gr.File(
                label="🔧 Download Raw MinerU Output (ZIP)",
                type="filepath",
                visible=False
            )

    # Toggle MinerU output visibility when checkbox changes
    download_raw.change(
        fn=lambda x: gr.update(visible=x),
        inputs=[download_raw],
        outputs=[mineru_output]
    )

    # Connect processing function
    process_btn.click(
        fn=process_pdf,
        inputs=[pdf_input, output_format, language, download_raw, keep_original_margins, binarize_enabled,
                font_bucket_9, font_bucket_10, font_bucket_11, font_bucket_12, font_bucket_14],
        outputs=[output_file, mineru_output]
    )


if __name__ == "__main__":
    app.launch()
