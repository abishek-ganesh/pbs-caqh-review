"""
Configuration Module

Manages application configuration and settings.

Components:
- settings.py: Application settings from environment variables
- validation_rules.py: Loads validation rules from YAML
- constants.py: Application constants and enums
"""

# Only import modules that exist
# from .settings import Settings  # TODO: Implement settings loader
from .constants import UserType, ValidationStatus, FieldCategory

__all__ = [
    # "Settings",
    "UserType",
    "ValidationStatus",
    "FieldCategory"
]
