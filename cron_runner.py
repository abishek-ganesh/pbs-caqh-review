#!/usr/bin/env python3
"""
CAQH Data Summary Review - Cron Runner

This script is the main entry point for the automated CAQH review process.
It runs on a schedule (via cron) to:
1. Fetch unprocessed PDF documents from SharePoint
2. Extract and validate fields using our extraction engine
3. Generate HTML reports
4. Write results back to SharePoint

Cron Setup (every 5 minutes):
    */5 * * * * /usr/bin/python3 /opt/caqh-reviewer/cron_runner.py >> /opt/caqh-reviewer/logs/cron.log 2>&1

Environment Variables Required:
    PBS_API_BASE_URL        - Base URL of the PBS Enterprise API
    PBS_API_ACCESS_TOKEN    - Azure AD bearer token
    PBS_SHAREPOINT_SITE_URL - SharePoint site URL for CAQH library
    PBS_CAQH_LIBRARY_NAME   - Document library name (optional, defaults to "CAQH library Test")

Usage:
    # Run normally
    python cron_runner.py

    # Dry run (no updates to SharePoint)
    python cron_runner.py --dry-run

    # Process specific item by ID
    python cron_runner.py --item-id 123

    # Verbose logging
    python cron_runner.py --verbose
"""

import os
import sys
import argparse
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.sharepoint import PBSEnterpriseClient, create_client_from_env, SharePointItem
from src.sharepoint.pbs_api_client import APIError, AuthenticationError
from src.extraction.field_extractor import extract_all_fields_from_text
from src.extraction.pdf_reader import read_pdf_text
from src.validation.validation_engine import ValidationEngine
from src.utils.html_generator import generate_html_output


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

    # Reduce noise from requests library
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


class CronRunner:
    """
    Main runner for the CAQH document processing pipeline.

    This class orchestrates the full workflow:
    1. Connect to PBS Enterprise API
    2. Get unprocessed items from SharePoint
    3. For each item:
       - Download PDF
       - Extract text (OCR if needed)
       - Extract and validate fields
       - Generate HTML report
       - Upload results back to SharePoint
    """

    def __init__(self, client: PBSEnterpriseClient, dry_run: bool = False):
        """
        Initialize the cron runner.

        Args:
            client: Configured PBSEnterpriseClient instance
            dry_run: If True, don't write results back to SharePoint
        """
        self.client = client
        self.dry_run = dry_run
        self.stats = {
            'processed': 0,
            'failed': 0,
            'skipped': 0
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
            logger.info("=" * 60)

        return self.stats

    def _process_item(self, item: SharePointItem):
        """
        Process a single SharePoint item.

        Args:
            item: SharePointItem to process
        """
        logger.info("-" * 40)
        logger.info(f"Processing item {item.item_id}: {item.file_name}")

        try:
            # Step 1: Download PDF
            logger.info("Downloading PDF...")
            pdf_bytes = self.client.download_pdf(item.file_ref)
            logger.info(f"Downloaded {len(pdf_bytes)} bytes")

            # Step 2: Extract text from PDF
            logger.info("Extracting text from PDF...")
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            try:
                text = read_pdf_text(tmp_path)
                logger.info(f"Extracted {len(text)} characters")
            finally:
                os.unlink(tmp_path)

            # Step 3: Extract fields
            logger.info("Extracting fields...")
            extraction_result = extract_all_fields_from_text(text)
            logger.info(f"Extracted {len(extraction_result.field_results)} fields")

            # Step 4: Validate fields
            logger.info("Validating fields...")
            validator = ValidationEngine()
            validation_result = validator.validate_document(extraction_result)
            logger.info(f"Validation complete: {validation_result.overall_status}")

            # Step 5: Generate HTML report
            logger.info("Generating HTML report...")
            html_report = generate_html_output(validation_result, item.file_name)
            logger.info(f"Generated HTML report ({len(html_report)} chars)")

            # Step 6: Write results back to SharePoint
            if self.dry_run:
                logger.info("[DRY RUN] Would mark item as processed")
                logger.info(f"[DRY RUN] HTML report preview: {html_report[:200]}...")
            else:
                logger.info("Marking item as processed...")
                self.client.mark_as_processed(item.item_id, html_report)
                logger.info("Successfully marked as processed")

            self.stats['processed'] += 1

        except Exception as e:
            logger.exception(f"Failed to process item {item.item_id}: {e}")
            self.stats['failed'] += 1


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

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose, log_file=args.log_file)

    # Check for required environment variables
    required_vars = ['PBS_API_BASE_URL', 'PBS_API_ACCESS_TOKEN', 'PBS_SHAREPOINT_SITE_URL']
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these variables before running the cron job.")
        logger.error("")
        logger.error("Example .env file:")
        logger.error("  PBS_API_BASE_URL=https://api.teampbs.com")
        logger.error("  PBS_API_ACCESS_TOKEN=your-azure-ad-token")
        logger.error("  PBS_SHAREPOINT_SITE_URL=https://sharepoint.teampbs.com/CAQH%20Data%20Summary")
        logger.error("  PBS_CAQH_LIBRARY_NAME=CAQH library Test")
        sys.exit(1)

    try:
        # Create client from environment variables
        client = create_client_from_env()

        # Run the processor
        runner = CronRunner(client, dry_run=args.dry_run)
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
