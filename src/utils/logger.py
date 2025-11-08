"""
Centralized logging infrastructure for the CAQH Data Summary Review tool.

This module provides consistent logging across all modules, replacing
print statements and providing proper log levels, formatting, and rotation.
"""

import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import json


class CAQHLogger:
    """
    Centralized logger for CAQH processing with consistent formatting.

    Features:
    - Structured logging with consistent format
    - Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - File rotation to prevent log files from growing too large
    - PHI/PII masking for sensitive data
    - Performance logging for optimization
    """

    # Sensitive field patterns to mask
    SENSITIVE_FIELDS = {
        'ssn', 'social_security_number', 'tax_id',
        'dob', 'date_of_birth', 'birthdate'
    }

    def __init__(
        self,
        name: str,
        log_dir: str = "logs",
        log_level: str = "INFO",
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        enable_console: bool = True,
        enable_file: bool = True
    ):
        """
        Initialize the CAQH logger.

        Args:
            name: Logger name (usually module name)
            log_dir: Directory for log files
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            max_bytes: Max size of log file before rotation
            backup_count: Number of backup files to keep
            enable_console: Whether to log to console
            enable_file: Whether to log to file
        """
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper()))
        self.logger.handlers = []  # Clear any existing handlers

        # Create log directory if it doesn't exist
        if enable_file:
            Path(log_dir).mkdir(parents=True, exist_ok=True)

        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        simple_formatter = logging.Formatter(
            '%(levelname)s | %(message)s'
        )

        # Add console handler
        if enable_console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)  # Console shows INFO and above
            console_handler.setFormatter(simple_formatter)
            self.logger.addHandler(console_handler)

        # Add file handler with rotation
        if enable_file:
            log_file = os.path.join(log_dir, f"{name}_{datetime.now():%Y%m%d}.log")
            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)  # File captures everything
            file_handler.setFormatter(detailed_formatter)
            self.logger.addHandler(file_handler)

            # Add error-specific log file
            error_log_file = os.path.join(log_dir, f"{name}_errors_{datetime.now():%Y%m%d}.log")
            error_handler = logging.handlers.RotatingFileHandler(
                filename=error_log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            error_handler.setLevel(logging.ERROR)  # Only errors and critical
            error_handler.setFormatter(detailed_formatter)
            self.logger.addHandler(error_handler)

    def _mask_sensitive_data(self, data: Any) -> Any:
        """
        Mask sensitive data in log messages.

        Args:
            data: Data to mask (dict, list, or string)

        Returns:
            Data with sensitive fields masked
        """
        if isinstance(data, dict):
            masked = {}
            for key, value in data.items():
                if any(sensitive in key.lower() for sensitive in self.SENSITIVE_FIELDS):
                    if isinstance(value, str) and len(value) > 4:
                        # Keep first and last 2 chars for reference
                        masked[key] = f"{value[:2]}***{value[-2:]}"
                    else:
                        masked[key] = "***MASKED***"
                else:
                    masked[key] = self._mask_sensitive_data(value)
            return masked
        elif isinstance(data, list):
            return [self._mask_sensitive_data(item) for item in data]
        elif isinstance(data, str):
            # Mask SSN patterns (XXX-XX-XXXX or XXXXXXXXX)
            import re
            ssn_pattern = r'\b\d{3}-?\d{2}-?\d{4}\b'
            if re.search(ssn_pattern, data):
                return re.sub(ssn_pattern, '***-**-****', data)
            return data
        else:
            return data

    # Logging methods with automatic sensitive data masking

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        if kwargs:
            masked_kwargs = self._mask_sensitive_data(kwargs)
            message = f"{message} | {json.dumps(masked_kwargs)}"
        self.logger.debug(message)

    def info(self, message: str, **kwargs):
        """Log info message."""
        if kwargs:
            masked_kwargs = self._mask_sensitive_data(kwargs)
            message = f"{message} | {json.dumps(masked_kwargs)}"
        self.logger.info(message)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        if kwargs:
            masked_kwargs = self._mask_sensitive_data(kwargs)
            message = f"{message} | {json.dumps(masked_kwargs)}"
        self.logger.warning(message)

    def error(self, message: str, exception: Optional[Exception] = None, **kwargs):
        """Log error message with optional exception."""
        if kwargs:
            masked_kwargs = self._mask_sensitive_data(kwargs)
            message = f"{message} | {json.dumps(masked_kwargs)}"
        if exception:
            message = f"{message} | Exception: {str(exception)}"
        self.logger.error(message, exc_info=exception is not None)

    def critical(self, message: str, exception: Optional[Exception] = None, **kwargs):
        """Log critical message with optional exception."""
        if kwargs:
            masked_kwargs = self._mask_sensitive_data(kwargs)
            message = f"{message} | {json.dumps(masked_kwargs)}"
        if exception:
            message = f"{message} | Exception: {str(exception)}"
        self.logger.critical(message, exc_info=exception is not None)

    # Specialized logging methods

    def log_extraction(
        self,
        field_name: str,
        value: Optional[str],
        confidence: float,
        method: str,
        success: bool = True
    ):
        """Log field extraction result."""
        if success:
            self.info(
                f"Extraction successful",
                field=field_name,
                value=value if value else "None",
                confidence=confidence,
                method=method
            )
        else:
            self.warning(
                f"Extraction failed",
                field=field_name,
                method=method,
                reason="No value found"
            )

    def log_validation(
        self,
        field_name: str,
        is_valid: bool,
        confidence: float,
        errors: Optional[list] = None,
        warnings: Optional[list] = None
    ):
        """Log field validation result."""
        if is_valid:
            self.info(
                f"Validation passed",
                field=field_name,
                confidence=confidence,
                warnings=warnings if warnings else []
            )
        else:
            self.error(
                f"Validation failed",
                field=field_name,
                confidence=confidence,
                errors=errors if errors else [],
                warnings=warnings if warnings else []
            )

    def log_performance(
        self,
        operation: str,
        duration_seconds: float,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log performance metrics."""
        self.debug(
            f"Performance metric",
            operation=operation,
            duration_seconds=round(duration_seconds, 3),
            details=details if details else {}
        )

    def log_pdf_processing(
        self,
        filename: str,
        status: str,
        page_count: Optional[int] = None,
        extraction_method: Optional[str] = None
    ):
        """Log PDF processing status."""
        self.info(
            f"PDF processing",
            filename=filename,
            status=status,
            page_count=page_count,
            extraction_method=extraction_method
        )


# Global logger instances for different modules
_loggers: Dict[str, CAQHLogger] = {}


def get_logger(
    name: str,
    log_level: Optional[str] = None,
    **kwargs
) -> CAQHLogger:
    """
    Get or create a logger instance.

    Args:
        name: Logger name (usually module name)
        log_level: Override default log level
        **kwargs: Additional arguments for CAQHLogger

    Returns:
        CAQHLogger instance
    """
    if name not in _loggers:
        # Get log level from environment or use default
        if log_level is None:
            log_level = os.environ.get('CAQH_LOG_LEVEL', 'INFO')

        _loggers[name] = CAQHLogger(name, log_level=log_level, **kwargs)

    return _loggers[name]


# Convenience function for module-level logging
def get_module_logger() -> CAQHLogger:
    """
    Get a logger for the calling module.

    Returns:
        CAQHLogger instance for the calling module
    """
    import inspect
    frame = inspect.currentframe()
    if frame and frame.f_back:
        module_name = frame.f_back.f_globals.get('__name__', 'unknown')
    else:
        module_name = 'unknown'

    # Simplify module name (e.g., src.extraction.field_extractor -> field_extractor)
    module_name = module_name.split('.')[-1]

    return get_logger(module_name)


# Example usage in other modules:
# from src.utils.logger import get_module_logger
# logger = get_module_logger()
# logger.info("Processing started", file="example.pdf")