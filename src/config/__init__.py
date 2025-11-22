"""
Configuration Module

Manages application configuration and settings.

Components:
- settings.py: Application settings from environment variables
- validation_rules.py: Loads validation rules from YAML
- constants.py: Application constants and enums
"""

from .constants import UserType, ValidationStatus, FieldCategory

__all__ = [
    "UserType",
    "ValidationStatus",
    "FieldCategory"
]
