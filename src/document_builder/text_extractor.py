"""Text Extraction Module

Handles text extraction from MinerU layout structures, including:
- Line and span parsing from nested layout blocks
- Text extraction with line break preservation
- Footnote detection using position and content pattern analysis
"""
from typing import Dict, List
import re


class TextExtractor:
    """Extract and process text from MinerU layout structures.

    This class handles:
    - Parsing text from nested lines/spans structures
    - Preserving line breaks and text hierarchy
    - Detecting footnotes based on position and content patterns
    """

    def __init__(self, enable_footnote_detection: bool = False):
        """
        Initialize text extractor.

        Args:
            enable_footnote_detection: If True, detect footnotes by position and content pattern
        """
        self.enable_footnote_detection = enable_footnote_detection

    def extract_text_lines_from_block(self, block: Dict) -> List[str]:
        """
        Extract text lines from block's lines/spans structure, preserving line breaks.

        MinerU layout blocks contain nested structure:
        block -> lines[] -> spans[] -> content

        This method flattens the structure while preserving line boundaries.
        Each line's spans are joined with spaces, but lines are kept separate.

        Args:
            block: Block with lines array containing spans

        Returns:
            List of text strings, one per line

        Example:
            Input block:
            {
                "lines": [
                    {"spans": [{"content": "Hello"}, {"content": "world"}]},
                    {"spans": [{"content": "Next line"}]}
                ]
            }

            Output: ["Hello world", "Next line"]
        """
        lines = block.get("lines", [])
        text_lines = []

        for line in lines:
            spans = line.get("spans", [])
            line_text_parts = []
            for span in spans:
                content = span.get("content", "")
                if content:
                    line_text_parts.append(content)

            # Join spans within a line with spaces, but keep lines separate
            if line_text_parts:
                text_lines.append(" ".join(line_text_parts))

        return text_lines

    def is_footnote_block(self, block: Dict, page_height: float) -> bool:
        """
        Detect if block is a footnote based on position and content pattern.

        Uses two signals to identify footnotes:
        1. Position: Block must be in bottom 20% of page
        2. Content pattern: First line must start with digit + space + letter

        Footnote example: "1 Литературовед"
        List example (NOT footnote): "1. Расскажите"

        Both signals are required to reduce false positives.

        Args:
            block: Block data with bbox and lines
            page_height: Page height in pixels (from layout.json page_size)

        Returns:
            True if block appears to be a footnote, False otherwise

        Example:
            Block at y=800px on 1000px page with content "1 Footnote text"
            -> is_at_bottom=True, has_footnote_pattern=True -> True

            Block at y=800px with content "1. List item"
            -> is_at_bottom=True, has_footnote_pattern=False -> False
        """
        if not self.enable_footnote_detection:
            return False

        bbox = block.get("bbox", [0, 0, 0, 0])
        y_top = bbox[1]

        # Signal 1: Position - bottom 20% of page
        # y increases downward in MinerU coordinates (top-left origin)
        is_at_bottom = y_top > page_height * 0.80
        if not is_at_bottom:
            return False

        # Signal 2: Content pattern - starts with number + space + letter
        # Footnotes: "1 Литературовед" (digit + space + letter)
        # vs Lists: "1. Расскажите" (digit + period + space)
        first_line_content = ""
        lines = block.get("lines", [])
        if lines:
            spans = lines[0].get("spans", [])
            if spans:
                first_line_content = spans[0].get("content", "")

        # Pattern: starts with digit(s), followed by space, then letter
        # Matches: "1 Text", "12 Text", "123 Text"
        # Does not match: "1. Text", "1) Text", "Text"
        has_footnote_pattern = bool(re.match(r'^\d+\s+[A-ZА-Яa-zа-я]', first_line_content))

        # Require BOTH signals to reduce false positives
        return has_footnote_pattern

    def extract_text_from_mineru_format(self, content: any) -> str:
        """
        Extract plain text from MinerU JSON format.

        Handles both list and dict formats:
        - List: [{'type': 'text', 'text': '...'}, ...]
        - Dict: {'content': [{'type': 'text', 'text': '...'}, ...]}

        Args:
            content: MinerU JSON response (list or dict)

        Returns:
            Extracted text as a single string with newlines
        """
        # Handle if content is already a list
        if isinstance(content, list):
            items = content
        elif isinstance(content, dict) and "content" in content:
            items = content["content"]
        else:
            # Fallback: try as markdown
            return content.get("text", "") if isinstance(content, dict) else str(content)

        text_parts = []

        for item in items:
            item_type = item.get("type", "")

            if item_type == "text":
                text = item.get("text", "")
                if text:
                    text_parts.append(text)
            elif item_type == "header":
                text = item.get("text", "")
                if text:
                    text_parts.append(f"\n{text}\n")
            elif item_type in ("image", "table", "equation"):
                # Skip non-text content
                continue
            elif item_type in ("page_footnote", "page_number", "discarded"):
                # Skip metadata
                continue
            else:
                # Unknown type, try to extract text
                text = item.get("text", "")
                if text:
                    text_parts.append(text)

        return "\n".join(text_parts)
