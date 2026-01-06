"""MinerU API Processor Module

Handles communication with MinerU API for PDF parsing.
"""
import os
import time
import requests
from typing import Dict, Optional, Literal
from pathlib import Path


OutputFormat = Literal["json", "markdown"]


class MinerUAPIProcessor:
    """Client for MinerU API to parse PDF documents."""

    API_BASE_URL = "https://mineru.net/api/v4"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize MinerU API client.

        Args:
            api_key: MinerU API key. If None, reads from MINERU_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("MINERU_API_KEY")
        if not self.api_key:
            raise ValueError(
                "MINERU_API_KEY not found. "
                "Set it in .env file or pass as parameter."
            )

        self.headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

    def submit_task(
        self,
        pdf_path: str,
        output_format: OutputFormat = "json"
    ) -> str:
        """
        Submit a PDF parsing task to MinerU API using the file-urls/batch workflow.

        Args:
            pdf_path: Path to the PDF file to parse
            output_format: "json" or "markdown"

        Returns:
            task_id: The task ID for polling

        Raises:
            requests.RequestException: If API call fails
        """
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        # Check file size (API limit is ~20MB for single file)
        file_size_mb = pdf_file.stat().st_size / (1024 * 1024)
        if file_size_mb > 20:
            raise ValueError(
                f"PDF file too large: {file_size_mb:.1f}MB. "
                f"API limit is 20MB."
            )

        # Step 1: Get upload URL from file-urls/batch endpoint
        batch_url = f"{self.API_BASE_URL}/file-urls/batch"
        batch_data = {
            "urls": [{
                "filename": pdf_file.name,
                "file_size": pdf_file.stat().st_size
            }]
        }

        batch_response = requests.post(
            batch_url,
            headers=self.headers,
            json=batch_data,
            timeout=30
        )
        batch_response.raise_for_status()
        batch_result = batch_response.json()

        # Extract upload URL from response
        if batch_result.get("code") != 0:
            raise ValueError(f"Failed to get upload URL: {batch_result}")

        upload_info = batch_result.get("data", {}).get("urls", [{}])[0]
        upload_url = upload_info.get("upload_url")
        task_id = upload_info.get("task_id")

        if not upload_url or not task_id:
            raise ValueError(f"No upload URL or task_id in response: {batch_result}")

        # Step 2: Upload file to the presigned URL using PUT
        with open(pdf_path, "rb") as f:
            upload_response = requests.put(
                upload_url,
                data=f,
                headers={},  # Don't set Content-Type, let OSS handle it
                timeout=120
            )
        upload_response.raise_for_status()

        return task_id

    def get_task_status(self, task_id: str) -> Dict:
        """
        Get the status of a parsing task.

        Args:
            task_id: The task ID to check

        Returns:
            Dict with task status and result if complete

        Raises:
            requests.RequestException: If API call fails
        """
        url = f"{self.API_BASE_URL}/extract/task/{task_id}"

        response = requests.get(
            url,
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()

        return response.json()

    def poll_task(
        self,
        task_id: str,
        max_wait_seconds: int = 600,
        poll_interval: int = 5
    ) -> Dict:
        """
        Poll a task until completion or timeout.

        Args:
            task_id: The task ID to poll
            max_wait_seconds: Maximum time to wait (default 10 min)
            poll_interval: Seconds between polls

        Returns:
            Dict with the completed task result

        Raises:
            TimeoutError: If task doesn't complete in time
            requests.RequestException: If API call fails
        """
        start_time = time.time()

        while True:
            result = self.get_task_status(task_id)

            # Check response structure
            if result.get("code") == 0:
                data = result.get("data", {})
                status = data.get("status", "")

                if status == "completed":
                    return result
                elif status == "failed":
                    error = data.get("error", "Unknown error")
                    raise RuntimeError(f"Task failed: {error}")
                elif status in ("pending", "processing"):
                    # Continue polling
                    pass
                else:
                    # Unknown status but continue polling
                    pass
            else:
                # Error response, but might be transient
                error_msg = result.get("msg", "Unknown error")
                print(f"Warning: API returned error: {error_msg}")

            # Check timeout
            if time.time() - start_time > max_wait_seconds:
                raise TimeoutError(
                    f"Task {task_id} did not complete within "
                    f"{max_wait_seconds} seconds"
                )

            time.sleep(poll_interval)

    def process_pdf(
        self,
        pdf_path: str,
        output_format: OutputFormat = "json"
    ) -> Dict:
        """
        Complete workflow: submit, poll, and get result.

        Args:
            pdf_path: Path to the PDF file
            output_format: "json" or "markdown"

        Returns:
            Dict with task_id, status, and result_url or content
        """
        task_id = self.submit_task(pdf_path, output_format)
        result = self.poll_task(task_id)

        return {
            "task_id": task_id,
            "status": result.get("data", {}).get("status"),
            "result": result.get("data", {})
        }
