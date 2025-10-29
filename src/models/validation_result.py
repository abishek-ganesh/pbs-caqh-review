"""
Validation Result Data Models

Defines the structure for validation results including field-level
and document-level validation outcomes.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..config.constants import ValidationStatus, ConfidenceLevel, RejectionReason


class FieldValidationResult(BaseModel):
    """Result of validating a single field"""

    field_name: str = Field(..., description="Name of the field")
    field_category: str = Field(..., description="Category (e.g., Personal Information)")
    extracted_value: Optional[Any] = Field(None, description="Value extracted from PDF")
    expected_value: Optional[Any] = Field(None, description="Expected value from validation rules")

    is_valid: bool = Field(..., description="Whether field passed validation")
    is_required: bool = Field(False, description="Whether field is required")

    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence (0-1)")
    confidence_level: ConfidenceLevel = Field(..., description="HIGH, MEDIUM, or LOW")

    validation_rules_applied: List[str] = Field(
        default_factory=list,
        description="List of validation rules applied"
    )

    errors: List[str] = Field(
        default_factory=list,
        description="Validation error messages"
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Validation warnings (not blocking)"
    )

    notes: Optional[str] = Field(None, description="Additional notes about validation")

    # Enhanced transparency fields
    cheat_sheet_rule: Optional[str] = Field(
        None,
        description="CAQH Cheat Sheet rule being validated"
    )

    validation_details: List[str] = Field(
        default_factory=list,
        description="Detailed breakdown of validation checks performed"
    )

    confidence_reasoning: Optional[str] = Field(
        None,
        description="Explanation of why confidence is at this level"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "field_name": "professional_license_expiration_date",
                "field_category": "Professional IDs",
                "extracted_value": "12/31/2024",
                "expected_value": None,
                "is_valid": True,
                "is_required": True,
                "confidence": 0.95,
                "confidence_level": "HIGH",
                "validation_rules_applied": ["required", "date_future"],
                "errors": [],
                "warnings": [],
                "notes": "Expiration date is valid and in the future"
            }
        }


class DocumentValidationResult(BaseModel):
    """Result of validating an entire PDF document"""

    document_id: str = Field(..., description="Unique identifier for the document")
    file_name: str = Field(..., description="Name of the PDF file")
    user_name: Optional[str] = Field(None, description="Name of the user who submitted")

    overall_status: ValidationStatus = Field(..., description="Overall validation status")

    field_results: List[FieldValidationResult] = Field(
        default_factory=list,
        description="Results for each field"
    )

    total_fields_checked: int = Field(0, description="Total number of fields checked")
    fields_passed: int = Field(0, description="Number of fields that passed")
    fields_failed: int = Field(0, description="Number of fields that failed")
    fields_warning: int = Field(0, description="Number of fields with warnings")

    required_fields_missing: List[str] = Field(
        default_factory=list,
        description="List of required fields that are missing"
    )

    low_confidence_fields: List[str] = Field(
        default_factory=list,
        description="Fields with confidence below threshold"
    )

    rejection_reasons: List[str] = Field(
        default_factory=list,
        description="Reasons for rejection (if AI Rejected)"
    )

    recommended_action: str = Field(
        ...,
        description="Recommended action (Auto-approve suggestion, Reject, or Human review)"
    )

    processing_time_seconds: float = Field(
        ...,
        description="Time taken to process the document"
    )

    processed_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of processing"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "DOC-2025-10-06-001",
                "file_name": "John_Doe_CAQH_DataSummary.pdf",
                "user_name": "John Doe",
                "overall_status": "AI Reviewed - Looks Good",
                "field_results": [],
                "total_fields_checked": 15,
                "fields_passed": 15,
                "fields_failed": 0,
                "fields_warning": 0,
                "required_fields_missing": [],
                "low_confidence_fields": [],
                "rejection_reasons": [],
                "recommended_action": "Looks good - ready for final human approval",
                "processing_time_seconds": 45.2,
                "processed_at": "2025-10-06T10:30:00",
                "metadata": {
                    "user_type": "BCBA",
                    "region": "Southern California"
                }
            }
        }


class ValidationSummary(BaseModel):
    """Summary of validation results for reporting"""

    total_documents: int = Field(0, description="Total documents processed")
    documents_approved: int = Field(0, description="Documents approved (AI suggested)")
    documents_rejected: int = Field(0, description="Documents rejected by AI")
    documents_needs_review: int = Field(0, description="Documents flagged for human review")

    avg_processing_time: float = Field(0.0, description="Average processing time (seconds)")
    avg_confidence_score: float = Field(0.0, description="Average confidence score")

    most_common_errors: List[tuple[str, int]] = Field(
        default_factory=list,
        description="Most common error types and counts"
    )

    fields_with_most_errors: List[tuple[str, int]] = Field(
        default_factory=list,
        description="Fields with most errors and counts"
    )

    generated_at: datetime = Field(
        default_factory=datetime.now,
        description="When this summary was generated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_documents": 11,
                "documents_approved": 5,
                "documents_rejected": 4,
                "documents_needs_review": 2,
                "avg_processing_time": 52.3,
                "avg_confidence_score": 0.88,
                "most_common_errors": [
                    ("Expired date", 3),
                    ("Invalid format", 2)
                ],
                "fields_with_most_errors": [
                    ("practice_location_name", 3),
                    ("tax_id", 2)
                ],
                "generated_at": "2025-10-06T15:00:00"
            }
        }
