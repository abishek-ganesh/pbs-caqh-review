"""
PBS Enterprise API Client

Handles communication with the PBS Enterprise API for SharePoint operations.
This is the middleware layer between our application and SharePoint on-prem.

API Documentation: docs/meeting-notes/2025-12-19_api_vm_updates.md
Postman Collection: docs/PBS Enterprise APIs - CAQH Library Test.postman_collection.json

Usage:
    from src.sharepoint.pbs_api_client import PBSEnterpriseClient

    client = PBSEnterpriseClient(
        base_url="https://api.teampbs.com",
        access_token="your-azure-ad-token",
        site_url="https://sharepoint.teampbs.com/CAQH%20Data%20Summary",
        library_name="CAQH library Test"
    )

    # Get unprocessed items
    items = client.get_unprocessed_items()

    # Process each item
    for item in items:
        pdf_bytes = client.download_pdf(item['file_ref'])
        # ... process PDF ...
        client.mark_as_processed(item['item_id'], html_report)
"""

import requests
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from urllib.parse import urljoin, quote

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class SharePointItem:
    """Represents a SharePoint list item from the CAQH library."""
    item_id: int
    file_ref: str           # Server-relative URL to the PDF
    file_name: str          # Just the filename
    processed: bool
    html_report: Optional[str]
    title: Optional[str]
    created: str
    modified: str
    raw_data: Dict[str, Any]  # Full response for debugging

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'SharePointItem':
        """Create SharePointItem from API response."""
        field_values = data.get('fieldValues', {})
        return cls(
            item_id=data.get('itemId'),
            file_ref=field_values.get('FileRef', ''),
            file_name=field_values.get('FileLeafRef', ''),
            processed=field_values.get('Processed', False),
            html_report=field_values.get('HTMLReport'),
            title=field_values.get('Title'),
            created=data.get('created', ''),
            modified=data.get('modified', ''),
            raw_data=data
        )


class PBSEnterpriseClientError(Exception):
    """Base exception for PBS Enterprise API errors."""
    pass


class AuthenticationError(PBSEnterpriseClientError):
    """Raised when authentication fails."""
    pass


class APIError(PBSEnterpriseClientError):
    """Raised when API returns an error."""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class PBSEnterpriseClient:
    """
    Client for the PBS Enterprise API SharePoint operations.

    This client wraps the PBS Enterprise API which provides access to
    SharePoint on-premises through a middleware layer.

    Attributes:
        base_url: Base URL of the PBS Enterprise API
        access_token: Azure AD bearer token for authentication
        site_url: SharePoint site URL containing the CAQH library
        library_name: Name of the document library (default: "CAQH library Test")
    """

    # API endpoints
    ENDPOINT_LIST_ITEMS = "/api/sharepoint/lists/items"
    ENDPOINT_DOCUMENTS = "/api/sharepoint/documents"

    def __init__(
        self,
        base_url: str,
        access_token: str,
        site_url: str,
        library_name: str = "CAQH library Test",
        timeout: int = 30
    ):
        """
        Initialize the PBS Enterprise API client.

        Args:
            base_url: Base URL of the PBS Enterprise API (e.g., "https://api.teampbs.com")
            access_token: Azure AD bearer token for authentication
            site_url: SharePoint site URL (e.g., "https://sharepoint.teampbs.com/CAQH%20Data%20Summary")
            library_name: Document library name (default: "CAQH library Test")
            timeout: Request timeout in seconds (default: 30)
        """
        self.base_url = base_url.rstrip('/')
        self.access_token = access_token
        self.site_url = site_url
        self.library_name = library_name
        self.timeout = timeout

        # Create session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        })

        logger.info(f"PBSEnterpriseClient initialized for {self.base_url}")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Dict = None,
        json_data: Dict = None,
        **kwargs
    ) -> requests.Response:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body data
            **kwargs: Additional arguments passed to requests

        Returns:
            Response object

        Raises:
            AuthenticationError: If authentication fails (401)
            APIError: If API returns an error
        """
        url = urljoin(self.base_url, endpoint)

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=self.timeout,
                **kwargs
            )

            # Check for authentication errors
            if response.status_code == 401:
                raise AuthenticationError(
                    "Authentication failed. Check your access token."
                )

            # Check for other errors
            if not response.ok:
                raise APIError(
                    f"API request failed: {response.status_code} {response.reason}",
                    status_code=response.status_code,
                    response_body=response.text
                )

            return response

        except requests.exceptions.Timeout:
            raise APIError(f"Request timed out after {self.timeout} seconds")
        except requests.exceptions.ConnectionError as e:
            raise APIError(f"Connection error: {str(e)}")

    def get_unprocessed_items(self) -> List[SharePointItem]:
        """
        Get all unprocessed items from the CAQH library.

        Returns items where Processed = false.

        Returns:
            List of SharePointItem objects representing unprocessed documents

        Raises:
            APIError: If the API request fails
        """
        logger.info("Fetching unprocessed items from CAQH library")

        # CAML query to filter unprocessed items
        # Note: The current Postman collection shows an empty query
        # We may need to add filtering once we know the exact CAML syntax
        caml_query = "<View><Query></Query></View>"

        params = {
            'listName': self.library_name,
            'siteUrl': self.site_url,
            'camlQuery': caml_query
        }

        response = self._make_request('GET', self.ENDPOINT_LIST_ITEMS, params=params)
        data = response.json()

        # Parse response into SharePointItem objects
        items = []
        for item_data in data:
            item = SharePointItem.from_api_response(item_data)
            # Filter to only unprocessed items
            if not item.processed:
                items.append(item)

        logger.info(f"Found {len(items)} unprocessed items")
        return items

    def get_item_by_id(self, item_id: int) -> SharePointItem:
        """
        Get a single item by its ID.

        Args:
            item_id: SharePoint item ID

        Returns:
            SharePointItem object

        Raises:
            APIError: If the API request fails
        """
        logger.info(f"Fetching item {item_id}")

        endpoint = f"{self.ENDPOINT_LIST_ITEMS}/{item_id}"
        params = {
            'listName': self.library_name,
            'siteUrl': self.site_url
        }

        response = self._make_request('GET', endpoint, params=params)
        data = response.json()

        return SharePointItem.from_api_response(data)

    def download_pdf(self, file_ref: str) -> bytes:
        """
        Download a PDF file from SharePoint.

        Args:
            file_ref: Server-relative URL to the file (from FileRef field)

        Returns:
            PDF file contents as bytes

        Raises:
            APIError: If the download fails

        Note:
            The exact download mechanism needs to be confirmed with Hasan.
            This is a placeholder implementation that may need adjustment.
        """
        logger.info(f"Downloading PDF: {file_ref}")

        # TODO: Confirm with Hasan how to download files
        # Option 1: Construct URL from site_url + file_ref
        # Option 2: Use a separate download endpoint
        # Option 3: file_ref is already a full URL

        # Placeholder implementation - try constructing URL
        # This may need to be adjusted based on Hasan's response
        if file_ref.startswith('http'):
            download_url = file_ref
        else:
            # Remove leading slash if present for proper joining
            file_path = file_ref.lstrip('/')
            download_url = f"{self.site_url}/{file_path}"

        response = self.session.get(
            download_url,
            timeout=self.timeout * 2  # Longer timeout for file downloads
        )

        if not response.ok:
            raise APIError(
                f"Failed to download PDF: {response.status_code}",
                status_code=response.status_code,
                response_body=response.text
            )

        logger.info(f"Downloaded {len(response.content)} bytes")
        return response.content

    def mark_as_processed(
        self,
        item_id: int,
        html_report: str,
        additional_fields: Dict[str, Any] = None
    ) -> SharePointItem:
        """
        Mark an item as processed and write the HTML report.

        Args:
            item_id: SharePoint item ID to update
            html_report: HTML report content to write
            additional_fields: Optional additional fields to update

        Returns:
            Updated SharePointItem object

        Raises:
            APIError: If the update fails
        """
        logger.info(f"Marking item {item_id} as processed")

        fields = {
            'Processed': True,
            'HTMLReport': html_report
        }

        if additional_fields:
            fields.update(additional_fields)

        request_body = {
            'siteUrl': self.site_url,
            'listName': self.library_name,
            'itemId': item_id,
            'fields': fields
        }

        response = self._make_request(
            'PUT',
            self.ENDPOINT_LIST_ITEMS,
            json_data=request_body
        )
        data = response.json()

        logger.info(f"Successfully marked item {item_id} as processed")
        return SharePointItem.from_api_response(data)

    def upload_document(
        self,
        file_path: str,
        file_content: bytes,
        metadata: Dict[str, Any] = None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Upload a document to the CAQH library.

        Args:
            file_path: Name/path for the file in SharePoint
            file_content: File contents as bytes
            metadata: Optional metadata fields to set
            overwrite: Whether to overwrite existing file

        Returns:
            API response with upload details

        Raises:
            APIError: If the upload fails

        Note:
            This is primarily for testing. In production, documents are
            uploaded by users through SharePoint directly.
        """
        logger.info(f"Uploading document: {file_path}")

        files = {
            'file': (file_path, file_content, 'application/pdf')
        }

        data = {
            'siteUrl': self.site_url,
            'libraryName': self.library_name,
            'overwrite': str(overwrite).lower()
        }

        if metadata:
            data.update(metadata)

        # Remove JSON content-type for multipart form upload
        headers = {'Authorization': f'Bearer {self.access_token}'}

        response = requests.post(
            urljoin(self.base_url, self.ENDPOINT_DOCUMENTS),
            files=files,
            data=data,
            headers=headers,
            timeout=self.timeout * 2
        )

        if not response.ok:
            raise APIError(
                f"Failed to upload document: {response.status_code}",
                status_code=response.status_code,
                response_body=response.text
            )

        logger.info(f"Successfully uploaded {file_path}")
        return response.json()

    def test_connection(self) -> bool:
        """
        Test the API connection and authentication.

        Returns:
            True if connection is successful

        Raises:
            AuthenticationError: If authentication fails
            APIError: If connection fails
        """
        logger.info("Testing API connection...")

        try:
            # Try to get list items (will return empty if no items)
            self.get_unprocessed_items()
            logger.info("Connection test successful")
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            raise

    def close(self):
        """Close the session and cleanup resources."""
        self.session.close()
        logger.info("PBSEnterpriseClient session closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


# Convenience function for creating client from environment variables
def create_client_from_env() -> PBSEnterpriseClient:
    """
    Create a PBSEnterpriseClient using environment variables.

    Required environment variables:
        PBS_API_BASE_URL: Base URL of the PBS Enterprise API
        PBS_API_ACCESS_TOKEN: Azure AD bearer token
        PBS_SHAREPOINT_SITE_URL: SharePoint site URL
        PBS_CAQH_LIBRARY_NAME: Document library name (optional, defaults to "CAQH library Test")

    Returns:
        Configured PBSEnterpriseClient instance

    Raises:
        ValueError: If required environment variables are not set
    """
    import os

    base_url = os.getenv('PBS_API_BASE_URL')
    access_token = os.getenv('PBS_API_ACCESS_TOKEN')
    site_url = os.getenv('PBS_SHAREPOINT_SITE_URL')
    library_name = os.getenv('PBS_CAQH_LIBRARY_NAME', 'CAQH library Test')

    missing = []
    if not base_url:
        missing.append('PBS_API_BASE_URL')
    if not access_token:
        missing.append('PBS_API_ACCESS_TOKEN')
    if not site_url:
        missing.append('PBS_SHAREPOINT_SITE_URL')

    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return PBSEnterpriseClient(
        base_url=base_url,
        access_token=access_token,
        site_url=site_url,
        library_name=library_name
    )
