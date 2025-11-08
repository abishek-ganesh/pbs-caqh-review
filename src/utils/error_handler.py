"""
Standardized error handling for the CAQH Data Summary Review tool.

This module provides consistent error handling patterns across the codebase,
replacing the multiple inconsistent patterns (exceptions, tuples, result objects).
"""

import traceback
from typing import Optional, Union, Tuple, Any, Dict
from enum import Enum
import logging


class ErrorLevel(Enum):
    """Error severity levels."""
    CRITICAL = "critical"  # System failure, cannot continue
    ERROR = "error"  # Operation failed, but system can continue
    WARNING = "warning"  # Operation succeeded with issues
    INFO = "info"  # Informational message


class ErrorCode(Enum):
    """Standardized error codes for different error types."""

    # PDF Errors (1xxx)
    PDF_READ_ERROR = 1001
    PDF_CORRUPT = 1002
    PDF_EMPTY = 1003
    PDF_WRONG_TYPE = 1004
    PDF_NOT_CAQH = 1005

    # Extraction Errors (2xxx)
    EXTRACTION_FAILED = 2001
    LABEL_NOT_FOUND = 2002
    PATTERN_NOT_MATCHED = 2003
    VALUE_NOT_FOUND = 2004
    SECTION_NOT_FOUND = 2005
    OCR_FAILED = 2006

    # Validation Errors (3xxx)
    VALIDATION_FAILED = 3001
    FIELD_REQUIRED = 3002
    FIELD_EMPTY = 3003
    INVALID_FORMAT = 3004
    INVALID_VALUE = 3005
    OUT_OF_RANGE = 3006

    # System Errors (4xxx)
    FILE_NOT_FOUND = 4001
    PERMISSION_DENIED = 4002
    OUT_OF_MEMORY = 4003
    CONFIGURATION_ERROR = 4004


class CAQHError(Exception):
    """Base exception class for CAQH processing errors."""

    def __init__(
        self,
        message: str,
        code: ErrorCode,
        level: ErrorLevel = ErrorLevel.ERROR,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        """
        Initialize CAQH error.

        Args:
            message: Human-readable error message
            code: Error code from ErrorCode enum
            level: Severity level from ErrorLevel enum
            details: Additional error details as dictionary
            cause: Original exception that caused this error
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.level = level
        self.details = details or {}
        self.cause = cause

        # Add traceback if cause is provided
        if cause:
            self.details['original_error'] = str(cause)
            self.details['traceback'] = traceback.format_exc()

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for serialization."""
        return {
            'message': self.message,
            'code': self.code.value,
            'level': self.level.value,
            'details': self.details
        }


class ErrorResult:
    """
    Standardized result wrapper for operations that may fail.

    This replaces the inconsistent tuple returns and provides a consistent
    way to handle success/failure across the codebase.
    """

    def __init__(
        self,
        success: bool,
        value: Optional[Any] = None,
        error: Optional[CAQHError] = None
    ):
        """
        Initialize error result.

        Args:
            success: Whether the operation succeeded
            value: The result value if successful
            error: The error if failed
        """
        self.success = success
        self.value = value
        self.error = error

    @classmethod
    def ok(cls, value: Any) -> 'ErrorResult':
        """Create a successful result."""
        return cls(success=True, value=value, error=None)

    @classmethod
    def fail(cls, error: CAQHError) -> 'ErrorResult':
        """Create a failed result."""
        return cls(success=False, value=None, error=error)

    def unwrap(self) -> Any:
        """
        Get the value or raise the error.

        Returns:
            The value if successful

        Raises:
            CAQHError if failed
        """
        if self.success:
            return self.value
        else:
            raise self.error

    def unwrap_or(self, default: Any) -> Any:
        """Get the value or return a default."""
        return self.value if self.success else default


class ErrorHandler:
    """Centralized error handler with logging."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize error handler.

        Args:
            logger: Logger instance to use (creates default if None)
        """
        self.logger = logger or logging.getLogger(__name__)

    def handle(self, error: CAQHError) -> None:
        """
        Handle an error by logging it appropriately.

        Args:
            error: The error to handle
        """
        log_message = f"[{error.code.name}] {error.message}"

        if error.details:
            log_message += f" | Details: {error.details}"

        # Log based on severity level
        if error.level == ErrorLevel.CRITICAL:
            self.logger.critical(log_message)
        elif error.level == ErrorLevel.ERROR:
            self.logger.error(log_message)
        elif error.level == ErrorLevel.WARNING:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)

    def wrap_operation(self, operation: callable, *args, **kwargs) -> ErrorResult:
        """
        Wrap an operation in error handling.

        Args:
            operation: The operation to execute
            *args: Arguments for the operation
            **kwargs: Keyword arguments for the operation

        Returns:
            ErrorResult with the operation result or error
        """
        try:
            result = operation(*args, **kwargs)
            return ErrorResult.ok(result)
        except CAQHError as e:
            self.handle(e)
            return ErrorResult.fail(e)
        except Exception as e:
            # Convert unexpected exceptions to CAQHError
            caqh_error = CAQHError(
                message=f"Unexpected error: {str(e)}",
                code=ErrorCode.EXTRACTION_FAILED,
                level=ErrorLevel.ERROR,
                cause=e
            )
            self.handle(caqh_error)
            return ErrorResult.fail(caqh_error)


# Convenience functions for common error scenarios

def pdf_read_error(filename: str, cause: Exception) -> CAQHError:
    """Create a PDF read error."""
    return CAQHError(
        message=f"Failed to read PDF: {filename}",
        code=ErrorCode.PDF_READ_ERROR,
        level=ErrorLevel.ERROR,
        details={'filename': filename},
        cause=cause
    )


def field_not_found_error(field_name: str, label: str) -> CAQHError:
    """Create a field not found error."""
    return CAQHError(
        message=f"Field '{field_name}' not found. Label '{label}' not in document.",
        code=ErrorCode.LABEL_NOT_FOUND,
        level=ErrorLevel.WARNING,
        details={'field': field_name, 'label': label}
    )


def validation_error(field_name: str, value: str, reason: str) -> CAQHError:
    """Create a validation error."""
    return CAQHError(
        message=f"Validation failed for '{field_name}': {reason}",
        code=ErrorCode.VALIDATION_FAILED,
        level=ErrorLevel.ERROR,
        details={'field': field_name, 'value': value, 'reason': reason}
    )


def wrong_document_error(expected: str, found: str) -> CAQHError:
    """Create a wrong document type error."""
    return CAQHError(
        message=f"Wrong document type. Expected: {expected}, Found: {found}",
        code=ErrorCode.PDF_WRONG_TYPE,
        level=ErrorLevel.ERROR,
        details={'expected': expected, 'found': found}
    )