"""
SharePoint Integration Module

Handles all SharePoint operations through the PBS Enterprise API middleware.
This module provides the interface between our CAQH extraction tool and
SharePoint on-premises.

Components:
- pbs_api_client.py: PBS Enterprise API client (primary integration point)

Usage:
    from src.sharepoint import PBSEnterpriseClient, create_client_from_env

    # Option 1: Create client with explicit credentials
    client = PBSEnterpriseClient(
        base_url="https://api.teampbs.com",
        access_token="your-token",
        site_url="https://sharepoint.teampbs.com/CAQH%20Data%20Summary",
        library_name="CAQH library Test"
    )

    # Option 2: Create client from environment variables
    client = create_client_from_env()

    # Get unprocessed items
    items = client.get_unprocessed_items()

    # Mark as processed with HTML report
    client.mark_as_processed(item_id=123, html_report="<html>...</html>")

API Documentation:
    - Full API docs: docs/meeting-notes/2025-12-19_api_vm_updates.md
    - Postman collection: docs/PBS Enterprise APIs - CAQH Library Test.postman_collection.json
"""

from .pbs_api_client import (
    PBSEnterpriseClient,
    PBSEnterpriseClientError,
    AuthenticationError,
    APIError,
    SharePointItem,
    create_client_from_env
)

__all__ = [
    "PBSEnterpriseClient",
    "PBSEnterpriseClientError",
    "AuthenticationError",
    "APIError",
    "SharePointItem",
    "create_client_from_env"
]
