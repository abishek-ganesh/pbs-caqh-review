#!/usr/bin/env python3
"""
JSON Report Generator for CAQH Data Summary Review Results

Generates structured JSON output for:
1. SharePoint storage (JSONReport field)
2. PBS Live notification messages
3. Resubmission tracking workflow

Schema: docs/technical/JSON_REPORT_FORMAT.md

Author: Abishek Ganesh
Created: January 29, 2026
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from src.models.validation_result import DocumentValidationResult, FieldValidationResult
from src.config.constants import ValidationStatus, PHI_FIELDS


# JSON Report Schema Version
SCHEMA_VERSION = "1.0"


def generate_json_report(
    validation_result: DocumentValidationResult,
    file_name: str,
    sharepoint_item_id: Optional[int] = None,
    page_count: int = 0,
    ocr_used: bool = False,
    processing_time_ms: int = 0,
    attempt_number: int = 1,
    original_submission_id: Optional[int] = None,
    previous_status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a JSON report from validation results.

    Args:
        validation_result: DocumentValidationResult from validation engine
        file_name: Original PDF filename
        sharepoint_item_id: SharePoint item ID
        page_count: Number of pages in PDF
        ocr_used: Whether OCR was needed for text extraction
        processing_time_ms: Processing time in milliseconds
        attempt_number: Submission attempt number (1 for first, 2 for resubmission)
        original_submission_id: For resubmissions, the original item ID
        previous_status: For resubmissions, the previous validation status

    Returns:
        Dictionary matching JSON_REPORT_FORMAT.md schema
    """
    # Determine overall status for JSON
    json_status = _map_validation_status(validation_result.overall_status)

    # Calculate confidence score (0-100)
    confidence_score = _calculate_overall_confidence(validation_result)

    # Determine if human review is required
    requires_human_review = json_status == "NEEDS_HUMAN_REVIEW"

    # Build fields section
    fields_dict = {}
    for field_result in validation_result.field_results:
        fields_dict[field_result.field_name] = _build_field_entry(field_result)

    # Build issues array (only failed fields)
    issues = _build_issues_array(validation_result.field_results)

    # Extract provider info
    provider_info = _extract_provider_info(validation_result.field_results)

    # Generate PBS Live messages
    pbs_live_messages = _generate_pbs_live_messages(issues, json_status)

    # Build the complete report
    report = {
        "version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "processing_time_ms": processing_time_ms,

        "document": {
            "file_name": file_name,
            "sharepoint_item_id": sharepoint_item_id,
            "is_valid_caqh_document": json_status != "WRONG_DOCUMENT",
            "page_count": page_count,
            "ocr_used": ocr_used
        },

        "submission": {
            "attempt_number": attempt_number,
            "original_submission_id": original_submission_id,
            "previous_status": previous_status
        },

        "result": {
            "status": json_status,
            "confidence_score": confidence_score,
            "requires_human_review": requires_human_review,
            "field_count": validation_result.total_fields_checked,
            "passed_count": validation_result.fields_passed,
            "failed_count": validation_result.fields_failed,
            "warning_count": validation_result.fields_warning
        },

        "provider": provider_info,

        "fields": fields_dict,

        "issues": issues,

        "pbs_live_message": pbs_live_messages
    }

    return report


def generate_json_report_string(
    validation_result: DocumentValidationResult,
    file_name: str,
    **kwargs
) -> str:
    """
    Generate JSON report as a formatted string.

    Args:
        validation_result: DocumentValidationResult from validation engine
        file_name: Original PDF filename
        **kwargs: Additional arguments passed to generate_json_report

    Returns:
        JSON string (pretty-printed)
    """
    report = generate_json_report(validation_result, file_name, **kwargs)
    # ensure_ascii=True escapes non-ASCII chars that can break SharePoint updates
    return json.dumps(report, indent=2, ensure_ascii=True)


def generate_minimal_json_report_string(
    validation_result: DocumentValidationResult,
    file_name: str,
    sharepoint_item_id: Optional[int] = None,
    **kwargs
) -> str:
    """
    Generate a minimal JSON report for SharePoint storage.

    This minimal version contains only essential fields for PBS Live notifications.
    The full detailed report is stored in the JSONReport field using generate_json_report_string().

    Args:
        validation_result: DocumentValidationResult from validation engine
        file_name: Original PDF filename
        sharepoint_item_id: SharePoint item ID

    Returns:
        Compact JSON string (~500-1000 chars max)
    """
    # Map status
    json_status = _map_validation_status(validation_result.overall_status)

    # Build minimal issues array (just field + message, max 5 issues)
    issues = []
    for field in validation_result.field_results:
        if field.errors:
            issues.append({
                "field": field.field_name,
                "message": _get_user_friendly_message(field.field_name, field.errors[0])
            })
            if len(issues) >= 5:  # Limit to 5 issues to keep size down
                break

    # Minimal report structure
    minimal_report = {
        "version": SCHEMA_VERSION,
        "status": json_status,
        "file_name": file_name,
        "item_id": sharepoint_item_id,
        "confidence": _calculate_overall_confidence(validation_result),
        "passed": validation_result.fields_passed,
        "failed": validation_result.fields_failed,
        "issues": issues
    }

    # Compact JSON (no indent) to minimize size
    return json.dumps(minimal_report, separators=(',', ':'), ensure_ascii=True)


def _map_validation_status(status: ValidationStatus) -> str:
    """
    Map internal ValidationStatus to JSON report status.

    Returns one of: AI_APPROVED, AI_REJECTED
    - NEEDS_HUMAN_REVIEW maps to AI_APPROVED (AI passed, human just needs to verify)
    - Any rejection/failure maps to AI_REJECTED
    """
    if status in (ValidationStatus.APPROVED, ValidationStatus.AI_REVIEWED_LOOKS_GOOD, ValidationStatus.NEEDS_HUMAN_REVIEW):
        return "AI_APPROVED"
    else:
        return "AI_REJECTED"


def _calculate_overall_confidence(validation_result: DocumentValidationResult) -> int:
    """
    Calculate overall confidence score (0-100).

    Based on average field confidence weighted by validation success.
    """
    if not validation_result.field_results:
        return 0

    total_confidence = 0.0
    count = 0

    for field in validation_result.field_results:
        if field.confidence is not None:
            total_confidence += field.confidence
            count += 1

    if count == 0:
        return 0

    avg_confidence = total_confidence / count

    # Adjust for failures (each failure reduces score)
    failure_penalty = validation_result.fields_failed * 5  # 5 points per failure

    score = int(avg_confidence * 100) - failure_penalty
    return max(0, min(100, score))  # Clamp to 0-100


def _build_field_entry(field: FieldValidationResult) -> Dict[str, Any]:
    """
    Build a field entry for the fields section.

    Masks sensitive PHI data.

    Status values:
    - PASS: Field was validated and passed
    - FAIL: Field was validated and failed
    - WARNING: Field has warnings but passed
    - EXTRACTED: Field was extracted but not validated (no validator exists)
    - —: Optional field with no value (not required, not an error)
    - NOT_FOUND: Required field that couldn't be extracted
    """
    # Check if field was actually validated or just extracted
    is_extraction_only = (
        field.validation_rules_applied == ["extraction_only"] or
        field.validation_rules_applied == []
    )

    # Determine field status based on validation state
    if field.errors:
        status = "FAIL"
    elif is_extraction_only:
        # Field wasn't validated, just extracted
        if field.extracted_value is None:
            if field.is_required:
                status = "NOT_FOUND"
            else:
                status = "—"  # Optional field, no value, no problem
        else:
            status = "EXTRACTED"  # Has value but wasn't validated
    elif field.warnings:
        status = "WARNING"
    elif field.extracted_value is None:
        status = "NOT_FOUND"
    elif field.is_valid:
        status = "PASS"
    else:
        status = "FAIL"

    # Mask PHI fields
    display_value = field.extracted_value
    if field.field_name.lower() in PHI_FIELDS or field.field_name == "ssn":
        display_value = _mask_sensitive_value(field.field_name, field.extracted_value)

    # Get message (first error or warning)
    message = None
    user_friendly_message = None

    if field.errors:
        message = field.errors[0]
        user_friendly_message = _get_user_friendly_message(field.field_name, field.errors[0])
    elif field.warnings:
        message = field.warnings[0]
        user_friendly_message = _get_user_friendly_message(field.field_name, field.warnings[0])

    entry = {
        "extracted_value": display_value,
        "status": status,
        "confidence": round(field.confidence, 2) if field.confidence else 0.0,
        "message": message
    }

    if user_friendly_message:
        entry["user_friendly_message"] = user_friendly_message

    return entry


def _mask_sensitive_value(field_name: str, value: Any) -> Optional[str]:
    """
    Mask sensitive PHI values for display.

    SSN: ***-**-1234
    Birth date: **/**/1990
    """
    if value is None:
        return None

    value_str = str(value)

    if field_name == "ssn" or field_name == "social_security_number":
        # Mask SSN: show only last 4 digits
        if len(value_str) >= 4:
            return f"***-**-{value_str[-4:]}"
        return "***-**-****"

    elif field_name == "birth_date":
        # Mask birth date: show only year
        if "/" in value_str:
            parts = value_str.split("/")
            if len(parts) == 3:
                return f"**/**/****"
        return "**/**/****"

    elif field_name in ("home_address", "personal_email"):
        # Partially mask
        return "[REDACTED]"

    return value_str


def _build_issues_array(field_results: List[FieldValidationResult]) -> List[Dict[str, str]]:
    """
    Build flattened issues array for easy iteration.

    Only includes fields that failed validation.
    """
    issues = []

    for field in field_results:
        if field.errors:
            for error in field.errors:
                issues.append({
                    "field": field.field_name,
                    "severity": "error",
                    "message": _get_user_friendly_message(field.field_name, error)
                })
        elif field.warnings:
            for warning in field.warnings:
                issues.append({
                    "field": field.field_name,
                    "severity": "warning",
                    "message": _get_user_friendly_message(field.field_name, warning)
                })

    return issues


def _extract_provider_info(field_results: List[FieldValidationResult]) -> Dict[str, Optional[str]]:
    """
    Extract provider identifying information from field results.
    """
    provider_info = {
        "name": None,
        "npi": None,
        "caqh_number": None
    }

    for field in field_results:
        if field.field_name == "provider_name" and field.extracted_value:
            provider_info["name"] = str(field.extracted_value)
        elif field.field_name == "individual_npi" and field.extracted_value:
            provider_info["npi"] = str(field.extracted_value)
        elif field.field_name == "caqh_provider_id" and field.extracted_value:
            provider_info["caqh_number"] = str(field.extracted_value)

    return provider_info


def _get_user_friendly_message(field_name: str, technical_message: str) -> str:
    """
    Convert technical validation message to user-friendly PBS Live message.

    These messages will be shown to individuals via PBS Live DM.
    """
    # Field-specific user-friendly templates
    templates = {
        "medicaid_id": "Please update your Medicaid ID in CAQH. The Medicaid ID field must be completed with your valid state Medicaid provider number.",

        "ssn": "Please verify and update your Social Security Number in CAQH. The SSN must be in the correct format.",

        "individual_npi": "Please verify your Individual NPI number in CAQH. The NPI must be a valid 10-digit number.",

        "practice_location_name": "Please verify your Practice Location Name in CAQH. The practice location must match 'Positive Behavior Supports Corporation' followed by the region.",

        "professional_license_expiration_date": "Please update your Professional License information in CAQH. Your license expiration date must be a future date - expired licenses cannot be accepted.",

        "license_number": "Please verify your License Number in CAQH. The license number must be provided.",

        "license_state": "Please verify your License State in CAQH.",

        "insurance_policy_number": "Please verify your Insurance Policy Number in CAQH.",

        "insurance_covered_location": "Please verify your Insurance Covered Location in CAQH. It should match your practice location.",

        "insurance_current_effective_date": "Please verify your Insurance Effective Date in CAQH.",

        "insurance_current_expiration_date": "Please update your Insurance Expiration Date in CAQH. It must be a future date.",

        "insurance_carrier_name": "Please verify your Insurance Carrier Name in CAQH.",

        "tax_id": "Please verify your Tax ID in CAQH. It must match the PBS Corporation Tax ID.",

        "organizational_npi": "Please verify your Organizational NPI in CAQH. It must match the PBS Corporation NPI.",

        "caqh_attestation_date": "Please ensure your CAQH attestation is current. Re-attest if needed.",
    }

    # Return template if available, otherwise format the technical message
    if field_name in templates:
        return templates[field_name]

    # Generic fallback - make technical message more friendly
    field_display = field_name.replace("_", " ").title()
    return f"Please review and update the {field_display} field in your CAQH profile. Issue: {technical_message}"


def _generate_pbs_live_messages(issues: List[Dict[str, str]], status: str) -> Dict[str, str]:
    """
    Generate pre-formatted messages for PBS Live Insertions.
    """
    approved_message = (
        "Your CAQH Data Summary submission has been reviewed and approved by our AI system. "
        "A human reviewer will complete the final review shortly."
    )

    if not issues:
        rejected_message = (
            "Your CAQH Data Summary submission has been reviewed. "
            "Please ensure all required fields are completed and resubmit."
        )
    else:
        # Format issues as bullet points
        issue_bullets = "\n".join([f"- {issue['message']}" for issue in issues])
        rejected_message = (
            f"Your CAQH Data Summary submission has been reviewed. "
            f"The following issues were found:\n\n{issue_bullets}\n\n"
            f"Please update your CAQH profile and resubmit."
        )

    return {
        "approved_message": approved_message,
        "rejected_message": rejected_message
    }


def get_validation_status_for_sharepoint(json_report: Dict[str, Any]) -> str:
    """
    Extract the validation status string for SharePoint field.

    Returns one of: AI_APPROVED, AI_REJECTED
    """
    return json_report.get("result", {}).get("status", "AI_APPROVED")


def get_issues_for_pbs_live(json_report: Dict[str, Any]) -> str:
    """
    Get formatted issues string for PBS Live DynamicTags.

    Used with $ISSUES tag in CAQH_REJECTED insertion.
    """
    issues = json_report.get("issues", [])
    if not issues:
        return "No specific issues identified. Please review your submission."

    return "\n".join([f"- {issue['message']}" for issue in issues])


if __name__ == "__main__":
    print("JSON Report Generator - Use generate_json_report() to create JSON from validation results")
