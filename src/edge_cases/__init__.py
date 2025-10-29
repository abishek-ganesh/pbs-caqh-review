"""
Edge Cases Module

Handles special cases and error scenarios.

Components:
- duplicate_detector.py: 15-minute duplicate detection logic
- document_type_checker.py: Wrong document type detection
- file_integrity.py: Corrupted/unreadable PDF handling
"""

from .duplicate_detector import (
    DuplicateDetector,
    DuplicateDetectionResult,
    SubmissionRecord,
    get_duplicate_detector
)
from .document_type_checker import (
    DocumentTypeChecker,
    DocumentTypeResult,
    get_document_type_checker
)
from .file_integrity import (
    FileIntegrityChecker,
    FileIntegrityResult,
    get_file_integrity_checker
)

__all__ = [
    "DuplicateDetector",
    "DuplicateDetectionResult",
    "SubmissionRecord",
    "get_duplicate_detector",
    "DocumentTypeChecker",
    "DocumentTypeResult",
    "get_document_type_checker",
    "FileIntegrityChecker",
    "FileIntegrityResult",
    "get_file_integrity_checker",
]
