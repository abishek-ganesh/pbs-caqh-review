"""
Comprehensive Error Reporting Module

Provides enhanced error reporting with:
- Actionable error messages showing CORRECT values
- Dynamic rejection email templates
- All-at-once comprehensive validation feedback
- JSON export for automation

This module enhances validation_engine.py's basic reporting with
stakeholder-friendly, actionable feedback.
"""

from typing import Dict, List, Optional
from datetime import datetime
import json

from ..models.validation_result import FieldValidationResult, DocumentValidationResult
from ..config.constants import ValidationStatus, ConfidenceLevel


class ComprehensiveReporter:
    """
    Enhanced reporter for CAQH validation results.

    Generates actionable feedback including:
    - What's wrong (error)
    - Why it's wrong (validation rule)
    - What it should be (correct value from Cheat Sheet)
    - How to fix it (actionable guidance)
    """

    def __init__(self):
        """Initialize the comprehensive reporter."""
        # Maps field names to their expected values/patterns from CAQH Cheat Sheet
        # These would ideally come from validation_rules.yaml
        self.field_guidance = self._build_field_guidance()

    def _build_field_guidance(self) -> Dict[str, Dict[str, str]]:
        """
        Build field-specific guidance for actionable error messages.

        Returns:
            Dictionary mapping field names to guidance information
        """
        return {
            "practice_location_name": {
                "correct_pattern": "Positive Behavior Supports Corporation [- Region]",
                "common_error": "Must match exactly as shown in CAQH system",
                "fix_instruction": "Copy the practice name exactly from your CAQH profile, including any regional suffix"
            },
            "ssn": {
                "correct_pattern": "XXX-XX-XXXX",
                "common_error": "Format must be 9 digits with hyphens",
                "fix_instruction": "Enter SSN in format XXX-XX-XXXX (e.g., 123-45-6789)"
            },
            "individual_npi": {
                "correct_pattern": "10-digit number",
                "common_error": "Must be exactly 10 digits and pass Luhn checksum",
                "fix_instruction": "Verify your NPI at https://npiregistry.cms.hhs.gov"
            },
            "professional_license_expiration_date": {
                "correct_pattern": "MM/DD/YYYY (must be future date)",
                "common_error": "Must be a future date, warn if expires within 30 days",
                "fix_instruction": "Update license if expired or expiring soon"
            },
            "medicaid_id": {
                "correct_pattern": "8-12 digit number (varies by state)",
                "common_error": "Must match Medicaid provider number in CAQH system",
                "fix_instruction": "Copy Medicaid Number exactly from your CAQH profile"
            },
            "practice_location_phone": {
                "correct_pattern": "XXX-XXX-XXXX or (XXX) XXX-XXXX",
                "common_error": "Must be valid 10-digit US phone number",
                "fix_instruction": "Enter phone in format XXX-XXX-XXXX"
            },
            "practice_location_email": {
                "correct_pattern": "valid@email.com",
                "common_error": "Must be valid email format",
                "fix_instruction": "Use a professional email address"
            },
            "practice_location_state": {
                "correct_pattern": "2-letter state code (e.g., CA, TX, FL)",
                "common_error": "Must be valid US state abbreviation",
                "fix_instruction": "Use 2-letter state code (e.g., CA for California)"
            },
            "practice_location_zip": {
                "correct_pattern": "XXXXX or XXXXX-XXXX",
                "common_error": "Must be 5-digit or 9-digit ZIP code",
                "fix_instruction": "Enter ZIP in format XXXXX or XXXXX-XXXX"
            },
            "date_of_birth": {
                "correct_pattern": "MM/DD/YYYY (must be past date, age 18-100)",
                "common_error": "Must be valid past date with reasonable age",
                "fix_instruction": "Verify DOB matches your legal documents"
            }
        }

    def generate_actionable_error_message(
        self,
        field_result: FieldValidationResult,
        show_correct_value: bool = True
    ) -> str:
        """
        Generate actionable error message for a failed field.

        Format:
        - What's wrong: [field_name] is [error description]
        - Found: [extracted_value]
        - Expected: [correct pattern]
        - How to fix: [actionable instruction]

        Args:
            field_result: Field validation result
            show_correct_value: Whether to include correct value guidance

        Returns:
            Actionable error message string
        """
        if field_result.is_valid:
            return f"✓ {field_result.field_name}: Valid"

        lines = []

        # What's wrong
        lines.append(f"✗ {field_result.field_name}:")

        # Specific errors
        if field_result.errors:
            for error in field_result.errors:
                lines.append(f"    Error: {error}")

        # Found value (don't show PHI)
        if field_result.extracted_value and not self._is_phi_field(field_result.field_name):
            value_display = field_result.extracted_value
            if len(value_display) > 100:
                value_display = value_display[:97] + "..."
            lines.append(f"    Found: \"{value_display}\"")

        # Show correct pattern/value
        if show_correct_value and field_result.field_name in self.field_guidance:
            guidance = self.field_guidance[field_result.field_name]
            lines.append(f"    Expected: {guidance['correct_pattern']}")
            lines.append(f"    Fix: {guidance['fix_instruction']}")

        return "\n".join(lines)

    def generate_comprehensive_error_report(
        self,
        validation_result: DocumentValidationResult,
        include_warnings: bool = True,
        include_passed_fields: bool = False
    ) -> str:
        """
        Generate comprehensive all-at-once error report.

        Shows ALL errors, warnings, and issues in one report
        (not incremental feedback).

        Args:
            validation_result: Document validation result
            include_warnings: Include fields with warnings
            include_passed_fields: Include fields that passed

        Returns:
            Comprehensive error report as string
        """
        lines = []

        # Header with visual separator
        lines.append("=" * 80)
        lines.append("COMPREHENSIVE VALIDATION REPORT")
        lines.append("All Errors & Issues (Fix All Before Resubmission)")
        lines.append("=" * 80)
        lines.append(f"Document: {validation_result.file_name}")
        lines.append(f"Status: {validation_result.overall_status.value}")
        lines.append(f"Processed: {validation_result.processed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Executive Summary
        lines.append("─" * 80)
        lines.append("SUMMARY")
        lines.append("─" * 80)
        total = validation_result.total_fields_checked
        passed = validation_result.fields_passed
        failed = validation_result.fields_failed
        warnings = validation_result.fields_warning

        lines.append(f"  ✓ Passed:   {passed}/{total} fields")
        lines.append(f"  ✗ Failed:   {failed}/{total} fields")
        lines.append(f"  ⚠ Warnings: {warnings}/{total} fields")

        if failed == 0 and warnings == 0:
            lines.append("\n  🎉 All validations passed! Document is ready for review.")
        elif failed > 0:
            lines.append(f"\n  ❌ {failed} field(s) must be corrected before resubmission.")

        lines.append("")

        # Critical Failures (if any)
        critical_failures = [
            r for r in validation_result.field_results
            if not r.is_valid and r.is_required
        ]

        if critical_failures:
            lines.append("─" * 80)
            lines.append("CRITICAL ERRORS (Must Fix)")
            lines.append("─" * 80)
            for field_result in critical_failures:
                lines.append(self.generate_actionable_error_message(field_result))
                lines.append("")

        # Group remaining failures by category
        failures_by_category = self._group_failures_by_category(
            validation_result.field_results,
            include_warnings=include_warnings,
            exclude_critical=True  # Already shown above
        )

        for category, fields in failures_by_category.items():
            if fields:
                lines.append("─" * 80)
                lines.append(f"{category.upper()} ISSUES")
                lines.append("─" * 80)
                for field_result in fields:
                    lines.append(self.generate_actionable_error_message(field_result))
                    lines.append("")

        # Low confidence warnings
        if validation_result.low_confidence_fields:
            lines.append("─" * 80)
            lines.append("LOW CONFIDENCE FIELDS (Verify Manually)")
            lines.append("─" * 80)
            for field_name in validation_result.low_confidence_fields:
                field_result = next(
                    (r for r in validation_result.field_results if r.field_name == field_name),
                    None
                )
                if field_result:
                    lines.append(f"  ⚠ {field_name}:")
                    lines.append(f"      Confidence: {field_result.confidence:.2f} (LOW)")
                    lines.append(f"      Please manually verify this field in your CAQH profile")
                    lines.append("")

        # Passed fields (optional)
        if include_passed_fields:
            passed_fields = [r for r in validation_result.field_results if r.is_valid]
            if passed_fields:
                lines.append("─" * 80)
                lines.append("PASSED VALIDATIONS")
                lines.append("─" * 80)
                for field_result in passed_fields:
                    lines.append(f"  ✓ {field_result.field_name}")
                lines.append("")

        # Next Steps
        lines.append("─" * 80)
        lines.append("NEXT STEPS")
        lines.append("─" * 80)

        if validation_result.overall_status == ValidationStatus.AI_REJECTED:
            lines.append("  1. Fix ALL errors listed above in your CAQH profile")
            lines.append("  2. Generate a new Data Summary PDF from CAQH")
            lines.append("  3. Submit the updated PDF")
            lines.append("  4. Do NOT submit until all errors are corrected")
        elif validation_result.overall_status == ValidationStatus.NEEDS_HUMAN_REVIEW:
            lines.append("  1. A credentialing specialist will review your submission manually")
            lines.append("  2. You may be contacted if additional information is needed")
            lines.append("  3. No action required at this time")
        else:  # AI_REVIEWED_LOOKS_GOOD
            lines.append("  1. Your submission looks good!")
            lines.append("  2. A credentialing specialist will perform final approval")
            lines.append("  3. No action required at this time")

        lines.append("")
        lines.append("=" * 80)
        lines.append("END OF REPORT")
        lines.append("=" * 80)

        return "\n".join(lines)

    def generate_rejection_email_template(
        self,
        validation_result: DocumentValidationResult,
        user_name: Optional[str] = None
    ) -> str:
        """
        Generate dynamic rejection email template.

        Shows CORRECT values from Cheat Sheet and specific, actionable guidance.

        Args:
            validation_result: Document validation result
            user_name: User's name for personalization

        Returns:
            Email template as string
        """
        # Get failed fields
        failed_fields = [
            r for r in validation_result.field_results
            if not r.is_valid
        ]

        # Email subject
        subject = f"CAQH Data Summary Rejected - {len(failed_fields)} Error(s) Found"

        # Email body
        body_lines = []

        # Greeting
        greeting = f"Dear {user_name}," if user_name else "Dear Provider,"
        body_lines.append(greeting)
        body_lines.append("")

        # Introduction
        body_lines.append(
            "Thank you for submitting your CAQH Data Summary. Unfortunately, we've identified "
            f"{len(failed_fields)} error(s) that must be corrected before we can process your application."
        )
        body_lines.append("")

        # List errors with actionable guidance
        body_lines.append("ERRORS FOUND:")
        body_lines.append("")

        for i, field_result in enumerate(failed_fields, 1):
            body_lines.append(f"{i}. {field_result.field_name.replace('_', ' ').title()}:")

            if field_result.errors:
                for error in field_result.errors:
                    body_lines.append(f"   Problem: {error}")

            # Add guidance if available
            if field_result.field_name in self.field_guidance:
                guidance = self.field_guidance[field_result.field_name]
                body_lines.append(f"   Correct Format: {guidance['correct_pattern']}")
                body_lines.append(f"   How to Fix: {guidance['fix_instruction']}")

            body_lines.append("")

        # Next steps
        body_lines.append("NEXT STEPS:")
        body_lines.append("")
        body_lines.append("1. Log into your CAQH profile at https://proview.caqh.org")
        body_lines.append("2. Correct ALL errors listed above")
        body_lines.append("3. Generate a new Data Summary PDF")
        body_lines.append("4. Submit the corrected PDF")
        body_lines.append("")
        body_lines.append("Please do NOT resubmit until all errors have been corrected in CAQH.")
        body_lines.append("")

        # Closing
        body_lines.append("If you have questions or need assistance, please contact the credentialing team.")
        body_lines.append("")
        body_lines.append("Thank you,")
        body_lines.append("PBS Credentialing Team")

        # Combine subject and body
        email_template = f"Subject: {subject}\n\n" + "\n".join(body_lines)

        return email_template

    def export_to_json(
        self,
        validation_result: DocumentValidationResult
    ) -> str:
        """
        Export validation result to JSON for automation/integration.

        Args:
            validation_result: Document validation result

        Returns:
            JSON string
        """
        # Convert to dict
        result_dict = validation_result.dict()

        # Add summary
        result_dict["summary"] = {
            "total_errors": validation_result.fields_failed,
            "total_warnings": validation_result.fields_warning,
            "critical_failures": len([
                r for r in validation_result.field_results
                if not r.is_valid and r.is_required
            ]),
            "requires_resubmission": validation_result.overall_status == ValidationStatus.AI_REJECTED,
            "ready_for_approval": validation_result.overall_status == ValidationStatus.AI_REVIEWED_LOOKS_GOOD
        }

        # Convert to JSON
        return json.dumps(result_dict, indent=2, default=str)

    def _group_failures_by_category(
        self,
        field_results: List[FieldValidationResult],
        include_warnings: bool = True,
        exclude_critical: bool = False
    ) -> Dict[str, List[FieldValidationResult]]:
        """
        Group field failures by category.

        Args:
            field_results: List of field validation results
            include_warnings: Include fields with warnings
            exclude_critical: Exclude required fields (already shown)

        Returns:
            Dictionary mapping categories to field results
        """
        categories: Dict[str, List[FieldValidationResult]] = {}

        for field_result in field_results:
            # Skip if valid and no warnings
            if field_result.is_valid and not (include_warnings and field_result.warnings):
                continue

            # Skip critical if requested
            if exclude_critical and field_result.is_required and not field_result.is_valid:
                continue

            category = field_result.field_category
            if category not in categories:
                categories[category] = []
            categories[category].append(field_result)

        return categories

    def _is_phi_field(self, field_name: str) -> bool:
        """
        Check if field contains PHI (Protected Health Information).

        Args:
            field_name: Name of the field

        Returns:
            True if field is PHI, False otherwise
        """
        phi_fields = {"ssn", "date_of_birth", "social_security_number"}
        return field_name.lower() in phi_fields


# Singleton instance for global access
_comprehensive_reporter_instance = None


def get_comprehensive_reporter() -> ComprehensiveReporter:
    """
    Get singleton instance of ComprehensiveReporter.

    Returns:
        ComprehensiveReporter instance
    """
    global _comprehensive_reporter_instance
    if _comprehensive_reporter_instance is None:
        _comprehensive_reporter_instance = ComprehensiveReporter()
    return _comprehensive_reporter_instance
