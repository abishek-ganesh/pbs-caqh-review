"""
PBS Enterprise SharePoint Middleware API Client

NEW CLIENT (Jan 2026) - Uses SharePoint Middleware with Client Credentials Flow.
Replaces the old pbs_api_client.py which used user tokens.

API Documentation:
    - docs/README-Middleware.md (local copy of .NET test client README)
    - docs/meeting-notes/hasan_nazish_feedback_jan9_2026.md

Configuration:
    - ApiBaseUrl: https://data.teampbs.com/SP-Enterprise-Middleware
    - TenantId: a43be288-8913-475d-97de-5b99b3dcc172
    - ClientId: [FROM RICHARD SALEEBY]
    - ClientSecret: [FROM RICHARD SALEEBY]
    - Scope: api://ba0e97bf-dbd2-4704-9947-a28c8d433784/.default

Usage:
    from src.sharepoint.pbs_middleware_client import PBSMiddlewareClient

    client = PBSMiddlewareClient(
        tenant_id="a43be288-8913-475d-97de-5b99b3dcc172",
        client_id="your-client-id",
        client_secret="your-client-secret",
        site_url="https://sharepoint.teampbs.com",
        library_name="CAQH library Test"
    )

    # Get unprocessed items
    items = client.get_unprocessed_items()

    # Process each item
    for item in items:
        pdf_bytes = client.download_document(item.file_ref)
        # ... process PDF ...
        client.mark_as_processed_with_json(item.item_id, json_report, "AI_APPROVED")
"""

import requests
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

# MSAL for Client Credentials Flow
try:
    from msal import ConfidentialClientApplication
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False
    ConfidentialClientApplication = None

# NTLM for Windows Integrated Auth
try:
    from requests_ntlm import HttpNtlmAuth
    NTLM_AVAILABLE = True
except ImportError:
    NTLM_AVAILABLE = False
    HttpNtlmAuth = None

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# SharePoint Middleware API configuration
DEFAULT_BASE_URL = "https://data.teampbs.com/SP-Enterprise-Middleware"
DEFAULT_TENANT_ID = "a43be288-8913-475d-97de-5b99b3dcc172"
DEFAULT_SCOPE = "api://ba0e97bf-dbd2-4704-9947-a28c8d433784/.default"
DEFAULT_SITE_URL = "https://sharepoint.teampbs.com"
DEFAULT_LIBRARY_NAME = "CAQH library Test"

# SharePoint column names (can be overridden via environment variables)
# Test library uses "ReviewStatus0", Production uses "AI_x0020_Review_x0020_Status"
DEFAULT_STATUS_COLUMN = "ReviewStatus0"


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class SharePointItem:
    """Represents a SharePoint list item from the CAQH library."""
    item_id: int
    file_ref: str           # Server-relative URL to the PDF
    file_name: str          # Just the filename (FileLeafRef)
    processed: str          # "Yes" or "No" (or None if not set)
    json_report: Optional[str]        # JSON report from AI validation
    validation_status: Optional[str]  # AI_APPROVED, AI_REJECTED, etc.
    title: Optional[str]
    created: str
    modified: str                     # Current Modified timestamp from SharePoint
    author_email: Optional[str]       # Author.Email - for PBS Live notifications
    author_name: Optional[str]        # Author.LookupValue - display name
    author_login: Optional[str]       # Author login/username
    version: Optional[str]            # Document version (e.g., "5.0") - not available via API
    pbs_region: Optional[str]         # PBSRegion - used for region filtering
    raw_data: Dict[str, Any]  # Full response for debugging

    @classmethod
    def from_api_response(
        cls,
        data: Dict[str, Any],
        status_column: str = "ReviewStatus0"
    ) -> 'SharePointItem':
        """Create SharePointItem from Middleware API response.

        Args:
            data: API response data
            status_column: SharePoint column name for AI review status
                          (default: "ReviewStatus0" for test,
                           use "AI_x0020_Review_x0020_Status" for production)
        """
        # Middleware returns fieldValues directly in the item
        field_values = data.get('fieldValues', data)

        # Debug: log all available field names (once per run)
        if not hasattr(cls, '_logged_fields'):
            logger.debug(f"Available fields in API response: {list(field_values.keys())}")
            cls._logged_fields = True

        # Extract Author info (can be nested object or direct fields)
        author = field_values.get('Author', {})
        if isinstance(author, dict):
            author_email = author.get('Email', '')
            author_name = author.get('LookupValue', '')
            # Extract username from email (e.g., "jsmith@teampbs.com" -> "jsmith")
            author_login = author_email.split('@')[0] if author_email else ''
        else:
            author_email = ''
            author_name = ''
            author_login = ''

        # Extract version info - not available via Middleware API, kept for backwards compatibility
        version = (
            field_values.get('OData__UIVersionString') or
            field_values.get('_UIVersionString') or
            ''
        )

        # Extract PBSRegion (Lookup column - returns {LookupId, LookupValue} or null)
        pbs_region_raw = field_values.get('PBSRegion')
        if isinstance(pbs_region_raw, dict):
            pbs_region = pbs_region_raw.get('LookupValue', '')
        elif isinstance(pbs_region_raw, str):
            pbs_region = pbs_region_raw
        else:
            pbs_region = ''

        return cls(
            item_id=data.get('itemId') or data.get('ID') or field_values.get('ID'),
            file_ref=field_values.get('FileRef', ''),
            file_name=field_values.get('FileLeafRef', ''),
            processed=field_values.get('Processed', None),
            json_report=field_values.get('JSONReport'),
            validation_status=field_values.get(status_column),
            title=field_values.get('Title'),
            created=field_values.get('Created', ''),
            modified=field_values.get('Modified', ''),
            author_email=author_email,
            author_name=author_name,
            author_login=author_login,
            version=version,
            pbs_region=pbs_region,
            raw_data=data
        )


# =============================================================================
# Exceptions
# =============================================================================

class PBSMiddlewareError(Exception):
    """Base exception for PBS Middleware API errors."""
    pass


class AuthenticationError(PBSMiddlewareError):
    """Raised when authentication fails."""
    pass


class TokenAcquisitionError(PBSMiddlewareError):
    """Raised when token acquisition fails."""
    pass


class APIError(PBSMiddlewareError):
    """Raised when API returns an error."""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


# =============================================================================
# Token Manager (MSAL Client Credentials Flow)
# =============================================================================

class TokenManager:
    """
    Manages OAuth2 tokens using MSAL Client Credentials Flow.

    This is the key difference from the old client - no user interaction needed.
    The app authenticates as itself using ClientID + ClientSecret.
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        scope: str = DEFAULT_SCOPE
    ):
        if not MSAL_AVAILABLE:
            raise ImportError(
                "MSAL library not installed. Run: pip install msal"
            )

        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope

        # MSAL authority URL
        self.authority = f"https://login.microsoftonline.com/{tenant_id}"

        # Create MSAL confidential client
        self._app = ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=self.authority
        )

        # Token cache
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

        logger.info(f"TokenManager initialized for tenant {tenant_id}")

    def get_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            Access token string

        Raises:
            TokenAcquisitionError: If token cannot be acquired
        """
        # Check if we have a valid cached token (with 5 min buffer)
        if self._token and self._token_expires:
            if datetime.now() < (self._token_expires - timedelta(minutes=5)):
                return self._token

        # Acquire new token
        logger.info("Acquiring new access token via Client Credentials Flow...")

        result = self._app.acquire_token_for_client(scopes=[self.scope])

        if "access_token" in result:
            self._token = result["access_token"]
            # Token typically expires in 1 hour
            expires_in = result.get("expires_in", 3600)
            self._token_expires = datetime.now() + timedelta(seconds=expires_in)

            logger.info(f"Token acquired, expires at {self._token_expires}")
            return self._token
        else:
            error = result.get("error", "unknown_error")
            error_desc = result.get("error_description", "No description")
            raise TokenAcquisitionError(
                f"Failed to acquire token: {error} - {error_desc}"
            )


# =============================================================================
# Main Client
# =============================================================================

class PBSMiddlewareClient:
    """
    Client for PBS Enterprise SharePoint Middleware API.

    Uses Client Credentials Flow (no user interaction) - perfect for cron jobs.

    Attributes:
        base_url: SharePoint Middleware API URL
        site_url: SharePoint site URL containing the CAQH library
        library_name: Name of the document library
        user: Optional user email for Author/Editor fields
    """

    # API endpoints (from README-Middleware.md)
    ENDPOINT_LIST_ITEMS = "/api/lists/items"     # POST create, PUT update
    ENDPOINT_LIST_QUERY = "/api/lists/query"     # POST query with CAML
    ENDPOINT_DOCUMENTS = "/api/documents"        # POST upload
    ENDPOINT_HEALTH = "/api/health"              # GET health check

    def __init__(
        self,
        tenant_id: str = DEFAULT_TENANT_ID,
        client_id: str = None,
        client_secret: str = None,
        base_url: str = DEFAULT_BASE_URL,
        site_url: str = DEFAULT_SITE_URL,
        library_name: str = DEFAULT_LIBRARY_NAME,
        status_column: str = DEFAULT_STATUS_COLUMN,
        user: str = None,
        timeout: int = 60,
        verify_ssl: bool = False,
        # NTLM auth (for Windows Integrated Auth)
        ntlm_username: str = None,
        ntlm_password: str = None,
        ntlm_domain: str = None
    ):
        """
        Initialize the PBS Middleware API client.

        Args:
            tenant_id: Azure AD tenant ID
            client_id: Azure App registration client ID (from Richard Saleeby)
            client_secret: Azure App registration client secret
            base_url: Middleware API URL (default: https://data.teampbs.com/SP-Enterprise-Middleware)
            site_url: SharePoint site URL (default: https://sharepoint.teampbs.com)
            library_name: Document library name (default: "CAQH library Test")
            status_column: SharePoint column for AI review status (default: "ReviewStatus0")
                          Production uses "AI_x0020_Review_x0020_Status"
            user: Optional user email for Author/Editor fields
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates (default: False for internal APIs)
            ntlm_username: Windows username for NTLM auth (use instead of client_id/secret)
            ntlm_password: Windows password for NTLM auth
            ntlm_domain: Windows domain for NTLM auth (e.g., "TEAMPBS")
        """
        self.base_url = base_url.rstrip('/')
        self.site_url = site_url
        self.library_name = library_name
        self.status_column = status_column
        self.user = user
        self.timeout = timeout
        self.verify_ssl = verify_ssl

        # Determine auth mode: NTLM or Bearer token
        self._use_ntlm = bool(ntlm_username and ntlm_password)
        self._ntlm_auth = None
        self._token_manager = None

        if self._use_ntlm:
            # Use NTLM (Windows Integrated Auth)
            if not NTLM_AVAILABLE:
                raise ImportError("requests-ntlm not installed. Run: pip install requests-ntlm")

            # Format: DOMAIN\\username or just username
            if ntlm_domain:
                ntlm_user = f"{ntlm_domain}\\{ntlm_username}"
            else:
                ntlm_user = ntlm_username

            self._ntlm_auth = HttpNtlmAuth(ntlm_user, ntlm_password)
            logger.info(f"PBSMiddlewareClient using NTLM auth for {ntlm_username}")

        else:
            # Use Bearer token (Azure AD Client Credentials)
            if not client_id or not client_secret:
                raise ValueError(
                    "Either NTLM credentials (ntlm_username, ntlm_password) or "
                    "Azure AD credentials (client_id, client_secret) are required."
                )

            self._token_manager = TokenManager(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )

        # Create session
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })

        logger.info(f"PBSMiddlewareClient initialized for {self.base_url}")

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers (with Bearer token if using Azure AD auth)."""
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

        # Add Bearer token if using Azure AD auth (not NTLM)
        if self._token_manager and not self._use_ntlm:
            token = self._token_manager.get_token()
            headers['Authorization'] = f'Bearer {token}'

        return headers

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Dict = None,
        **kwargs
    ) -> requests.Response:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, PUT)
            endpoint: API endpoint path
            json_data: JSON body data
            **kwargs: Additional arguments passed to requests

        Returns:
            Response object

        Raises:
            AuthenticationError: If authentication fails (401)
            APIError: If API returns an error
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        # Use NTLM auth if configured
        auth = self._ntlm_auth if self._use_ntlm else None

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                auth=auth,
                timeout=self.timeout,
                verify=self.verify_ssl,
                **kwargs
            )

            # Log request details for debugging
            logger.debug(f"{method} {url} -> {response.status_code}")

            # Check for authentication errors
            if response.status_code == 401:
                raise AuthenticationError(
                    "Authentication failed. Check client credentials."
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

    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------

    def check_health(self) -> Dict[str, Any]:
        """
        Check API health status.

        Returns:
            Health status response
        """
        logger.info("Checking API health...")
        response = self._make_request('GET', self.ENDPOINT_HEALTH)
        return response.json()

    # -------------------------------------------------------------------------
    # Query Operations
    # -------------------------------------------------------------------------

    def query_items(
        self,
        caml_query: str,
        view_fields: List[str] = None,
        row_limit: int = 100
    ) -> List[SharePointItem]:
        """
        Query items from the library using CAML.

        Args:
            caml_query: CAML query XML
            view_fields: List of fields to return
            row_limit: Maximum rows to return

        Returns:
            List of SharePointItem objects
        """
        request_body = {
            "siteUrl": self.site_url,
            "listName": self.library_name,
            "camlQuery": caml_query,
            "rowLimit": row_limit
        }

        if view_fields:
            request_body["viewFields"] = view_fields

        if self.user:
            request_body["user"] = self.user

        response = self._make_request('POST', self.ENDPOINT_LIST_QUERY, json_data=request_body)

        # Debug: log raw response
        logger.info(f"Response status: {response.status_code}")
        logger.debug(f"Response headers: {dict(response.headers)}")
        raw_text = response.text[:1000] if response.text else "(empty)"
        logger.info(f"Response text (first 1000 chars): {raw_text}")

        if not response.text or not response.text.strip():
            logger.warning("API returned empty response - returning empty list")
            return []

        try:
            data = response.json()
        except Exception as e:
            logger.error(f"JSON parse failed. Raw response: {response.text[:2000]}")
            raise

        # Parse response
        items = []
        if isinstance(data, list):
            for item_data in data:
                items.append(SharePointItem.from_api_response(item_data, status_column=self.status_column))
        elif isinstance(data, dict):
            # Handle wrapped response
            items_list = data.get('items', data.get('value', []))
            for item_data in items_list:
                items.append(SharePointItem.from_api_response(item_data, status_column=self.status_column))

        return items

    def get_unprocessed_items(self, dry_run: bool = False) -> List[SharePointItem]:
        """
        Get all unprocessed items from the CAQH library.

        Returns items where Processed = No or is empty/null.

        To re-process a document (resubmission), manually set Processed = No
        in SharePoint, or use Power Automate to reset it when a file is replaced.

        Args:
            dry_run: Unused, kept for backwards compatibility

        Returns:
            List of SharePointItem objects
        """
        logger.info("Fetching unprocessed items from CAQH library...")

        # CAML query for unprocessed items from 2026+, newest first
        # Filters: (Processed=No OR Processed=null) AND Created >= 2026-01-01
        # The library has thousands of old items we don't want to process
        caml_query = """<View>
            <Query>
                <Where>
                    <And>
                        <Or>
                            <Eq>
                                <FieldRef Name='Processed'/>
                                <Value Type='Boolean'>0</Value>
                            </Eq>
                            <IsNull>
                                <FieldRef Name='Processed'/>
                            </IsNull>
                        </Or>
                        <Geq>
                            <FieldRef Name='Created'/>
                            <Value Type='DateTime'>2026-01-01T00:00:00Z</Value>
                        </Geq>
                    </And>
                </Where>
                <OrderBy>
                    <FieldRef Name='Modified' Ascending='FALSE'/>
                </OrderBy>
            </Query>
        </View>"""

        # Fields we need (including JSON report fields for validation status tracking)
        view_fields = [
            "ID",
            "Title",
            "FileRef",
            "FileLeafRef",
            "Processed",
            "JSONReport",
            self.status_column,  # AI review status column (configurable)
            "Created",
            "Modified",
            "Author",  # For PBS Live notifications - returns {Email, LookupId, LookupValue}
            "OData__UIVersionString",  # Document version (e.g., "5.0")
            "PBSRegion"
        ]

        items = self.query_items(
            caml_query=caml_query,
            view_fields=view_fields,
            row_limit=100
        )

        logger.info(f"Found {len(items)} unprocessed items")

        return items

    def get_item_by_id(self, item_id: int) -> SharePointItem:
        """
        Get a specific item by ID.

        Args:
            item_id: SharePoint item ID

        Returns:
            SharePointItem object
        """
        logger.info(f"Fetching item {item_id}...")

        # CAML query for specific item ID
        caml_query = f"""<View>
            <Query>
                <Where>
                    <Eq>
                        <FieldRef Name='ID'/>
                        <Value Type='Counter'>{item_id}</Value>
                    </Eq>
                </Where>
            </Query>
        </View>"""

        # Fields we need (including JSON report fields for validation status tracking)
        view_fields = [
            "ID",
            "Title",
            "FileRef",
            "FileLeafRef",
            "Processed",
            "JSONReport",
            self.status_column,  # AI review status column (configurable)
            "Created",
            "Modified",
            "Author",
            "OData__UIVersionString",
            "PBSRegion"
        ]

        items = self.query_items(
            caml_query=caml_query,
            view_fields=view_fields,
            row_limit=1
        )

        if not items:
            raise APIError(f"Item {item_id} not found", status_code=404)

        return items[0]

    # -------------------------------------------------------------------------
    # Create/Update Operations
    # -------------------------------------------------------------------------

    def create_item(self, field_values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new list item.

        Args:
            field_values: Dictionary of field name -> value

        Returns:
            API response with created item details
        """
        request_body = {
            "siteUrl": self.site_url,
            "listName": self.library_name,
            "fieldValues": field_values
        }

        if self.user:
            request_body["user"] = self.user

        response = self._make_request('POST', self.ENDPOINT_LIST_ITEMS, json_data=request_body)
        return response.json()

    def update_item(self, item_id: int, field_values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing list item.

        Args:
            item_id: SharePoint item ID
            field_values: Dictionary of field name -> value to update

        Returns:
            API response with updated item details
        """
        logger.info(f"Updating item {item_id}...")

        request_body = {
            "siteUrl": self.site_url,
            "listName": self.library_name,
            "itemId": item_id,
            "fieldValues": field_values
        }

        if self.user:
            request_body["user"] = self.user

        response = self._make_request('PUT', self.ENDPOINT_LIST_ITEMS, json_data=request_body)
        return response.json()

    def mark_as_processed_with_json(
        self,
        item_id: int,
        json_report: str,
        validation_status: str,
    ) -> Dict[str, Any]:
        """
        Mark an item as processed with JSON report and validation status.

        NOTE: Due to SharePoint Middleware API limitations, we must update
        fields individually. Combining multiple text fields in one call
        causes silent failures where no fields are updated.

        SharePoint Fields Updated:
            - JSONReport (Multi-line text): Full JSON report
            - AI Review Status (text): AI_APPROVED, AI_REJECTED, etc.
              (column name is configurable via status_column)
            - Processed (Boolean): Set to True

        Args:
            item_id: SharePoint item ID
            json_report: JSON report string
            validation_status: Status string (AI_APPROVED, AI_REJECTED, etc.)

        Returns:
            API response from the final update call
        """
        # WORKAROUND: SharePoint Middleware silently fails when updating
        # multiple fields together. Update each field individually.

        # Update JSONReport
        logger.info(f"Updating JSONReport field for item {item_id}...")
        result1 = self.update_item(item_id, {"JSONReport": json_report})
        logger.debug(f"JSONReport update response: {result1}")

        # Update AI Review Status (column name is configurable)
        logger.info(f"Updating {self.status_column} field for item {item_id}...")
        result2 = self.update_item(item_id, {self.status_column: validation_status})
        logger.debug(f"{self.status_column} update response: {result2}")

        # Update Processed boolean
        logger.info(f"Updating Processed field for item {item_id}...")
        result_final = self.update_item(item_id, {"Processed": True})

        return result_final

    # -------------------------------------------------------------------------
    # Document Operations
    # -------------------------------------------------------------------------

    def upload_document(
        self,
        file_name: str,
        file_content: bytes,
        metadata: Dict[str, Any] = None,
        folder_path: str = None,
        overwrite: bool = True
    ) -> Dict[str, Any]:
        """
        Upload a document to the library.

        Args:
            file_name: Name for the file
            file_content: File contents as bytes
            metadata: Optional metadata fields
            folder_path: Optional subfolder path
            overwrite: Whether to overwrite existing file

        Returns:
            API response with upload details
        """
        logger.info(f"Uploading document: {file_name}")

        # For multipart upload, we need different headers
        token = self._token_manager.get_token()

        files = {
            'file': (file_name, file_content, 'application/pdf')
        }

        form_data = {
            'siteUrl': self.site_url,
            'libraryName': self.library_name,
            'overwrite': str(overwrite).lower()
        }

        if folder_path:
            form_data['folderPath'] = folder_path

        if self.user:
            form_data['user'] = self.user

        if metadata:
            for key, value in metadata.items():
                form_data[key] = str(value)

        url = f"{self.base_url}{self.ENDPOINT_DOCUMENTS}"

        response = requests.post(
            url,
            files=files,
            data=form_data,
            headers={'Authorization': f'Bearer {token}'},
            timeout=self.timeout * 2,
            verify=self.verify_ssl
        )

        if not response.ok:
            raise APIError(
                f"Upload failed: {response.status_code}",
                status_code=response.status_code,
                response_body=response.text
            )

        logger.info(f"Successfully uploaded {file_name}")
        return response.json()

    def download_document(self, file_ref: str) -> bytes:
        """
        Download a document by its FileRef using the middleware API.

        Args:
            file_ref: Server-relative URL to the file (e.g., "/CAQH library Test/file.pdf")

        Returns:
            File contents as bytes
        """
        # Extract filename from file_ref
        file_name = file_ref.split('/')[-1] if '/' in file_ref else file_ref
        logger.info(f"Downloading document: {file_name}")

        # Use POST /api/documents/download with form data
        token = self._token_manager.get_token()

        form_data = {
            "siteUrl": self.site_url,
            "libraryName": self.library_name,
            "fileName": file_name
        }

        response = requests.post(
            f"{self.base_url}/api/documents/download",
            headers={'Authorization': f'Bearer {token}'},
            data=form_data,
            timeout=self.timeout * 2,
            verify=self.verify_ssl
        )

        if not response.ok:
            raise APIError(
                f"Download failed: {response.status_code}",
                status_code=response.status_code,
                response_body=response.text[:500] if response.text else None
            )

        logger.info(f"Downloaded {len(response.content)} bytes")
        return response.content

    # -------------------------------------------------------------------------
    # Context Manager
    # -------------------------------------------------------------------------

    def close(self):
        """Close the session."""
        self.session.close()
        logger.info("PBSMiddlewareClient session closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# =============================================================================
# Factory Functions
# =============================================================================

def create_client_from_env() -> PBSMiddlewareClient:
    """
    Create a PBSMiddlewareClient using environment variables.

    NTLM Auth (preferred for Windows Integrated Auth):
        PBS_NTLM_USERNAME: Windows username
        PBS_NTLM_PASSWORD: Windows password
        PBS_NTLM_DOMAIN: Windows domain (optional, e.g., "TEAMPBS")

    Azure AD Auth (alternative):
        PBS_CLIENT_ID: Azure App client ID
        PBS_CLIENT_SECRET: Azure App client secret

    Optional environment variables:
        PBS_TENANT_ID: Azure tenant ID (default: PBS tenant)
        PBS_MIDDLEWARE_URL: API base URL (default: https://data.teampbs.com/SP-Enterprise-Middleware)
        PBS_SHAREPOINT_SITE_URL: SharePoint site URL
        PBS_CAQH_LIBRARY_NAME: Library name
        PBS_CAQH_STATUS_COLUMN: AI review status column name
            - Test: "ReviewStatus0" (default)
            - Production: "AI_x0020_Review_x0020_Status"
        PBS_USER_EMAIL: User email for Author/Editor fields

    Returns:
        Configured PBSMiddlewareClient instance
    """
    import os

    # Check for NTLM credentials first (preferred for this API)
    ntlm_username = os.getenv('PBS_NTLM_USERNAME')
    ntlm_password = os.getenv('PBS_NTLM_PASSWORD')
    ntlm_domain = os.getenv('PBS_NTLM_DOMAIN')

    # Fall back to Azure AD credentials
    client_id = os.getenv('PBS_CLIENT_ID')
    client_secret = os.getenv('PBS_CLIENT_SECRET')

    # Must have either NTLM or Azure AD credentials
    if not (ntlm_username and ntlm_password) and not (client_id and client_secret):
        raise ValueError(
            "Missing credentials. Set either:\n"
            "  - PBS_NTLM_USERNAME and PBS_NTLM_PASSWORD (for Windows auth), or\n"
            "  - PBS_CLIENT_ID and PBS_CLIENT_SECRET (for Azure AD auth)"
        )

    return PBSMiddlewareClient(
        tenant_id=os.getenv('PBS_TENANT_ID', DEFAULT_TENANT_ID),
        client_id=client_id,
        client_secret=client_secret,
        ntlm_username=ntlm_username,
        ntlm_password=ntlm_password,
        ntlm_domain=ntlm_domain,
        base_url=os.getenv('PBS_MIDDLEWARE_URL', DEFAULT_BASE_URL),
        site_url=os.getenv('PBS_SHAREPOINT_SITE_URL', DEFAULT_SITE_URL),
        library_name=os.getenv('PBS_CAQH_LIBRARY_NAME', DEFAULT_LIBRARY_NAME),
        status_column=os.getenv('PBS_CAQH_STATUS_COLUMN', DEFAULT_STATUS_COLUMN),
        user=os.getenv('PBS_USER_EMAIL')
    )


def create_client(
    client_id: str,
    client_secret: str,
    **kwargs
) -> PBSMiddlewareClient:
    """
    Create a PBSMiddlewareClient with explicit credentials.

    Args:
        client_id: Azure App client ID (from Richard Saleeby)
        client_secret: Azure App client secret
        **kwargs: Additional arguments passed to PBSMiddlewareClient

    Returns:
        Configured PBSMiddlewareClient instance
    """
    return PBSMiddlewareClient(
        client_id=client_id,
        client_secret=client_secret,
        **kwargs
    )
