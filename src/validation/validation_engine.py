"""
Validation Engine

Core orchestrator for CAQH PDF validation.
Coordinates field extraction, validation, confidence scoring,
and status determination.
"""

import time
from typing import Dict, Optional, List, Callable
from datetime import datetime

from ..models.validation_result import FieldValidationResult, DocumentValidationResult
from ..models.extraction_result import FieldExtractionResult, DocumentExtractionResult
from ..config.constants import ValidationStatus, ConfidenceLevel

from .rule_loader import RuleLoader, FieldRule, get_rule_loader
from .confidence_scorer import ConfidenceScorer, get_confidence_scorer
from .field_validators import (
    validate_medicaid_id,
    validate_ssn_field,
    validate_individual_npi,
    validate_practice_location_name,
    validate_license_expiration_date,
    CRITICAL_FIELD_VALIDATORS
)


class ValidationEngine:
    """
    Main validation engine for CAQH Data Summary PDFs.

    Orchestrates the complete validation workflow:
    1. Load validation rules
    2. Validate extracted fields
    3. Calculate confidence scores
    4. Determine document status
    5. Generate comprehensive reports
    """

    def __init__(
        self,
        rule_loader: Optional[RuleLoader] = None,
        confidence_scorer: Optional[ConfidenceScorer] = None
    ):
        """
        Initialize the ValidationEngine.

        Args:
            rule_loader: RuleLoader instance (uses singleton if None)
            confidence_scorer: ConfidenceScorer instance (uses singleton if None)
        """
        self.rule_loader = rule_loader or get_rule_loader()
        self.confidence_scorer = confidence_scorer or get_confidence_scorer()

        # Load rules on initialization
        self.rules = self.rule_loader.load_rules()

        # Build validator registry
        self.validator_registry = self._build_validator_registry()

    def _build_validator_registry(self) -> Dict[str, Callable]:
        """
        Build registry mapping field names to validator functions.

        Returns:
            Dictionary mapping field names to validator callables
        """
        # Start with critical field validators
        registry = CRITICAL_FIELD_VALIDATORS.copy()

        # TODO: Add more validators as they're implemented
        # registry["practice_address"] = validate_practice_address
        # registry["phone_number"] = validate_phone_number
        # etc.

        return registry

    def validate_field(
        self,
        field_name: str,
        extracted_value: Optional[str],
        extraction_result: Optional[FieldExtractionResult] = None
    ) -> FieldValidationResult:
        """
        Validate a single field.

        Args:
            field_name: Name of the field to validate
            extracted_value: The extracted value
            extraction_result: Full extraction result with metadata (optional)

        Returns:
            FieldValidationResult with validation outcome
        """
        # Get validation rule
        rule = self.rule_loader.get_rule(field_name)

        # Check if validator exists
        if field_name in self.validator_registry:
            # Use implemented validator
            validator_func = self.validator_registry[field_name]
            validation_result = validator_func(extracted_value)

            # Adjust confidence if extraction result provided
            if extraction_result:
                adjusted_confidence = self.confidence_scorer.calculate_final_confidence(
                    extraction_result=extraction_result,
                    validation_result=validation_result
                )
                # Update confidence in validation result
                validation_result.confidence = adjusted_confidence
                validation_result.confidence_level = self.confidence_scorer.get_confidence_level(
                    adjusted_confidence
                )

            return validation_result

        # No validator implemented yet - create placeholder result
        if rule:
            return FieldValidationResult(
                field_name=field_name,
                field_category=rule.field_category,
                extracted_value=extracted_value,
                expected_value=None,
                is_valid=True,  # Assume valid if no validator
                is_required=rule.required,
                confidence=0.50,  # Medium-low - not validated
                confidence_level=ConfidenceLevel.MEDIUM,
                validation_rules_applied=["not_yet_implemented"],
                errors=[],
                warnings=["Validation not yet implemented for this field"],
                notes=f"Validator for {field_name} not yet implemented"
            )
        else:
            # No rule found
            return FieldValidationResult(
                field_name=field_name,
                field_category="unknown",
                extracted_value=extracted_value,
                expected_value=None,
                is_valid=True,
                is_required=False,
                confidence=0.30,  # Low - unknown field
                confidence_level=ConfidenceLevel.LOW,
                validation_rules_applied=[],
                errors=[],
                warnings=["No validation rule found for this field"],
                notes=f"Field {field_name} not in validation rules"
            )

    def validate_document(
        self,
        extraction_result: DocumentExtractionResult,
        document_id: Optional[str] = None,
        user_name: Optional[str] = None
    ) -> DocumentValidationResult:
        """
        Validate an entire document with all-at-once validation.

        This is the main entry point for document validation.

        Args:
            extraction_result: Complete extraction result from PDF
            document_id: Optional document identifier
            user_name: Optional user name from extraction

        Returns:
            DocumentValidationResult with comprehensive validation outcome
        """
        start_time = time.time()

        # Generate document ID if not provided
        if document_id is None:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            document_id = f"DOC-{timestamp}"

        # Validate all extracted fields
        field_results: List[FieldValidationResult] = []

        for field_extraction in extraction_result.field_results:
            validation_result = self.validate_field(
                field_name=field_extraction.field_name,
                extracted_value=field_extraction.extracted_value,
                extraction_result=field_extraction
            )
            field_results.append(validation_result)

        # Calculate summary statistics
        total_fields = len(field_results)
        fields_passed = sum(1 for r in field_results if r.is_valid)
        fields_failed = sum(1 for r in field_results if not r.is_valid)
        fields_warning = sum(1 for r in field_results if r.warnings)

        # Identify required fields that are missing or failed
        required_fields_missing = [
            r.field_name
            for r in field_results
            if r.is_required and (not r.is_valid or r.extracted_value is None)
        ]

        # Identify low confidence fields
        low_confidence_fields = [
            r.field_name
            for r in field_results
            if r.confidence < self.confidence_scorer.MEDIUM_CONFIDENCE_THRESHOLD
        ]

        # Determine overall status and recommended action
        overall_status, recommended_action, rejection_reasons = self._determine_document_status(
            field_results=field_results,
            required_fields_missing=required_fields_missing,
            low_confidence_fields=low_confidence_fields,
            is_caqh_document=extraction_result.is_caqh_document
        )

        # Calculate processing time
        processing_time = time.time() - start_time

        # Build document validation result
        return DocumentValidationResult(
            document_id=document_id,
            file_name=extraction_result.pdf_filename,
            user_name=user_name,
            overall_status=overall_status,
            field_results=field_results,
            total_fields_checked=total_fields,
            fields_passed=fields_passed,
            fields_failed=fields_failed,
            fields_warning=fields_warning,
            required_fields_missing=required_fields_missing,
            low_confidence_fields=low_confidence_fields,
            rejection_reasons=rejection_reasons,
            recommended_action=recommended_action,
            processing_time_seconds=round(processing_time, 2),
            processed_at=datetime.now(),
            metadata={
                "extraction_method": extraction_result.extraction_method,
                "extraction_time": extraction_result.extraction_time,
                "is_caqh_document": extraction_result.is_caqh_document,
                "total_extraction_errors": len(extraction_result.errors),
                "total_extraction_warnings": len(extraction_result.warnings)
            }
        )

    def _determine_document_status(
        self,
        field_results: List[FieldValidationResult],
        required_fields_missing: List[str],
        low_confidence_fields: List[str],
        is_caqh_document: bool
    ) -> tuple[ValidationStatus, str, List[str]]:
        """
        Determine overall document status and recommended action.

        Business logic:
        1. If not a CAQH document → AI Rejected
        2. If any low confidence field → Needs Human Review
        3. If any required critical field missing/failed → AI Rejected
        4. If all critical fields pass with high confidence → AI Reviewed - Looks Good
        5. Otherwise → Needs Human Review

        Args:
            field_results: List of field validation results
            required_fields_missing: List of missing required fields
            low_confidence_fields: List of fields with low confidence
            is_caqh_document: Whether document is a valid CAQH PDF

        Returns:
            Tuple of (ValidationStatus, recommended_action, rejection_reasons)
        """
        rejection_reasons = []

        # Check 1: Not a CAQH document
        if not is_caqh_document:
            return (
                ValidationStatus.AI_REJECTED,
                "Document is not a valid CAQH Data Summary",
                ["Not a CAQH Data Summary document"]
            )

        # Check 2: Low confidence fields → Human Review
        if low_confidence_fields:
            return (
                ValidationStatus.NEEDS_HUMAN_REVIEW,
                f"Low confidence on {len(low_confidence_fields)} field(s) - requires human review",
                []
            )

        # Check 3: Required critical fields missing/failed → AI Rejected
        critical_fields = self.confidence_scorer._get_critical_fields()

        critical_failures = [
            r for r in field_results
            if r.field_name in critical_fields
            and (not r.is_valid or r.extracted_value is None)
        ]

        if critical_failures:
            for failure in critical_failures:
                if failure.errors:
                    rejection_reasons.extend(failure.errors)
                else:
                    rejection_reasons.append(
                        f"{failure.field_name}: Missing or invalid"
                    )

            return (
                ValidationStatus.AI_REJECTED,
                f"Critical field failures: {', '.join([f.field_name for f in critical_failures])}",
                rejection_reasons
            )

        # Check 4: All critical fields pass with high confidence → Looks Good
        critical_results = [
            r for r in field_results
            if r.field_name in critical_fields
        ]

        if critical_results:
            all_critical_high_confidence = all(
                r.confidence >= self.confidence_scorer.HIGH_CONFIDENCE_THRESHOLD
                for r in critical_results
            )

            if all_critical_high_confidence and all(r.is_valid for r in critical_results):
                return (
                    ValidationStatus.AI_REVIEWED_LOOKS_GOOD,
                    "All critical fields validated successfully - ready for human approval",
                    []
                )

        # Check 5: Has some failures but not critical → Needs Review
        if required_fields_missing or any(not r.is_valid for r in field_results):
            failed_fields = [r.field_name for r in field_results if not r.is_valid]
            return (
                ValidationStatus.NEEDS_HUMAN_REVIEW,
                f"Some fields failed validation: {', '.join(failed_fields[:5])}{'...' if len(failed_fields) > 5 else ''}",
                []
            )

        # Default: Looks Good
        return (
            ValidationStatus.AI_REVIEWED_LOOKS_GOOD,
            "All fields validated successfully - ready for human approval",
            []
        )

    def generate_validation_report(
        self,
        validation_result: DocumentValidationResult,
        include_passed_fields: bool = True,
        group_by_category: bool = True
    ) -> str:
        """
        Generate human-readable validation report.

        Args:
            validation_result: Document validation result
            include_passed_fields: Whether to include fields that passed
            group_by_category: Whether to group fields by category

        Returns:
            Formatted validation report as string
        """
        report_lines = []

        # Header
        report_lines.append("=" * 80)
        report_lines.append("CAQH DATA SUMMARY VALIDATION REPORT")
        report_lines.append("=" * 80)
        report_lines.append(f"Document: {validation_result.file_name}")
        report_lines.append(f"Document ID: {validation_result.document_id}")
        if validation_result.user_name:
            report_lines.append(f"User: {validation_result.user_name}")
        report_lines.append(f"Status: {validation_result.overall_status.value}")
        report_lines.append(f"Processed: {validation_result.processed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Processing Time: {validation_result.processing_time_seconds}s")
        report_lines.append("")

        # Summary
        report_lines.append("-" * 80)
        report_lines.append("SUMMARY")
        report_lines.append("-" * 80)
        report_lines.append(f"Total Fields Checked: {validation_result.total_fields_checked}")
        report_lines.append(f"Fields Passed: {validation_result.fields_passed}")
        report_lines.append(f"Fields Failed: {validation_result.fields_failed}")
        report_lines.append(f"Fields with Warnings: {validation_result.fields_warning}")
        report_lines.append(f"Recommended Action: {validation_result.recommended_action}")
        report_lines.append("")

        # Required fields missing
        if validation_result.required_fields_missing:
            report_lines.append("-" * 80)
            report_lines.append("REQUIRED FIELDS MISSING")
            report_lines.append("-" * 80)
            for field in validation_result.required_fields_missing:
                report_lines.append(f"  • {field}")
            report_lines.append("")

        # Low confidence fields
        if validation_result.low_confidence_fields:
            report_lines.append("-" * 80)
            report_lines.append("LOW CONFIDENCE FIELDS")
            report_lines.append("-" * 80)
            for field in validation_result.low_confidence_fields:
                report_lines.append(f"  • {field}")
            report_lines.append("")

        # Rejection reasons
        if validation_result.rejection_reasons:
            report_lines.append("-" * 80)
            report_lines.append("REJECTION REASONS")
            report_lines.append("-" * 80)
            for reason in validation_result.rejection_reasons:
                report_lines.append(f"  • {reason}")
            report_lines.append("")

        # Field details
        report_lines.append("-" * 80)
        report_lines.append("FIELD VALIDATION DETAILS")
        report_lines.append("-" * 80)

        if group_by_category:
            # Group by category
            categories: Dict[str, List[FieldValidationResult]] = {}
            for field_result in validation_result.field_results:
                category = field_result.field_category
                if category not in categories:
                    categories[category] = []
                categories[category].append(field_result)

            for category, fields in categories.items():
                report_lines.append(f"\n{category.upper()}")
                report_lines.append("-" * 40)
                for field in fields:
                    if not include_passed_fields and field.is_valid:
                        continue
                    report_lines.extend(self._format_field_result(field))

        else:
            # Linear list
            for field_result in validation_result.field_results:
                if not include_passed_fields and field_result.is_valid:
                    continue
                report_lines.extend(self._format_field_result(field_result))

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("END OF REPORT")
        report_lines.append("=" * 80)

        return "\n".join(report_lines)

    def _format_field_result(self, field: FieldValidationResult) -> List[str]:
        """
        Format a single field result for report.

        Args:
            field: Field validation result

        Returns:
            List of formatted lines
        """
        lines = []

        # Field name and status
        status_symbol = "✓" if field.is_valid else "✗"
        lines.append(f"\n  {status_symbol} {field.field_name}")

        # Value
        if field.extracted_value:
            lines.append(f"      Value: {field.extracted_value}")

        # Confidence
        lines.append(f"      Confidence: {field.confidence:.2f} ({field.confidence_level.value})")

        # Errors
        if field.errors:
            lines.append("      Errors:")
            for error in field.errors:
                lines.append(f"        • {error}")

        # Warnings
        if field.warnings:
            lines.append("      Warnings:")
            for warning in field.warnings:
                lines.append(f"        • {warning}")

        # Notes
        if field.notes:
            lines.append(f"      Notes: {field.notes}")

        return lines


# Singleton instance for global access
_validation_engine_instance = None


def get_validation_engine() -> ValidationEngine:
    """
    Get singleton instance of ValidationEngine.

    Returns:
        ValidationEngine instance
    """
    global _validation_engine_instance
    if _validation_engine_instance is None:
        _validation_engine_instance = ValidationEngine()
    return _validation_engine_instance
