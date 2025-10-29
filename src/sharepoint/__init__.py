"""
SharePoint Integration Module

Handles all SharePoint operations including reading submissions,
updating records, and triggering email workflows.

Components:
- client.py: SharePoint API client
- list_manager.py: CAQH Data Summary list operations
- status_updater.py: Updates Approval Status and Rejection Reason fields
- submission_reader.py: Reads new/unreviewed submissions
"""

from .client import SharePointClient
from .list_manager import CAQHListManager

__all__ = ["SharePointClient", "CAQHListManager"]
