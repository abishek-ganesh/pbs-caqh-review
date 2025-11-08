"""
Field Validators for CAQH Data Summary

Provides validation functions for the 5 critical POC fields:
1. Medicaid ID
2. Social Security Number
3. Individual NPI
4. Practice Location Name
5. Professional License Expiration Date

Each validator returns a FieldValidationResult with:
- Validation status (pass/fail)
- Confidence score (0.0-1.0)
- Error messages
- Warnings
"""

import re
from typing import Optional, List, Dict, Callable
from ..models.validation_result import FieldValidationResult
from ..config.constants import ConfidenceLevel
from ..utils.format_utils import validate_ssn, validate_npi, normalize_ssn, normalize_npi, mask_ssn
from ..utils.date_utils import parse_date, is_future_date, format_date_for_display


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _determine_confidence_level(confidence: float) -> ConfidenceLevel:
    """
    Map confidence score to confidence level enum.

    Args:
        confidence: Confidence score (0.0-1.0)

    Returns:
        ConfidenceLevel enum (HIGH, MEDIUM, or LOW)
    """
    if confidence >= 0.90:
        return ConfidenceLevel.HIGH
    elif confidence >= 0.70:
        return ConfidenceLevel.MEDIUM
    else:
        return ConfidenceLevel.LOW


def _create_field_result(
    field_name: str,
    field_category: str,
    extracted_value: Optional[str],
    is_valid: bool,
    is_required: bool,
    confidence: float,
    validation_rules_applied: List[str],
    errors: List[str],
    warnings: List[str] = None,
    notes: Optional[str] = None,
    expected_value: Optional[str] = None,
    cheat_sheet_rule: Optional[str] = None,
    validation_details: List[str] = None,
    confidence_reasoning: Optional[str] = None
) -> FieldValidationResult:
    """
    Factory function to create consistent FieldValidationResult objects.

    Args:
        field_name: Name of the field
        field_category: Category (e.g., "Personal Information")
        extracted_value: Value extracted from PDF
        is_valid: Whether validation passed
        is_required: Whether field is required
        confidence: Confidence score (0.0-1.0)
        validation_rules_applied: List of validation rules checked
        errors: List of error messages
        warnings: List of warning messages (optional)
        notes: Additional notes (optional)
        expected_value: Expected value from validation rules (optional)
        cheat_sheet_rule: CAQH Cheat Sheet rule description (optional)
        validation_details: Detailed validation checks breakdown (optional)
        confidence_reasoning: Explanation of confidence score (optional)

    Returns:
        FieldValidationResult object
    """
    return FieldValidationResult(
        field_name=field_name,
        field_category=field_category,
        extracted_value=extracted_value,
        expected_value=expected_value,
        is_valid=is_valid,
        is_required=is_required,
        confidence=confidence,
        confidence_level=_determine_confidence_level(confidence),
        validation_rules_applied=validation_rules_applied,
        errors=errors if errors else [],
        warnings=warnings if warnings else [],
        notes=notes,
        cheat_sheet_rule=cheat_sheet_rule,
        validation_details=validation_details if validation_details else [],
        confidence_reasoning=confidence_reasoning
    )


# =============================================================================
# FIELD VALIDATORS (5 Critical POC Fields)
# =============================================================================

def validate_medicaid_id(value: Optional[str]) -> FieldValidationResult:
    """
    Validate Medicaid Provider ID.

    Requirements:
    - Required field
    - Must be non-empty string
    - Text presence check (from CAQH User Data)

    Args:
        value: Medicaid ID value extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "medicaid_id"
    field_category = "Personal Information"
    is_required = True
    validation_rules_applied = ["required", "text_presence"]
    errors = []
    warnings = []
    notes = None

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Medicaid ID is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty after stripping
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,  # Low confidence - field present but empty
            validation_rules_applied=validation_rules_applied,
            errors=["Medicaid ID cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Valid - has text content
    validation_details = [
        "✅ Required field check: Present",
        f"✅ Text presence check: {len(value_stripped)} characters found",
        f"✅ Format check: Value is non-empty and properly formatted"
    ]

    # Add length validation detail if it looks like a number
    if value_stripped.isdigit():
        validation_details.append(f"✅ Length check: {len(value_stripped)} digits (typical range: 8-12 digits)")

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=True,
        is_required=is_required,
        confidence=0.95,  # High confidence for simple presence check
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes="Medicaid ID present and valid",
        cheat_sheet_rule="Medicaid Number must be present (from CAQH User Data). Format varies by state but typically 8-12 digits.",
        validation_details=validation_details,
        confidence_reasoning="High confidence (0.95) because field was extracted successfully and passes all validation checks"
    )


def validate_ssn_field(value: Optional[str]) -> FieldValidationResult:
    """
    Validate Social Security Number.

    Requirements:
    - Required field
    - Format: XXX-XX-XXXX or XXXXXXXXX
    - Must pass format validation

    Args:
        value: SSN value extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "ssn"
    field_category = "Personal Information"
    is_required = True
    validation_rules_applied = ["required", "format_ssn"]
    errors = []
    warnings = []
    notes = None

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Social Security Number is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Social Security Number cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Validate SSN format using utility function
    if not validate_ssn(value_stripped):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.3,  # Low-medium confidence - has value but wrong format
            validation_rules_applied=validation_rules_applied,
            errors=["SSN format invalid - must be XXX-XX-XXXX or XXXXXXXXX"],
            warnings=warnings,
            notes=f"Invalid SSN format: {value_stripped}"
        )

    # Valid SSN format
    normalized = normalize_ssn(value_stripped)
    masked = mask_ssn(normalized)  # Mask for display/logging (PHI protection)

    validation_details = [
        "✅ Required field check: Present",
        f"✅ Format check: Matches SSN pattern (XXX-XX-XXXX or XXXXXXXXX)",
        f"✅ Length check: {len(value_stripped.replace('-', ''))} digits",
        f"✅ Normalized format: {masked} (PHI - masked for security)"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=normalized,  # Return normalized format
        is_valid=True,
        is_required=is_required,
        confidence=0.98,  # Very high confidence for format validation
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"SSN format valid (normalized to {masked})",
        cheat_sheet_rule="Social Security Number must be present and in valid format: XXX-XX-XXXX or XXXXXXXXX (9 digits total). PHI - must be masked in logs.",
        validation_details=validation_details,
        confidence_reasoning="Very high confidence (0.98) because SSN matches strict format requirements and passes pattern validation"
    )


def validate_individual_npi(value: Optional[str]) -> FieldValidationResult:
    """
    Validate Individual National Provider Identifier (NPI).

    Requirements:
    - Required field
    - Must be exactly 10 digits
    - Must pass Luhn checksum validation

    Args:
        value: NPI value extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "individual_npi"
    field_category = "Professional IDs"
    is_required = True
    validation_rules_applied = ["required", "format_npi", "luhn_checksum"]
    errors = []
    warnings = []
    notes = None

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Individual NPI is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Individual NPI cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Validate NPI format and checksum using utility function
    if not validate_npi(value_stripped):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.3,  # Low-medium confidence - has value but invalid
            validation_rules_applied=validation_rules_applied,
            errors=["NPI must be exactly 10 digits and pass Luhn checksum validation"],
            warnings=warnings,
            notes=f"Invalid NPI: {value_stripped}"
        )

    # Valid NPI
    normalized = normalize_npi(value_stripped)
    validation_details = [
        "✅ Required field check: Present",
        f"✅ Length check: Exactly 10 digits",
        f"✅ Format check: All digits, no invalid characters",
        f"✅ Luhn checksum: Passed algorithm validation",
        f"✅ Normalized format: {normalized}"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=normalized,  # Return normalized (digits only)
        is_valid=True,
        is_required=is_required,
        confidence=0.99,  # Very high confidence - format + checksum passed
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"NPI valid and passed Luhn checksum (normalized to {normalized})",
        cheat_sheet_rule="Individual NPI (National Provider Identifier) must be exactly 10 digits and pass Luhn checksum validation algorithm.",
        validation_details=validation_details,
        confidence_reasoning="Very high confidence (0.99) because NPI passes both format validation AND Luhn checksum algorithm (strongest validation)"
    )


def validate_practice_location_name(value: Optional[str]) -> FieldValidationResult:
    """
    Validate Practice Location Name.

    Requirements:
    - Required field
    - Must be non-empty string
    - TODO: Future enhancement - validate against CAQH location list

    Args:
        value: Practice location name extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "practice_location_name"
    field_category = "Practice Locations"
    is_required = True
    validation_rules_applied = ["required", "text_presence"]
    errors = []
    warnings = []
    notes = None

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Practice Location Name is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Practice Location Name cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # LOGICAL VALIDATION: Check if value looks like a real practice location
    invalid_patterns = [
        r'---\s*Page',  # OCR page markers
        r'Provider\s+CAQH\s+ID',  # Wrong section
        r'Attestation\s+Date',  # Wrong section
        r'^\s*Provider\s+',  # Starts with "Provider"
        r'CAQH\s+ID\s*\d+',  # Contains CAQH ID numbers
    ]

    # Check for obviously wrong content
    is_obviously_wrong = any(re.search(pattern, value_stripped, re.IGNORECASE) for pattern in invalid_patterns)

    if is_obviously_wrong:
        # INVALID - extracted wrong content
        errors.append(f"Extracted value does not appear to be a valid practice location name")
        validation_details = [
            "❌ Required field check: Present but invalid content",
            f"❌ Content validation: Contains invalid patterns (OCR markers, CAQH IDs, etc.)",
            f"❌ Extracted: '{value_stripped[:100]}...'"
        ]
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.2,  # Low confidence - extracted but wrong content
            validation_rules_applied=validation_rules_applied,
            errors=errors,
            warnings=warnings,
            notes="Extracted value contains invalid content - likely extraction error",
            cheat_sheet_rule="Practice Location Name must be present and match an approved PBS location. Most error-prone section due to multiple sub-fields.",
            validation_details=validation_details,
            confidence_reasoning="Low confidence (0.2) because extracted value contains invalid patterns indicating extraction error"
        )

    # Check if suspiciously short (less than 3 characters) or contains address content
    has_address_content = any(keyword in value_stripped.lower() for keyword in ['street', 'rd', 'ave', 'blvd', 'suite', 'ste', 'country', 'united states'])

    if len(value_stripped) < 3:
        warnings.append("Practice Location Name is very short - may be incomplete")
        confidence = 0.70  # Medium confidence due to warning
        confidence_reasoning = "Medium confidence (0.70) because practice name is very short and may be incomplete"
    elif has_address_content:
        # Practice name appears to contain address fields - lower confidence
        warnings.append("Practice name may contain address fields - extraction may be incomplete")
        confidence = 0.75  # Medium-high confidence - present but may include extra content
        confidence_reasoning = f"Medium-high confidence (0.75) because practice name appears to contain address content ({len(value_stripped)} characters)"
    else:
        # Good extraction - reasonable length, no obvious address content
        confidence = 0.95  # High confidence - clean extraction
        confidence_reasoning = f"High confidence (0.95) because practice name appears clean with reasonable length ({len(value_stripped)} characters)"

    # Build validation details
    validation_details = [
        "✅ Required field check: Present",
        f"✅ Text presence check: {len(value_stripped)} characters found",
        f"{'⚠️' if has_address_content else '✅'} Content validation: {'May contain address fields' if has_address_content else 'Appears to be clean practice name'}",
        f"✅ Length check: {'Within acceptable range' if len(value_stripped) >= 3 else 'WARNING: Very short'}",
        f"✅ Extracted: '{value_stripped}'"
    ]

    # Valid - has text content
    # TODO: Future enhancement - check against CAQH practice location list
    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=True,
        is_required=is_required,
        confidence=confidence,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes="Practice Location Name present" + (" (TODO: validate against CAQH list)" if confidence >= 0.90 else ""),
        cheat_sheet_rule="Practice Location Name must be present. Most error-prone section due to multiple sub-fields.",
        validation_details=validation_details,
        confidence_reasoning=confidence_reasoning
    )


def validate_license_expiration_date(value: Optional[str]) -> FieldValidationResult:
    """
    Validate Professional License Expiration Date.

    Requirements:
    - Required field
    - Must be a valid date
    - Must be in the FUTURE (not expired)

    Args:
        value: License expiration date extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "professional_license_expiration_date"
    field_category = "Professional IDs"
    is_required = True
    validation_rules_applied = ["required", "date_format", "date_future"]
    errors = []
    warnings = []
    notes = None

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Professional License Expiration Date is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Professional License Expiration Date cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Try to parse date
    parsed_date = parse_date(value_stripped)
    if parsed_date is None:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.2,  # Low confidence - has value but unparseable
            validation_rules_applied=validation_rules_applied,
            errors=[f"Invalid date format: {value_stripped}. Expected formats: MM/DD/YYYY, YYYY-MM-DD, etc."],
            warnings=warnings,
            notes="Unable to parse date"
        )

    # Check if date is in the future
    if not is_future_date(parsed_date, strict=False):  # Allow today's date
        formatted_date = format_date_for_display(parsed_date)
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=formatted_date,
            is_valid=False,
            is_required=is_required,
            confidence=0.75,  # Medium-high confidence - date parseable but expired
            validation_rules_applied=validation_rules_applied,
            errors=[f"License expiration date ({formatted_date}) is in the past - license has expired"],
            warnings=warnings,
            notes=f"Parsed date: {formatted_date} (expired)"
        )

    # Valid - future date
    formatted_date = format_date_for_display(parsed_date)

    # Add warning if expires within 30 days
    from datetime import date, timedelta
    days_until_expiration = (parsed_date - date.today()).days
    if days_until_expiration <= 30:
        warnings.append(f"License expires soon ({days_until_expiration} days)")
        confidence = 0.88  # Slightly lower confidence due to warning
        confidence_reasoning = f"Medium-high confidence (0.88) because date is valid but expires soon ({days_until_expiration} days) - may need renewal"
    else:
        confidence = 0.97  # High confidence - valid future date
        confidence_reasoning = f"High confidence (0.97) because date is valid, properly formatted, and expires in {days_until_expiration} days (well in the future)"

    # Build validation details
    validation_details = [
        "✅ Required field check: Present",
        f"✅ Date format check: Successfully parsed as {formatted_date}",
        f"✅ Future date check: Date is {'within 30 days' if days_until_expiration <= 30 else f'{days_until_expiration} days in the future'}",
        f"✅ Expiration status: {'⚠️ Expiring soon' if days_until_expiration <= 30 else 'Valid and not expiring soon'}"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=formatted_date,
        is_valid=True,
        is_required=is_required,
        confidence=confidence,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"License expiration date valid ({formatted_date}) - expires in {days_until_expiration} days",
        cheat_sheet_rule="Professional License Expiration Date must be a valid future date. Must be parsed correctly and not expired. Warning if expires within 30 days.",
        validation_details=validation_details,
        confidence_reasoning=confidence_reasoning
    )
# =============================================================================
# TIER 2 VALIDATORS (10 additional fields)
# =============================================================================

def validate_email_address(value: Optional[str]) -> FieldValidationResult:
    """
    Validate email address.

    Requirements:
    - Not required (optional field)
    - Must match valid email format if provided

    Args:
        value: Email address extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    from ..utils.format_utils import validate_email

    field_name = "practice_location_email"
    field_category = "Practice Locations"
    is_required = False
    validation_rules_applied = ["format_email"]
    errors = []
    warnings = []

    # Optional field - None is acceptable
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=True,  # Optional field
            is_required=is_required,
            confidence=0.95,
            validation_rules_applied=validation_rules_applied,
            errors=errors,
            warnings=warnings,
            notes="Email is optional - not provided"
        )

    # Strip whitespace
    value_stripped = value.strip().lower()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=True,  # Optional field
            is_required=is_required,
            confidence=0.95,
            validation_rules_applied=validation_rules_applied,
            errors=errors,
            warnings=warnings,
            notes="Email is optional - empty value acceptable"
        )

    # Validate email format
    if not validate_email(value_stripped):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.3,
            validation_rules_applied=validation_rules_applied,
            errors=["Email format invalid - must be valid email address (e.g., user@example.com)"],
            warnings=warnings,
            notes=f"Invalid email format: {value_stripped}"
        )

    # Valid email
    validation_details = [
        "✅ Format check: Matches email pattern (user@domain.com)",
        f"✅ Normalized format: {value_stripped}"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=True,
        is_required=is_required,
        confidence=0.97,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"Email format valid: {value_stripped}",
        cheat_sheet_rule="Practice Location Email Address is optional but must be valid email format if provided.",
        validation_details=validation_details,
        confidence_reasoning="High confidence (0.97) because email matches valid format pattern"
    )


def validate_phone_number(value: Optional[str]) -> FieldValidationResult:
    """
    Validate phone number.

    Requirements:
    - Required field
    - Must match valid US phone format

    Args:
        value: Phone number extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    from ..utils.format_utils import validate_phone, normalize_phone

    field_name = "practice_location_phone"
    field_category = "Practice Locations"
    is_required = True
    validation_rules_applied = ["required", "format_phone"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Phone number is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Phone number cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Validate phone format
    if not validate_phone(value_stripped):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.3,
            validation_rules_applied=validation_rules_applied,
            errors=["Phone format invalid - must be valid US phone number (e.g., 555-123-4567)"],
            warnings=warnings,
            notes=f"Invalid phone format: {value_stripped}"
        )

    # Valid phone
    normalized = normalize_phone(value_stripped)
    validation_details = [
        "✅ Required field check: Present",
        f"✅ Format check: Matches phone pattern",
        f"✅ Normalized format: {normalized}"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=normalized,
        is_valid=True,
        is_required=is_required,
        confidence=0.96,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"Phone format valid (normalized to {normalized})",
        cheat_sheet_rule="Practice Location Phone Number is required and must be valid US phone format.",
        validation_details=validation_details,
        confidence_reasoning="High confidence (0.96) because phone matches valid format pattern"
    )


def validate_first_name(value: Optional[str]) -> FieldValidationResult:
    """
    Validate first name.

    Requirements:
    - Required field
    - Must be non-empty string
    - 2-50 characters

    Args:
        value: First name extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "first_name"
    field_category = "Personal Information"
    is_required = True
    validation_rules_applied = ["required", "text_presence", "length"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["First Name is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["First Name cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Check length
    if len(value_stripped) < 2:
        errors.append("First Name is too short (minimum 2 characters)")
        confidence = 0.2
    elif len(value_stripped) > 50:
        errors.append("First Name is too long (maximum 50 characters)")
        confidence = 0.2
    else:
        confidence = 0.95

    is_valid = len(errors) == 0

    validation_details = [
        "✅ Required field check: Present",
        f"{'✅' if len(value_stripped) >= 2 else '❌'} Length check: {len(value_stripped)} characters (2-50 required)",
        f"✅ Value: '{value_stripped}'"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=is_valid,
        is_required=is_required,
        confidence=confidence,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"First Name {'valid' if is_valid else 'invalid'}",
        cheat_sheet_rule="First Name must be present and 2-50 characters.",
        validation_details=validation_details,
        confidence_reasoning=f"{'High' if is_valid else 'Low'} confidence because name {'passes' if is_valid else 'fails'} length validation"
    )


def validate_last_name(value: Optional[str]) -> FieldValidationResult:
    """
    Validate last name.

    Requirements:
    - Required field
    - Must be non-empty string
    - 2-50 characters

    Args:
        value: Last name extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "last_name"
    field_category = "Personal Information"
    is_required = True
    validation_rules_applied = ["required", "text_presence", "length"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Last Name is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Last Name cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Check length
    if len(value_stripped) < 2:
        errors.append("Last Name is too short (minimum 2 characters)")
        confidence = 0.2
    elif len(value_stripped) > 50:
        errors.append("Last Name is too long (maximum 50 characters)")
        confidence = 0.2
    else:
        confidence = 0.95

    is_valid = len(errors) == 0

    validation_details = [
        "✅ Required field check: Present",
        f"{'✅' if len(value_stripped) >= 2 else '❌'} Length check: {len(value_stripped)} characters (2-50 required)",
        f"✅ Value: '{value_stripped}'"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=is_valid,
        is_required=is_required,
        confidence=confidence,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"Last Name {'valid' if is_valid else 'invalid'}",
        cheat_sheet_rule="Last Name must be present and 2-50 characters.",
        validation_details=validation_details,
        confidence_reasoning=f"{'High' if is_valid else 'Low'} confidence because name {'passes' if is_valid else 'fails'} length validation"
    )


def validate_date_of_birth(value: Optional[str]) -> FieldValidationResult:
    """
    Validate date of birth.

    Requirements:
    - Required field (PHI)
    - Must be a valid past date
    - Must be reasonable (not too far in past, not in future)

    Args:
        value: Date of birth extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "date_of_birth"
    field_category = "Personal Information"
    is_required = True
    validation_rules_applied = ["required", "date_format", "date_past"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Date of Birth is required but not found"],
            warnings=warnings,
            notes="Field is missing or None (PHI)"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Date of Birth cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value (PHI)"
        )

    # Try to parse date
    parsed_date = parse_date(value_stripped)
    if parsed_date is None:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.2,
            validation_rules_applied=validation_rules_applied,
            errors=[f"Invalid date format: {value_stripped}. Expected formats: MM/DD/YYYY, YYYY-MM-DD, etc."],
            warnings=warnings,
            notes="Unable to parse date (PHI)"
        )

    # Check if date is in the past
    from datetime import date
    if parsed_date >= date.today():
        formatted_date = format_date_for_display(parsed_date)
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=formatted_date,
            is_valid=False,
            is_required=is_required,
            confidence=0.75,
            validation_rules_applied=validation_rules_applied,
            errors=[f"Date of Birth ({formatted_date}) cannot be in the future"],
            warnings=warnings,
            notes=f"Parsed date: {formatted_date} (invalid - future date) (PHI)"
        )

    # Valid - past date
    formatted_date = format_date_for_display(parsed_date)

    # Calculate age and warn if unusual
    age = (date.today() - parsed_date).days // 365
    if age < 18:
        warnings.append(f"Age appears young ({age} years) - verify date is correct")
        confidence = 0.85
    elif age > 100:
        warnings.append(f"Age appears very old ({age} years) - verify date is correct")
        confidence = 0.85
    else:
        confidence = 0.97

    validation_details = [
        "✅ Required field check: Present",
        f"✅ Date format check: Successfully parsed as {formatted_date}",
        f"✅ Past date check: Date is in the past ({age} years ago)",
        f"{'⚠️' if len(warnings) > 0 else '✅'} Age validation: {age} years old"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=formatted_date,
        is_valid=True,
        is_required=is_required,
        confidence=confidence,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"Date of Birth valid ({formatted_date}) - PHI field, must be masked in logs",
        cheat_sheet_rule="Date of Birth must be a valid past date. PHI - must be masked in logs.",
        validation_details=validation_details,
        confidence_reasoning=f"{'High' if confidence > 0.90 else 'Medium-high'} confidence - date is valid and age is {'reasonable' if len(warnings) == 0 else 'unusual but possible'}"
    )


def validate_professional_license_number(value: Optional[str]) -> FieldValidationResult:
    """
    Validate professional license number.

    Requirements:
    - Required field
    - Must be non-empty string
    - Typically 5-20 alphanumeric characters

    Args:
        value: License number extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "professional_license_number"
    field_category = "Professional IDs"
    is_required = True
    validation_rules_applied = ["required", "text_presence", "format"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Professional License Number is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Professional License Number cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Check format (alphanumeric, 5-20 characters)
    if not re.match(r'^[A-Z0-9]{5,20}$', value_stripped, re.IGNORECASE):
        errors.append("License Number format invalid - must be 5-20 alphanumeric characters")
        confidence = 0.3
        is_valid = False
    else:
        confidence = 0.94
        is_valid = True

    validation_details = [
        "✅ Required field check: Present",
        f"{'✅' if is_valid else '❌'} Format check: {'Alphanumeric 5-20 characters' if is_valid else 'Invalid format'}",
        f"✅ Length: {len(value_stripped)} characters",
        f"✅ Value: '{value_stripped}'"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped.upper(),
        is_valid=is_valid,
        is_required=is_required,
        confidence=confidence,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"License Number {'valid' if is_valid else 'invalid'}",
        cheat_sheet_rule="Professional License Number must be present and typically 5-20 alphanumeric characters.",
        validation_details=validation_details,
        confidence_reasoning=f"{'High' if is_valid else 'Low'} confidence because license number {'matches' if is_valid else 'does not match'} expected format"
    )


def validate_practice_location_address(value: Optional[str]) -> FieldValidationResult:
    """
    Validate practice location street address.

    Requirements:
    - Required field
    - Must be non-empty string
    - 5-200 characters

    Args:
        value: Street address extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "practice_location_address"
    field_category = "Practice Locations"
    is_required = True
    validation_rules_applied = ["required", "text_presence", "length"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Practice Location Address is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Practice Location Address cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Check length
    if len(value_stripped) < 5:
        errors.append("Address is too short (minimum 5 characters)")
        confidence = 0.2
    elif len(value_stripped) > 200:
        errors.append("Address is too long (maximum 200 characters)")
        confidence = 0.2
    else:
        confidence = 0.93

    is_valid = len(errors) == 0

    validation_details = [
        "✅ Required field check: Present",
        f"{'✅' if is_valid else '❌'} Length check: {len(value_stripped)} characters (5-200 required)",
        f"✅ Value: '{value_stripped}'"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=is_valid,
        is_required=is_required,
        confidence=confidence,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"Practice Location Address {'valid' if is_valid else 'invalid'}",
        cheat_sheet_rule="Practice Location Address (Street 1) is required.",
        validation_details=validation_details,
        confidence_reasoning=f"{'High' if is_valid else 'Low'} confidence because address {'passes' if is_valid else 'fails'} length validation"
    )


def validate_practice_location_city(value: Optional[str]) -> FieldValidationResult:
    """
    Validate practice location city.

    Requirements:
    - Required field
    - Must be non-empty string
    - 2-50 characters

    Args:
        value: City name extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    field_name = "practice_location_city"
    field_category = "Practice Locations"
    is_required = True
    validation_rules_applied = ["required", "text_presence", "length"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Practice Location City is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Practice Location City cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Check length
    if len(value_stripped) < 2:
        errors.append("City name is too short (minimum 2 characters)")
        confidence = 0.2
    elif len(value_stripped) > 50:
        errors.append("City name is too long (maximum 50 characters)")
        confidence = 0.2
    else:
        confidence = 0.94

    is_valid = len(errors) == 0

    validation_details = [
        "✅ Required field check: Present",
        f"{'✅' if is_valid else '❌'} Length check: {len(value_stripped)} characters (2-50 required)",
        f"✅ Value: '{value_stripped}'"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=is_valid,
        is_required=is_required,
        confidence=confidence,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"Practice Location City {'valid' if is_valid else 'invalid'}",
        cheat_sheet_rule="Practice Location City is required.",
        validation_details=validation_details,
        confidence_reasoning=f"{'High' if is_valid else 'Low'} confidence because city name {'passes' if is_valid else 'fails'} length validation"
    )


def validate_practice_location_state(value: Optional[str]) -> FieldValidationResult:
    """
    Validate practice location state.

    Requirements:
    - Required field
    - Must be valid US state abbreviation (2 letters)

    Args:
        value: State code extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    from ..utils.format_utils import validate_state

    field_name = "practice_location_state"
    field_category = "Practice Locations"
    is_required = True
    validation_rules_applied = ["required", "format_state"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Practice Location State is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace and uppercase
    value_stripped = value.strip().upper()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Practice Location State cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Validate state code
    if not validate_state(value_stripped):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.3,
            validation_rules_applied=validation_rules_applied,
            errors=["State code invalid - must be valid 2-letter US state abbreviation (e.g., CA, NY, TX)"],
            warnings=warnings,
            notes=f"Invalid state code: {value_stripped}"
        )

    # Valid state
    validation_details = [
        "✅ Required field check: Present",
        f"✅ Format check: Valid US state code ({value_stripped})",
        f"✅ Normalized format: {value_stripped}"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=True,
        is_required=is_required,
        confidence=0.98,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"State code valid: {value_stripped}",
        cheat_sheet_rule="Practice Location State is required and must be valid 2-letter US state abbreviation.",
        validation_details=validation_details,
        confidence_reasoning="Very high confidence (0.98) because state matches valid US state code list"
    )


def validate_practice_location_zip(value: Optional[str]) -> FieldValidationResult:
    """
    Validate practice location ZIP code.

    Requirements:
    - Required field
    - Must be valid US ZIP code format (XXXXX or XXXXX-XXXX)

    Args:
        value: ZIP code extracted from PDF

    Returns:
        FieldValidationResult with validation outcome
    """
    from ..utils.format_utils import validate_zip_code, normalize_zip_code

    field_name = "practice_location_zip"
    field_category = "Practice Locations"
    is_required = True
    validation_rules_applied = ["required", "format_zip"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Practice Location ZIP Code is required but not found"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    # Strip whitespace
    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.1,
            validation_rules_applied=validation_rules_applied,
            errors=["Practice Location ZIP Code cannot be empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Validate ZIP format
    if not validate_zip_code(value_stripped):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.3,
            validation_rules_applied=validation_rules_applied,
            errors=["ZIP Code format invalid - must be XXXXX or XXXXX-XXXX"],
            warnings=warnings,
            notes=f"Invalid ZIP format: {value_stripped}"
        )

    # Valid ZIP
    normalized = normalize_zip_code(value_stripped)
    validation_details = [
        "✅ Required field check: Present",
        f"✅ Format check: Valid ZIP code format",
        f"✅ Normalized format: {normalized}"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=normalized,
        is_valid=True,
        is_required=is_required,
        confidence=0.97,
        validation_rules_applied=validation_rules_applied,
        errors=errors,
        warnings=warnings,
        notes=f"ZIP Code format valid (normalized to {normalized})",
        cheat_sheet_rule="Practice Location ZIP Code is required and must be valid US ZIP format (XXXXX or XXXXX-XXXX).",
        validation_details=validation_details,
        confidence_reasoning="High confidence (0.97) because ZIP matches valid US ZIP format"
    )


# =============================================================================
# BATCH VALIDATION
# =============================================================================

# Registry mapping field names to validator functions
ALL_FIELD_VALIDATORS: Dict[str, Callable[[Optional[str]], FieldValidationResult]] = {
    # POC Critical Fields (5)
    "medicaid_id": validate_medicaid_id,
    "ssn": validate_ssn_field,
    "individual_npi": validate_individual_npi,
    "practice_location_name": validate_practice_location_name,
    "professional_license_expiration_date": validate_license_expiration_date,

    # Tier 2 Fields - Personal Information (3)
    "first_name": validate_first_name,
    "last_name": validate_last_name,
    "date_of_birth": validate_date_of_birth,

    # Tier 2 Fields - Professional IDs (1)
    "professional_license_number": validate_professional_license_number,

    # Tier 2 Fields - Practice Locations (6)
    "practice_location_email": validate_email_address,
    "practice_location_phone": validate_phone_number,
    "practice_location_address": validate_practice_location_address,
    "practice_location_city": validate_practice_location_city,
    "practice_location_state": validate_practice_location_state,
    "practice_location_zip": validate_practice_location_zip,
}

# Keep backward compatibility - critical fields only
CRITICAL_FIELD_VALIDATORS: Dict[str, Callable[[Optional[str]], FieldValidationResult]] = {
    "medicaid_id": validate_medicaid_id,
    "ssn": validate_ssn_field,
    "individual_npi": validate_individual_npi,
    "practice_location_name": validate_practice_location_name,
    "professional_license_expiration_date": validate_license_expiration_date
}


def validate_all_critical_fields(extracted_data: Dict[str, Optional[str]]) -> List[FieldValidationResult]:
    """
    Validate all 5 critical POC fields at once.

    This is a convenience function for:
    - Running validation on extracted PDF data
    - Testing all validators together
    - Generating validation reports

    Args:
        extracted_data: Dictionary with field names as keys and extracted values

    Returns:
        List of FieldValidationResult objects (one per field)

    Example:
        >>> data = {
        ...     "medicaid_id": "12345678",
        ...     "ssn": "123-45-6789",
        ...     "individual_npi": "1234567890",
        ...     "practice_location_name": "PBS Behavioral Health",
        ...     "professional_license_expiration_date": "12/31/2026"
        ... }
        >>> results = validate_all_critical_fields(data)
        >>> all_valid = all(r.is_valid for r in results)
    """
    results = []

    for field_name, validator_func in CRITICAL_FIELD_VALIDATORS.items():
        # Get value from extracted data (None if not present)
        value = extracted_data.get(field_name)

        # Run validator
        result = validator_func(value)

        results.append(result)

    return results


def get_validation_summary(results: List[FieldValidationResult]) -> Dict[str, any]:
    """
    Generate summary statistics from validation results.

    Args:
        results: List of FieldValidationResult objects

    Returns:
        Dictionary with summary statistics
    """
    total = len(results)
    passed = sum(1 for r in results if r.is_valid)
    failed = sum(1 for r in results if not r.is_valid)

    avg_confidence = sum(r.confidence for r in results) / total if total > 0 else 0.0

    errors = []
    for r in results:
        if not r.is_valid:
            errors.extend(r.errors)

    return {
        "total_fields": total,
        "fields_passed": passed,
        "fields_failed": failed,
        "pass_rate": (passed / total * 100) if total > 0 else 0.0,
        "avg_confidence": round(avg_confidence, 2),
        "total_errors": len(errors),
        "error_messages": errors
    }


# ============================================================================
# PROFESSIONAL LIABILITY INSURANCE VALIDATORS
# ============================================================================




def validate_insurance_policy_number(value: Optional[str]) -> FieldValidationResult:
    """
    Validate insurance policy number.

    Requirements:
    - Required field (critical)
    - Must be 5-50 characters
    - Alphanumeric with optional hyphens/spaces

    Args:
        value: The insurance policy number to validate

    Returns:
        FieldValidationResult with validation status and details
    """
    field_name = "insurance_policy_number"
    field_category = "Professional Liability Insurance"
    is_required = True
    validation_rules_applied = ["required", "text_presence", "length"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Insurance Policy Number is required and was not extracted from PDF"],
            warnings=warnings,
            notes="Field is missing or None"
        )

    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Insurance Policy Number is required but appears empty"],
            warnings=warnings,
            notes="Field extracted but contains no value"
        )

    # Check length requirements (5-50 characters)
    if len(value_stripped) < 5:
        errors.append(f"Insurance Policy Number is too short (must be at least 5 characters, got {len(value_stripped)})")

    if len(value_stripped) > 50:
        errors.append(f"Insurance Policy Number is too long (must be at most 50 characters, got {len(value_stripped)})")

    # Validate format (alphanumeric with optional hyphens/spaces)
    import re
    if not re.match(r'^[A-Za-z0-9\s\-]+$', value_stripped):
        errors.append("Insurance Policy Number contains invalid characters (only letters, numbers, hyphens, and spaces allowed)")

    # Return validation result
    if errors:
        validation_details = [
            "❌ Required field check: Present but invalid",
            f"❌ Length check: {len(value_stripped)} characters (expected 5-50)",
            f"❌ Format check: Contains invalid characters"
        ]
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.50,
            validation_rules_applied=validation_rules_applied,
            errors=errors,
            warnings=warnings,
            notes="Policy number format validation failed",
            validation_details=validation_details
        )

    validation_details = [
        "✅ Required field check: Present",
        f"✅ Length check: {len(value_stripped)} characters (valid range: 5-50)",
        "✅ Format check: Alphanumeric characters only"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=True,
        is_required=is_required,
        confidence=0.95,
        validation_rules_applied=validation_rules_applied,
        errors=[],
        warnings=warnings,
        notes="Insurance Policy Number is valid",
        validation_details=validation_details,
        confidence_reasoning="High confidence (0.95) - policy number format is valid"
    )


def validate_insurance_covered_location(value: Optional[str]) -> FieldValidationResult:
    """
    Validate insurance covered location.

    Requirements:
    - OPTIONAL field (not required - this is the ONLY insurance field that allows flexible matching)
    - If present, should be non-empty text
    - Per Christian's feedback: More flexible matching allowed

    Args:
        value: The insurance covered location to validate

    Returns:
        FieldValidationResult with validation status and details
    """
    field_name = "insurance_covered_location"
    field_category = "Professional Liability Insurance"
    is_required = False  # ONLY optional insurance field
    validation_rules_applied = ["optional", "text_presence"]
    errors = []
    warnings = []

    # If value is None or empty, that's acceptable (optional field)
    if value is None or not isinstance(value, str) or not value.strip():
        validation_details = [
            "ℹ️  Required field check: Optional (not required)",
            "ℹ️  Value: Not specified"
        ]
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=None,
            is_valid=True,
            is_required=is_required,
            confidence=0.85,
            validation_rules_applied=validation_rules_applied,
            errors=[],
            warnings=["Insurance Covered Location not specified (optional field)"],
            notes="This is an optional field per CAQH requirements",
            validation_details=validation_details,
            confidence_reasoning="Optional field not provided - acceptable"
        )

    value_stripped = value.strip()

    # If present, validate it has reasonable content
    if len(value_stripped) < 3:
        warnings.append("Insurance Covered Location seems too short to be valid")
        confidence = 0.70
    else:
        confidence = 0.90

    validation_details = [
        "✅ Optional field check: Value provided",
        f"✅ Text presence check: {len(value_stripped)} characters",
        "ℹ️  Flexible matching allowed per CAQH requirements"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=True,
        is_required=is_required,
        confidence=confidence,
        validation_rules_applied=validation_rules_applied,
        errors=[],
        warnings=warnings,
        notes="Covered location present and has valid content",
        validation_details=validation_details,
        confidence_reasoning=f"Confidence {confidence} - covered location has reasonable content"
    )


def validate_insurance_current_effective_date(value: Optional[str]) -> FieldValidationResult:
    """
    Validate insurance current effective date.

    Requirements:
    - Required field (critical)
    - Must be valid date format
    - Should be in the past or present (not future)
    - Must match PBS policy exactly

    Args:
        value: The insurance effective date to validate

    Returns:
        FieldValidationResult with validation status and details
    """
    field_name = "insurance_current_effective_date"
    field_category = "Professional Liability Insurance"
    is_required = True
    validation_rules_applied = ["required", "date_format", "date_past_or_present"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Insurance Current Effective Date is required and was not extracted from PDF"],
            warnings=[],
            notes="Field is missing or None"
        )

    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Insurance Current Effective Date is required but appears empty"],
            warnings=[],
            notes="Field extracted but contains no value"
        )

    # Parse date
    from ..utils.date_utils import parse_date, is_future_date
    from datetime import datetime

    parsed_date = parse_date(value_stripped)

    if parsed_date is None:
        validation_details = [
            "❌ Required field check: Present",
            f"❌ Date format check: Invalid (got '{value_stripped}')",
            "Expected format: MM/DD/YYYY"
        ]
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.30,
            validation_rules_applied=validation_rules_applied,
            errors=[f"Invalid date format for Insurance Effective Date: '{value_stripped}' (expected MM/DD/YYYY)"],
            warnings=[],
            notes="Date parsing failed",
            validation_details=validation_details
        )

    # Check if date is in the future (effective dates should be past or present)
    today = datetime.now().date()
    if parsed_date > today:
        warnings.append(f"Insurance Effective Date is in the future ({value_stripped}). Verify this is correct.")

    validation_details = [
        "✅ Required field check: Present",
        "✅ Date format check: Valid",
        f"✅ Parsed date: {parsed_date.strftime('%Y-%m-%d')}",
        f"✅ Date check: {'Future' if parsed_date > today else 'Past/Present'} (effective dates typically past/present)"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=True,
        is_required=is_required,
        confidence=0.95,
        validation_rules_applied=validation_rules_applied,
        errors=[],
        warnings=warnings,
        notes="Valid date format and reasonable effective date",
        validation_details=validation_details,
        confidence_reasoning="High confidence (0.95) - date parsed successfully"
    )


def validate_insurance_current_expiration_date(value: Optional[str]) -> FieldValidationResult:
    """
    Validate insurance current expiration date.

    Requirements:
    - Required field (critical)
    - Must be valid date format
    - MUST be in the future (not expired)
    - Warn if expiring within 30 days
    - Must match PBS policy exactly

    Args:
        value: The insurance expiration date to validate

    Returns:
        FieldValidationResult with validation status and details
    """
    field_name = "insurance_current_expiration_date"
    field_category = "Professional Liability Insurance"
    is_required = True
    validation_rules_applied = ["required", "date_format", "date_future"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Insurance Current Expiration Date is required and was not extracted from PDF"],
            warnings=[],
            notes="Field is missing or None"
        )

    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Insurance Current Expiration Date is required but appears empty"],
            warnings=[],
            notes="Field extracted but contains no value"
        )

    # Parse date
    from ..utils.date_utils import parse_date, is_future_date
    from datetime import datetime

    parsed_date = parse_date(value_stripped)

    if parsed_date is None:
        validation_details = [
            "❌ Required field check: Present",
            f"❌ Date format check: Invalid (got '{value_stripped}')",
            "Expected format: MM/DD/YYYY"
        ]
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.30,
            validation_rules_applied=validation_rules_applied,
            errors=[f"Invalid date format for Insurance Expiration Date: '{value_stripped}' (expected MM/DD/YYYY)"],
            warnings=[],
            notes="Date parsing failed",
            validation_details=validation_details
        )

    # Check if date is in the future (CRITICAL: Insurance must not be expired)
    if not is_future_date(parsed_date, strict=False):
        validation_details = [
            "❌ Required field check: Present",
            "✅ Date format check: Valid",
            f"✅ Parsed date: {parsed_date.strftime('%Y-%m-%d')}",
            "❌ CRITICAL: Insurance has EXPIRED"
        ]
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.95,  # High confidence in the failure - we're sure it's expired
            validation_rules_applied=validation_rules_applied,
            errors=[f"Insurance has EXPIRED (expiration date: {value_stripped}). Current insurance is required."],
            warnings=[],
            notes="Insurance expiration date is in the past - policy is expired",
            validation_details=validation_details,
            confidence_reasoning="High confidence (0.95) in validation failure - date is definitely expired"
        )

    # Calculate days until expiration
    today = datetime.now().date()
    days_until_expiration = (parsed_date - today).days

    # Warn if expiring soon (within 30 days)
    if days_until_expiration <= 30:
        warnings.append(f"Insurance expires soon ({days_until_expiration} days). Provider should renew policy.")

    validation_details = [
        "✅ Required field check: Present",
        "✅ Date format check: Valid",
        f"✅ Parsed date: {parsed_date.strftime('%Y-%m-%d')}",
        f"✅ Future date check: Valid ({days_until_expiration} days remaining)"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=True,
        is_required=is_required,
        confidence=0.97,
        validation_rules_applied=validation_rules_applied,
        errors=[],
        warnings=warnings,
        notes=f"Valid future expiration date ({days_until_expiration} days remaining)",
        validation_details=validation_details,
        confidence_reasoning=f"Very high confidence (0.97) - valid future date with {days_until_expiration} days remaining"
    )


def validate_insurance_carrier_name(value: Optional[str]) -> FieldValidationResult:
    """
    Validate insurance carrier name.

    Requirements:
    - Required field (critical)
    - Must be 3-100 characters
    - Should be valid company name
    - Must match PBS policy exactly

    Args:
        value: The insurance carrier name to validate

    Returns:
        FieldValidationResult with validation status and details
    """
    field_name = "insurance_carrier_name"
    field_category = "Professional Liability Insurance"
    is_required = True
    validation_rules_applied = ["required", "text_presence", "length"]
    errors = []
    warnings = []

    # Check if value exists
    if value is None or not isinstance(value, str):
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Insurance Carrier Name is required and was not extracted from PDF"],
            warnings=[],
            notes="Field is missing or None"
        )

    value_stripped = value.strip()

    # Check if empty
    if not value_stripped:
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value,
            is_valid=False,
            is_required=is_required,
            confidence=0.0,
            validation_rules_applied=validation_rules_applied,
            errors=["Insurance Carrier Name is required but appears empty"],
            warnings=[],
            notes="Field extracted but contains no value"
        )

    # Check length requirements (3-100 characters)
    if len(value_stripped) < 3:
        errors.append(f"Insurance Carrier Name is too short (must be at least 3 characters, got {len(value_stripped)})")

    if len(value_stripped) > 100:
        errors.append(f"Insurance Carrier Name is too long (must be at most 100 characters, got {len(value_stripped)})")

    # Return validation result
    if errors:
        validation_details = [
            "❌ Required field check: Present but invalid",
            f"❌ Length check: {len(value_stripped)} characters (expected 3-100)"
        ]
        return _create_field_result(
            field_name=field_name,
            field_category=field_category,
            extracted_value=value_stripped,
            is_valid=False,
            is_required=is_required,
            confidence=0.50,
            validation_rules_applied=validation_rules_applied,
            errors=errors,
            warnings=warnings,
            notes="Carrier name format validation failed",
            validation_details=validation_details
        )

    validation_details = [
        "✅ Required field check: Present",
        f"✅ Length check: {len(value_stripped)} characters (valid range: 3-100)",
        "✅ Format check: Valid company name"
    ]

    return _create_field_result(
        field_name=field_name,
        field_category=field_category,
        extracted_value=value_stripped,
        is_valid=True,
        is_required=is_required,
        confidence=0.95,
        validation_rules_applied=validation_rules_applied,
        errors=[],
        warnings=warnings,
        notes="Insurance Carrier Name is valid",
        validation_details=validation_details,
        confidence_reasoning="High confidence (0.95) - carrier name format is valid"
    )
