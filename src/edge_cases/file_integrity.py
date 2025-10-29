"""
File Integrity Checker Module

Detects corrupted or unreadable PDF files.
Validates file integrity before processing.

Business Rules:
- Detect PDF corruption (malformed headers, truncated files)
- Detect unreadable PDFs (password-protected, encrypted without proper decryption)
- Detect extraction failures (OCR fails, no text extractable)
- Route corrupted files to "Needs Human Review" with error details

Corruption Types:
- Malformed PDF structure
- Truncated files (incomplete downloads)
- Password-protected/encrypted PDFs
- OCR failures on scanned documents
- Empty or zero-byte files
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError


class FileIntegrityResult(BaseModel):
    """Result of file integrity check"""
    is_valid: bool
    corruption_type: Optional[str] = None  # "corrupted_pdf", "encrypted", "empty_file", "extraction_failed", etc.
    errors: List[str] = []
    warnings: List[str] = []
    message: str
    recommendation: str  # "process_normally", "needs_review", "reject_corrupted"
    file_size_bytes: int = 0
    page_count: Optional[int] = None
    is_encrypted: bool = False


class FileIntegrityChecker:
    """
    Checks PDF file integrity and readability.

    Performs multiple checks:
    1. File existence and size
    2. PDF structure validation
    3. Encryption detection
    4. Text extraction validation
    5. Page count verification
    """

    MIN_FILE_SIZE = 1000  # bytes - minimum viable PDF size
    MIN_EXTRACTABLE_TEXT = 100  # characters - minimum text that should be extractable

    def __init__(self):
        """Initialize file integrity checker"""
        pass

    def check_file_exists(self, file_path: str) -> Optional[FileIntegrityResult]:
        """
        Check if file exists and has non-zero size.

        Args:
            file_path: Path to the file

        Returns:
            FileIntegrityResult if file doesn't exist or is empty, None otherwise
        """
        path = Path(file_path)

        if not path.exists():
            return FileIntegrityResult(
                is_valid=False,
                corruption_type="file_not_found",
                errors=[f"File not found: {file_path}"],
                message=f"File does not exist: {file_path}",
                recommendation="reject_corrupted",
                file_size_bytes=0
            )

        file_size = path.stat().st_size

        if file_size == 0:
            return FileIntegrityResult(
                is_valid=False,
                corruption_type="empty_file",
                errors=["File is empty (0 bytes)"],
                message="File is empty. This may indicate a failed upload or corrupted file.",
                recommendation="reject_corrupted",
                file_size_bytes=0
            )

        if file_size < self.MIN_FILE_SIZE:
            return FileIntegrityResult(
                is_valid=False,
                corruption_type="file_too_small",
                errors=[f"File is suspiciously small ({file_size} bytes)"],
                message=(
                    f"File is only {file_size} bytes, which is too small for a valid PDF. "
                    f"This may indicate a corrupted or truncated file."
                ),
                recommendation="reject_corrupted",
                file_size_bytes=file_size
            )

        return None  # File exists and has reasonable size

    def check_pdf_structure(self, file_path: str) -> Optional[FileIntegrityResult]:
        """
        Check PDF structure using PyPDF2.

        Args:
            file_path: Path to the PDF file

        Returns:
            FileIntegrityResult if PDF is corrupted, None if valid
        """
        try:
            file_size = os.path.getsize(file_path)

            with open(file_path, 'rb') as f:
                reader = PdfReader(f)

                # Check if PDF is encrypted
                is_encrypted = reader.is_encrypted

                # Try to get page count
                page_count = len(reader.pages)

                if page_count == 0:
                    return FileIntegrityResult(
                        is_valid=False,
                        corruption_type="no_pages",
                        errors=["PDF has no pages"],
                        message="PDF file contains no pages. This indicates a corrupted or invalid PDF.",
                        recommendation="reject_corrupted",
                        file_size_bytes=file_size,
                        page_count=0,
                        is_encrypted=is_encrypted
                    )

                if is_encrypted:
                    # Try to decrypt if encrypted (in case it's unprotected encryption)
                    try:
                        reader.decrypt('')
                    except:
                        return FileIntegrityResult(
                            is_valid=False,
                            corruption_type="encrypted",
                            errors=["PDF is encrypted and cannot be decrypted"],
                            message=(
                                "PDF is password-protected or encrypted. "
                                "Please remove encryption and resubmit."
                            ),
                            recommendation="reject_corrupted",
                            file_size_bytes=file_size,
                            page_count=page_count,
                            is_encrypted=True
                        )

        except PdfReadError as e:
            return FileIntegrityResult(
                is_valid=False,
                corruption_type="corrupted_pdf",
                errors=[f"PDF read error: {str(e)}"],
                message=(
                    f"PDF structure is corrupted or malformed: {str(e)}. "
                    f"This file cannot be processed."
                ),
                recommendation="reject_corrupted",
                file_size_bytes=os.path.getsize(file_path) if os.path.exists(file_path) else 0
            )

        except Exception as e:
            return FileIntegrityResult(
                is_valid=False,
                corruption_type="unknown_error",
                errors=[f"Unexpected error reading PDF: {str(e)}"],
                message=f"Error reading PDF file: {str(e)}",
                recommendation="needs_review",
                file_size_bytes=os.path.getsize(file_path) if os.path.exists(file_path) else 0
            )

        return None  # PDF structure is valid

    def check_text_extraction(
        self,
        file_path: str,
        extracted_text: Optional[str] = None
    ) -> Optional[FileIntegrityResult]:
        """
        Check if text can be extracted from PDF.

        Args:
            file_path: Path to the PDF file
            extracted_text: Pre-extracted text (if already extracted)

        Returns:
            FileIntegrityResult if extraction failed, None if successful
        """
        # If text not provided, try to extract it
        if extracted_text is None:
            try:
                from src.extraction.pdf_reader import read_pdf_text
                extracted_text = read_pdf_text(file_path)
            except Exception as e:
                return FileIntegrityResult(
                    is_valid=False,
                    corruption_type="extraction_failed",
                    errors=[f"Text extraction failed: {str(e)}"],
                    message=(
                        f"Failed to extract text from PDF: {str(e)}. "
                        f"This may indicate a corrupted file or unsupported PDF format."
                    ),
                    recommendation="needs_review",
                    file_size_bytes=os.path.getsize(file_path) if os.path.exists(file_path) else 0
                )

        # Check if extracted text is sufficient
        if not extracted_text or len(extracted_text.strip()) < self.MIN_EXTRACTABLE_TEXT:
            return FileIntegrityResult(
                is_valid=False,
                corruption_type="insufficient_text",
                errors=[f"Extracted text too short ({len(extracted_text) if extracted_text else 0} characters)"],
                warnings=["PDF may be scanned images without OCR, or text extraction failed"],
                message=(
                    f"Extracted only {len(extracted_text) if extracted_text else 0} characters from PDF. "
                    f"This may be a scanned document without text, or extraction failed. "
                    f"Manual review recommended."
                ),
                recommendation="needs_review",
                file_size_bytes=os.path.getsize(file_path) if os.path.exists(file_path) else 0
            )

        return None  # Text extraction successful

    def validate_file(
        self,
        file_path: str,
        extracted_text: Optional[str] = None
    ) -> FileIntegrityResult:
        """
        Comprehensive file integrity validation.

        Performs all checks in sequence:
        1. File existence and size check
        2. PDF structure validation
        3. Text extraction validation

        Args:
            file_path: Path to the PDF file
            extracted_text: Pre-extracted text (optional)

        Returns:
            FileIntegrityResult with validation results
        """
        # 1. Check file exists and has valid size
        file_check = self.check_file_exists(file_path)
        if file_check:
            return file_check

        # 2. Check PDF structure
        structure_check = self.check_pdf_structure(file_path)
        if structure_check:
            return structure_check

        # 3. Check text extraction
        extraction_check = self.check_text_extraction(file_path, extracted_text)
        if extraction_check:
            return extraction_check

        # All checks passed
        try:
            file_size = os.path.getsize(file_path)
            with open(file_path, 'rb') as f:
                reader = PdfReader(f)
                page_count = len(reader.pages)
                is_encrypted = reader.is_encrypted
        except:
            file_size = 0
            page_count = None
            is_encrypted = False

        return FileIntegrityResult(
            is_valid=True,
            message=(
                f"File integrity validated successfully "
                f"({file_size} bytes, {page_count} pages, "
                f"{len(extracted_text) if extracted_text else '?'} characters extracted)"
            ),
            recommendation="process_normally",
            file_size_bytes=file_size,
            page_count=page_count,
            is_encrypted=is_encrypted
        )

    def quick_check(self, file_path: str, extracted_text: Optional[str] = None) -> bool:
        """
        Quick boolean check if file is valid.

        Args:
            file_path: Path to the PDF file
            extracted_text: Pre-extracted text (optional)

        Returns:
            True if file is valid, False otherwise
        """
        result = self.validate_file(file_path, extracted_text)
        return result.is_valid


# Singleton instance
_checker_instance: Optional[FileIntegrityChecker] = None


def get_file_integrity_checker() -> FileIntegrityChecker:
    """
    Get singleton instance of FileIntegrityChecker.

    Returns:
        FileIntegrityChecker instance
    """
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = FileIntegrityChecker()
    return _checker_instance
