"""
Extraction Result Data Models

Pydantic models for PDF field extraction results with confidence scoring.
Mirrors the validation_result.py structure for seamless integration.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class FieldExtractionResult(BaseModel):
    """
    Result of extracting a single field from a PDF.

    Includes the extracted value, confidence score, extraction method,
    and contextual information for debugging and validation.
    """

    field_name: str = Field(..., description="Name of the field extracted")

    extracted_value: Optional[str] = Field(
        default=None,
        description="The value extracted from the PDF (None if not found)"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for extraction (0.0-1.0)"
    )

    extraction_method: str = Field(
        ...,
        description="Method used for extraction (native_pdf, ocr, pattern_match, ai_assisted)"
    )

    raw_text_context: Optional[str] = Field(
        default=None,
        description="Surrounding text context where value was found (for debugging)"
    )

    position: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Position in PDF (page number, coordinates, etc.)"
    )

    errors: List[str] = Field(
        default_factory=list,
        description="Errors encountered during extraction"
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about extraction quality or ambiguity"
    )

    notes: Optional[str] = Field(
        default=None,
        description="Additional notes about extraction process"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "field_name": "medicaid_id",
                "extracted_value": "12345678",
                "confidence": 0.95,
                "extraction_method": "native_pdf",
                "raw_text_context": "Medicaid ID: 12345678",
                "position": {"page": 1, "x": 100, "y": 200},
                "errors": [],
                "warnings": [],
                "notes": "Found using label-proximity extraction"
            }
        }


class DocumentExtractionResult(BaseModel):
    """
    Complete extraction result for an entire PDF document.

    Contains results for all fields attempted, summary statistics,
    and overall extraction quality metrics.
    """

    pdf_path: str = Field(..., description="Path to the PDF file processed")

    pdf_filename: str = Field(..., description="Filename of the PDF")

    total_fields_attempted: int = Field(
        ...,
        description="Total number of fields extraction was attempted for"
    )

    fields_extracted: int = Field(
        ...,
        description="Number of fields successfully extracted (with value)"
    )

    field_results: List[FieldExtractionResult] = Field(
        default_factory=list,
        description="Individual extraction results for each field"
    )

    extraction_time: float = Field(
        ...,
        description="Total time taken for extraction (seconds)"
    )

    extraction_method: str = Field(
        ...,
        description="Primary extraction method used (native_pdf, ocr, hybrid)"
    )

    is_caqh_document: bool = Field(
        default=True,
        description="Whether document was detected as valid CAQH Data Summary"
    )

    errors: List[str] = Field(
        default_factory=list,
        description="Document-level errors (corrupted PDF, wrong format, etc.)"
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Document-level warnings"
    )

    extracted_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when extraction was performed"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "pdf_path": "/path/to/document.pdf",
                "pdf_filename": "document.pdf",
                "total_fields_attempted": 5,
                "fields_extracted": 5,
                "field_results": [],
                "extraction_time": 2.5,
                "extraction_method": "native_pdf",
                "is_caqh_document": True,
                "errors": [],
                "warnings": [],
                "extracted_at": "2025-10-08T10:30:00"
            }
        }


class ExtractionSummary(BaseModel):
    """
    Summary statistics for extraction results.

    Provides high-level metrics about extraction quality,
    useful for reporting and confidence assessment.
    """

    total_fields: int
    fields_extracted: int
    fields_not_found: int
    extraction_rate: float  # Percentage of fields successfully extracted
    avg_confidence: float  # Average confidence across all extracted fields
    high_confidence_fields: int  # Fields with confidence >= 0.90
    medium_confidence_fields: int  # Fields with 0.70 <= confidence < 0.90
    low_confidence_fields: int  # Fields with confidence < 0.70
    total_errors: int
    total_warnings: int
    extraction_method: str

    class Config:
        json_schema_extra = {
            "example": {
                "total_fields": 5,
                "fields_extracted": 5,
                "fields_not_found": 0,
                "extraction_rate": 100.0,
                "avg_confidence": 0.92,
                "high_confidence_fields": 4,
                "medium_confidence_fields": 1,
                "low_confidence_fields": 0,
                "total_errors": 0,
                "total_warnings": 1,
                "extraction_method": "native_pdf"
            }
        }


def get_extraction_summary(result: DocumentExtractionResult) -> ExtractionSummary:
    """
    Generate summary statistics from document extraction result.

    Args:
        result: Document extraction result to summarize

    Returns:
        ExtractionSummary with calculated metrics
    """
    total_fields = result.total_fields_attempted
    fields_extracted = result.fields_extracted
    fields_not_found = total_fields - fields_extracted

    extraction_rate = (fields_extracted / total_fields * 100) if total_fields > 0 else 0.0

    # Calculate confidence statistics
    extracted_results = [r for r in result.field_results if r.extracted_value is not None]

    if extracted_results:
        avg_confidence = sum(r.confidence for r in extracted_results) / len(extracted_results)
        high_confidence = sum(1 for r in extracted_results if r.confidence >= 0.90)
        medium_confidence = sum(1 for r in extracted_results if 0.70 <= r.confidence < 0.90)
        low_confidence = sum(1 for r in extracted_results if r.confidence < 0.70)
    else:
        avg_confidence = 0.0
        high_confidence = 0
        medium_confidence = 0
        low_confidence = 0

    # Count errors and warnings
    total_errors = len(result.errors) + sum(len(r.errors) for r in result.field_results)
    total_warnings = len(result.warnings) + sum(len(r.warnings) for r in result.field_results)

    return ExtractionSummary(
        total_fields=total_fields,
        fields_extracted=fields_extracted,
        fields_not_found=fields_not_found,
        extraction_rate=round(extraction_rate, 1),
        avg_confidence=round(avg_confidence, 2),
        high_confidence_fields=high_confidence,
        medium_confidence_fields=medium_confidence,
        low_confidence_fields=low_confidence,
        total_errors=total_errors,
        total_warnings=total_warnings,
        extraction_method=result.extraction_method
    )
