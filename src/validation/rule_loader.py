"""
Validation Rule Loader

Loads and parses validation rules from validation_rules.yaml.
Provides type-safe access to field validation configurations.
"""

import yaml
from pathlib import Path
from typing import Dict, Optional, List, Any
from pydantic import BaseModel, Field, ValidationError
from functools import lru_cache


class ExtractionConfig(BaseModel):
    """Configuration for field extraction from PDF"""

    labels: List[str] = Field(
        default_factory=list,
        description="Text labels to search for in PDF"
    )

    pattern: Optional[str] = Field(
        None,
        description="Regex pattern for extracting value"
    )

    section: Optional[str] = Field(
        None,
        description="PDF section where field is located"
    )

    max_distance: int = Field(
        50,
        description="Maximum characters after label to search"
    )

    confidence_threshold: float = Field(
        0.85,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for valid extraction"
    )

    requires_masking: bool = Field(
        False,
        description="Whether field contains PHI requiring masking"
    )

    validation: Optional[str] = Field(
        None,
        description="Additional validation to apply (e.g., luhn_checksum)"
    )

    notes: Optional[str] = Field(
        None,
        description="Notes about extraction"
    )


class FieldRule(BaseModel):
    """Validation rule for a single field"""

    field_name: str = Field(
        ...,
        description="Name of the field"
    )

    required: bool = Field(
        False,
        description="Whether field is required"
    )

    validation_type: str = Field(
        ...,
        description="Type of validation (format, date, text_presence, lookup, etc.)"
    )

    error_message: str = Field(
        ...,
        description="Error message for validation failure"
    )

    critical: bool = Field(
        False,
        description="Whether this is a critical POC field"
    )

    field_category: str = Field(
        "general",
        description="Category (provider_identification, professional_ids, etc.)"
    )

    # Optional format validation
    format_regex: Optional[str] = Field(
        None,
        description="Regex pattern for format validation"
    )

    # Optional special validations
    luhn_checksum: bool = Field(
        False,
        description="Whether to apply Luhn checksum validation"
    )

    requires_masking: bool = Field(
        False,
        description="Whether field contains PHI requiring masking"
    )

    # Date validation specific
    date_future: bool = Field(
        False,
        description="Whether date must be in the future"
    )

    date_past: bool = Field(
        False,
        description="Whether date must be in the past"
    )

    # Extraction configuration
    extraction: Optional[ExtractionConfig] = Field(
        None,
        description="Configuration for extracting this field from PDF"
    )

    # Additional metadata
    lookup_source: Optional[str] = Field(
        None,
        description="Source for lookup validation (e.g., state_license_library)"
    )

    notes: Optional[str] = Field(
        None,
        description="Additional notes about the field"
    )


class RuleLoader:
    """
    Loads and manages validation rules from YAML configuration.

    Provides type-safe access to field validation rules with caching
    for performance.
    """

    def __init__(self, rules_path: Optional[Path] = None):
        """
        Initialize the RuleLoader.

        Args:
            rules_path: Path to validation_rules.yaml. If None, uses default location.
        """
        if rules_path is None:
            # Default to src/config/validation_rules.yaml
            current_file = Path(__file__)
            rules_path = current_file.parent.parent / "config" / "validation_rules.yaml"

        self.rules_path = Path(rules_path)
        self._rules: Dict[str, FieldRule] = {}
        self._raw_yaml: Dict[str, Any] = {}
        self._loaded = False

    def load_rules(self, force_reload: bool = False) -> Dict[str, FieldRule]:
        """
        Load validation rules from YAML file.

        Args:
            force_reload: If True, reload rules even if already loaded

        Returns:
            Dictionary mapping field names to FieldRule objects

        Raises:
            FileNotFoundError: If rules file doesn't exist
            yaml.YAMLError: If YAML parsing fails
            ValidationError: If rules don't match expected structure
        """
        if self._loaded and not force_reload:
            return self._rules

        if not self.rules_path.exists():
            raise FileNotFoundError(
                f"Validation rules file not found: {self.rules_path}"
            )

        try:
            # Load YAML
            with open(self.rules_path, 'r', encoding='utf-8') as f:
                self._raw_yaml = yaml.safe_load(f)

            if not isinstance(self._raw_yaml, dict):
                raise ValueError("Validation rules YAML must be a dictionary")

            # Parse each field rule
            self._rules = {}

            for field_name, rule_dict in self._raw_yaml.items():
                if not isinstance(rule_dict, dict):
                    continue  # Skip non-dict entries (comments, etc.)

                # Add field_name to the rule dict for validation
                rule_dict['field_name'] = field_name

                # Parse extraction config if present
                if 'extraction' in rule_dict and isinstance(rule_dict['extraction'], dict):
                    rule_dict['extraction'] = ExtractionConfig(**rule_dict['extraction'])

                # Create FieldRule object
                try:
                    field_rule = FieldRule(**rule_dict)
                    self._rules[field_name] = field_rule
                except ValidationError as e:
                    # Log error but continue loading other rules
                    print(f"Warning: Failed to parse rule for field '{field_name}': {e}")
                    continue

            self._loaded = True
            return self._rules

        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Failed to parse YAML file {self.rules_path}: {e}")

    def get_rule(self, field_name: str) -> Optional[FieldRule]:
        """
        Get validation rule for a specific field.

        Args:
            field_name: Name of the field

        Returns:
            FieldRule object, or None if field not found
        """
        if not self._loaded:
            self.load_rules()

        return self._rules.get(field_name)

    def get_all_rules(self) -> Dict[str, FieldRule]:
        """
        Get all loaded validation rules.

        Returns:
            Dictionary mapping field names to FieldRule objects
        """
        if not self._loaded:
            self.load_rules()

        return self._rules.copy()

    def get_critical_fields(self) -> Dict[str, FieldRule]:
        """
        Get only critical POC fields.

        Returns:
            Dictionary of critical field rules
        """
        if not self._loaded:
            self.load_rules()

        return {
            name: rule
            for name, rule in self._rules.items()
            if rule.critical
        }

    def get_required_fields(self) -> Dict[str, FieldRule]:
        """
        Get only required fields.

        Returns:
            Dictionary of required field rules
        """
        if not self._loaded:
            self.load_rules()

        return {
            name: rule
            for name, rule in self._rules.items()
            if rule.required
        }

    def get_fields_by_category(self, category: str) -> Dict[str, FieldRule]:
        """
        Get fields by category.

        Args:
            category: Field category (e.g., "provider_identification")

        Returns:
            Dictionary of field rules in the category
        """
        if not self._loaded:
            self.load_rules()

        return {
            name: rule
            for name, rule in self._rules.items()
            if rule.field_category == category
        }

    def reload_rules(self) -> Dict[str, FieldRule]:
        """
        Force reload of validation rules from file.

        Useful for testing or when rules file has been updated.

        Returns:
            Dictionary of reloaded rules
        """
        return self.load_rules(force_reload=True)

    def get_field_names(self) -> List[str]:
        """
        Get list of all field names.

        Returns:
            List of field names
        """
        if not self._loaded:
            self.load_rules()

        return list(self._rules.keys())

    def has_field(self, field_name: str) -> bool:
        """
        Check if a field has a validation rule.

        Args:
            field_name: Name of the field

        Returns:
            True if field has a rule, False otherwise
        """
        if not self._loaded:
            self.load_rules()

        return field_name in self._rules


# Singleton instance for global access
@lru_cache(maxsize=1)
def get_rule_loader() -> RuleLoader:
    """
    Get singleton instance of RuleLoader.

    Uses LRU cache to ensure only one instance is created.

    Returns:
        RuleLoader instance
    """
    return RuleLoader()
