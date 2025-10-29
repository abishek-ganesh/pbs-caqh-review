"""
OCR Cache Manager for Test PDFs

This module provides caching functionality for OCR/text extraction results
to speed up testing iterations. For testing purposes only, not for production.
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime

from src.extraction.pdf_reader import read_pdf_text

logger = logging.getLogger(__name__)


class OCRCacheManager:
    """Manages cached OCR/text extraction results for test PDFs."""

    def __init__(self, cache_dir: str = "data/ocr_cache"):
        """
        Initialize the OCR cache manager.

        Args:
            cache_dir: Directory to store cached OCR results
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> Dict[str, Any]:
        """Load cache metadata from disk."""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_metadata(self):
        """Save cache metadata to disk."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2, default=str)

    def _get_pdf_hash(self, pdf_path: str) -> str:
        """
        Generate a hash for a PDF file to detect changes.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            MD5 hash of the PDF file
        """
        with open(pdf_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def _get_cache_filename(self, pdf_path: str) -> str:
        """
        Generate a cache filename for a PDF.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Cache filename based on PDF filename
        """
        pdf_name = Path(pdf_path).stem
        # Replace spaces and special chars with underscores
        safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in pdf_name)
        return f"{safe_name}.txt"

    def is_cached(self, pdf_path: str) -> bool:
        """
        Check if a PDF's text extraction is cached and valid.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            True if valid cache exists, False otherwise
        """
        cache_file = self.cache_dir / self._get_cache_filename(pdf_path)
        if not cache_file.exists():
            return False

        # Check if PDF has changed since cache was created
        pdf_path_str = str(Path(pdf_path).resolve())
        if pdf_path_str in self.metadata:
            cached_hash = self.metadata[pdf_path_str].get('pdf_hash')
            current_hash = self._get_pdf_hash(pdf_path)
            return cached_hash == current_hash

        return False

    def get_cached_text(self, pdf_path: str) -> Optional[str]:
        """
        Retrieve cached text for a PDF.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Cached text if available, None otherwise
        """
        if not self.is_cached(pdf_path):
            return None

        cache_file = self.cache_dir / self._get_cache_filename(pdf_path)
        with open(cache_file, 'r', encoding='utf-8') as f:
            return f.read()

    def cache_text(self, pdf_path: str, text: str, extraction_method: str = "pdfplumber"):
        """
        Cache extracted text for a PDF.

        Args:
            pdf_path: Path to the PDF file
            text: Extracted text to cache
            extraction_method: Method used for extraction (pdfplumber, ocr, etc.)
        """
        cache_file = self.cache_dir / self._get_cache_filename(pdf_path)

        # Save text to cache file
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(text)

        # Update metadata
        pdf_path_str = str(Path(pdf_path).resolve())
        self.metadata[pdf_path_str] = {
            'cache_file': cache_file.name,
            'pdf_hash': self._get_pdf_hash(pdf_path),
            'extraction_method': extraction_method,
            'cached_at': datetime.now().isoformat(),
            'text_length': len(text)
        }
        self._save_metadata()

        logger.info(f"Cached text for {Path(pdf_path).name} ({len(text)} chars)")

    def extract_and_cache(self, pdf_path: str, force: bool = False) -> str:
        """
        Extract text from PDF and cache it, or return cached version.

        Args:
            pdf_path: Path to the PDF file
            force: Force re-extraction even if cache exists

        Returns:
            Extracted text
        """
        # Check cache first (unless forced)
        if not force:
            cached_text = self.get_cached_text(pdf_path)
            if cached_text is not None:
                logger.info(f"Using cached text for {Path(pdf_path).name}")
                return cached_text

        # Extract text
        logger.info(f"Extracting text from {Path(pdf_path).name}")
        text = read_pdf_text(pdf_path)

        # Cache the result
        self.cache_text(pdf_path, text)

        return text

    def clear_cache(self):
        """Clear all cached OCR results."""
        for cache_file in self.cache_dir.glob("*.txt"):
            cache_file.unlink()
        self.metadata = {}
        self._save_metadata()
        logger.info("Cleared OCR cache")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache.

        Returns:
            Dictionary with cache statistics
        """
        total_files = len(self.metadata)
        total_size = sum(
            (self.cache_dir / meta['cache_file']).stat().st_size
            for meta in self.metadata.values()
            if (self.cache_dir / meta['cache_file']).exists()
        )

        return {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'cache_dir': str(self.cache_dir)
        }


# Singleton instance for easy access
_cache_manager = None

def get_cache_manager() -> OCRCacheManager:
    """Get the singleton cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = OCRCacheManager()
    return _cache_manager