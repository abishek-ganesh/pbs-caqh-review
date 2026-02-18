"""
Mistral Document AI OCR client for CAQH PDF extraction.

This module provides OCR capabilities using Azure's Mistral Document AI,
which produces cleaner, more structured output than Tesseract OCR.

Usage:
    from src.extraction.mistral_ocr import MistralOCR

    ocr = MistralOCR()
    text = ocr.extract_text("path/to/document.pdf")
"""

import os
import base64
import json
import logging
import requests
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple

import PyPDF2

logger = logging.getLogger(__name__)

# Maximum pages per Mistral OCR request
MAX_PAGES_PER_CHUNK = 30


class MistralOCR:
    """
    OCR client using Azure Mistral Document AI.

    Produces clean, structured text with HTML table formatting
    that preserves label-value relationships.
    """

    DEFAULT_ENDPOINT = "https://pbs-caqh.services.ai.azure.com/providers/mistral/azure/ocr"
    DEFAULT_MODEL = "mistral-document-ai-2505"

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
    ):
        """
        Initialize the Mistral OCR client.

        Args:
            api_key: Azure API key (uses AZURE_OPENAI_API_KEY env var if not provided)
            endpoint: Mistral OCR endpoint URL
            model: Model name (defaults to mistral-document-ai-2505)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.endpoint = endpoint or os.getenv("AZURE_MISTRAL_ENDPOINT", self.DEFAULT_ENDPOINT)
        self.model = model or os.getenv("AZURE_MISTRAL_DEPLOYMENT_NAME", self.DEFAULT_MODEL)
        self.timeout = timeout

    def is_configured(self) -> bool:
        """Check if the Mistral OCR client is properly configured."""
        return bool(self.api_key)

    def get_page_count(self, pdf_path: str) -> int:
        """Get the number of pages in a PDF file."""
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return len(reader.pages)

    def split_pdf_into_chunks(
        self,
        pdf_path: str,
        chunk_size: int = MAX_PAGES_PER_CHUNK
    ) -> List[Tuple[str, int, int]]:
        """
        Split a PDF into chunks of specified page size.

        Args:
            pdf_path: Path to the PDF file
            chunk_size: Maximum pages per chunk (default: 30)

        Returns:
            List of (temp_file_path, start_page, end_page) tuples.
            Caller is responsible for cleaning up temp files.
        """
        chunks = []
        pdf_path = Path(pdf_path)

        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            total_pages = len(reader.pages)

            for start_page in range(0, total_pages, chunk_size):
                end_page = min(start_page + chunk_size, total_pages)

                # Create a new PDF with just this chunk's pages
                writer = PyPDF2.PdfWriter()
                for page_num in range(start_page, end_page):
                    writer.add_page(reader.pages[page_num])

                # Write to temp file
                temp_file = tempfile.NamedTemporaryFile(
                    suffix=".pdf",
                    prefix=f"chunk_{start_page+1}-{end_page}_",
                    delete=False
                )
                writer.write(temp_file)
                temp_file.close()

                chunks.append((temp_file.name, start_page + 1, end_page))
                logger.debug(f"Created chunk: pages {start_page + 1}-{end_page} -> {temp_file.name}")

        return chunks

    def extract_text(self, pdf_path: str, include_images: bool = False) -> str:
        """
        Extract text from a PDF using Mistral Document AI.

        For PDFs with more than 30 pages, automatically splits into chunks
        and merges results.

        Args:
            pdf_path: Path to the PDF file
            include_images: Whether to include base64 images in response

        Returns:
            Extracted text in markdown/HTML table format

        Raises:
            ValueError: If API key not configured
            FileNotFoundError: If PDF file not found
            Exception: If API request fails
        """
        if not self.is_configured():
            raise ValueError(
                "Mistral OCR not configured. "
                "Set AZURE_OPENAI_API_KEY environment variable."
            )

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Check page count - use chunking if > 30 pages
        page_count = self.get_page_count(str(pdf_path))
        logger.info(f"PDF has {page_count} pages")

        if page_count > MAX_PAGES_PER_CHUNK:
            return self._extract_text_chunked(str(pdf_path), page_count, include_images)

        # Standard extraction for PDFs <= 30 pages
        return self._extract_text_single(str(pdf_path), include_images)

    def _extract_text_single(self, pdf_path: str, include_images: bool = False) -> str:
        """Extract text from a single PDF (must be <= 30 pages)."""
        pdf_path = Path(pdf_path)

        # Convert PDF to base64
        logger.info(f"Converting PDF to base64: {pdf_path.name}")
        pdf_base64 = self._pdf_to_base64(str(pdf_path))

        # Build request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "document": {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{pdf_base64}"
            },
            "include_image_base64": include_images
        }

        # Make request
        logger.info(f"Sending to Mistral OCR endpoint...")
        response = requests.post(
            self.endpoint,
            headers=headers,
            json=payload,
            timeout=self.timeout
        )

        if response.status_code != 200:
            error_msg = f"Mistral OCR failed: {response.status_code} - {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        result = response.json()

        # Extract text from response
        text = self._extract_text_from_response(result)
        logger.info(f"Extracted {len(text):,} characters from {pdf_path.name}")

        return text

    def _extract_text_chunked(
        self,
        pdf_path: str,
        total_pages: int,
        include_images: bool = False
    ) -> str:
        """
        Extract text from a large PDF by splitting into chunks.

        Args:
            pdf_path: Path to the PDF file
            total_pages: Total number of pages
            include_images: Whether to include base64 images in response

        Returns:
            Merged text from all chunks
        """
        pdf_name = Path(pdf_path).name
        num_chunks = (total_pages + MAX_PAGES_PER_CHUNK - 1) // MAX_PAGES_PER_CHUNK

        logger.info(
            f"Large PDF detected: {total_pages} pages. "
            f"Processing in {num_chunks} chunks of up to {MAX_PAGES_PER_CHUNK} pages each..."
        )

        # Split PDF into chunks
        chunks = self.split_pdf_into_chunks(pdf_path)
        all_text_parts = []

        try:
            for i, (chunk_path, start_page, end_page) in enumerate(chunks, 1):
                logger.info(
                    f"[Chunk {i}/{num_chunks}] Processing pages {start_page}-{end_page}..."
                )

                try:
                    chunk_text = self._extract_text_single(chunk_path, include_images)
                    all_text_parts.append(f"--- Page {start_page}-{end_page} ---\n{chunk_text}")
                    logger.info(
                        f"[Chunk {i}/{num_chunks}] Extracted {len(chunk_text):,} characters"
                    )
                except Exception as e:
                    logger.error(f"[Chunk {i}/{num_chunks}] Failed: {e}")
                    all_text_parts.append(
                        f"--- Page {start_page}-{end_page} ---\n"
                        f"[ERROR: Failed to extract text from this section: {e}]"
                    )

        finally:
            # Clean up temp files
            for chunk_path, _, _ in chunks:
                try:
                    os.unlink(chunk_path)
                except Exception:
                    pass

        merged_text = "\n\n".join(all_text_parts)
        logger.info(
            f"Completed chunked extraction: {len(merged_text):,} total characters "
            f"from {total_pages} pages ({num_chunks} chunks)"
        )

        return merged_text

    def _pdf_to_base64(self, pdf_path: str) -> str:
        """Convert PDF file to base64 string."""
        with open(pdf_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _extract_text_from_response(self, response: dict) -> str:
        """Extract plain text from Mistral OCR response."""
        text_parts = []

        # Try to extract text from pages
        if "pages" in response:
            for page in response["pages"]:
                if "markdown" in page:
                    text_parts.append(page["markdown"])
                elif "text" in page:
                    text_parts.append(page["text"])

        # Try direct text/markdown fields
        if "markdown" in response:
            text_parts.append(response["markdown"])
        if "text" in response:
            text_parts.append(response["text"])

        if text_parts:
            return "\n\n".join(text_parts)

        # Return raw response if we can't parse it
        logger.warning("Could not parse Mistral response, returning raw JSON")
        return json.dumps(response, indent=2)


def test_connection() -> bool:
    """
    Test the Mistral OCR connection with a simple request.

    Returns True if configured (actual test requires a PDF).
    """
    ocr = MistralOCR()

    if not ocr.is_configured():
        print("Mistral OCR not configured")
        print("  Set AZURE_OPENAI_API_KEY environment variable")
        return False

    print("Mistral OCR configured")
    print(f"  Endpoint: {ocr.endpoint}")
    print(f"  Model: {ocr.model}")
    return True


if __name__ == "__main__":
    test_connection()
