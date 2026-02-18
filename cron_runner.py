#!/usr/bin/env python3
"""
CAQH Data Summary Review - Cron Runner

This script is the main entry point for the automated CAQH review process.
It runs on a schedule (via cron) to:
1. Fetch unprocessed PDF documents from SharePoint
2. Run Mistral Document AI OCR to extract text
3. Run GPT-5-mini to extract 70 fields from the document
4. Generate JSON reports with confidence scores
5. Write results back to SharePoint (Processed, ReviewStatus0, JSONReport)
6. Send PBS Live notifications to submitters

Pipeline: Mistral Document AI OCR -> GPT-5-mini Field Extraction
Cost: ~$0.03 per PDF

Cron Setup (every 5 minutes):
    */5 * * * * /opt/caqh-reviewer/venv/bin/python /opt/caqh-reviewer/cron_runner.py >> /opt/caqh-reviewer/logs/cron.log 2>&1

Environment Variables Required:
    # SharePoint Middleware (Client Credentials Flow)
    PBS_CLIENT_ID           - Azure App registration client ID (from Richard Saleeby)
    PBS_CLIENT_SECRET       - Azure App registration client secret

    # Azure AI Foundry (for OCR and extraction)
    AZURE_OPENAI_ENDPOINT   - Azure OpenAI/Mistral endpoint URL
    AZURE_OPENAI_API_KEY    - Azure OpenAI API key

Optional Environment Variables:
    PBS_TENANT_ID           - Azure tenant ID (default: PBS tenant)
    PBS_MIDDLEWARE_URL      - API base URL (default: https://data.teampbs.com/SP-Enterprise-Middleware)
    PBS_SHAREPOINT_SITE_URL - SharePoint site URL (default: https://sharepoint.teampbs.com)
    PBS_CAQH_LIBRARY_NAME   - Library name (default: "CAQH library Test")
    PBS_LIVE_ENABLED        - Enable/disable PBS Live notifications (default: true)
    PBS_ALLOWED_REGIONS     - Comma-separated list of regions to process (default: see code)
                              Set to "*" to disable region filtering

Usage:
    # Run normally (with PBS Live notifications)
    python cron_runner.py

    # Dry run (no updates to SharePoint or notifications)
    python cron_runner.py --dry-run

    # Process specific item by ID
    python cron_runner.py --item-id 123

    # Disable PBS Live notifications
    python cron_runner.py --no-notifications

    # Verbose logging
    python cron_runner.py --verbose
"""

import os
import sys
import json
import re
import argparse
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from src.sharepoint.pbs_middleware_client import (
    PBSMiddlewareClient,
    create_client_from_env,
    SharePointItem,
    APIError,
    AuthenticationError
)
from src.sharepoint.pbs_live_client import (
    PBSLiveClient,
    create_pbs_live_client_from_env,
    PBSLiveError
)
from src.extraction.mistral_ocr import MistralOCR
from src.utils.cost_tracker import CostTracker
from src.validation.business_rules_validator import BusinessRulesValidator, ValidationStatus


# =============================================================================
# Region Filtering
# =============================================================================
# Only process items from approved regions. This is for phased rollout -
# more regions will be added over time via the PBS_ALLOWED_REGIONS env var.
# =============================================================================

DEFAULT_ALLOWED_REGIONS = [
    "District of Columbia",
    "Delaware",
    "Broward",
    "Capital",
    "Central Florida",
    "Emerald Coast",
    "Miami-Dade",
    "North Florida",
    "Palm Beach",
    "Southwest",
    "Space Coast",
    "Suncoast",
    "Suwannee River",
    "Treasure Coast",
    "West Coast",
    "East Tennessee",
    "Middle Tennessee",
    "Southeast Tennessee",
    "West Tennessee",
]


def get_allowed_regions() -> list[str]:
    """Get list of allowed regions from env var or defaults.

    Set PBS_ALLOWED_REGIONS as a comma-separated list to override.
    Set to "*" to allow all regions (disable filtering).
    """
    env_val = os.getenv("PBS_ALLOWED_REGIONS", "").strip()
    if not env_val:
        return [r.lower() for r in DEFAULT_ALLOWED_REGIONS]
    if env_val == "*":
        return []  # Empty list = no filtering
    return [r.strip().lower() for r in env_val.split(",") if r.strip()]


# Configure logging
def setup_logging(verbose: bool = False, log_file: Optional[str] = None):
    """Configure logging for the cron runner."""
    level = logging.DEBUG if verbose else logging.INFO

    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
    )

    # Reduce noise from verbose libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('pdfminer').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('pytesseract').setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# =============================================================================
# All 70 Fields to Extract (Mistral + GPT-5-mini Pipeline)
# =============================================================================

ALL_EXTRACTION_FIELDS = [
    # Provider Identification (9 fields)
    "first_name", "middle_name", "last_name", "suffix",
    "date_of_birth", "gender", "ssn", "individual_npi", "caqh_number",
    # Professional Identification (3 fields)
    "medicaid_id", "professional_license_number", "professional_license_expiration_date",
    # Practice Location (8 fields)
    "practice_location_name", "practice_location_address", "practice_location_city",
    "practice_location_state", "practice_location_zip", "practice_location_phone",
    "practice_location_email",
    # Insurance Information (13 fields)
    "insurance_policy_number", "insurance_carrier_name", "insurance_covered_location",
    "insurance_current_effective_date", "insurance_current_expiration_date",
    "insurance_each_occurrence", "insurance_general_aggregate", "insurance_individual_coverage",
    "insurance_self_insured",
    "insurance_address_street_1", "insurance_address_street_2", "insurance_address_city",
    "insurance_address_state", "insurance_address_zip", "insurance_address_country",
    "insurance_phone", "insurance_fax",
    # Specialty Information (6 fields)
    "primary_specialty", "secondary_specialty", "board_certified",
    "certifying_board_name", "initial_certification_date", "certification_expiration_date",
    # Education (5 fields)
    "professional_school_name", "graduation_date", "undergraduate_school_name",
    "undergraduate_degree", "undergraduate_graduation_date",
    # Demographics (8 fields)
    "birth_city", "birth_state", "birth_country", "home_address_street",
    "home_address_city", "home_address_state", "home_address_zip", "race_ethnicity",
    # Credentialing Contact (9 fields)
    "credentialing_contact_first_name", "credentialing_contact_last_name",
    "credentialing_contact_address", "credentialing_contact_city",
    "credentialing_contact_state", "credentialing_contact_zip",
    "credentialing_contact_phone", "credentialing_contact_fax",
    "credentialing_contact_email",
    # Billing Contact (9 fields)
    "billing_contact_first_name", "billing_contact_last_name",
    "billing_contact_address", "billing_contact_city", "billing_contact_state",
    "billing_contact_zip", "billing_contact_phone", "billing_contact_fax",
    "billing_contact_email",
    # Training (1 field)
    "cultural_competency_training",
]


# =============================================================================
# GPT-5-mini Extraction
# =============================================================================

def extract_with_gpt5_mini(ocr_text: str, fields: list, tracker: CostTracker = None) -> dict:
    """Extract fields from OCR text using GPT-5-mini."""
    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    )

    system_prompt = """You are an expert at extracting structured data from CAQH Provider Data Summary documents.

The text is in HTML table format with labels and values in adjacent cells. For example:
<tr><td>Policy Number :</td><td>6799172</td></tr>

## EXTRACTION GUIDELINES:

### PROVIDER IDENTIFICATION:
- Extract from "PERSONAL INFORMATION" section
- first_name, middle_name, last_name, suffix in the name section
- SSN format: XXX-XX-XXXX (preserve format)
- NPI: 10 digits

### PROFESSIONAL LICENSE:
- Look in "PROFESSIONAL IDENTIFICATION NUMBERS" section
- If provider has MULTIPLE licenses, prefer the one with Status = "Active"

### INSURANCE INFORMATION (CRITICAL - DO NOT RETURN NULL):
- Look in "INSURANCE INFORMATION" section (NOT Medicaid section)
- CAQH documents ALWAYS have insurance information - if you see multiple policies, pick ONE
- Selection priority:
  1. Carrier = "Lexington Insurance Company" (PBS's carrier)
  2. Covered location contains "Positive Behavior Supports"
  3. If neither match, pick the FIRST policy listed
- REQUIRED FIELDS - extract from the selected policy:
  - insurance_carrier_name: e.g., "Lexington Insurance Company"
  - insurance_policy_number: 7-digit number like "6799172"
  - insurance_current_effective_date: MM/DD/YYYY format
  - insurance_current_expiration_date: MM/DD/YYYY format
- Coverage limits (in "COVERAGE INFORMATION" table):
  - insurance_each_occurrence: "Each Occurrence" amount (e.g., "$1,000,000")
  - insurance_general_aggregate: "General Aggregate" amount (e.g., "$3,000,000")
  - insurance_individual_coverage: "Per Person" limit
  - insurance_self_insured: "Yes" or "No" - is the provider self-insured?
- DO NOT return null for insurance fields - there is always at least one policy

### PRACTICE LOCATION:
- Look in "PRACTICE LOCATIONS" section
- practice_location_name should be "Positive Behavior Supports Corporation - [Region]"

### SPECIALTY INFORMATION:
- Look in "SPECIALTY INFORMATION" section
- Primary specialty format: "Name (TaxonomyCode)" e.g., "Behavior Analyst (103K00000X)"

### CREDENTIALING CONTACT:
- Look in "CREDENTIALING CONTACT" or "CAQH CREDENTIALING CONTACT" section
- Extract ALL fields: first_name, last_name, address, city, state, zip, phone, fax, email
- Address may be in a separate table/row from the name - still extract it
- Common address for PBS: "7108 S Kanner Hwy, Stuart, FL 34997"

### GENERAL RULES:
- Preserve exact date formats (MM/DD/YYYY or M/D/YYYY)
- Return null if field cannot be found
- For each field, provide value and confidence (0.0-1.0)

Return a JSON object with this structure:
{
    "field_name": {
        "value": "extracted value or null",
        "confidence": 0.95
    }
}"""

    field_list = "\n".join([f"- {f}" for f in fields])
    user_prompt = f"""Extract these {len(fields)} fields from the CAQH Data Summary:

{field_list}

Document text (first 60,000 characters):
```
{ocr_text[:60000]}
```

Return ONLY a valid JSON object with the extracted values and confidence scores."""

    start_time = time.time()

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
    )

    elapsed_time = time.time() - start_time
    result = json.loads(response.choices[0].message.content)

    usage = response.usage
    if tracker:
        tracker.log_gpt_usage(
            usage.prompt_tokens,
            usage.completion_tokens,
            "gpt-5-mini",
            "cron_extraction"
        )

    return {
        "fields": result,
        "tokens": {
            "prompt": usage.prompt_tokens,
            "completion": usage.completion_tokens,
            "total": usage.total_tokens,
        },
        "elapsed_seconds": round(elapsed_time, 2)
    }


def get_field_status(data: dict) -> str:
    """Determine field status based on extraction result."""
    if not data or not data.get("value"):
        return "NOT_FOUND"
    confidence = data.get("confidence", 0)
    if confidence >= 0.90:
        return "EXTRACTED"
    elif confidence >= 0.70:
        return "LOW_CONFIDENCE"
    return "VERY_LOW_CONFIDENCE"


# =============================================================================
# Email Post-Processing (Fix OCR Artifacts)
# =============================================================================
# Mistral OCR sometimes introduces artifacts in email addresses:
# - Rogue spaces: "rrp inero@teampbs.com" instead of "rrpinero@teampbs.com"
# - Character swaps: "rptinero" instead of "rrpinero"
# This function cleans email fields after extraction.
# =============================================================================

# List of email fields that should be cleaned
EMAIL_FIELDS = [
    "practice_location_email",
    "credentialing_contact_email",
    "billing_contact_email",
]


def clean_email(email: str) -> str:
    """
    Clean an email address by removing OCR artifacts.

    Args:
        email: Raw email string from extraction

    Returns:
        Cleaned email string
    """
    if not email or not isinstance(email, str):
        return email

    # Remove any spaces in the email (common OCR artifact)
    email = email.replace(" ", "")

    # Validate it still looks like an email
    if "@" not in email:
        return email

    return email


def post_process_extraction(fields: dict) -> dict:
    """
    Post-process extracted fields to fix common OCR artifacts.

    Currently handles:
    - Email addresses with rogue spaces

    Args:
        fields: Dictionary of extracted fields from GPT-5-mini

    Returns:
        Cleaned fields dictionary
    """
    if not fields:
        return fields

    cleaned_count = 0

    for field_name in EMAIL_FIELDS:
        if field_name in fields and fields[field_name]:
            field_data = fields[field_name]
            if isinstance(field_data, dict) and field_data.get("value"):
                original_value = field_data["value"]
                cleaned_value = clean_email(original_value)

                if cleaned_value != original_value:
                    logger.info(f"Email cleaned: '{original_value}' -> '{cleaned_value}'")
                    field_data["value"] = cleaned_value
                    # Boost confidence slightly since we fixed a known issue
                    if field_data.get("confidence", 0) < 0.85:
                        field_data["confidence"] = min(0.85, field_data.get("confidence", 0) + 0.2)
                    cleaned_count += 1

    if cleaned_count > 0:
        logger.info(f"Post-processing: cleaned {cleaned_count} email field(s)")

    return fields


def categorize_fields(fields: dict) -> dict:
    """Organize fields into categories for the report viewer."""
    categories = {
        "Provider Identification": [
            "first_name", "middle_name", "last_name", "suffix",
            "date_of_birth", "gender", "ssn", "individual_npi", "caqh_number"
        ],
        "Professional Identification": [
            "medicaid_id", "professional_license_number", "professional_license_expiration_date"
        ],
        "Practice Location": [
            "practice_location_name", "practice_location_address", "practice_location_city",
            "practice_location_state", "practice_location_zip", "practice_location_phone",
            "practice_location_email"
        ],
        "Insurance Information": [
            "insurance_policy_number", "insurance_carrier_name", "insurance_covered_location",
            "insurance_current_effective_date", "insurance_current_expiration_date",
            "insurance_each_occurrence", "insurance_general_aggregate", "insurance_individual_coverage",
            "insurance_self_insured",
            "insurance_address_street_1", "insurance_address_street_2", "insurance_address_city",
            "insurance_address_state", "insurance_address_zip", "insurance_address_country",
            "insurance_phone", "insurance_fax"
        ],
        "Specialty Information": [
            "primary_specialty", "secondary_specialty", "board_certified",
            "certifying_board_name", "initial_certification_date", "certification_expiration_date"
        ],
        "Education": [
            "professional_school_name", "graduation_date", "undergraduate_school_name",
            "undergraduate_degree", "undergraduate_graduation_date"
        ],
        "Demographics": [
            "birth_city", "birth_state", "birth_country", "home_address_street",
            "home_address_city", "home_address_state", "home_address_zip", "race_ethnicity"
        ],
        "Credentialing Contact": [
            "credentialing_contact_first_name", "credentialing_contact_last_name",
            "credentialing_contact_address", "credentialing_contact_city",
            "credentialing_contact_state", "credentialing_contact_zip",
            "credentialing_contact_phone", "credentialing_contact_fax",
            "credentialing_contact_email"
        ],
        "Billing Contact": [
            "billing_contact_first_name", "billing_contact_last_name",
            "billing_contact_address", "billing_contact_city", "billing_contact_state",
            "billing_contact_zip", "billing_contact_phone", "billing_contact_fax",
            "billing_contact_email"
        ],
        "Training": ["cultural_competency_training"]
    }

    result = {}
    for category, field_names in categories.items():
        category_fields = {}
        for name in field_names:
            data = fields.get(name, {})
            category_fields[name] = {
                "extracted_value": data.get("value") if data else None,
                "confidence": round(data.get("confidence", 0), 2) if data else 0,
                "status": get_field_status(data) if data else "NOT_FOUND"
            }
        result[category] = category_fields
    return result


def detect_multiple_insurance_policies(ocr_text: str) -> tuple[bool, int]:
    """
    Detect if a CAQH document contains multiple insurance policies.

    Multiple policies are normal and acceptable per Christian (Feb 2026).
    Our extraction selects the best PBS policy with the furthest expiration date.
    This detection is used for informational logging only - it does NOT block approval.

    Args:
        ocr_text: The full OCR text from the document

    Returns:
        Tuple of (has_multiple_policies, count)
    """
    if not ocr_text:
        return False, 0

    # Pattern to match "Policy Number" field headers in CAQH format
    # The CAQH format shows "Policy Number :" or "Policy Number:" as field labels
    policy_patterns = [
        r'Policy\s+Number\s*:',  # "Policy Number :" or "Policy Number:"
        r'Policy\s*#\s*:',       # "Policy #:"
        r'Policy\s+No\s*\.?\s*:', # "Policy No:" or "Policy No.:"
    ]

    total_count = 0
    for pattern in policy_patterns:
        matches = re.findall(pattern, ocr_text, re.IGNORECASE)
        total_count += len(matches)

    # If we find more than 1 policy number field, there are multiple policies
    has_multiple = total_count > 1

    if has_multiple:
        logger.info(f"Detected {total_count} insurance policy entries in document")

    return has_multiple, total_count


def generate_extraction_report(
    extraction_result: dict,
    file_name: str,
    sharepoint_item_id: int = None,
    ocr_chars: int = 0,
    processing_time_ms: int = 0,
    ocr_text: str = None,
) -> dict:
    """Generate a JSON report from extraction results with business rules validation."""
    fields = extraction_result.get("fields", {})

    extracted_count = sum(1 for f in fields.values() if f and f.get("value"))
    high_confidence_count = sum(
        1 for f in fields.values() if f and f.get("confidence", 0) >= 0.90
    )
    low_confidence_count = sum(
        1 for f in fields.values() if f and f.get("value") and f.get("confidence", 0) < 0.70
    )

    confidences = [f.get("confidence", 0) for f in fields.values() if f and f.get("value")]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0

    categorized_fields = categorize_fields(fields)

    # =========================================================================
    # Business Rules Validation (NEW - Jan 2026)
    # =========================================================================
    # Instead of determining status purely from extraction confidence,
    # we now apply PBS business rules to validate the extracted content.
    # This catches issues like:
    # - Missing required fields
    # - Expired licenses/certifications
    # - Practice location not being PBS
    # - Cultural competency not marked "Yes"
    # =========================================================================

    # Flatten fields for validation (convert nested format to simple key-value)
    flat_fields_for_validation = {
        name: data.get("value") if isinstance(data, dict) else data
        for name, data in fields.items()
    }

    # Run business rules validation
    validator = BusinessRulesValidator()
    validation_result = validator.validate(flat_fields_for_validation)

    # =========================================================================
    # Informational: Multiple Insurance Policies
    # =========================================================================
    # Multiple insurance policies are normal and OK per Christian (Feb 2026).
    # Our extraction already selects the correct PBS policy with the furthest
    # expiration date. Multiple policies should NOT block AI_APPROVED status.
    # We log it as INFO for awareness but it does not affect the decision.
    # =========================================================================
    if ocr_text:
        has_multiple_policies, policy_count = detect_multiple_insurance_policies(ocr_text)
        if has_multiple_policies:
            logger.info(f"Document contains {policy_count} insurance policies - extraction selected best PBS policy (this is normal)")

    # Use validation result to determine final status
    # Status logic:
    #   - ERROR → AI_REJECTED
    #   - >2 warnings → NEEDS_HUMAN_REVIEW
    #   - else → AI_APPROVED
    # Note: Multiple insurance policies do NOT block approval (per Christian, Feb 2026)
    from src.validation.business_rules_validator import ValidationStatus
    if validation_result.error_count > 0:
        validation_result.status = ValidationStatus.AI_REJECTED
    elif validation_result.warning_count > 2:
        validation_result.status = ValidationStatus.NEEDS_HUMAN_REVIEW

    status = validation_result.status.value

    # Combine extraction confidence with validation confidence
    # Validation confidence is 0-100, extraction is 0-1
    extraction_confidence_pct = avg_confidence * 100
    combined_confidence = (extraction_confidence_pct + validation_result.confidence_score) / 2

    # Log validation results
    logger.info(f"Validation: {status} (extraction={extraction_confidence_pct:.1f}%, validation={validation_result.confidence_score:.1f}%)")
    if validation_result.error_count > 0:
        logger.info(f"  Errors: {validation_result.error_count}")
        for issue in [i for i in validation_result.issues if i.severity.value == "error"][:3]:
            logger.info(f"    - {issue.field_name}: {issue.message}")
    if validation_result.warning_count > 0:
        logger.info(f"  Warnings: {validation_result.warning_count}")

    return {
        "version": "1.1",  # Updated version for validation-enabled reports
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "processing_time_ms": processing_time_ms,
        "document": {
            "file_name": file_name,
            "sharepoint_item_id": sharepoint_item_id,
            "ocr_characters": ocr_chars,
            "extraction_method": "Mistral OCR + GPT-5-mini"
        },
        "result": {
            "status": status,
            "confidence_score": round(combined_confidence, 1),
            "extraction_confidence": round(extraction_confidence_pct, 1),
            "validation_confidence": round(validation_result.confidence_score, 1),
            "requires_human_review": status == "NEEDS_HUMAN_REVIEW",
            "total_fields": len(ALL_EXTRACTION_FIELDS),
            "extracted_count": extracted_count,
            "high_confidence_count": high_confidence_count,
            "low_confidence_count": low_confidence_count
        },
        "validation": {
            "status": status,
            "summary": validation_result.summary,
            "error_count": validation_result.error_count,
            "warning_count": validation_result.warning_count,
            "issues": [issue.to_dict() for issue in validation_result.issues]
        },
        "tokens": extraction_result.get("tokens", {}),
        "fields": categorized_fields,
        "fields_flat": {
            name: {
                "extracted_value": data.get("value") if data else None,
                "confidence": round(data.get("confidence", 0), 2) if data else 0,
                "status": get_field_status(data) if data else "NOT_FOUND"
            }
            for name, data in fields.items()
        }
    }


class CronRunner:
    """
    Main runner for the CAQH document processing pipeline.

    This class orchestrates the full workflow:
    1. Connect to PBS SharePoint Middleware API
    2. Get unprocessed items from SharePoint
    3. For each item:
       - Download PDF
       - Extract text (OCR if needed)
       - Extract and validate fields
       - Generate JSON report
       - Upload results back to SharePoint
       - Send PBS Live notification to submitter
    """

    def __init__(
        self,
        client: PBSMiddlewareClient,
        pbs_live_client: Optional[PBSLiveClient] = None,
        dry_run: bool = False
    ):
        """
        Initialize the cron runner.

        Args:
            client: Configured PBSMiddlewareClient instance
            pbs_live_client: Optional PBSLiveClient for notifications
            dry_run: If True, don't write results back to SharePoint
        """
        self.client = client
        self.pbs_live_client = pbs_live_client
        self.dry_run = dry_run
        self.stats = {
            'processed': 0,
            'failed': 0,
            'skipped': 0,
            'notifications_sent': 0,
            'notifications_failed': 0
        }

    def run(self, item_id: Optional[int] = None) -> dict:
        """
        Run the processing pipeline.

        Args:
            item_id: If provided, only process this specific item

        Returns:
            Dictionary with processing statistics
        """
        start_time = datetime.now()
        logger.info("=" * 60)
        logger.info(f"CAQH Cron Runner started at {start_time.isoformat()}")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info("=" * 60)

        try:
            if item_id:
                # Process single item
                logger.info(f"Processing single item: {item_id}")
                item = self.client.get_item_by_id(item_id)
                self._process_item(item)
            else:
                # Process all unprocessed items
                items = self.client.get_unprocessed_items()
                logger.info(f"Found {len(items)} unprocessed items")

                # Filter by allowed regions
                allowed_regions = get_allowed_regions()
                if allowed_regions:
                    filtered_items = []
                    for item in items:
                        item_region = (item.pbs_region or "").strip().lower()
                        if item_region in allowed_regions:
                            filtered_items.append(item)
                        else:
                            region_display = item.pbs_region or "(none)"
                            logger.info(f"Skipping item {item.item_id} ({item.file_name}) - region '{region_display}' not in allowed list")
                            self.stats['skipped'] += 1
                    logger.info(f"After region filter: {len(filtered_items)} items to process ({len(items) - len(filtered_items)} skipped)")
                    items = filtered_items

                for item in items:
                    self._process_item(item)

        except AuthenticationError as e:
            logger.error(f"Authentication failed: {e}")
            raise
        except APIError as e:
            logger.error(f"API error: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            raise

        finally:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.info("=" * 60)
            logger.info(f"CAQH Cron Runner completed at {end_time.isoformat()}")
            logger.info(f"Duration: {duration:.1f} seconds")
            logger.info(f"Processed: {self.stats['processed']}")
            logger.info(f"Failed: {self.stats['failed']}")
            logger.info(f"Skipped: {self.stats['skipped']}")
            logger.info(f"Notifications sent: {self.stats['notifications_sent']}")
            logger.info(f"Notifications failed: {self.stats['notifications_failed']}")
            logger.info("=" * 60)

        return self.stats

    def _process_item(self, item: SharePointItem):
        """
        Process a single SharePoint item using Mistral OCR + GPT-5-mini pipeline.

        Args:
            item: SharePointItem to process
        """
        logger.info("-" * 40)
        logger.info(f"Processing item {item.item_id}: {item.file_name}")
        logger.debug(f"Item details - file_ref: {item.file_ref}, author_login: {item.author_login}, author_email: {item.author_email}")

        # Track processing time
        item_start_time = datetime.now()
        tracker = CostTracker()

        try:
            # Step 1: Download PDF
            logger.info("[Step 1] Downloading PDF...")
            pdf_bytes = self.client.download_document(item.file_ref)
            logger.info(f"Downloaded {len(pdf_bytes):,} bytes")

            # Save to temp file for OCR
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            try:
                # Step 2: Run Mistral Document AI OCR
                logger.info("[Step 2] Running Mistral Document AI OCR...")
                ocr = MistralOCR()
                if not ocr.is_configured():
                    raise RuntimeError("Mistral OCR not configured - check AZURE_OPENAI_API_KEY")

                ocr_start = time.time()
                ocr_text = ocr.extract_text(tmp_path)
                ocr_elapsed = time.time() - ocr_start

                logger.info(f"Extracted {len(ocr_text):,} characters in {ocr_elapsed:.1f}s")

                # Estimate pages for cost tracking
                estimated_pages = max(1, len(ocr_text) // 3000)
                tracker.log_mistral_ocr(estimated_pages, item.file_name)

                # Step 3: Run GPT-5-mini Field Extraction
                logger.info(f"[Step 3] Running GPT-5-mini extraction ({len(ALL_EXTRACTION_FIELDS)} fields)...")
                extraction_result = extract_with_gpt5_mini(ocr_text, ALL_EXTRACTION_FIELDS, tracker)

                logger.info(f"Tokens: {extraction_result['tokens']['total']:,}")
                logger.info(f"Extraction time: {extraction_result['elapsed_seconds']:.1f}s")

                # Count extracted fields
                fields = extraction_result.get("fields", {})

                # Post-process to clean OCR artifacts (especially emails with rogue spaces)
                fields = post_process_extraction(fields)
                extraction_result["fields"] = fields  # Update the result with cleaned fields

                extracted_count = sum(1 for f in fields.values() if f and f.get("value"))
                logger.info(f"Extracted {extracted_count}/{len(ALL_EXTRACTION_FIELDS)} fields")

            finally:
                os.unlink(tmp_path)

            # Calculate processing time
            processing_time_ms = int((datetime.now() - item_start_time).total_seconds() * 1000)

            # Step 4: Generate JSON report
            logger.info("[Step 4] Generating JSON report...")
            json_report = generate_extraction_report(
                extraction_result=extraction_result,
                file_name=item.file_name,
                sharepoint_item_id=item.item_id,
                ocr_chars=len(ocr_text),
                processing_time_ms=processing_time_ms,
                ocr_text=ocr_text  # For multiple insurance policy detection
            )

            json_report_str = json.dumps(json_report, indent=2, ensure_ascii=True)
            validation_status = json_report["result"]["status"]
            logger.info(f"Generated JSON report ({len(json_report_str):,} chars), status: {validation_status}")

            # Step 5: Write results back to SharePoint
            if self.dry_run:
                logger.info("[DRY RUN] Would mark item as processed")
                logger.info(f"[DRY RUN] JSON status: {validation_status}")
                logger.info(f"[DRY RUN] JSON report preview: {json_report_str[:300]}...")
            else:
                logger.info("[Step 5] Updating SharePoint...")
                self.client.mark_as_processed_with_json(
                    item_id=item.item_id,
                    json_report=json_report_str,
                    validation_status=validation_status,
                )
                logger.info(f"Successfully marked as processed (status: {validation_status})")

            # Step 6: Send PBS Live notification to submitter
            self._send_notification(item, json_report, validation_status)

            # Log cost summary
            tracker.print_summary()

            self.stats['processed'] += 1

        except Exception as e:
            error_str = str(e)
            logger.exception(f"Failed to process item {item.item_id}: {e}")

            # Check if this is a "too many pages" error from Mistral OCR
            if "document_parser_too_many_pages" in error_str or "too_many_pages" in error_str:
                logger.info(f"Marking item {item.item_id} as PROCESSING_ERROR (document too large)")

                # Extract page count from error message if possible
                import re
                page_match = re.search(r'has (\d+) pages', error_str)
                page_count = page_match.group(1) if page_match else "unknown"

                # Create error report
                error_report = {
                    "version": "1.2",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "processing_time_ms": 0,
                    "document": {
                        "file_name": item.file_name,
                        "sharepoint_item_id": item.item_id,
                    },
                    "result": {
                        "status": "PROCESSING_ERROR",
                        "error": f"Document has {page_count} pages, exceeds 30-page limit for OCR processing",
                        "requires_human_review": True,
                    },
                    "validation": {
                        "status": "PROCESSING_ERROR",
                        "summary": f"Cannot process: document has {page_count} pages (max 30)",
                        "error_count": 1,
                        "warning_count": 0,
                        "issues": [{
                            "field_name": "document",
                            "message": f"Document has {page_count} pages, which exceeds the 30-page limit. Please upload a shorter document or contact support.",
                            "severity": "ERROR",
                            "rule_name": "document_page_limit"
                        }]
                    },
                    "fields": {},
                    "fields_flat": {}
                }

                if not self.dry_run:
                    try:
                        self.client.mark_as_processed_with_json(
                            item_id=item.item_id,
                            json_report=json.dumps(error_report, indent=2),
                            validation_status="PROCESSING_ERROR"
                        )
                        logger.info(f"Item {item.item_id} marked as PROCESSING_ERROR")
                        self.stats['processed'] += 1  # Count as processed (won't retry)
                    except Exception as update_error:
                        logger.error(f"Failed to mark item as error: {update_error}")
                        self.stats['failed'] += 1
                else:
                    logger.info(f"[DRY RUN] Would mark item {item.item_id} as PROCESSING_ERROR")
                    self.stats['processed'] += 1
            else:
                self.stats['failed'] += 1

    def _send_notification(
        self,
        item: SharePointItem,
        json_report: dict,
        validation_status: str
    ):
        """
        Send PBS Live notification to the submitter.

        Args:
            item: SharePointItem with author info
            json_report: Generated JSON report dict
            validation_status: AI_APPROVED, AI_REJECTED, etc.
        """
        # Skip if no PBS Live client configured
        if not self.pbs_live_client:
            logger.debug("PBS Live client not configured, skipping notification")
            return

        # Skip if dry run
        if self.dry_run:
            logger.info(f"[DRY RUN] Would send PBS Live notification to {item.author_login} for {item.file_name}")
            return

        # Get submitter username
        username = item.author_login
        if not username:
            logger.warning(f"No author username for item {item.item_id}, skipping notification")
            return

        # Log the file_name for debugging
        logger.debug(f"Notification details - username: {username}, file_name: '{item.file_name}', item_id: {item.item_id}")

        try:
            if validation_status == "AI_APPROVED":
                logger.info(f"Sending approval notification to {username} for {item.file_name}...")
                success = self.pbs_live_client.send_approval_notification(
                    username=username,
                    file_name=item.file_name,
                    sharepoint_item_id=item.item_id
                )

            elif validation_status == "AI_REJECTED":
                # Extract issues from JSON report (issues are nested under 'validation')
                validation_data = json_report.get('validation', {})
                issues = validation_data.get('issues', [])
                issue_messages = [issue.get('message', str(issue)) for issue in issues[:10]]  # Limit to 10

                # Step 1: Send personal rejection notification (non-fatal if user has no PBS Live room)
                try:
                    logger.info(f"Sending rejection notification to {username} for {item.file_name} with {len(issue_messages)} issues...")
                    success = self.pbs_live_client.send_rejection_notification(
                        username=username,
                        issues=issue_messages,
                        file_name=item.file_name,
                        sharepoint_item_id=item.item_id
                    )
                except Exception as e:
                    # "Room not found" = user doesn't have PBS Live room yet, but group creation will still work
                    logger.warning(f"Personal notification failed for {username} (non-fatal, will still create group): {e}")
                    success = False

                # Step 2: Create CAQH Review group for direct communication (always attempt)
                try:
                    room_id = self.pbs_live_client.create_caqh_review_group(
                        submitter_username=username,
                        credentialer_usernames=["chelenius"],  # Christian - credentialing team
                        file_name=item.file_name,
                        submission_id=item.item_id,
                        issues=issue_messages
                    )
                    if room_id:
                        logger.info(f"CAQH Review group created/updated: {room_id}")
                        # Count as success if group was created, even if personal notification failed
                        if not success:
                            success = True
                            logger.info(f"User {username} notified via CAQH Review group (personal message failed)")
                except Exception as e:
                    logger.warning(f"Failed to create CAQH Review group (non-fatal): {e}")

            else:
                logger.warning(f"Unknown validation status: {validation_status}, skipping notification")
                return

            if success:
                self.stats['notifications_sent'] += 1
                logger.info(f"PBS Live notification sent successfully to {username}")
            else:
                self.stats['notifications_failed'] += 1
                logger.error(f"Failed to send PBS Live notification to {username}")

        except PBSLiveError as e:
            self.stats['notifications_failed'] += 1
            logger.error(f"PBS Live error for {username}: {e}")
        except Exception as e:
            self.stats['notifications_failed'] += 1
            logger.exception(f"Unexpected error sending notification to {username}: {e}")


def main():
    """Main entry point for the cron runner."""
    parser = argparse.ArgumentParser(
        description='CAQH Data Summary Review - Automated Processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without writing results back to SharePoint'
    )

    parser.add_argument(
        '--item-id',
        type=int,
        help='Process only this specific item ID'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--log-file',
        type=str,
        help='Path to log file (in addition to stdout)'
    )

    parser.add_argument(
        '--no-notifications',
        action='store_true',
        help='Disable PBS Live notifications'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose, log_file=args.log_file)

    # Check for required environment variables (Client Credentials Flow + Azure AI)
    required_vars = [
        'PBS_CLIENT_ID', 'PBS_CLIENT_SECRET',
        'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_ENDPOINT'
    ]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these variables before running the cron job.")
        logger.error("")
        logger.error("Example .env file:")
        logger.error("  # SharePoint Middleware")
        logger.error("  PBS_CLIENT_ID=your-azure-app-client-id")
        logger.error("  PBS_CLIENT_SECRET=your-azure-app-client-secret")
        logger.error("")
        logger.error("  # Azure AI (Mistral OCR + GPT-5-mini)")
        logger.error("  AZURE_OPENAI_ENDPOINT=https://your-endpoint.cognitiveservices.azure.com/")
        logger.error("  AZURE_OPENAI_API_KEY=your-api-key")
        sys.exit(1)

    # Log configuration
    logger.info(f"Azure AI Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT')}")
    logger.info(f"Pipeline: Mistral Document AI OCR + GPT-5-mini")

    # Log region filtering config
    allowed_regions = get_allowed_regions()
    if allowed_regions:
        logger.info(f"Region filter: {len(allowed_regions)} regions enabled")
        logger.debug(f"Allowed regions: {', '.join(sorted(allowed_regions))}")
    else:
        logger.info("Region filter: DISABLED (all regions allowed)")

    try:
        # Create SharePoint client from environment variables
        client = create_client_from_env()

        # Create PBS Live client for notifications
        if args.no_notifications:
            logger.info("PBS Live notifications disabled via --no-notifications flag")
            pbs_live_client = None
        else:
            try:
                pbs_live_client = create_pbs_live_client_from_env()
                logger.info("PBS Live notifications enabled")
            except Exception as e:
                logger.warning(f"PBS Live client not available: {e}")
                logger.warning("Continuing without PBS Live notifications")
                pbs_live_client = None

        # Run the processor
        runner = CronRunner(
            client=client,
            pbs_live_client=pbs_live_client,
            dry_run=args.dry_run
        )
        stats = runner.run(item_id=args.item_id)

        # Exit with error code if any failures
        if stats['failed'] > 0:
            sys.exit(1)

    except AuthenticationError as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(2)
    except APIError as e:
        logger.error(f"API error: {e}")
        sys.exit(3)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(4)


if __name__ == '__main__':
    main()
