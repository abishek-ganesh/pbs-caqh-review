"""
Date Validation Utilities

Provides helper functions for date validation including:
- Future date validation (e.g., expiration dates)
- Past date validation (e.g., birth dates, issue dates)
- Date range validation
- Date parsing
"""

from datetime import datetime, date, timedelta
from typing import Union, Optional
import re


def parse_date(date_str: str) -> Optional[date]:
    """
    Parse a date string into a date object.

    Supports multiple common date formats:
    - MM/DD/YYYY
    - M/D/YYYY
    - YYYY-MM-DD
    - MM-DD-YYYY
    - Month DD, YYYY

    Args:
        date_str: String representation of a date

    Returns:
        date object if successfully parsed, None otherwise
    """
    if not date_str or not isinstance(date_str, str):
        return None

    # Remove extra whitespace
    date_str = date_str.strip()

    # Common date formats to try
    formats = [
        "%m/%d/%Y",      # 12/31/2024
        "%m-%d-%Y",      # 12-31-2024
        "%Y-%m-%d",      # 2024-12-31
        "%B %d, %Y",     # December 31, 2024
        "%b %d, %Y",     # Dec 31, 2024
        "%m/%d/%y",      # 12/31/24
        "%m-%d-%y",      # 12-31-24
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    return None


def is_future_date(date_value: Union[str, date, datetime],
                   strict: bool = True) -> bool:
    """
    Check if a date is in the future.

    Used for validating expiration dates (license, insurance, certification).

    Args:
        date_value: Date to check (string, date, or datetime)
        strict: If True, date must be > today. If False, date >= today is ok.

    Returns:
        True if date is in the future, False otherwise
    """
    if isinstance(date_value, str):
        date_value = parse_date(date_value)

    if date_value is None:
        return False

    if isinstance(date_value, datetime):
        date_value = date_value.date()

    today = date.today()

    if strict:
        return date_value > today
    else:
        return date_value >= today


def is_past_date(date_value: Union[str, date, datetime],
                strict: bool = True) -> bool:
    """
    Check if a date is in the past.

    Used for validating birth dates, issue dates, hire dates, etc.

    Args:
        date_value: Date to check (string, date, or datetime)
        strict: If True, date must be < today. If False, date <= today is ok.

    Returns:
        True if date is in the past, False otherwise
    """
    if isinstance(date_value, str):
        date_value = parse_date(date_value)

    if date_value is None:
        return False

    if isinstance(date_value, datetime):
        date_value = date_value.date()

    today = date.today()

    if strict:
        return date_value < today
    else:
        return date_value <= today


def is_valid_date_range(start_date: Union[str, date, datetime],
                       end_date: Union[str, date, datetime]) -> bool:
    """
    Check if a date range is valid (start < end).

    Used for validating insurance effective/expiration dates, etc.

    Args:
        start_date: Start date (string, date, or datetime)
        end_date: End date (string, date, or datetime)

    Returns:
        True if start_date < end_date, False otherwise
    """
    if isinstance(start_date, str):
        start_date = parse_date(start_date)

    if isinstance(end_date, str):
        end_date = parse_date(end_date)

    if start_date is None or end_date is None:
        return False

    if isinstance(start_date, datetime):
        start_date = start_date.date()

    if isinstance(end_date, datetime):
        end_date = end_date.date()

    return start_date < end_date


def is_reasonable_birth_date(birth_date: Union[str, date, datetime]) -> bool:
    """
    Check if a birth date is reasonable for a practitioner.

    Assumes practitioner must be:
    - At least 18 years old
    - No more than 100 years old

    Args:
        birth_date: Birth date to check

    Returns:
        True if birth date is reasonable, False otherwise
    """
    if isinstance(birth_date, str):
        birth_date = parse_date(birth_date)

    if birth_date is None:
        return False

    if isinstance(birth_date, datetime):
        birth_date = birth_date.date()

    today = date.today()

    # Calculate age
    age = today.year - birth_date.year

    # Adjust for birthday not yet occurred this year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1

    # Must be at least 18, no more than 100
    return 18 <= age <= 100


def get_date_difference_days(date1: Union[str, date, datetime],
                             date2: Union[str, date, datetime]) -> Optional[int]:
    """
    Get the difference in days between two dates.

    Args:
        date1: First date
        date2: Second date

    Returns:
        Number of days between dates (positive if date2 > date1)
    """
    if isinstance(date1, str):
        date1 = parse_date(date1)

    if isinstance(date2, str):
        date2 = parse_date(date2)

    if date1 is None or date2 is None:
        return None

    if isinstance(date1, datetime):
        date1 = date1.date()

    if isinstance(date2, datetime):
        date2 = date2.date()

    delta = date2 - date1
    return delta.days


def format_date_for_display(date_value: Union[str, date, datetime]) -> str:
    """
    Format a date for user-friendly display.

    Args:
        date_value: Date to format

    Returns:
        Formatted date string (MM/DD/YYYY)
    """
    if isinstance(date_value, str):
        date_value = parse_date(date_value)

    if date_value is None:
        return "Invalid date"

    if isinstance(date_value, datetime):
        date_value = date_value.date()

    return date_value.strftime("%m/%d/%Y")


def is_within_timeframe(date_value: Union[str, date, datetime],
                       days: int) -> bool:
    """
    Check if a date is within N days of today (past or future).

    Useful for duplicate detection (within 15 minutes = ~0.01 days).

    Args:
        date_value: Date to check
        days: Number of days

    Returns:
        True if date is within timeframe, False otherwise
    """
    if isinstance(date_value, str):
        # For datetime strings, try parsing as datetime first
        try:
            date_value = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
        except:
            date_value = parse_date(date_value)

    if date_value is None:
        return False

    if isinstance(date_value, date) and not isinstance(date_value, datetime):
        date_value = datetime.combine(date_value, datetime.min.time())

    now = datetime.now()
    delta = abs((date_value - now).total_seconds() / 86400)  # Convert to days

    return delta <= days
