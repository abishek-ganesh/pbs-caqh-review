"""
Validation Module

Validates extracted fields against CAQH Cheat Sheet rules.
Implements all validation logic from validation_rules.yaml.

Components:
- validation_engine.py: Main validation orchestrator
- rule_loader.py: Loads validation rules from YAML
- confidence_scorer.py: Calculates confidence scores
- field_validators.py: Individual field validation functions
"""

from .validation_engine import ValidationEngine, get_validation_engine
from .rule_loader import RuleLoader, FieldRule, get_rule_loader
from .confidence_scorer import ConfidenceScorer, get_confidence_scorer
from .field_validators import (
    validate_medicaid_id,
    validate_ssn_field,
    validate_individual_npi,
    validate_practice_location_name,
    validate_license_expiration_date,
    CRITICAL_FIELD_VALIDATORS,
    validate_all_critical_fields,
    get_validation_summary
)

__all__ = [
    # Main components
    "ValidationEngine",
    "get_validation_engine",
    "RuleLoader",
    "FieldRule",
    "get_rule_loader",
    "ConfidenceScorer",
    "get_confidence_scorer",

    # Field validators
    "validate_medicaid_id",
    "validate_ssn_field",
    "validate_individual_npi",
    "validate_practice_location_name",
    "validate_license_expiration_date",
    "CRITICAL_FIELD_VALIDATORS",
    "validate_all_critical_fields",
    "get_validation_summary"
]
