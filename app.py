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
    font_bucket_10: int,
    font_bucket_11: int,
    font_bucket_12: int,
    progress=gr.Progress()
) -> tuple:
    """
    Main processing pipeline using MinerU API.

    Args:
        pdf_file: Uploaded PDF file object
        output_format: "json" or "markdown" - MinerU output format
        language: Language code for OCR (e.g., "ru" for Russian)
        download_raw: If True, also return raw MinerU output ZIP
        keep_original_margins: If True, use exact positioning; if False, use consistent 1.5cm margins
        font_bucket_10: Bbox height threshold for 10pt font (default 22)
        font_bucket_11: Bbox height threshold for 11pt font (default 30)
        font_bucket_12: Bbox height threshold for 12pt font (default 40)
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

    try:
        # Validate file
        progress(0.05, desc="Validating PDF file...")

        # Check file extension
        if not validate_pdf_path(pdf_path):
            raise gr.Error("Invalid file. Please upload a PDF file.")

        # Check file size (MinerU API limit is 200MB)
        is_valid, size_mb, msg = check_file_size_limit(pdf_path, max_mb=200)
        if not is_valid:
            raise gr.Error(msg)

        progress(0.1, desc=f"Processing PDF ({size_mb:.1f} MB)...")

        # Submit to MinerU API
        progress(0.15, desc="Submitting to MinerU API...")
        result = mineru.process_pdf(pdf_path, output_format=output_format, language=language)

        task_id = result.get("task_id")
        status = result.get("status")
        result_data = result.get("result", {})

        if status == "completed":
            progress(0.8, desc="Parsing complete! Building PDF...")

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
                        "bucket_10": font_bucket_10,
                        "bucket_11": font_bucket_11,
                        "bucket_12": font_bucket_12,
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
        raise
    except Exception as e:
        raise gr.Error(f"Processing failed: {str(e)}")


# Create Gradio interface
with gr.Blocks(title="PDF Document Cleaner") as app:
    gr.Markdown("""
    # 📚 PDF Document Cleaner

    Upload a scanned PDF document and get a clean, readable document
    with text extracted via **MinerU API** and preserved structure.

    **Features:**
    - Multi-language OCR support (109 languages including Russian)
    - Preserves document structure: headings, paragraphs, lists
    - Extracts images, tables, and formulas
    - Outputs searchable PDF

    **Limitations:**
    - Maximum file size: 200 MB
    - Requires internet connection (MinerU cloud API)
    """)

    with gr.Row():
        with gr.Column():
            pdf_input = gr.File(
                label="Upload PDF Document",
                file_types=[".pdf"],
                type="filepath"
            )

            output_format = gr.Radio(
                choices=[
                    ("JSON → PDF (Structured, preserves tables/images)", "json"),
                    ("Markdown → PDF (Simple text-focused)", "markdown")
                ],
                value="json",
                label="Output Format",
                info="JSON preserves more structure, Markdown is simpler"
            )

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
                label="Document Language",
                info="Select the primary language for better OCR accuracy"
            )

            gr.Markdown("""
            **Tips for best results:**
            - Use high-quality scans
            - Ensure pages are properly oriented
            - Files must be under 200 MB
            """)

            download_raw = gr.Checkbox(
                label="Download raw MinerU output (for diagnostics)",
                value=False,
                info="Enable to also download the raw MinerU ZIP file for debugging"
            )

            keep_original_margins = gr.Checkbox(
                label="Keep original page margins",
                value=True,
                info="When unchecked, uses consistent 1.5cm margins on all sides"
            )

            gr.Markdown("---")
            gr.Markdown("### 🎨 Font Size Buckets (bbox height thresholds)")

            font_bucket_10 = gr.Slider(
                minimum=16,
                maximum=28,
                value=22,
                step=1,
                label="9pt → 10pt threshold",
                info="Bbox height below this → 9pt, above → 10pt (default: 22)"
            )

            font_bucket_11 = gr.Slider(
                minimum=20,
                maximum=35,
                value=30,
                step=1,
                label="10pt → 11pt threshold",
                info="Bbox height below this → 10pt, above → 11pt (default: 30)"
            )

            font_bucket_12 = gr.Slider(
                minimum=25,
                maximum=50,
                value=40,
                step=1,
                label="11pt → 12pt threshold",
                info="Bbox height below this → 11pt, above → 12pt (default: 40)"
            )

            process_btn = gr.Button(
                "🚀 Process Document",
                variant="primary",
                size="lg"
            )

        with gr.Column():
            output_file = gr.File(
                label="📥 Download Cleaned Document",
                type="filepath"
            )

            mineru_output = gr.File(
                label="🔧 Download Raw MinerU Output (ZIP)",
                type="filepath",
                visible=False
            )

            gr.Markdown("""
            **What happens during processing:**
            1. PDF is uploaded to MinerU cloud API
            2. Document is parsed with AI-powered OCR
            3. Text, images, tables are extracted
            4. Clean PDF is generated with preserved structure
            """)

    # Toggle MinerU output visibility when checkbox changes
    download_raw.change(
        fn=lambda x: gr.update(visible=x),
        inputs=[download_raw],
        outputs=[mineru_output]
    )

    # Connect processing function
    process_btn.click(
        fn=process_pdf,
        inputs=[pdf_input, output_format, language, download_raw, keep_original_margins,
                font_bucket_10, font_bucket_11, font_bucket_12],
        outputs=[output_file, mineru_output]
    )

    gr.Markdown("""
    ---

    **Powered by [MinerU](https://mineru.net/)** - An open-source document parsing solution.

    Processing time depends on document length and complexity, typically 10-60 seconds.
    """)


if __name__ == "__main__":
    app.launch()
