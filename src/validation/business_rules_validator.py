"""
Business Rules Validator for CAQH Data Summary Review

This module applies PBS-specific business rules to extracted fields
to determine if a document should be approved, rejected, or needs human review.

Business rules are derived from:
- docs/BUSINESS_RULES.md
- docs/CAQH_Cheat_Sheet.md
- Ground truth rejection reasons from Christian's testing

Usage:
    from src.validation.business_rules_validator import BusinessRulesValidator

    validator = BusinessRulesValidator()
    result = validator.validate(extracted_fields)

    print(result.status)  # AI_APPROVED, AI_REJECTED, NEEDS_HUMAN_REVIEW
    print(result.issues)  # List of validation issues found
"""

import re
import logging
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Possible validation statuses."""
    AI_APPROVED = "AI_APPROVED"
    AI_REJECTED = "AI_REJECTED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class IssueSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"      # Must be fixed - causes rejection
    WARNING = "warning"  # Should review - causes human review
    INFO = "info"        # FYI - doesn't affect status


@dataclass
class ValidationIssue:
    """A single validation issue found during review."""
    field_name: str
    message: str
    severity: IssueSeverity
    rule_name: str
    extracted_value: Optional[str] = None
    expected_value: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "message": self.message,
            "severity": self.severity.value,
            "rule_name": self.rule_name,
            "extracted_value": self.extracted_value,
            "expected_value": self.expected_value
        }


@dataclass
class ValidationResult:
    """Result of business rules validation."""
    status: ValidationStatus
    issues: List[ValidationIssue] = field(default_factory=list)
    confidence_score: float = 0.0
    summary: str = ""

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "confidence_score": self.confidence_score,
            "summary": self.summary,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [i.to_dict() for i in self.issues]
        }


class BusinessRulesValidator:
    """
    Validates extracted CAQH fields against PBS business rules.

    Rules are organized by category:
    1. Required Field Presence - Critical fields must be present
    2. Format Validation - SSN, NPI, dates must be valid formats
    3. Date Expiration - Licenses/certs must not be expired
    4. PBS-Specific - Practice location must be PBS, etc.
    5. Cross-Field - Employment address should match Practice Location
    """

    # PBS Practice Location variations that are acceptable
    # Flexible matching: handles OCR artifacts, spacing issues, plural variations
    PBS_NAME_PATTERNS = [
        r"Positive\s*Behavior\s*Supports?\s*Corporations?",  # Handles spacing/plural
        r"PBS\s*Corp(?:oration)?",
    ]

    # Valid PBS regions (for reference, not strict validation)
    PBS_REGIONS = [
        "West Coast", "East Coast", "Central Florida", "Southern California",
        "Emerald Coast", "Treasure Coast", "South Florida", "North Florida",
        "Middle Tennessee", "Tennessee", "Ohio", "Texas", "Arizona", "Colorado",
        "Broward", "North Carolina"
    ]

    # Fields that MUST be present (error if missing)
    REQUIRED_FIELDS = [
        "first_name", "last_name", "date_of_birth", "gender",
        "ssn", "individual_npi", "caqh_number",
        "professional_license_number", "professional_license_expiration_date",
        "practice_location_name", "practice_location_address",
        "practice_location_city", "practice_location_state", "practice_location_zip",
        "insurance_carrier_name", "insurance_policy_number",
        "insurance_current_effective_date", "insurance_current_expiration_date",
        "insurance_each_occurrence", "insurance_general_aggregate",  # Added Feb 13, 2026
        "insurance_individual_coverage", "insurance_self_insured",    # Added Feb 13, 2026
        "primary_specialty",
        "credentialing_contact_first_name", "credentialing_contact_last_name",
        "credentialing_contact_email",
        "billing_contact_first_name",  # Added Feb 17, 2026 - per Christian's feedback
    ]

    # Fields that SHOULD be present (warning if missing)
    RECOMMENDED_FIELDS = [
        "practice_location_phone",
        "insurance_address_street_1", "insurance_address_city",
        "insurance_address_state", "insurance_address_zip",
        "board_certified", "certifying_board_name",
        "billing_contact_last_name", "billing_contact_phone",
        "billing_contact_email",
    ]

    # Date fields that should not be expired
    EXPIRATION_DATE_FIELDS = [
        "professional_license_expiration_date",
        "insurance_current_expiration_date",
        "certification_expiration_date"
    ]

    def __init__(self, reference_date: Optional[date] = None):
        """
        Initialize the business rules validator.

        Args:
            reference_date: Optional date to use instead of today for expiration checks.
                           Useful for testing with ground truth data that has old dates.
        """
        self.today = reference_date or date.today()

    def validate(self, fields: Dict[str, Any]) -> ValidationResult:
        """
        Validate extracted fields against all business rules.

        Args:
            fields: Dictionary of field_name -> extracted value
                   Can be flat dict or nested with "extracted_value" keys

        Returns:
            ValidationResult with status and list of issues
        """
        # Normalize fields to flat dict of values
        flat_fields = self._normalize_fields(fields)

        issues: List[ValidationIssue] = []

        # Run all validation rules
        issues.extend(self._validate_required_fields(flat_fields))
        issues.extend(self._validate_recommended_fields(flat_fields))
        issues.extend(self._validate_ssn_format(flat_fields))
        issues.extend(self._validate_npi_format(flat_fields))
        issues.extend(self._validate_date_formats(flat_fields))
        issues.extend(self._validate_expiration_dates(flat_fields))
        issues.extend(self._validate_pbs_practice_location(flat_fields))
        issues.extend(self._validate_cultural_competency(flat_fields))
        issues.extend(self._validate_insurance_fields(flat_fields))
        issues.extend(self._validate_cross_field_rules(flat_fields))

        # Determine status based on issues
        status = self._determine_status(issues)

        # Calculate confidence score
        confidence = self._calculate_confidence(issues, flat_fields)

        # Generate summary
        summary = self._generate_summary(status, issues)

        return ValidationResult(
            status=status,
            issues=issues,
            confidence_score=confidence,
            summary=summary
        )

    def _normalize_fields(self, fields: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """Normalize fields to flat dict of string values."""
        flat = {}
        for key, value in fields.items():
            if isinstance(value, dict):
                # Handle nested format: {"extracted_value": "...", "confidence": ...}
                flat[key] = value.get("extracted_value") or value.get("value")
            else:
                flat[key] = value

            # Normalize empty strings and special markers to None
            if flat[key] in [None, "", "[BLANK]", "[NOT EXTRACTED]"]:
                flat[key] = None

        return flat

    def _validate_required_fields(self, fields: Dict) -> List[ValidationIssue]:
        """Check that all required fields are present."""
        issues = []
        for field_name in self.REQUIRED_FIELDS:
            value = fields.get(field_name)
            if not value:
                issues.append(ValidationIssue(
                    field_name=field_name,
                    message=f"Required field '{field_name}' is missing or empty",
                    severity=IssueSeverity.ERROR,
                    rule_name="required_field_presence",
                    extracted_value=None,
                    expected_value="(non-empty value)"
                ))
        return issues

    def _validate_recommended_fields(self, fields: Dict) -> List[ValidationIssue]:
        """Check that recommended fields are present."""
        issues = []

        # Determine if professional school fields are applicable
        # Professional school is only relevant for BCBAs (board certified analysts)
        # Non-BCBA providers (RBTs, etc.) don't need education section filled
        is_bcba = self._is_bcba_provider(fields)

        # Build conditional recommended fields
        conditional_fields = list(self.RECOMMENDED_FIELDS)
        if is_bcba:
            conditional_fields.extend(["professional_school_name", "graduation_date"])

        for field_name in conditional_fields:
            value = fields.get(field_name)
            if not value:
                issues.append(ValidationIssue(
                    field_name=field_name,
                    message=f"Recommended field '{field_name}' is missing",
                    severity=IssueSeverity.INFO,
                    rule_name="recommended_field_presence",
                    extracted_value=None,
                    expected_value="(non-empty value)"
                ))
        return issues

    def _is_bcba_provider(self, fields: Dict) -> bool:
        """Determine if the provider is a BCBA based on extracted fields.

        BCBAs have specialty "Behavior Analyst" (103K00000X).
        RBTs have specialty "Behavior Technician" (106S00000X) - NOT BCBAs.
        BCaBAs have a different certification level.

        Only BCBAs require professional school (graduate school) info.
        RBTs, BCaBAs, and other non-BCBA providers do NOT need it.

        Note: Both BCBAs and RBTs are certified through BACB (Behavior Analyst
        Certification Board), so board_certified=Yes + BACB board does NOT
        necessarily mean BCBA. We must check the specialty type.
        """
        specialty = fields.get("primary_specialty", "") or ""
        specialty_lower = specialty.lower()

        # Explicitly exclude non-BCBA provider types
        non_bcba_indicators = [
            "technician",    # RBT = "Behavior Technician"
            "106s00000x",    # RBT taxonomy code
            "rbt",           # Registered Behavior Technician
            "bcaba",         # Board Certified Assistant Behavior Analyst
        ]
        for indicator in non_bcba_indicators:
            if indicator in specialty_lower:
                return False

        # Check for BCBA indicators
        bcba_indicators = [
            "behavior analyst",    # "Behavior Analyst (103K00000X)"
            "behavioral analyst",  # "Applied Behavioral Analyst" (CAQH ProviderType)
            "103k00000x",          # BCBA taxonomy code
            "bcba",                # Direct BCBA mention
        ]
        for indicator in bcba_indicators:
            if indicator in specialty_lower:
                return True

        return False

    def _validate_ssn_format(self, fields: Dict) -> List[ValidationIssue]:
        """Validate SSN format: XXX-XX-XXXX."""
        issues = []
        ssn = fields.get("ssn")
        if ssn:
            pattern = r"^\d{3}-\d{2}-\d{4}$"
            if not re.match(pattern, ssn):
                issues.append(ValidationIssue(
                    field_name="ssn",
                    message=f"SSN format invalid: '{ssn}'. Expected format: XXX-XX-XXXX",
                    severity=IssueSeverity.ERROR,
                    rule_name="ssn_format",
                    extracted_value=ssn,
                    expected_value="XXX-XX-XXXX"
                ))
        return issues

    def _validate_npi_format(self, fields: Dict) -> List[ValidationIssue]:
        """Validate NPI format: 10 digits with valid Luhn checksum."""
        issues = []
        npi = fields.get("individual_npi")
        if npi:
            # Check basic format (10 digits)
            if not re.match(r"^\d{10}$", npi):
                issues.append(ValidationIssue(
                    field_name="individual_npi",
                    message=f"NPI must be exactly 10 digits: '{npi}'",
                    severity=IssueSeverity.ERROR,
                    rule_name="npi_format",
                    extracted_value=npi,
                    expected_value="10 digits"
                ))
            else:
                # Validate Luhn checksum
                if not self._validate_npi_luhn(npi):
                    issues.append(ValidationIssue(
                        field_name="individual_npi",
                        message=f"NPI checksum invalid: '{npi}'",
                        severity=IssueSeverity.WARNING,
                        rule_name="npi_checksum",
                        extracted_value=npi,
                        expected_value="Valid NPI checksum"
                    ))
        return issues

    def _validate_npi_luhn(self, npi: str) -> bool:
        """Validate NPI using Luhn algorithm with healthcare prefix."""
        try:
            # Prepend 80840 for healthcare NPI validation
            full_number = "80840" + npi
            digits = [int(d) for d in full_number]

            # Luhn algorithm
            for i in range(len(digits) - 2, -1, -2):
                digits[i] *= 2
                if digits[i] > 9:
                    digits[i] -= 9

            return sum(digits) % 10 == 0
        except (ValueError, TypeError):
            return False

    def _validate_date_formats(self, fields: Dict) -> List[ValidationIssue]:
        """Validate that date fields are parseable."""
        issues = []
        date_fields = [
            "date_of_birth", "professional_license_expiration_date",
            "insurance_current_effective_date", "insurance_current_expiration_date",
            "certification_expiration_date", "initial_certification_date",
            "graduation_date", "undergraduate_graduation_date"
        ]

        for field_name in date_fields:
            value = fields.get(field_name)
            if value:
                parsed = self._parse_date(value)
                if parsed is None:
                    issues.append(ValidationIssue(
                        field_name=field_name,
                        message=f"Cannot parse date: '{value}'",
                        severity=IssueSeverity.WARNING,
                        rule_name="date_format",
                        extracted_value=value,
                        expected_value="MM/DD/YYYY or M/D/YYYY"
                    ))
        return issues

    def _validate_expiration_dates(self, fields: Dict) -> List[ValidationIssue]:
        """Check that expiration dates are not in the past."""
        issues = []

        for field_name in self.EXPIRATION_DATE_FIELDS:
            value = fields.get(field_name)
            if value:
                parsed = self._parse_date(value)
                if parsed and parsed < self.today:
                    issues.append(ValidationIssue(
                        field_name=field_name,
                        message=f"Expired: '{value}' is in the past",
                        severity=IssueSeverity.ERROR,
                        rule_name="expiration_date_check",
                        extracted_value=value,
                        expected_value=f"Date after {self.today.strftime('%m/%d/%Y')}"
                    ))
        return issues

    def _validate_pbs_practice_location(self, fields: Dict) -> List[ValidationIssue]:
        """Validate practice location contains PBS.

        Handles variations from PDF extraction including:
        - Concatenated text (no spaces): "PositiveBehaviorSupports Corporation"
        - Plural variations: "Corporations" vs "Corporation"
        - Region suffixes: "- Middle Tennessee", "-Broward", etc.
        - "Location" prefix from extraction artifacts
        """
        issues = []
        location_name = fields.get("practice_location_name")

        if location_name:
            # Strip common extraction artifacts
            clean_name = location_name
            if clean_name.lower().startswith("location "):
                clean_name = clean_name[9:]  # Remove "Location " prefix

            # Check if any PBS pattern matches (with flexible spacing)
            is_pbs = any(
                re.search(pattern, clean_name, re.IGNORECASE)
                for pattern in self.PBS_NAME_PATTERNS
            )

            if not is_pbs:
                issues.append(ValidationIssue(
                    field_name="practice_location_name",
                    message=f"Practice location must include 'Positive Behavior Supports Corporation'. Found: '{location_name}'",
                    severity=IssueSeverity.ERROR,
                    rule_name="pbs_practice_location",
                    extracted_value=location_name,
                    expected_value="Positive Behavior Supports Corporation - [Region]"
                ))

        return issues

    def _validate_cultural_competency(self, fields: Dict) -> List[ValidationIssue]:
        """Validate cultural competency training is marked Yes."""
        issues = []
        value = fields.get("cultural_competency_training")

        if value:
            if value.lower() not in ["yes", "y", "true", "1"]:
                issues.append(ValidationIssue(
                    field_name="cultural_competency_training",
                    message=f"Cultural competency training should be 'Yes'. Found: '{value}'",
                    severity=IssueSeverity.ERROR,
                    rule_name="cultural_competency_required",
                    extracted_value=value,
                    expected_value="Yes"
                ))
        else:
            # If not extracted, it's a warning (might be missing from profile)
            issues.append(ValidationIssue(
                field_name="cultural_competency_training",
                message="Cultural competency training field not found",
                severity=IssueSeverity.WARNING,
                rule_name="cultural_competency_presence",
                extracted_value=None,
                expected_value="Yes"
            ))

        return issues

    def _validate_insurance_fields(self, fields: Dict) -> List[ValidationIssue]:
        """Validate insurance-related fields."""
        issues = []

        # Check insurance carrier is present and reasonable
        carrier = fields.get("insurance_carrier_name")
        if carrier:
            # Lexington Insurance Company is the expected carrier for PBS
            if "Lexington" not in carrier and "Insurance" not in carrier:
                issues.append(ValidationIssue(
                    field_name="insurance_carrier_name",
                    message=f"Verify insurance carrier: '{carrier}'",
                    severity=IssueSeverity.INFO,
                    rule_name="insurance_carrier_check",
                    extracted_value=carrier,
                    expected_value="Lexington Insurance Company (typical)"
                ))

        # Check insurance address is populated
        ins_address = fields.get("insurance_address_street_1")
        ins_city = fields.get("insurance_address_city")
        ins_state = fields.get("insurance_address_state")

        if not all([ins_address, ins_city, ins_state]):
            missing = []
            if not ins_address:
                missing.append("street")
            if not ins_city:
                missing.append("city")
            if not ins_state:
                missing.append("state")

            issues.append(ValidationIssue(
                field_name="insurance_address",
                message=f"Insurance address incomplete. Missing: {', '.join(missing)}",
                severity=IssueSeverity.WARNING,
                rule_name="insurance_address_complete",
                extracted_value=f"{ins_address}, {ins_city}, {ins_state}",
                expected_value="Complete address (street, city, state)"
            ))

        return issues

    def _validate_cross_field_rules(self, fields: Dict) -> List[ValidationIssue]:
        """Validate rules that involve multiple fields."""
        issues = []

        # Note: Employment address vs Practice Location validation
        # This is mentioned in PParent rejection but we don't extract employment section
        # This would require extracting employment_address fields to implement

        # Check that credentialing contact is PBS staff
        cred_email = fields.get("credentialing_contact_email")
        if cred_email and "@teampbs.com" not in cred_email.lower():
            issues.append(ValidationIssue(
                field_name="credentialing_contact_email",
                message=f"Credentialing contact should be PBS staff. Found: '{cred_email}'",
                severity=IssueSeverity.WARNING,
                rule_name="credentialing_contact_pbs",
                extracted_value=cred_email,
                expected_value="@teampbs.com email"
            ))

        # Check board certification consistency (conditional required fields)
        # Per CAQH Cheat Sheet: If board_certified=Yes, then board name, initial cert date,
        # and expiration date are all REQUIRED
        board_certified = fields.get("board_certified")
        certifying_board = fields.get("certifying_board_name")
        initial_cert = fields.get("initial_certification_date")
        cert_expiration = fields.get("certification_expiration_date")

        if board_certified and board_certified.lower() in ["yes", "y", "true"]:
            if not certifying_board:
                issues.append(ValidationIssue(
                    field_name="certifying_board_name",
                    message="Board Certified = Yes but Certifying Board Name is missing (required)",
                    severity=IssueSeverity.ERROR,  # Changed from WARNING to ERROR
                    rule_name="board_cert_conditional_required",
                    extracted_value=None,
                    expected_value="Behavior Analyst Certification Board"
                ))
            if not initial_cert:
                issues.append(ValidationIssue(
                    field_name="initial_certification_date",
                    message="Board Certified = Yes but Initial Certification Date is missing (required)",
                    severity=IssueSeverity.ERROR,  # Changed from WARNING to ERROR
                    rule_name="board_cert_conditional_required",
                    extracted_value=None,
                    expected_value="Valid date (MM/DD/YYYY)"
                ))
            if not cert_expiration:
                issues.append(ValidationIssue(
                    field_name="certification_expiration_date",
                    message="Board Certified = Yes but Certification Expiration Date is missing (required)",
                    severity=IssueSeverity.ERROR,  # Changed from WARNING to ERROR
                    rule_name="board_cert_conditional_required",
                    extracted_value=None,
                    expected_value="Valid future date"
                ))

        return issues

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse a date string in various formats."""
        if not date_str:
            return None

        # Common date formats
        formats = [
            "%m/%d/%Y",   # 01/31/2025
            "%m-%d-%Y",   # 01-31-2025
            "%Y-%m-%d",   # 2025-01-31
            "%-m/%-d/%Y", # 1/31/2025 (may not work on Windows)
            "%m/%d/%y",   # 01/31/25
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        # Try flexible parsing for formats like "1/31/2025"
        try:
            parts = re.split(r'[/\-]', date_str)
            if len(parts) == 3:
                month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                if year < 100:
                    year += 2000
                return date(year, month, day)
        except (ValueError, TypeError):
            pass

        return None

    def _determine_status(self, issues: List[ValidationIssue]) -> ValidationStatus:
        """Determine overall status based on issues found."""
        error_count = sum(1 for i in issues if i.severity == IssueSeverity.ERROR)
        warning_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)

        if error_count > 0:
            return ValidationStatus.AI_REJECTED
        elif warning_count > 2:  # More than 2 warnings = needs review
            return ValidationStatus.NEEDS_HUMAN_REVIEW
        else:
            return ValidationStatus.AI_APPROVED

    def _calculate_confidence(self, issues: List[ValidationIssue], fields: Dict) -> float:
        """Calculate confidence score based on issues and field coverage."""
        # Start with base confidence
        base_confidence = 100.0

        # Deduct for errors (10 points each)
        error_count = sum(1 for i in issues if i.severity == IssueSeverity.ERROR)
        base_confidence -= error_count * 10

        # Deduct for warnings (3 points each)
        warning_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)
        base_confidence -= warning_count * 3

        # Deduct for info items (0.5 points each)
        info_count = sum(1 for i in issues if i.severity == IssueSeverity.INFO)
        base_confidence -= info_count * 0.5

        # Calculate field coverage bonus
        filled_required = sum(1 for f in self.REQUIRED_FIELDS if fields.get(f))
        coverage_ratio = filled_required / len(self.REQUIRED_FIELDS)

        # Final score (minimum 0, maximum 100)
        final_score = max(0, min(100, base_confidence * coverage_ratio))

        return round(final_score, 1)

    def _generate_summary(self, status: ValidationStatus, issues: List[ValidationIssue]) -> str:
        """Generate a human-readable summary."""
        error_count = sum(1 for i in issues if i.severity == IssueSeverity.ERROR)
        warning_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)

        if status == ValidationStatus.AI_APPROVED:
            return "All business rules passed. Document ready for human approval."
        elif status == ValidationStatus.AI_REJECTED:
            error_fields = [i.field_name for i in issues if i.severity == IssueSeverity.ERROR][:5]
            return f"Rejected: {error_count} error(s) found. Issues with: {', '.join(error_fields)}"
        else:
            return f"Needs review: {warning_count} warning(s) found. Manual verification required."


# Convenience function for quick validation
def validate_extracted_fields(fields: Dict[str, Any]) -> ValidationResult:
    """
    Quick validation of extracted fields.

    Args:
        fields: Dictionary of extracted field values

    Returns:
        ValidationResult with status and issues
    """
    validator = BusinessRulesValidator()
    return validator.validate(fields)


if __name__ == "__main__":
    # Quick test
    test_fields = {
        "first_name": "Paige",
        "last_name": "Parent",
        "date_of_birth": "3/10/1999",
        "gender": "Female",
        "ssn": "380-23-5112",
        "individual_npi": "1194566232",
        "caqh_number": "16669412",
        "professional_license_number": "1-25-85064",
        "professional_license_expiration_date": "10/16/2027",
        "practice_location_name": "Positive Behavior Supports Corporation - West Coast",
        "practice_location_address": "6421 N Florida Ave",
        "practice_location_city": "Tampa",
        "practice_location_state": "FL",
        "practice_location_zip": "33604-6007",
        "insurance_carrier_name": "Lexington Insurance Company",
        "insurance_policy_number": "6799172",
        "insurance_current_effective_date": "01/31/2025",
        "insurance_current_expiration_date": "01/31/2026",
        "primary_specialty": "Behavior Analyst (103K00000X)",
        "credentialing_contact_first_name": "Christian",
        "credentialing_contact_last_name": "Helenius",
        "credentialing_contact_email": "chelenius@teampbs.com",
        "cultural_competency_training": "Yes",
    }

    result = validate_extracted_fields(test_fields)
    print(f"Status: {result.status.value}")
    print(f"Confidence: {result.confidence_score}")
    print(f"Summary: {result.summary}")
    print(f"\nIssues ({len(result.issues)}):")
    for issue in result.issues:
        print(f"  [{issue.severity.value}] {issue.field_name}: {issue.message}")
