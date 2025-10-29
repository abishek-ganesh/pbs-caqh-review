"""
PDF Text Extraction Module

Handles low-level PDF text extraction with multiple strategies:
1. Native PDF text extraction (pdfplumber - primary)
2. OCR fallback for scanned documents (pytesseract)
3. Document type validation (CAQH Data Summary detection)
4. Error handling for corrupted/invalid PDFs
"""

import re
from pathlib import Path
from typing import Optional, Tuple
import pdfplumber
import PyPDF2

# Optional: OCR dependencies (not needed for native PDFs)
try:
    from PIL import Image
    import pdf2image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    # Dummy classes to prevent NameError if OCR not available
    Image = None
    pdf2image = None
    pytesseract = None


class PDFReadError(Exception):
    """Raised when PDF cannot be read"""
    pass


class WrongDocumentTypeError(Exception):
    """Raised when document is not a CAQH Data Summary"""
    pass


def read_pdf_text(pdf_path: str) -> str:
    """
    Extract text from PDF using best available method.

    Tries pdfplumber first (best for native PDFs), falls back to PyPDF2.
    Uses OCR only if absolutely no text can be extracted.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Extracted text from all pages concatenated

    Raises:
        PDFReadError: If PDF cannot be read
        FileNotFoundError: If PDF file doesn't exist
    """
    pdf_file = Path(pdf_path)

    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if not pdf_file.is_file():
        raise PDFReadError(f"Path is not a file: {pdf_path}")

    # Strategy 1: Try pdfplumber first (best for native PDFs)
    pdfplumber_error = None
    pypdf2_error = None
    ocr_error = None
    pdfplumber_text_length = 0
    pypdf2_text_length = 0

    try:
        text = _extract_with_pdfplumber(pdf_path)
        pdfplumber_text_length = len(text) if text else 0

        # If we got ANY text, use it (even if minimal)
        if text and len(text.strip()) > 0:
            return text

    except Exception as e:
        pdfplumber_error = str(e)

    # Strategy 2: Try PyPDF2 as fallback
    try:
        text = _extract_with_pypdf2(pdf_path)
        pypdf2_text_length = len(text) if text else 0

        # If we got ANY text, use it
        if text and len(text.strip()) > 0:
            return text

    except Exception as e:
        pypdf2_error = str(e)

    # Strategy 3: Try OCR only if both native methods failed to get ANY text
    if OCR_AVAILABLE:
        try:
            text = extract_with_ocr(pdf_path)
            if text and len(text.strip()) > 0:
                return text
        except Exception as e:
            ocr_error = str(e)

    # If we get here, all methods failed - provide detailed error info
    error_details = []

    # Include extraction attempts and text lengths
    error_details.append(f"pdfplumber extracted {pdfplumber_text_length} chars")
    if pdfplumber_error:
        error_details.append(f"pdfplumber error: {pdfplumber_error}")

    error_details.append(f"PyPDF2 extracted {pypdf2_text_length} chars")
    if pypdf2_error:
        error_details.append(f"PyPDF2 error: {pypdf2_error}")

    if ocr_error:
        error_details.append(f"OCR error: {ocr_error}")

    error_msg = "Failed to extract text from PDF. " + " | ".join(error_details)

    raise PDFReadError(error_msg)


def _extract_with_pdfplumber(pdf_path: str) -> str:
    """
    Extract text using pdfplumber with coordinate-based sorting.

    This ensures text is read row-by-row (left-to-right, top-to-bottom)
    instead of column-by-column, which preserves label-value associations
    in multi-column forms.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted text from all pages with proper reading order
    """
    text_parts = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # Extract words with their coordinates
            words = page.extract_words()

            if not words:
                continue

            # Sort by Y-coordinate (top to bottom), then X-coordinate (left to right)
            # Use 5-pixel tolerance for Y to group words on same line
            Y_TOLERANCE = 5

            # Group words by row (similar Y-coordinates)
            rows = {}
            for word in words:
                # Round Y-coordinate to nearest 5 pixels to group words on same line
                row_key = round(word['top'] / Y_TOLERANCE) * Y_TOLERANCE
                if row_key not in rows:
                    rows[row_key] = []
                rows[row_key].append(word)

            # Sort rows by Y-coordinate (top to bottom)
            sorted_rows = sorted(rows.items(), key=lambda x: x[0])

            # Build text row by row
            page_lines = []
            for row_y, row_words in sorted_rows:
                # Sort words in row by X-coordinate (left to right)
                sorted_words = sorted(row_words, key=lambda w: w['x0'])

                # Reconstruct line with spacing
                line_text = ""
                prev_x1 = None

                for word in sorted_words:
                    # Add space if there's a gap between words
                    if prev_x1 is not None:
                        gap = word['x0'] - prev_x1
                        # Add space if gap is significant (more than 3 pixels)
                        if gap > 3:
                            # Add extra spaces for large gaps (approximate column separations)
                            if gap > 20:
                                line_text += "  "
                            else:
                                line_text += " "

                    line_text += word['text']
                    prev_x1 = word['x1']

                if line_text.strip():
                    page_lines.append(line_text)

            # Add page text with header
            if page_lines:
                text_parts.append(f"\n--- Page {page_num} ---\n")
                text_parts.append("\n".join(page_lines))

    return "".join(text_parts)


def _extract_with_pypdf2(pdf_path: str) -> str:
    """
    Extract text using PyPDF2 (fallback method).

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted text from all pages
    """
    text_parts = []

    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)

        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"\n--- Page {page_num} ---\n")
                text_parts.append(page_text)

    return "".join(text_parts)


def is_scanned_pdf(text: str) -> bool:
    """
    Detect if PDF is scanned (no native text, needs OCR).

    Heuristics:
    - Very little text extracted
    - Text is garbled or mostly special characters
    - No recognizable words

    Args:
        text: Extracted text from PDF

    Returns:
        True if PDF appears to be scanned, False otherwise
    """
    if not text or len(text.strip()) < 50:
        return True

    # Count alphanumeric characters
    alphanumeric = sum(1 for c in text if c.isalnum())
    total_chars = len(text)

    # If less than 30% alphanumeric, likely garbled
    if total_chars > 0 and (alphanumeric / total_chars) < 0.30:
        return True

    # Check for common English words (basic heuristic)
    common_words = ["the", "and", "or", "is", "of", "to", "in", "for", "on"]
    text_lower = text.lower()
    word_count = sum(1 for word in common_words if word in text_lower)

    # If very few common words found, likely scanned
    if word_count < 3:
        return True

    return False


def extract_with_ocr(pdf_path: str) -> str:
    """
    Extract text from PDF using OCR (for scanned documents).

    Uses Tesseract with layout analysis to preserve reading order
    in multi-column documents.

    Requires:
    - pytesseract Python package
    - tesseract-ocr system package

    Args:
        pdf_path: Path to PDF file

    Returns:
        OCR-extracted text from all pages

    Raises:
        PDFReadError: If OCR fails or tesseract not available
    """
    if not OCR_AVAILABLE:
        raise PDFReadError(
            "Tesseract OCR not available. Install pytesseract and tesseract-ocr."
        )

    try:
        # Convert PDF pages to images at higher DPI for better OCR
        images = pdf2image.convert_from_path(pdf_path, dpi=300)

        text_parts = []
        for page_num, image in enumerate(images, start=1):
            # Configure Tesseract for form documents
            # PSM 6 = Assume uniform block of text (good for forms)
            # PSM 4 = Assume single column of text (alternative)
            custom_config = r'--oem 3 --psm 6'

            # Use Tesseract with TSV output to get word coordinates
            # This allows us to sort words by position (row-by-row, not column-by-column)
            tsv_data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
                config=custom_config
            )

            # Group words by row based on their Y coordinates
            rows = {}
            Y_TOLERANCE = 8  # pixels - words within this range are on same line

            for i in range(len(tsv_data['text'])):
                word = tsv_data['text'][i].strip()
                if not word:  # Skip empty strings
                    continue

                # Get bounding box coordinates
                x = tsv_data['left'][i]
                y = tsv_data['top'][i]
                width = tsv_data['width'][i]
                height = tsv_data['height'][i]
                conf = tsv_data['conf'][i]

                # Skip low-confidence words (likely OCR errors)
                if conf < 0:  # -1 means no confidence (not a word)
                    continue

                # Group words by row (Y coordinate)
                row_key = round(y / Y_TOLERANCE) * Y_TOLERANCE
                if row_key not in rows:
                    rows[row_key] = []

                rows[row_key].append({
                    'text': word,
                    'x': x,
                    'y': y,
                    'width': width,
                    'height': height,
                    'conf': conf
                })

            # Build text row by row
            page_lines = []
            for row_y in sorted(rows.keys()):
                # Sort words in row by X coordinate (left to right)
                row_words = sorted(rows[row_y], key=lambda w: w['x'])

                # Reconstruct line with proper spacing
                line_text = ""
                prev_x_end = None

                for word_data in row_words:
                    word = word_data['text']
                    x = word_data['x']

                    # Add space between words based on gap
                    if prev_x_end is not None:
                        gap = x - prev_x_end
                        # Lower threshold - add space for smaller gaps
                        if gap > 3:  # Significant gap (reduced from 10)
                            if gap > 40:  # Large gap - likely column separator
                                line_text += "  "
                            else:
                                line_text += " "

                    # Post-process word to fix common OCR issues
                    # Add space before capital letters in camelCase (e.g., "SocialSecurity" -> "Social Security")
                    processed_word = ""
                    for j, char in enumerate(word):
                        # Add space before capital letter if:
                        # 1. Not first character
                        # 2. Previous character is lowercase
                        # 3. Current character is uppercase
                        if j > 0 and word[j-1].islower() and char.isupper():
                            processed_word += " " + char
                        else:
                            processed_word += char

                    line_text += processed_word
                    prev_x_end = x + word_data['width']

                if line_text.strip():
                    page_lines.append(line_text)

            # Add page text with header
            if page_lines:
                text_parts.append(f"\n--- Page {page_num} (OCR) ---\n")
                text_parts.append("\n".join(page_lines))

        return "".join(text_parts)

    except Exception as e:
        raise PDFReadError(f"OCR extraction failed: {e}")


def is_caqh_document(text: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that PDF is a CAQH Data Summary document.

    Checks for CAQH-specific indicators:
    - "CAQH" in document
    - "Data Summary" or "Provider Data" in title area
    - Expected field labels (SSN, NPI, etc.)

    Args:
        text: Extracted PDF text

    Returns:
        Tuple of (is_caqh: bool, error_message: Optional[str])
    """
    if not text or len(text.strip()) < 100:
        return False, "Document text is too short or empty"

    text_lower = text.lower()

    # Check for CAQH indicators
    has_caqh = "caqh" in text_lower
    has_data_summary = "data summary" in text_lower or "provider data" in text_lower

    # Check for expected field labels (at least 3 of these should be present)
    expected_labels = [
        "social security",
        "npi",
        "medicaid",
        "license",
        "practice location"
    ]
    label_count = sum(1 for label in expected_labels if label in text_lower)

    # Document is likely CAQH if it has CAQH branding OR data summary + field labels
    if has_caqh or (has_data_summary and label_count >= 3):
        return True, None

    # Not a CAQH document
    if label_count < 2:
        error = "Document does not appear to be a CAQH Data Summary (missing expected field labels)"
    else:
        error = "Document may not be a CAQH Data Summary (no CAQH branding found)"

    return False, error


def get_pdf_metadata(pdf_path: str) -> dict:
    """
    Extract PDF metadata (title, author, creation date, etc.).

    Useful for logging and validation.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Dictionary of metadata fields
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            metadata = pdf.metadata or {}

            return {
                "title": metadata.get("Title", ""),
                "author": metadata.get("Author", ""),
                "subject": metadata.get("Subject", ""),
                "creator": metadata.get("Creator", ""),
                "producer": metadata.get("Producer", ""),
                "creation_date": metadata.get("CreationDate", ""),
                "page_count": len(pdf.pages),
                "file_size_bytes": Path(pdf_path).stat().st_size
            }
    except Exception as e:
        return {
            "error": f"Failed to extract metadata: {e}",
            "page_count": 0,
            "file_size_bytes": 0
        }


def validate_pdf_file(pdf_path: str) -> Tuple[bool, Optional[str]]:
    """
    Comprehensive PDF file validation.

    Checks:
    1. File exists and is readable
    2. File is valid PDF format
    3. File is CAQH Data Summary document
    4. File is not corrupted

    Args:
        pdf_path: Path to PDF file

    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])
    """
    # Check file exists
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        return False, f"File not found: {pdf_path}"

    if not pdf_file.is_file():
        return False, f"Path is not a file: {pdf_path}"

    # Check file size (too small = likely corrupted)
    file_size = pdf_file.stat().st_size
    if file_size < 1000:  # Less than 1KB
        return False, "PDF file is too small (likely corrupted or empty)"

    # Try to read PDF
    try:
        text = read_pdf_text(pdf_path)
    except PDFReadError as e:
        return False, f"Failed to read PDF: {e}"
    except Exception as e:
        return False, f"Unexpected error reading PDF: {e}"

    # Check if CAQH document
    is_caqh, error = is_caqh_document(text)
    if not is_caqh:
        return False, error

    return True, None
