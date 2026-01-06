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

    API_BASE_URL = "https://api.mineru.net/api/v1"

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
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def submit_task(
        self,
        pdf_path: str,
        output_format: OutputFormat = "json"
    ) -> str:
        """
        Submit a PDF parsing task to MinerU API.

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

        # Check file size (API limit is 200MB)
        file_size_mb = pdf_file.stat().st_size / (1024 * 1024)
        if file_size_mb > 200:
            raise ValueError(
                f"PDF file too large: {file_size_mb:.1f}MB. "
                f"API limit is 200MB."
            )

        url = f"{self.API_BASE_URL}/tasks/submit"

        # Prepare multipart form data
        files = {
            "file": (pdf_file.name, open(pdf_path, "rb"), "application/pdf")
        }
        data = {
            "output_format": output_format
        }

        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files=files,
                data=data,
                timeout=60
            )
            response.raise_for_status()

            result = response.json()
            task_id = result.get("data", {}).get("task_id")

            if not task_id:
                raise ValueError(f"No task_id in response: {result}")

            return task_id

        finally:
            files["file"][1].close()

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
        url = f"{self.API_BASE_URL}/tasks/{task_id}"

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
            data = result.get("data", {})
            status = data.get("status")

            if status == "completed":
                return result
            elif status == "failed":
                error = data.get("error", "Unknown error")
                raise RuntimeError(f"Task failed: {error}")
            elif status in ("pending", "processing"):
                # Continue polling
                pass
            else:
                raise ValueError(f"Unknown status: {status}")

            # Check timeout
            if time.time() - start_time > max_wait_seconds:
                raise TimeoutError(
                    f"Task {task_id} did not complete within "
                    f"{max_wait_seconds} seconds"
                )

            time.sleep(poll_interval)

    def download_result(self, task_id: str, output_path: str) -> str:
        """
        Download the result file from a completed task.

        Args:
            task_id: The completed task ID
            output_path: Where to save the result file

        Returns:
            Path to the downloaded file

        Raises:
            requests.RequestException: If download fails
        """
        url = f"{self.API_BASE_URL}/tasks/{task_id}/download"

        response = requests.get(
            url,
            headers=self.headers,
            stream=True,
            timeout=60
        )
        response.raise_for_status()

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return str(output_file)

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
