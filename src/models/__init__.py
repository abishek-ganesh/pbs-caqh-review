"""
Data Models Module

Pydantic models for type safety and validation.

Components:
- pdf_submission.py: PDF submission data model
- extracted_fields.py: Extracted field data models
- validation_result.py: Validation result models
- caqh_user.py: CAQH user data model (BCBA, BCaBA, LBHC, RBT)
- sharepoint_record.py: SharePoint record model
"""

from .validation_result import FieldValidationResult, DocumentValidationResult, ValidationSummary
from .extraction_result import FieldExtractionResult, DocumentExtractionResult, ExtractionSummary, get_extraction_summary

__all__ = [
    "FieldValidationResult",
    "DocumentValidationResult",
    "ValidationSummary",
    "FieldExtractionResult",
    "DocumentExtractionResult",
    "ExtractionSummary",
    "get_extraction_summary"
]
