"""
PDF Extraction Module

Extracts fields from CAQH Data Summary PDFs using multiple strategies:
- Native PDF text extraction (pdfplumber, PyPDF2)
- OCR for scanned documents (pytesseract)
- AI-assisted field mapping (OpenAI/Claude)

Components:
- pdf_reader.py: Low-level PDF text extraction
- field_extractor.py: High-level field extraction with confidence scoring (to be implemented)
- ocr_handler.py: OCR processing for scanned documents (future)
"""

from .pdf_reader import (
    read_pdf_text,
    is_scanned_pdf,
    extract_with_ocr,
    is_caqh_document,
    get_pdf_metadata,
    validate_pdf_file,
    PDFReadError,
    WrongDocumentTypeError
)

from .field_extractor import (
    extract_field,
    extract_all_fields,
    extract_poc_fields,
    load_extraction_config
)

__all__ = [
    "read_pdf_text",
    "is_scanned_pdf",
    "extract_with_ocr",
    "is_caqh_document",
    "get_pdf_metadata",
    "validate_pdf_file",
    "PDFReadError",
    "WrongDocumentTypeError",
    "extract_field",
    "extract_all_fields",
    "extract_poc_fields",
    "load_extraction_config",
]
