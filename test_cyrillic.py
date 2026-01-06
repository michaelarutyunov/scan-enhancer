#!/usr/bin/env python3
"""
Test script to verify Cyrillic rendering works correctly.

This script creates a test PDF with known Cyrillic text to verify
that the font setup is working correctly.

Usage:
    python test_cyrillic.py

Output:
    Creates test_cyrillic_output.pdf in the current directory.
    Check the PDF to verify Cyrillic characters are rendered correctly.
"""
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.document_builder import DocumentBuilder


def test_cyrillic_rendering():
    """Test Cyrillic text rendering in PDF output."""
    print("=" * 60)
    print("CYRILLIC FONT TEST")
    print("=" * 60)

    # Test content with known Cyrillic text
    test_content = [
        {"type": "header", "text": "Тест кириллицы"},
        {"type": "text", "text": "Литовские пословицы и поговорки"},
        {"type": "text", "text": "Много рук поднимут и тяжкую ношу."},
        {"type": "text", "text": "Жизнь — счастье в труде."},
        {"type": "text", "text": "Не нажав сошника, не выкопаешь пирога."},
        {"type": "header", "text": "Немецкие"},
        {"type": "text", "text": "Бесполезно носить дрова в лес."},
        {"type": "text", "text": "Время выиграно — всё выиграно."},
        {"type": "header", "text": "Алфавит"},
        {"type": "text", "text": "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"},
        {"type": "text", "text": "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"},
    ]

    output_path = "test_cyrillic_output.pdf"

    # Create document builder
    builder = DocumentBuilder(output_path)

    print(f"\nFont in use: {builder.font_name}")
    print(f"Font is Cyrillic-capable: {builder.font_name != 'Helvetica'}")

    if builder.font_name == 'Helvetica':
        print("\n⚠️  WARNING: Using Helvetica fallback!")
        print("   Cyrillic text will NOT render correctly.")
        print("   Install fonts-dejavu-core or add DejaVuSans.ttf to fonts/ directory")
    else:
        print(f"\n✅ Using Cyrillic-capable font: {builder.font_name}")

    # Add test content
    builder.add_from_mineru_json(test_content)

    # Finalize PDF
    builder.finalize()

    print(f"\n📄 Test PDF created: {output_path}")
    print("   Open the PDF and verify that Cyrillic text is readable.")
    print("   Expected: Proper Russian letters (Ц, Ч, Ш, Щ, Ы, Ь, Э, Ю, Я, etc.)")
    print("   Failure:  Latin lookalikes (JI for Л, H for И, T for Т, etc.)")
    print("=" * 60)

    return output_path


if __name__ == "__main__":
    test_cyrillic_rendering()
