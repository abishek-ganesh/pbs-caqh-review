"""
Confidence Scorer

Calculates confidence scores for extracted and validated fields.
Combines extraction confidence with validation results to produce
final confidence scores for decision-making.
"""

from typing import Optional, Dict, Any
from ..models.validation_result import FieldValidationResult
from ..models.extraction_result import FieldExtractionResult
from ..config.constants import ConfidenceLevel


class ConfidenceScorer:
    """
    Calculates and adjusts confidence scores for field extraction and validation.

    Confidence scoring helps determine:
    - Whether to trust an extracted value
    - Whether to route to human review
    - Overall document status
    """

    # Base confidence scores by extraction method
    BASE_CONFIDENCE = {
        "native_pdf": 0.95,      # High - text directly from PDF
        "ocr": 0.75,             # Medium - OCR has some error rate
        "pattern_match": 0.85,   # Medium-high - regex patterns
        "ai_assisted": 0.80,     # Medium-high - AI extraction
        "manual": 1.0,           # Maximum - human entered
        "unknown": 0.50          # Low - method unknown
    }

    # Confidence thresholds for categorization
    HIGH_CONFIDENCE_THRESHOLD = 0.90
    MEDIUM_CONFIDENCE_THRESHOLD = 0.70

    def __init__(self):
        """Initialize the ConfidenceScorer."""
        pass

    def calculate_extraction_confidence(
        self,
        extraction_method: str,
        has_value: bool,
        raw_text_context: Optional[str] = None,
        pattern_match_strength: Optional[float] = None
    ) -> float:
        """
        Calculate base confidence for field extraction.

        Args:
            extraction_method: Method used (native_pdf, ocr, pattern_match, etc.)
            has_value: Whether a value was extracted
            raw_text_context: Context around extracted value (for quality assessment)
            pattern_match_strength: Strength of pattern match (0.0-1.0) if applicable

        Returns:
            Confidence score (0.0-1.0)
        """
        # Start with base confidence for extraction method
        base = self.BASE_CONFIDENCE.get(extraction_method.lower(), self.BASE_CONFIDENCE["unknown"])

        # No value extracted = very low confidence
        if not has_value:
            return 0.0

        confidence = base

        # Adjust for pattern match strength if provided
        if pattern_match_strength is not None:
            # Weight: 70% base method, 30% pattern strength
            confidence = (0.7 * base) + (0.3 * pattern_match_strength)

        # Adjust for context quality (if available)
        if raw_text_context:
            # Short context = less reliable extraction
            context_length = len(raw_text_context)
            if context_length < 10:
                confidence *= 0.90  # Reduce by 10%
            elif context_length < 5:
                confidence *= 0.80  # Reduce by 20%

        # Ensure within bounds
        return max(0.0, min(1.0, confidence))

    def adjust_for_validation(
        self,
        extraction_confidence: float,
        validation_passed: bool,
        has_errors: bool,
        has_warnings: bool,
        is_required: bool
    ) -> float:
        """
        Adjust confidence based on validation results.

        Args:
            extraction_confidence: Base confidence from extraction
            validation_passed: Whether field passed validation
            has_errors: Whether validation produced errors
            has_warnings: Whether validation produced warnings
            is_required: Whether field is required

        Returns:
            Adjusted confidence score (0.0-1.0)
        """
        confidence = extraction_confidence

        if validation_passed:
            # Validation passed - boost confidence slightly
            confidence = min(1.0, confidence + 0.05)

            # If warnings exist, reduce boost
            if has_warnings:
                confidence = min(1.0, confidence - 0.02)

        else:  # Validation failed
            # Failed validation significantly reduces confidence
            if is_required:
                # Required field failure = very low confidence
                confidence *= 0.30
            else:
                # Optional field failure = moderate reduction
                confidence *= 0.50

            # Multiple errors = even lower confidence
            if has_errors:
                confidence *= 0.90

        return max(0.0, min(1.0, confidence))

    def adjust_for_field_characteristics(
        self,
        base_confidence: float,
        value: Any,
        field_type: str,
        is_critical: bool = False
    ) -> float:
        """
        Adjust confidence based on field-specific characteristics.

        Args:
            base_confidence: Starting confidence score
            value: The extracted/validated value
            field_type: Type of field (ssn, npi, date, text, etc.)
            is_critical: Whether this is a critical POC field

        Returns:
            Adjusted confidence score (0.0-1.0)
        """
        confidence = base_confidence

        # Critical fields have stricter confidence requirements
        if is_critical and confidence < 0.90:
            # Penalize critical fields that don't meet high threshold
            confidence *= 0.95

        # Field-specific adjustments
        if field_type == "text":
            if isinstance(value, str):
                # Very short text values are suspicious
                if len(value) < 2:
                    confidence *= 0.70
                # Very long values might be extraction errors
                elif len(value) > 200:
                    confidence *= 0.90

        elif field_type == "date":
            if isinstance(value, str):
                # Date format consistency check
                # Well-formatted dates (MM/DD/YYYY, YYYY-MM-DD) get boost
                if "/" in value or "-" in value:
                    confidence = min(1.0, confidence + 0.02)

        elif field_type in ["ssn", "npi", "tax_id"]:
            if isinstance(value, str):
                # Structured IDs should be clean (digits only or proper format)
                if value.replace("-", "").isdigit():
                    confidence = min(1.0, confidence + 0.03)

        return max(0.0, min(1.0, confidence))

    def calculate_final_confidence(
        self,
        extraction_result: FieldExtractionResult,
        validation_result: FieldValidationResult
    ) -> float:
        """
        Calculate final confidence score combining extraction and validation.

        This is the main method that orchestrates all confidence adjustments.

        Args:
            extraction_result: Result of field extraction
            validation_result: Result of field validation

        Returns:
            Final confidence score (0.0-1.0)
        """
        # Start with extraction confidence
        confidence = extraction_result.confidence

        # Adjust for validation outcome
        confidence = self.adjust_for_validation(
            extraction_confidence=confidence,
            validation_passed=validation_result.is_valid,
            has_errors=len(validation_result.errors) > 0,
            has_warnings=len(validation_result.warnings) > 0,
            is_required=validation_result.is_required
        )

        # Adjust for field characteristics
        # Determine field type from validation type
        field_type = self._infer_field_type(validation_result.field_name)

        confidence = self.adjust_for_field_characteristics(
            base_confidence=confidence,
            value=validation_result.extracted_value,
            field_type=field_type,
            is_critical=validation_result.field_name in self._get_critical_fields()
        )

        return round(confidence, 2)

    def get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """
        Map confidence score to confidence level enum.

        Args:
            confidence: Confidence score (0.0-1.0)

        Returns:
            ConfidenceLevel (HIGH, MEDIUM, or LOW)
        """
        if confidence >= self.HIGH_CONFIDENCE_THRESHOLD:
            return ConfidenceLevel.HIGH
        elif confidence >= self.MEDIUM_CONFIDENCE_THRESHOLD:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _infer_field_type(self, field_name: str) -> str:
        """
        Infer field type from field name for characteristic adjustments.

        Args:
            field_name: Name of the field

        Returns:
            Field type (text, date, ssn, npi, etc.)
        """
        field_name_lower = field_name.lower()

        if "date" in field_name_lower or "expiration" in field_name_lower:
            return "date"
        elif "ssn" in field_name_lower or "social_security" in field_name_lower:
            return "ssn"
        elif "npi" in field_name_lower:
            return "npi"
        elif "tax_id" in field_name_lower or "ein" in field_name_lower:
            return "tax_id"
        elif "phone" in field_name_lower:
            return "phone"
        elif "email" in field_name_lower:
            return "email"
        elif "zip" in field_name_lower or "postal" in field_name_lower:
            return "zip"
        else:
            return "text"

    def _get_critical_fields(self) -> set:
        """
        Get set of critical field names.

        Returns:
            Set of critical field names
        """
        # These are the 5 POC critical fields
        return {
            "medicaid_id",
            "ssn",
            "individual_npi",
            "practice_location_name",
            "professional_license_expiration_date"
        }

    def calculate_document_confidence(
        self,
        field_confidences: Dict[str, float],
        critical_fields_only: bool = False
    ) -> float:
        """
        Calculate overall document confidence from field confidences.

        Args:
            field_confidences: Dictionary mapping field names to confidence scores
            critical_fields_only: If True, only consider critical fields

        Returns:
            Overall document confidence (0.0-1.0)
        """
        if not field_confidences:
            return 0.0

        if critical_fields_only:
            # Filter to only critical fields
            critical_fields = self._get_critical_fields()
            relevant_confidences = [
                conf for field, conf in field_confidences.items()
                if field in critical_fields
            ]
        else:
            relevant_confidences = list(field_confidences.values())

        if not relevant_confidences:
            return 0.0

        # Use weighted average (could also use minimum for conservative approach)
        # Weight critical fields more heavily
        total_weight = 0.0
        weighted_sum = 0.0

        critical_fields = self._get_critical_fields()

        for field_name, confidence in field_confidences.items():
            if field_name in critical_fields:
                weight = 2.0  # Critical fields weighted 2x
            else:
                weight = 1.0

            weighted_sum += confidence * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return round(weighted_sum / total_weight, 2)


# Singleton instance for global access
_confidence_scorer_instance = None


def get_confidence_scorer() -> ConfidenceScorer:
    """
    Get singleton instance of ConfidenceScorer.

    Returns:
        ConfidenceScorer instance
    """
    global _confidence_scorer_instance
    if _confidence_scorer_instance is None:
        _confidence_scorer_instance = ConfidenceScorer()
    return _confidence_scorer_instance
