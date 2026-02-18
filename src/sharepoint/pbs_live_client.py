"""
PBS Live API Client

Sends notifications and creates group conversations via PBS Live.
Used for notifying CAQH submitters of AI review results and creating
review conversations for twice-rejected submissions.

API Documentation:
    - docs/technical/PBS_LIVE_INSERTIONS_API.md

PBS Live Insertions List:
    - https://sharepoint.teampbs.com/Lists/PBS%20Live%20Insertions/AllItems.aspx

Group Creation Task:
    - https://tracker.teampbs.com/task/6766

Created: January 29, 2026
Updated: February 6, 2026 - Added CAQH Review group creation
"""

import os
import logging
from typing import Dict, Optional, Any

import requests
from requests_ntlm import HttpNtlmAuth
import urllib3

# Suppress SSL warnings for internal PBS server (self-signed cert)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# PBS Live Insertions IDs (created Jan 29, 2026)
CAQH_APPROVED_INSERTION_ID = 205
CAQH_REJECTED_INSERTION_ID = 206

# API Configuration
PBS_LIVE_API_URL = "https://data.teampbs.com/pbslivecommunication/InjectMessage/PBSLiveInsertion"
PBS_LIVE_GROUP_API_URL = "https://pbslivecs.teampbs.com/create-custom-group"

# Bearer Token for Group API (provided by Sasa - permanent token)
PBS_LIVE_GROUP_API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdGF0dXMiOiJQZXJtYW5lbnQiLCJpYXQiOjE2NzgxMDMyMDB9.8v_5d6DWTBArr6djXCNkjtC1v_fWtMTx4-87krSBSak"

# NTLM Authentication (for Insertions API)
PBS_LIVE_NTLM_DOMAIN = "POSITIVE"
PBS_LIVE_NTLM_USERNAME = "sp_Farmp"
PBS_LIVE_NTLM_PASSWORD = "PBSWorks!"


# =============================================================================
# Exceptions
# =============================================================================

class PBSLiveError(Exception):
    """Base exception for PBS Live API errors."""
    pass


class PBSLiveAuthError(PBSLiveError):
    """Authentication error with PBS Live API."""
    pass


class PBSLiveAPIError(PBSLiveError):
    """API error from PBS Live."""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


# =============================================================================
# PBS Live Client
# =============================================================================

class PBSLiveClient:
    """
    Client for sending PBS Live notifications and creating group conversations.

    Authentication:
        - Insertions API (notifications): NTLM auth with sp_Farmp service account
        - Group API (create_caqh_review_group): Bearer token auth

    Usage:
        client = PBSLiveClient()

        # Send approval notification
        client.send_approval_notification("jsmith")

        # Send rejection notification with issues
        client.send_rejection_notification("jsmith", [
            "NPI number is invalid",
            "License expiration date has passed"
        ])

        # Create CAQH Review group (for twice-rejected submissions)
        # Note: Uses short username format (jsmith, not domain\\jsmith)
        # Note: Duplicate identifiers return existing group (no duplicates created)
        room_id = client.create_caqh_review_group(
            submitter_username="jsmith",
            credentialer_usernames=["credentialer1", "credentialer2"],
            file_name="JSmith_DataSummary.pdf",
            submission_id=12345,
            issues=["NPI invalid", "License expired"]
        )
    """

    def __init__(
        self,
        api_url: str = PBS_LIVE_API_URL,
        domain: str = PBS_LIVE_NTLM_DOMAIN,
        username: str = PBS_LIVE_NTLM_USERNAME,
        password: str = PBS_LIVE_NTLM_PASSWORD,
        timeout: int = 30,
        enabled: bool = True
    ):
        """
        Initialize PBS Live client.

        Args:
            api_url: PBS Live API endpoint
            domain: NTLM domain
            username: NTLM username
            password: NTLM password
            timeout: Request timeout in seconds
            enabled: If False, notifications are logged but not sent (for testing)
        """
        self.api_url = api_url
        self.auth = HttpNtlmAuth(f"{domain}\\{username}", password)
        self.timeout = timeout
        self.enabled = enabled

        logger.info(f"PBSLiveClient initialized (enabled={enabled})")

    def _send_insertion(
        self,
        insertion_id: int,
        identifier_value: str,
        dynamic_tags: Optional[Dict[str, str]] = None,
        reference: Optional[str] = None
    ) -> bool:
        """
        Send a PBS Live insertion message.

        Args:
            insertion_id: PBS Live Insertions list ID
            identifier_value: Username of the recipient
            dynamic_tags: Optional placeholder replacements (e.g., {"$ISSUES": "..."})
            reference: Optional reference ID for tracking

        Returns:
            True if successful, False otherwise
        """
        payload = {
            "PBSLiveInsertionsId": insertion_id,
            "IdentifierValue": identifier_value,
            "Retry": True
        }

        if dynamic_tags:
            payload["DYNAMICTAGS"] = dynamic_tags

        if reference:
            payload["Reference"] = reference

        if not self.enabled:
            logger.info(f"[PBS LIVE DISABLED] Would send insertion {insertion_id} to {identifier_value}")
            logger.debug(f"[PBS LIVE DISABLED] Payload: {payload}")
            return True

        try:
            logger.info(f"Sending PBS Live insertion {insertion_id} to {identifier_value}...")

            response = requests.post(
                self.api_url,
                json=payload,
                auth=self.auth,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
                verify=False  # Internal PBS server has self-signed cert
            )

            if response.status_code == 200:
                logger.info(f"Successfully sent PBS Live notification to {identifier_value}")
                return True
            elif response.status_code == 401:
                logger.error(f"PBS Live authentication failed (401)")
                raise PBSLiveAuthError("Authentication failed - check NTLM credentials")
            else:
                logger.error(f"PBS Live API error: {response.status_code} - {response.text}")
                raise PBSLiveAPIError(
                    f"API error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text
                )

        except requests.exceptions.Timeout:
            logger.error(f"PBS Live request timed out after {self.timeout}s")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"PBS Live connection error: {e}")
            return False

    def send_approval_notification(
        self,
        username: str,
        file_name: Optional[str] = None,
        sharepoint_item_id: Optional[int] = None
    ) -> bool:
        """
        Send CAQH approval notification to user.

        Message: "Your CAQH Data Summary submission for $NAME has been reviewed and approved
                  by our AI system. A human reviewer will complete the final review shortly."

        Args:
            username: PBS username of the submitter
            file_name: PDF filename to include in message (e.g., "JCruz_DataSummary.pdf")
            sharepoint_item_id: Optional SharePoint item ID for tracking

        Returns:
            True if sent successfully
        """
        reference = f"CAQH-{sharepoint_item_id}" if sharepoint_item_id else None

        # Log file_name for debugging (use default if empty)
        actual_file_name = file_name if file_name else "your submission"
        logger.debug(f"Approval notification - file_name param: '{file_name}', using: '{actual_file_name}'")

        dynamic_tags = {"$NAME": actual_file_name}

        return self._send_insertion(
            insertion_id=CAQH_APPROVED_INSERTION_ID,
            identifier_value=username,
            dynamic_tags=dynamic_tags,
            reference=reference
        )

    def send_rejection_notification(
        self,
        username: str,
        issues: list,
        file_name: Optional[str] = None,
        sharepoint_item_id: Optional[int] = None
    ) -> bool:
        """
        Send CAQH rejection notification with list of issues.

        Message: "Your CAQH Data Summary submission for $NAME has been reviewed. The following
                  issues were found that need correction: $ISSUES Please update your
                  submission and resubmit."

        Args:
            username: PBS username of the submitter
            issues: List of issue strings to include in message
            file_name: PDF filename to include in message (e.g., "JCruz_DataSummary.pdf")
            sharepoint_item_id: Optional SharePoint item ID for tracking

        Returns:
            True if sent successfully
        """
        # Format issues as bullet list with HTML line breaks for PBS Live rendering
        if issues:
            issues_text = "<br><br>" + "<br>".join(f"- {issue}" for issue in issues)
        else:
            issues_text = "<br><br>- Validation issues found (see report for details)"

        # Add resubmission instructions
        issues_text += (
            "<br><br><b>To resubmit:</b>"
            "<br>- Log into SharePoint"
            "<br>- Click \"About Me\" in the right hand menu"
            "<br>- Click \"My HR Docs\""
            "<br>- Upload your CAQH Data Summary to the \"CAQH Data Summary\" spot"
            "<br>- If you are having difficulties with this upload, please visit the "
            "<a href=\"https://sharepoint.teampbs.com/sites/My/Pages/CredentialingHelpPage.aspx\">Credentialing Help Page</a>"
        )

        reference = f"CAQH-{sharepoint_item_id}" if sharepoint_item_id else None

        # Use default filename if empty (use fallback to ensure $NAME is always replaced)
        actual_file_name = file_name if file_name else "your submission"
        logger.debug(f"Rejection notification - file_name param: '{file_name}', using: '{actual_file_name}'")

        # Build dynamic tags with both $NAME and $ISSUES
        dynamic_tags = {
            "$NAME": actual_file_name,
            "$ISSUES": issues_text
        }

        return self._send_insertion(
            insertion_id=CAQH_REJECTED_INSERTION_ID,
            identifier_value=username,
            dynamic_tags=dynamic_tags,
            reference=reference
        )

    def create_caqh_review_group(
        self,
        submitter_username: str,
        credentialer_usernames: list,
        file_name: str,
        submission_id: int,
        issues: list,
        review_reason: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a CAQH Review group for twice-rejected submissions.

        This creates a dedicated PBS Live group where the submitter and
        credentialer(s) can communicate directly about the submission issues.

        Args:
            submitter_username: PBS username of the submitter (primary user)
            credentialer_usernames: List of credentialer usernames to add
            file_name: PDF filename (e.g., "JSmith_DataSummary.pdf")
            submission_id: SharePoint item ID for the submission
            issues: List of issue strings explaining why submission was rejected
            review_reason: Optional summary reason for the review

        Returns:
            roomId if successful, None otherwise
        """
        # Build the initial message with issues
        # Use <br> for line breaks since PBS Live doesn't render \n as line breaks
        if issues:
            issues_text = "<br><br>".join(f"• {issue}" for issue in issues)
            initial_message = (
                f"Your CAQH submission '{file_name}' needs attention.<br><br>"
                f"Issues found:<br><br>{issues_text}<br><br>"
                f"Please discuss with the credentialing team here."
            )
        else:
            initial_message = (
                f"Your CAQH submission '{file_name}' needs attention. "
                f"Please discuss with the credentialing team here."
            )

        # Build user list (submitter + credentialers)
        users_list = [submitter_username] + credentialer_usernames

        # Build payload per Sasa's spec
        # Note: API expects "receiversUsernames" not "usersList" per error response
        # Using U{username} as identifier = one persistent group per user (all their rejections go here)
        payload = {
            "primaryUser": submitter_username,
            "title": f"CAQH Review - {submitter_username}",
            "identifier": f"U{submitter_username}",
            "receiversUsernames": users_list,
            "initialMessage": initial_message,
            "type": "CaqhReview",
            "additionalData": {
                "submissionId": str(submission_id),
                "fileName": file_name,
                "reviewReason": review_reason or "Submission rejected"
            }
        }

        if not self.enabled:
            logger.info(f"[PBS LIVE DISABLED] Would create CAQH Review group for {submitter_username}")
            logger.debug(f"[PBS LIVE DISABLED] Payload: {payload}")
            return "mock-room-id-disabled"

        try:
            logger.info(f"Creating CAQH Review group for submission {submission_id}...")

            # Group API uses Bearer token auth (not NTLM)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {PBS_LIVE_GROUP_API_TOKEN}"
            }

            response = requests.post(
                PBS_LIVE_GROUP_API_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=False  # Internal PBS server has self-signed cert
            )

            if response.status_code == 200:
                result = response.json()
                room_id = result.get("_id") or result.get("roomId") or result.get("id")
                group_title = result.get("displayname", "Unknown")
                # Note: API returns existing group if duplicate identifier is used
                logger.info(f"CAQH Review group ready: {room_id} ({group_title})")
                logger.debug(f"Full group response: {result}")
                return room_id
            elif response.status_code == 401:
                logger.error("PBS Live Group API authentication failed (401)")
                raise PBSLiveAuthError("Authentication failed - check credentials")
            else:
                logger.error(f"PBS Live Group API error: {response.status_code} - {response.text}")
                raise PBSLiveAPIError(
                    f"API error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text
                )

        except requests.exceptions.Timeout:
            logger.error(f"PBS Live Group API request timed out after {self.timeout}s")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"PBS Live Group API connection error: {e}")
            return None


# =============================================================================
# Factory Functions
# =============================================================================

def create_pbs_live_client_from_env() -> PBSLiveClient:
    """
    Create PBSLiveClient from environment variables.

    Environment Variables (all optional, have defaults):
        PBS_LIVE_API_URL: API endpoint URL
        PBS_LIVE_ENABLED: "true" or "false" (default: true)
        PBS_LIVE_NTLM_DOMAIN: NTLM domain (default: POSITIVE)
        PBS_LIVE_NTLM_USERNAME: NTLM username (default: sp_Farmp)
        PBS_LIVE_NTLM_PASSWORD: NTLM password

    Returns:
        Configured PBSLiveClient instance
    """
    enabled_str = os.getenv('PBS_LIVE_ENABLED', 'true').lower()
    enabled = enabled_str in ('true', '1', 'yes')

    return PBSLiveClient(
        api_url=os.getenv('PBS_LIVE_API_URL', PBS_LIVE_API_URL),
        domain=os.getenv('PBS_LIVE_NTLM_DOMAIN', PBS_LIVE_NTLM_DOMAIN),
        username=os.getenv('PBS_LIVE_NTLM_USERNAME', PBS_LIVE_NTLM_USERNAME),
        password=os.getenv('PBS_LIVE_NTLM_PASSWORD', PBS_LIVE_NTLM_PASSWORD),
        enabled=enabled
    )
