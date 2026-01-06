#!/usr/bin/env python3
"""Test script for layout.json based PDF rendering.

This script tests the exact positioning feature using layout.json from MinerU output.
"""
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.document_builder import create_pdf_from_layout, DocumentBuilder


def test_layout_rendering():
    """Test PDF rendering using layout.json."""

    # Paths to test files
    layout_json_path = "interim/layout.json"
    output_pdf_path = "interim/test_layout_output.pdf"
    temp_dir = "interim"

    if not os.path.exists(layout_json_path):
        print(f"ERROR: {layout_json_path} not found")
        return False

    # Load layout.json
    print(f"Loading {layout_json_path}...")
    with open(layout_json_path, 'r', encoding='utf-8') as f:
        layout_data = json.load(f)

    # Print summary
    pdf_info = layout_data.get("pdf_info", [])
    print(f"Found {len(pdf_info)} pages in layout.json")

    for i, page in enumerate(pdf_info):
        page_idx = page.get("page_idx", i)
        page_size = page.get("page_size", [0, 0])
        preproc_blocks = page.get("preproc_blocks", [])
        discarded_blocks = page.get("discarded_blocks", [])

        print(f"\nPage {page_idx}:")
        print(f"  Size: {page_size[0]}x{page_size[1]} points")
        print(f"  Content blocks: {len(preproc_blocks)}")
        print(f"  Discarded blocks: {len(discarded_blocks)}")

        # Show first few blocks for debugging
        for j, block in enumerate(preproc_blocks[:3]):
            block_type = block.get("type", "unknown")
            bbox = block.get("bbox", [])
            text = extract_text(block)[:50] if extract_text(block) else "[no text]"
            print(f"    Block {j}: type={block_type}, bbox={bbox}, text={text}...")

        # Show discarded blocks (page numbers)
        for j, block in enumerate(discarded_blocks):
            text = extract_text(block)
            if text.strip():
                print(f"    Page number: '{text.strip()}'")

    # Create PDF
    print(f"\nGenerating PDF: {output_pdf_path}")
    try:
        create_pdf_from_layout(
            output_path=output_pdf_path,
            layout_data=layout_data,
            temp_dir=temp_dir
        )
        print(f"SUCCESS: PDF created at {output_pdf_path}")

        # Check file size
        size_kb = os.path.getsize(output_pdf_path) / 1024
        print(f"Output file size: {size_kb:.1f} KB")

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def extract_text(block):
    """Extract text from block's lines/spans structure."""
    lines = block.get("lines", [])
    text_parts = []

    for line in lines:
        spans = line.get("spans", [])
        for span in spans:
            content = span.get("content", "")
            if content:
                text_parts.append(content)

    return " ".join(text_parts)


if __name__ == "__main__":
    success = test_layout_rendering()
    sys.exit(0 if success else 1)
