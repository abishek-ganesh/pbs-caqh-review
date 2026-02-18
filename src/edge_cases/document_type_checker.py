"""
Document Type Checker Module

Detects wrong document types (Word docs, non-CAQH PDFs, etc.).
Validates that the submitted document is a legitimate CAQH Data Summary PDF.

Business Rules:
- Detect Word documents (.docx, .doc)
- Detect non-CAQH PDFs (missing required sections/headers)
- Check for minimum document structure (not just a screenshot or letter)
- Return helpful error message with SharePoint link

Wrong Document Examples (from testing):
- Liability coverage letters
- Resume PDFs
- Screenshots
- Incomplete/truncated CAQH exports
"""

import os
import re
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel


class DocumentTypeResult(BaseModel):
    """Result of document type check"""
    is_valid_caqh: bool
    document_type: str  # "valid_caqh", "wrong_document", "word_document", "unknown"
    missing_markers: List[str] = []
    message: str
    recommendation: str  # "process_normally", "reject_wrong_document", "needs_review"
    help_url: Optional[str] = None


class DocumentTypeChecker:
    """
    Checks if a document is a valid CAQH Data Summary PDF.

    Uses multiple heuristics:
    1. File extension check (.pdf vs .doc/.docx)
    2. Required CAQH markers presence (headers, sections)
    3. Document structure validation (minimum length, sections)
    4. Common wrong document patterns
    """

    # Required markers that should appear in a valid CAQH Data Summary
    # Note: "Data Summary" may not appear in browser-printed exports, so we have alternatives
    REQUIRED_MARKERS = [
        ("CAQH", "CAQH reference or branding"),
        ("Provider", "Provider information section"),
    ]

    # Alternative markers for "Data Summary" - if ANY of these are present, document is valid
    # This handles browser-printed CAQH exports that don't have "Data Summary" title
    ALTERNATIVE_DATA_SUMMARY_MARKERS = [
        "Data Summary",           # Standard CAQH export
        "CAQH Provider ID",       # Browser-printed format (e.g., "Provider CAQH ID 16624351")
        "Provider CAQH",          # OCR variation - reversed order (e.g., "Provider CAQH  16644960")
        "Attestation Date",       # Browser-printed format header
        "Attestation",            # OCR variation - "Attestation" without "Date" suffix
        "CAQH Data Summary Date", # Some exports have this variant
    ]

    # At least 2 of these sections should be present
    EXPECTED_SECTIONS = [
        ("Individual NPI", "Individual NPI field"),
        ("Practice Location", "Practice Location section"),
        ("Professional License", "Professional License section"),
        ("Education", "Education section"),
        ("Social Security", "Social Security Number field"),
    ]

    # Known wrong document patterns (case-insensitive)
    # These are checked when CAQH markers are missing
    WRONG_DOCUMENT_PATTERNS = [
        "liability coverage",
        "insurance certificate",
        "resume",
        "curriculum vitae",
        "attestation letter",
        "reference letter",
    ]

    # CAQH-related documents that are NOT Data Summaries (checked even with CAQH markers)
    # These are often confused with Data Summaries but are the wrong document type
    CAQH_WRONG_FORMAT_PATTERNS = [
        "provider application",    # CAQH Provider Application form (fillable form, not summary)
        "std. app.",               # Standard Application form marker
        "complete only this application",  # Application form instructions
    ]

    def __init__(self, sharepoint_help_url: Optional[str] = None):
        """
        Initialize document type checker.

        Args:
            sharepoint_help_url: URL to SharePoint help page for instructions
        """
        self.sharepoint_help_url = sharepoint_help_url or \
            "https://sharepoint.teampbs.com/Pages/CAQHCheatSheet.aspx"

    def check_file_extension(self, file_path: str) -> DocumentTypeResult:
        """
        Check file extension to detect Word documents.

        Args:
            file_path: Path to the file

        Returns:
            DocumentTypeResult if wrong type detected, None if PDF
        """
        path = Path(file_path)
        extension = path.suffix.lower()

        if extension in ['.doc', '.docx']:
            return DocumentTypeResult(
                is_valid_caqh=False,
                document_type="word_document",
                message=(
                    f"Word document detected ({extension}). "
                    f"Please export CAQH Data Summary as PDF from CAQH ProView."
                ),
                recommendation="reject_wrong_document",
                help_url=self.sharepoint_help_url
            )

        elif extension not in ['.pdf']:
            return DocumentTypeResult(
                is_valid_caqh=False,
                document_type="unknown",
                message=(
                    f"Unsupported file type ({extension}). "
                    f"Only PDF documents are accepted."
                ),
                recommendation="reject_wrong_document",
                help_url=self.sharepoint_help_url
            )

        return None  # PDF extension is valid

    def check_required_markers(self, text: str) -> DocumentTypeResult:
        """
        Check for required CAQH markers in document text.

        Args:
            text: Extracted text from PDF

        Returns:
            DocumentTypeResult if markers missing, None if all present
        """
        text_lower = text.lower()
        missing_markers = []

        # Check required markers (CAQH, Provider)
        for marker, description in self.REQUIRED_MARKERS:
            if marker.lower() not in text_lower:
                missing_markers.append(description)

        # Check for Data Summary OR alternative markers
        # Browser-printed CAQH exports may not have "Data Summary" but will have
        # "CAQH Provider ID" or "Attestation Date" in the header
        has_data_summary_marker = False
        for alt_marker in self.ALTERNATIVE_DATA_SUMMARY_MARKERS:
            if alt_marker.lower() in text_lower:
                has_data_summary_marker = True
                break

        if not has_data_summary_marker:
            missing_markers.append("Data Summary title (or CAQH Provider ID/Attestation Date)")

        if missing_markers:
            return DocumentTypeResult(
                is_valid_caqh=False,
                document_type="wrong_document",
                missing_markers=missing_markers,
                message=(
                    f"Document is missing required CAQH markers: {', '.join(missing_markers)}. "
                    f"This does not appear to be a CAQH Data Summary PDF."
                ),
                recommendation="reject_wrong_document",
                help_url=self.sharepoint_help_url
            )

        return None  # All required markers present

    def check_expected_sections(self, text: str) -> int:
        """
        Count how many expected sections are present.

        Handles both normal text ("Individual NPI") and concatenated text
        from PDF extraction ("individualnpi") where spaces are stripped.

        Args:
            text: Extracted text from PDF

        Returns:
            Number of expected sections found
        """
        text_lower = text.lower()
        sections_found = 0

        for section, description in self.EXPECTED_SECTIONS:
            section_lower = section.lower()
            # Check with spaces (normal text) OR without spaces (concatenated PDF text)
            if section_lower in text_lower or section_lower.replace(" ", "") in text_lower:
                sections_found += 1

        return sections_found

    def check_wrong_document_patterns(self, text: str) -> Optional[str]:
        """
        Check for patterns indicating a wrong document type.

        Args:
            text: Extracted text from PDF

        Returns:
            Pattern matched if wrong document detected, None otherwise
        """
        text_lower = text.lower()

        for pattern in self.WRONG_DOCUMENT_PATTERNS:
            if pattern in text_lower:
                return pattern

        return None

    def check_caqh_wrong_format(self, text: str) -> Optional[str]:
        """
        Check for CAQH-related documents that are NOT Data Summaries.

        These documents have CAQH markers but are the wrong format
        (e.g., Provider Application forms instead of Data Summary exports).

        Args:
            text: Extracted text from PDF

        Returns:
            Pattern matched if wrong format detected, None otherwise
        """
        text_lower = text.lower()

        for pattern in self.CAQH_WRONG_FORMAT_PATTERNS:
            if pattern in text_lower:
                return pattern

        return None

    def check_document_structure(self, text: str, has_caqh_markers: bool = False) -> DocumentTypeResult:
        """
        Check document structure (length, sections, etc.).

        Args:
            text: Extracted text from PDF
            has_caqh_markers: Whether the document has all required CAQH markers

        Returns:
            DocumentTypeResult if structure invalid, None if valid
        """
        # Minimum length check (CAQH documents should be substantial)
        MIN_LENGTH = 2000  # characters
        if len(text) < MIN_LENGTH:
            return DocumentTypeResult(
                is_valid_caqh=False,
                document_type="wrong_document",
                message=(
                    f"Document is too short ({len(text)} characters). "
                    f"CAQH Data Summary PDFs are typically much longer. "
                    f"This may be a screenshot, partial export, or wrong document."
                ),
                recommendation="reject_wrong_document",
                help_url=self.sharepoint_help_url
            )

        # Check for expected sections
        sections_found = self.check_expected_sections(text)
        if sections_found < 2:  # At least 2 sections required
            return DocumentTypeResult(
                is_valid_caqh=False,
                document_type="wrong_document",
                message=(
                    f"Document contains only {sections_found} expected CAQH sections. "
                    f"Valid CAQH Data Summaries should contain multiple sections "
                    f"(Practice Location, Professional License, Education, etc.)"
                ),
                recommendation="reject_wrong_document",
                help_url=self.sharepoint_help_url
            )

        # Check for wrong document patterns ONLY if CAQH markers are missing
        # If document has CAQH markers, don't reject based on patterns
        # (e.g., "liability coverage" legitimately appears in the Professional Liability section)
        if not has_caqh_markers:
            wrong_pattern = self.check_wrong_document_patterns(text)
            if wrong_pattern:
                return DocumentTypeResult(
                    is_valid_caqh=False,
                    document_type="wrong_document",
                    message=(
                        f"Document appears to be '{wrong_pattern}', not a CAQH Data Summary. "
                        f"Please submit the complete CAQH Data Summary PDF from CAQH ProView."
                    ),
                    recommendation="reject_wrong_document",
                    help_url=self.sharepoint_help_url
                )

        return None  # Structure looks valid

    def validate_document(
        self,
        file_path: str,
        extracted_text: str
    ) -> DocumentTypeResult:
        """
        Comprehensive document type validation.

        Performs all checks in sequence:
        1. File extension check
        2. Required markers check
        3. Document structure check

        Args:
            file_path: Path to the PDF file
            extracted_text: Extracted text from the PDF

        Returns:
            DocumentTypeResult with validation results
        """
        # 1. Check file extension
        extension_result = self.check_file_extension(file_path)
        if extension_result:
            return extension_result

        # 2. Check required markers
        markers_result = self.check_required_markers(extracted_text)
        has_caqh_markers = (markers_result is None)  # None means all markers present

        if markers_result:
            return markers_result

        # 3. Check document structure (pass whether CAQH markers are present)
        structure_result = self.check_document_structure(extracted_text, has_caqh_markers=has_caqh_markers)
        if structure_result:
            return structure_result

        # 4. Check for CAQH-related documents that are NOT Data Summaries
        # (e.g., Provider Application forms have CAQH markers but are wrong format)
        wrong_format = self.check_caqh_wrong_format(extracted_text)
        if wrong_format:
            return DocumentTypeResult(
                is_valid_caqh=False,
                document_type="wrong_document",
                message=(
                    f"Document appears to be a CAQH '{wrong_format}', not a CAQH Data Summary. "
                    f"Please submit the CAQH Data Summary PDF export from CAQH ProView, "
                    f"not the Provider Application form."
                ),
                recommendation="reject_wrong_document",
                help_url=self.sharepoint_help_url
            )

        # All checks passed - valid CAQH document
        sections_found = self.check_expected_sections(extracted_text)
        return DocumentTypeResult(
            is_valid_caqh=True,
            document_type="valid_caqh",
            message=(
                f"Document appears to be a valid CAQH Data Summary "
                f"({sections_found} expected sections found, {len(extracted_text)} characters)"
            ),
            recommendation="process_normally"
        )

    def quick_check(self, file_path: str, extracted_text: str) -> bool:
        """
        Quick boolean check if document is valid CAQH.

        Args:
            file_path: Path to the PDF file
            extracted_text: Extracted text from the PDF

        Returns:
            True if valid CAQH document, False otherwise
        """
        result = self.validate_document(file_path, extracted_text)
        return result.is_valid_caqh


# Singleton instance
_checker_instance: Optional[DocumentTypeChecker] = None


def get_document_type_checker(sharepoint_help_url: Optional[str] = None) -> DocumentTypeChecker:
    """
    Get singleton instance of DocumentTypeChecker.

    Args:
        sharepoint_help_url: URL to SharePoint help page

    Returns:
        DocumentTypeChecker instance
    """
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = DocumentTypeChecker(sharepoint_help_url=sharepoint_help_url)
    return _checker_instance
