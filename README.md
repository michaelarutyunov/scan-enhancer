---
title: PDF Document Cleaner
emoji: 📚
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 6.0.0
app_file: app.py
pinned: false
python_version: "3.10"
---

# PDF Document Cleaner 📚

A HuggingFace Spaces application that processes scanned PDF documents using **MinerU API** to extract text while preserving images, tables, and document structure.

## Features

- **Multi-Language OCR**: Supports 109 languages including Russian, powered by MinerU
- **Structure Preservation**: Extracts and preserves headings, paragraphs, lists, tables, and images
- **Format Options**: Output as JSON (structured) or Markdown (simple text)
- **PDF Output**: Generates clean, searchable PDF documents
- **Cloud Processing**: Uses MinerU cloud API - no local models needed

## How It Works

1. **Upload**: PDF file is uploaded to the application
2. **API Processing**: File is sent to MinerU cloud API for parsing
3. **Content Extraction**: Text, images, tables, and formulas are extracted
4. **PDF Generation**: Clean PDF is assembled with preserved structure

## Usage

1. Upload a scanned PDF document (max 200 MB, 600 pages)
2. Select output format: JSON → PDF (structured) or Markdown → PDF (simple)
3. Click "Process Document"
4. Wait for processing to complete (typically 10-60 seconds)
5. Download the cleaned PDF

## Setup

### HuggingFace Spaces Deployment

1. Create a new Space on HuggingFace
2. Set `MINERU_API_KEY` as a Space secret (get your key at https://mineru.net/)
3. Upload all files from this repository
4. The Space will start automatically

### Local Development

```bash
# Clone repository
git clone <repo-url>
cd scan-enhancer

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and add your API key
cp .env.example .env
# Edit .env and add your MINERU_API_KEY

# Run application
python app.py
```

The app will be available at `http://localhost:7860`

## Technical Details

### Technology Stack

- **API**: MinerU Cloud API (document parsing)
- **PDF Processing**: ReportLab 4.0+ (PDF generation)
- **UI Framework**: Gradio 6.0+
- **HTTP Client**: requests 2.31+
- **Environment**: python-dotenv 1.0+

### Architecture

```
┌─────────────────┐
│  Gradio UI      │
│  (File Upload)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  File Validation│
│  - Size check   │
│  - Type check   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  MinerU API     │
│  Cloud Process  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Document       │
│  Builder (PDF)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Output (PDF)   │
└─────────────────┘
```

### Project Structure

```
scan-enhancer/
├── src/
│   ├── mineru_processor.py  # MinerU API client
│   ├── document_builder.py  # PDF output from API results
│   └── utils.py             # Helper functions
├── app.py                   # Main Gradio application
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variables template
└── README.md               # This file
```

## API Limits

| Limit | Value |
|-------|-------|
| File size | 200 MB per file |
| Pages | 600 pages per file |
| Daily quota | 2000 pages (varies by plan) |

*Get your API key at https://mineru.net/*

## License

See [LICENSE](LICENSE) file for details.

## Acknowledgments

- [MinerU](https://mineru.net/) for the document parsing API
- [Gradio](https://gradio.app/) for the UI framework
- [ReportLab](https://www.reportlab.com/) for PDF generation
