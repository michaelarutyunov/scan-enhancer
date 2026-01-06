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
from src.document_builder import create_pdf_from_mineru
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
    progress=gr.Progress()
) -> str:
    """
    Main processing pipeline using MinerU API.

    Args:
        pdf_file: Uploaded PDF file object
        output_format: "json" or "markdown" - MinerU output format
        progress: Gradio progress tracker

    Returns:
        Path to output PDF file for download
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
        result = mineru.process_pdf(pdf_path, output_format=output_format)

        task_id = result.get("task_id")
        status = result.get("status")

        if status == "completed":
            progress(0.8, desc="Parsing complete! Building PDF...")

            # Get the parsed content
            result_data = result.get("result", {})
            temp_dir = result.get("temp_dir")

            # Create output filename
            base_name = clean_filename(os.path.basename(pdf_path))
            output_path = f"{base_name}_cleaned.pdf"

            # Build PDF from MinerU output
            create_pdf_from_mineru(
                output_path=output_path,
                content=result_data,
                content_type=output_format,
                temp_dir=temp_dir
            )

            progress(1.0, desc="Complete!")
            return output_path
        else:
            raise gr.Error(f"Processing failed: {status}")

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

            gr.Markdown("""
            **Tips for best results:**
            - Use high-quality scans
            - Ensure pages are properly oriented
            - Files must be under 200 MB
            """)

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

            gr.Markdown("""
            **What happens during processing:**
            1. PDF is uploaded to MinerU cloud API
            2. Document is parsed with AI-powered OCR
            3. Text, images, tables are extracted
            4. Clean PDF is generated with preserved structure
            """)

    # Connect processing function
    process_btn.click(
        fn=process_pdf,
        inputs=[pdf_input, output_format],
        outputs=output_file
    )

    gr.Markdown("""
    ---

    **Powered by [MinerU](https://mineru.net/)** - An open-source document parsing solution.

    Processing time depends on document length and complexity, typically 10-60 seconds.
    """)


if __name__ == "__main__":
    app.launch()
