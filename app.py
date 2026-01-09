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
from src.pipeline import PDFProcessingPipeline, apply_corrections_and_generate_pdf
from src.processing_options import ProcessingOptions
from src.utils import clean_filename

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
    rendering_mode: str,
    binarize_enabled: bool,
    binarize_block_size: int,
    binarize_c_constant: int,
    enable_formula: bool,
    enable_footnote_detection: bool,
    font_bucket_9: float,
    font_bucket_10: float,
    font_bucket_11: float,
    font_bucket_12: float,
    font_bucket_14: float,
    enable_ocr_correction: bool,
    quality_cutoff: float,
    progress=gr.Progress()
) -> tuple:
    """
    Main processing pipeline using MinerU API.

    This is a thin wrapper around PDFProcessingPipeline that:
    1. Validates inputs
    2. Creates ProcessingOptions from UI parameters
    3. Executes pipeline
    4. Converts ProcessingResult to Gradio UI outputs

    Args:
        pdf_file: Uploaded PDF file object
        language: Language code for OCR (e.g., "ru" for Russian)
        download_raw: If True, also return raw MinerU output ZIP
        rendering_mode: "exact" for exact positioning, "flow" for flow-based rendering with calculated margins
        binarize_enabled: If True, preprocess PDF with binarization before sending to MinerU
        binarize_block_size: Block size for adaptive thresholding (odd number, 11-51)
        binarize_c_constant: C constant subtracted from mean for adaptive thresholding (0-30)
        enable_formula: If True, enable MinerU formula recognition; if False, treat as text
        enable_footnote_detection: If True, detect footnotes by position and content pattern
        font_bucket_9: Line height threshold in points for 9pt font (default 17.0)
        font_bucket_10: Line height threshold in points for 10pt font (default 22.0)
        font_bucket_11: Line height threshold in points for 11pt font (default 28.0)
        font_bucket_12: Line height threshold in points for 12pt font (default 30.0)
        font_bucket_14: Line height threshold in points for 14pt font (default 32.0)
        enable_ocr_correction: If True, pause for manual OCR correction of low-confidence items
        quality_cutoff: Confidence threshold for flagging items for review (0.0-1.0)
        progress: Gradio progress tracker

    Returns:
        Tuple of (output PDF path, binarized PDF path or None, MinerU ZIP path or None,
                 corrections_table, apply_btn, state, status, correction_status)
    """
    if pdf_file is None:
        raise gr.Error("Please upload a PDF file")

    if mineru is None:
        raise gr.Error(
            "MinerU API not configured. "
            "Please set MINERU_API_KEY environment variable."
        )

    # Save original filename for final output naming (before any preprocessing)
    original_base_name = clean_filename(os.path.basename(pdf_file.name))

    # Convert rendering mode to boolean for backend compatibility
    # "exact" → True (exact positioning), "flow" → False (flow-based rendering)
    keep_original_margins = (rendering_mode == "exact")

    # Create processing options from UI parameters
    try:
        options = ProcessingOptions(
            pdf_path=pdf_file.name,
            language=language,
            download_raw=download_raw,
            keep_original_margins=keep_original_margins,
            binarize_enabled=binarize_enabled,
            binarize_block_size=binarize_block_size,
            binarize_c_constant=binarize_c_constant,
            enable_formula=enable_formula,
            enable_footnote_detection=enable_footnote_detection,
            font_buckets={
                "bucket_9": font_bucket_9,
                "bucket_10": font_bucket_10,
                "bucket_11": font_bucket_11,
                "bucket_12": font_bucket_12,
                "bucket_14": font_bucket_14,
            },
            enable_ocr_correction=enable_ocr_correction,
            quality_cutoff=quality_cutoff,
            original_filename=original_base_name,
        )
    except ValueError as e:
        raise gr.Error(f"Invalid configuration: {str(e)}")

    # Create pipeline and execute
    pipeline = PDFProcessingPipeline(
        mineru_processor=mineru,
        progress_callback=lambda p, d: progress(p, desc=d)
    )

    result = pipeline.process(options)

    # Convert result to Gradio outputs
    if result.is_failed:
        raise gr.Error(result.error or "Processing failed")

    return result.to_gradio_outputs()


# Create Gradio interface
with gr.Blocks(title="PDF Cleaner & OCR Corrector") as app:
    gr.Markdown("# 📄 PDF Cleaner & OCR Corrector")

    gr.Markdown("""
    Powered by [MinerU](https://mineru.net/) - An open-source document parsing solution.

    📖 **[View User Guide](https://github.com/michaelarutyunov/scan-enhancer/blob/main/docs/USER_GUIDE.md)** - Detailed settings explanations & troubleshooting
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
                value="en",
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
            gr.Markdown("### Rendering Settings")

            download_raw = gr.Checkbox(
                label="Download raw MinerU output (for diagnostics)",
                value=True,
                info="Enable to also download the raw MinerU ZIP file for debugging"
            )

            rendering_mode = gr.Radio(
                label="PDF Rendering Mode",
                choices=[
                    ("Exact Layout - Preserves original positioning and spacing", "exact"),
                    ("Flow Layout - Reformats with consistent margins", "flow")
                ],
                value="exact",
                info="Choose how the PDF should be rendered"
            )

            with gr.Accordion("📊 Mode Comparison - Which should I choose?", open=False):
                gr.Markdown("""
| Feature | Exact Layout | Flow Layout |
|---------|-------------|-------------|
| **Positioning** | Preserves exact X/Y coordinates from scan | Reformats content with dynamic spacing |
| **Margins** | Uses original document margins (may be uneven) | Calculates consistent margins (0.5-2cm) |
| **Font Sizing** | Analyzes line heights, customizable via buckets | Fixed sizes (titles: 12pt, body: 10.5pt, footnotes: 8pt) |
| **Best For** | Documents with specific layouts, tables, diagrams | Text-heavy documents, books, articles |
| **Customization** | High - adjust font bucket thresholds | Limited - uses standard typography |

**💡 Tip**: Try **Exact Layout** first. If margins look uneven or fonts are inconsistent, switch to **Flow Layout**.
                """)

            enable_formula = gr.Checkbox(
                label="Enable formula detection (MinerU feature)",
                value=False,
                info="Disable if text is being misclassified as equations (e.g., single letters or special characters)"
            )

            enable_footnote_detection = gr.Checkbox(
                label="Detect footnotes automatically",
                value=False,
                info="Works in both modes. Detects footnotes at page bottom and renders in 8pt font"
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

            # Font Size Buckets Section (only for Exact Layout mode)
            with gr.Group(visible=True) as font_buckets_group:
                gr.Markdown("---")
                gr.Markdown("### Font Size Buckets (line height thresholds in points)")
                gr.Markdown("*Only applies to Exact Layout mode. Flow mode uses standard fonts.*")

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

    # Toggle font buckets visibility based on rendering mode
    rendering_mode.change(
        fn=lambda mode: gr.update(visible=(mode == "exact")),
        inputs=[rendering_mode],
        outputs=[font_buckets_group]
    )

    # Connect processing function
    process_btn.click(
        fn=process_pdf,
        inputs=[pdf_input, language, download_raw, rendering_mode, binarize_enabled,
                binarize_block_size, binarize_c_constant, enable_formula, enable_footnote_detection,
                font_bucket_9, font_bucket_10, font_bucket_11, font_bucket_12, font_bucket_14,
                enable_ocr_correction, quality_cutoff],
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
        fn=lambda pdf_path, status: (
            gr.update(visible=pdf_path is not None),  # output_file - show if PDF generated
            gr.update(visible=False),  # corrections_table - hide
            gr.update(visible=False),  # apply_corrections_btn - hide
            gr.update(visible=False),  # correction_header - hide
            gr.update(visible=False),  # correction_instructions - hide
            gr.update(visible=status is not None),  # correction_status - show with message
            None  # processor_state - clear
        ),
        inputs=[output_file, correction_status],
        outputs=[
            output_file,
            corrections_table,
            apply_corrections_btn,
            correction_header,
            correction_instructions,
            correction_status,
            processor_state
        ]
    )


if __name__ == "__main__":
    app.launch(ssr_mode=False)  # Disable SSR to fix DataFrame rendering issues
