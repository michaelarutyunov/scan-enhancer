"""
OCR Post-Processor Module

Handles extraction of low-confidence OCR results and manual correction workflow.
Filters MinerU OCR output by confidence scores and enables user to manually correct errors.
"""

import json
import shutil
from pathlib import Path
from typing import List, Dict, Tuple
import pandas as pd


class OCRPostProcessor:
    """
    Manages OCR quality control and manual correction workflow.

    This class extracts low-confidence OCR results from MinerU's layout.json,
    presents them to users for manual correction via a DataFrame interface,
    and applies corrections back to the layout.json file.
    """

    def __init__(self, layout_json_path: str, quality_threshold: float = 0.95):
        """
        Initialize OCR post-processor.

        Args:
            layout_json_path: Path to MinerU layout.json file
            quality_threshold: Confidence score threshold (0.0-1.0).
                             Items below this threshold will be flagged for review.
        """
        self.layout_path = Path(layout_json_path)
        self.threshold = quality_threshold
        self.layout_data = None
        self.low_conf_items = []

    def load_layout(self) -> Dict:
        """
        Load layout.json from MinerU output.

        Returns:
            Dict containing the parsed JSON data
        """
        with open(self.layout_path, 'r', encoding='utf-8') as f:
            self.layout_data = json.load(f)
        return self.layout_data

    def extract_low_confidence_items(self) -> List[Dict]:
        """
        Extract text items with confidence below threshold.

        Scans through all pages, blocks, lines, and spans in the layout.json
        to find text with OCR confidence scores below the threshold.

        Returns:
            List of dicts with keys:
                - id: Sequential item ID
                - page: Page number
                - score: OCR confidence score (0.0-1.0)
                - block_type: Type of block (text, title, etc.)
                - content: Original OCR text
                - correction: Initialized to original text (for user to edit)
                - location: Dict with positional info for applying corrections
        """
        if not self.layout_data:
            self.load_layout()

        low_conf_items = []
        item_id = 0

        # Iterate through all pages
        for page in self.layout_data.get("pdf_info", []):
            page_idx = page.get("page_idx", 0)

            # Process both preproc_blocks and discarded_blocks
            for block_list, block_category in [
                (page.get("preproc_blocks", []), "preproc"),
                (page.get("discarded_blocks", []), "discarded")
            ]:
                for block_idx, block in enumerate(block_list):
                    block_type = block.get("type", "unknown")

                    # Only process text and title blocks
                    if block_type not in ["text", "title"]:
                        continue

                    # Iterate through lines in block
                    for line_idx, line in enumerate(block.get("lines", [])):
                        # Iterate through spans in line
                        for span_idx, span in enumerate(line.get("spans", [])):
                            if span.get("type") != "text":
                                continue

                            score = span.get("score", 1.0)
                            content = span.get("content", "")

                            # Check if below threshold and has content
                            if score < self.threshold and content.strip():
                                low_conf_items.append({
                                    "id": item_id,
                                    "page": page_idx,
                                    "score": round(score, 3),
                                    "block_type": block_type,
                                    "content": content,
                                    "correction": content,  # Initialize with original
                                    # Store location for patching later
                                    "location": {
                                        "page_idx": page_idx,
                                        "block_category": block_category,
                                        "block_idx": block_idx,
                                        "line_idx": line_idx,
                                        "span_idx": span_idx
                                    }
                                })
                                item_id += 1

        self.low_conf_items = low_conf_items
        return low_conf_items

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert low-confidence items to pandas DataFrame for UI display.

        Creates a user-friendly table format for display in Gradio's
        DataFrame component.

        Returns:
            DataFrame with columns: Page, Score, Type, Original, Correction
        """
        if not self.low_conf_items:
            return pd.DataFrame(
                columns=["Page", "Score", "Type", "Original", "Correction"]
            )

        df_data = []
        for item in self.low_conf_items:
            df_data.append({
                "Page": item["page"],
                "Score": item["score"],
                "Type": item["block_type"],
                "Original": item["content"],
                "Correction": item["correction"]
            })

        return pd.DataFrame(df_data)

    def from_dataframe(self, df: pd.DataFrame) -> None:
        """
        Update corrections from DataFrame (edited in UI).

        Takes the user-edited DataFrame and updates the internal
        low_conf_items list with the corrections.

        Args:
            df: DataFrame with 'Correction' column updated by user

        Raises:
            ValueError: If DataFrame row count doesn't match low_conf_items
        """
        if len(df) != len(self.low_conf_items):
            raise ValueError(
                f"DataFrame has {len(df)} rows but expected {len(self.low_conf_items)} items"
            )

        for idx, row in df.iterrows():
            self.low_conf_items[idx]["correction"] = str(row["Correction"])

    def apply_corrections(self, backup: bool = True) -> Tuple[str, int]:
        """
        Apply user corrections to layout.json.

        Patches the original layout.json file with user corrections.
        Optionally creates a backup before modifying.

        Args:
            backup: If True, save layout.json as layout_uncorrected.json first

        Returns:
            Tuple of (status_message, num_corrections_applied)
        """
        if not self.layout_data:
            self.load_layout()

        # Backup original if requested
        if backup:
            backup_path = self.layout_path.parent / "layout_uncorrected.json"
            shutil.copy(self.layout_path, backup_path)

        # Apply corrections
        num_applied = 0
        num_deleted = 0

        for item in self.low_conf_items:
            correction = item["correction"].strip()
            original = item["content"]

            # Skip if no change
            if correction == original:
                continue

            loc = item["location"]

            # Navigate to the span in the data structure
            page = self.layout_data["pdf_info"][loc["page_idx"]]

            if loc["block_category"] == "preproc":
                blocks = page["preproc_blocks"]
            else:
                blocks = page["discarded_blocks"]

            block = blocks[loc["block_idx"]]
            line = block["lines"][loc["line_idx"]]
            span = line["spans"][loc["span_idx"]]

            # Apply correction
            if correction:
                span["content"] = correction
                num_applied += 1
            else:
                # Empty correction = delete
                span["content"] = ""
                num_deleted += 1

        # Save modified layout.json
        with open(self.layout_path, 'w', encoding='utf-8') as f:
            json.dump(self.layout_data, f, ensure_ascii=False, indent=2)

        # Build status message
        status = f"Applied {num_applied} corrections, deleted {num_deleted} items"
        if backup:
            status += f" | Backup: layout_uncorrected.json"

        return status, num_applied + num_deleted
