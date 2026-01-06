"""MinerU API Processor Module

Handles communication with MinerU API for PDF parsing.
"""
import os
import time
import requests
import zipfile
import io
import json
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
        output_format: OutputFormat = "json",
        language: str = "ru"
    ) -> str:
        """
        Submit a PDF parsing task to MinerU API using the file-urls/batch workflow.

        Args:
            pdf_path: Path to the PDF file to parse
            output_format: "json" or "markdown"
            language: Document language code (e.g., "ru" for Russian, "ch" for Chinese)

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

        # Step 1: Get upload URL from file-urls/batch endpoint
        batch_url = f"{self.API_BASE_URL}/file-urls/batch"
        batch_data = {
            "model_version": "pipeline",  # Use pipeline for better multi-language support (Russian, etc.)
            "language": language,
            "files": [{
                "name": pdf_file.name,
                "data_id": pdf_file.stem  # Use filename without extension as data_id
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

        # Extract upload URL and task_id from response
        if batch_result.get("code") != 0:
            raise ValueError(f"Failed to get upload URL: {batch_result}")

        data = batch_result.get("data", {})
        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls", [])

        if not file_urls:
            raise ValueError(f"No file_urls in response: {batch_result}")

        upload_url = file_urls[0]  # Use first upload URL
        task_id = batch_id  # Use batch_id as task_id for polling

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

        For batch file uploads, uses the batch results endpoint.

        Args:
            task_id: The batch_id to check

        Returns:
            Dict with task status and result if complete

        Raises:
            requests.RequestException: If API call fails
        """
        url = f"{self.API_BASE_URL}/extract-results/batch/{task_id}"

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

        For batch file uploads, polls the batch results endpoint.

        Args:
            task_id: The batch_id to poll
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

            # Check response structure for batch results
            if result.get("code") == 0:
                data = result.get("data", {})
                extract_results = data.get("extract_result", [])

                if not extract_results:
                    # No results yet, continue polling
                    pass
                else:
                    # Check first file's status
                    first_result = extract_results[0]
                    state = first_result.get("state", "")

                    if state == "done":
                        return result
                    elif state == "failed":
                        error = first_result.get("err_msg", "Unknown error")
                        raise RuntimeError(f"Task failed: {error}")
                    elif state in ("waiting-file", "pending", "running", "converting"):
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
        output_format: OutputFormat = "json",
        language: str = "ru"
    ) -> Dict:
        """
        Complete workflow: submit, poll, and get result.

        For batch file uploads, downloads and extracts the ZIP file content.

        Args:
            pdf_path: Path to the PDF file
            output_format: "json" or "markdown"
            language: Document language code (default "ru" for Russian)

        Returns:
            Dict with task_id, status ("completed"/"failed"), and parsed content or error message
        """
        task_id = self.submit_task(pdf_path, output_format, language)
        result = self.poll_task(task_id)

        # Extract data from batch response format
        data = result.get("data", {})
        extract_results = data.get("extract_result", [])

        if extract_results:
            first_result = extract_results[0]
            state = first_result.get("state", "")

            if state != "done":
                # Extract error message if available
                error_msg = first_result.get("err_msg", "Unknown error")
                return {
                    "task_id": task_id,
                    "status": state,  # Return actual state: failed, running, etc.
                    "result": {"error": error_msg}
                }

            # Download and extract the ZIP file content
            full_zip_url = first_result.get("full_zip_url")
            if not full_zip_url:
                return {
                    "task_id": task_id,
                    "status": "failed",
                    "result": {"error": "No full_zip_url in response"}
                }

            try:
                # Download the ZIP file
                zip_response = requests.get(full_zip_url, timeout=60)
                zip_response.raise_for_status()

                # Create a temporary directory for extracted files
                import tempfile
                temp_dir = tempfile.mkdtemp(prefix="mineru_")

                # Save ZIP file for diagnostic download
                zip_path = os.path.join(temp_dir, "mineru_output.zip")
                with open(zip_path, 'wb') as f:
                    f.write(zip_response.content)
                print(f"DEBUG: Saved MinerU ZIP to: {zip_path}")

                # Extract content from ZIP
                with zipfile.ZipFile(io.BytesIO(zip_response.content)) as zip_ref:
                    # Extract all files to temp directory
                    zip_ref.extractall(temp_dir)

                    # Find the content file
                    zip_files = zip_ref.namelist()
                    print(f"DEBUG: ZIP files: {zip_files}")

                    # Determine which file to use based on output format
                    content_file = None

                    if output_format == "json":
                        # For JSON format, look for content_list.json first
                        for f in zip_files:
                            if 'content_list' in f and f.endswith('.json'):
                                content_file = f
                                break

                    # If no JSON file found, or markdown requested, look for markdown
                    if not content_file:
                        for f in zip_files:
                            if f == 'full.md' or f.endswith('.md'):
                                content_file = f
                                break

                    # Fallback: first non-image, non-directory file
                    if not content_file:
                        for f in zip_files:
                            if not f.endswith('/') and not f.startswith('images/'):
                                content_file = f
                                break

                    if not content_file:
                        return {
                            "task_id": task_id,
                            "status": "failed",
                            "result": {"error": "No content file found in ZIP"}
                        }

                    print(f"DEBUG: Content file: {content_file}")
                    content_path = os.path.join(temp_dir, content_file)
                    with open(content_path, 'rb') as f:
                        content_bytes = f.read()

                    print(f"DEBUG: Content size: {len(content_bytes)} bytes")

                    # Parse based on file extension
                    if content_file.endswith('.json'):
                        # Parse JSON content
                        try:
                            content_text = content_bytes.decode('utf-8')
                            if not content_text.strip():
                                return {
                                    "task_id": task_id,
                                    "status": "failed",
                                    "result": {"error": "Content file is empty"},
                                    "zip_path": zip_path
                                }

                            # Log raw MinerU output for debugging
                            print("=" * 60)
                            print("DEBUG: RAW MINERU OUTPUT (first 500 chars):")
                            print(content_text[:500])
                            print("=" * 60)

                            content = json.loads(content_text)
                        except json.JSONDecodeError as je:
                            return {
                                "task_id": task_id,
                                "status": "failed",
                                "result": {"error": f"Invalid JSON: {str(je)}. First 200 chars: {content_text[:200]}"},
                                "zip_path": zip_path
                            }
                    else:
                        # Treat as markdown/text
                        content = content_bytes.decode('utf-8')

                        # Log raw MinerU output for debugging
                        print("=" * 60)
                        print("DEBUG: RAW MINERU OUTPUT (first 500 chars):")
                        print(content[:500])
                        print("=" * 60)

                    return {
                        "task_id": task_id,
                        "status": "completed",
                        "result": content,
                        "temp_dir": temp_dir,  # Pass temp dir for image access
                        "zip_path": zip_path   # Pass ZIP path for diagnostic download
                    }

            except Exception as e:
                import traceback
                return {
                    "task_id": task_id,
                    "status": "failed",
                    "result": {"error": f"Failed to download/extract ZIP: {str(e)}\nTraceback: {traceback.format_exc()}"}
                }
        else:
            return {
                "task_id": task_id,
                "status": "unknown",
                "result": {}
            }
