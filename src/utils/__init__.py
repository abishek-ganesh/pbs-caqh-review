"""
Utilities Module

Helper functions and utilities used across the application.

Components:
- logger.py: Centralized logging with PHI masking
- date_utils.py: Date parsing and validation utilities
- format_utils.py: Format validation helpers
- config_loader.py: Environment and config file loading
- encryption.py: PHI encryption utilities
- sharepoint_helpers.py: SharePoint API helpers
- reporting.py: Comprehensive error reporting and rejection templates
"""

# Only import modules that exist
# from .logger import get_logger  # TODO: Implement logger
from .date_utils import is_future_date, is_past_date
from .format_utils import validate_ssn, validate_npi, validate_phone, validate_email
from .reporting import ComprehensiveReporter, get_comprehensive_reporter

__all__ = [
    # "get_logger",
    "is_future_date",
    "is_past_date",
    "validate_ssn",
    "validate_npi",
    "validate_phone",
    "validate_email",
    "ComprehensiveReporter",
    "get_comprehensive_reporter",
]
