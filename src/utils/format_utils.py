"""
Format Validation Utilities

Provides helper functions for validating field formats including:
- SSN (Social Security Number)
- NPI (National Provider Identifier) with Luhn checksum
- Phone numbers
- Email addresses
- Zip codes
- Tax IDs
- State abbreviations
"""

import re
from typing import Optional
from ..config.constants import REGEX_PATTERNS, US_STATES


def validate_ssn(ssn: str) -> bool:
    """
    Validate Social Security Number format.

    Accepts:
    - 123-45-6789
    - 123456789

    Args:
        ssn: Social Security Number to validate

    Returns:
        True if valid SSN format, False otherwise
    """
    if not ssn or not isinstance(ssn, str):
        return False

    # Remove any whitespace
    ssn = ssn.strip()

    # Check pattern
    pattern = REGEX_PATTERNS["ssn"]
    return bool(re.match(pattern, ssn))


def validate_npi(npi: str) -> bool:
    """
    Validate National Provider Identifier (NPI) format and checksum.

    NPI must be:
    - Exactly 10 digits
    - Pass Luhn checksum validation with "80840" prefix

    Per CMS specification, NPIs use the constant prefix "80840"
    (US Health Industry Number) when calculating the Luhn checksum.

    Args:
        npi: NPI to validate

    Returns:
        True if valid NPI, False otherwise
    """
    if not npi or not isinstance(npi, str):
        return False

    # Remove any whitespace or hyphens
    npi = npi.strip().replace("-", "")

    # Check basic format (10 digits)
    pattern = REGEX_PATTERNS["npi"]
    if not re.match(pattern, npi):
        return False

    # Validate Luhn checksum with US Health Industry Number prefix
    # Per CMS spec: prepend "80840" to NPI for Luhn calculation
    full_number = "80840" + npi
    return _validate_luhn_checksum(full_number)


def _validate_luhn_checksum(number: str) -> bool:
    """
    Validate a number using the Luhn algorithm.

    Used for NPI validation.

    Args:
        number: Number string to validate

    Returns:
        True if checksum is valid, False otherwise
    """
    def luhn_digit(n):
        """Double a digit and subtract 9 if result > 9"""
        doubled = n * 2
        return doubled if doubled < 10 else doubled - 9

    digits = [int(d) for d in number]

    # Luhn algorithm: process from right to left
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 0:
            # Check digit and every other digit from right (don't double)
            checksum += digit
        else:
            # Double every second digit from right
            checksum += luhn_digit(digit)

    return checksum % 10 == 0


def validate_phone(phone: str) -> bool:
    """
    Validate phone number format.

    Accepts various formats:
    - 555-123-4567
    - (555) 123-4567
    - 555.123.4567
    - 5551234567
    - +1-555-123-4567

    Args:
        phone: Phone number to validate

    Returns:
        True if valid phone format, False otherwise
    """
    if not phone or not isinstance(phone, str):
        return False

    # Remove whitespace
    phone = phone.strip()

    # Check pattern
    pattern = REGEX_PATTERNS["phone"]
    return bool(re.match(pattern, phone))


def validate_email(email: str) -> bool:
    """
    Validate email address format.

    Basic email validation - checks for:
    - Valid characters
    - @ symbol
    - Domain with extension

    Args:
        email: Email address to validate

    Returns:
        True if valid email format, False otherwise
    """
    if not email or not isinstance(email, str):
        return False

    # Remove whitespace
    email = email.strip().lower()

    # Check pattern
    pattern = REGEX_PATTERNS["email"]
    return bool(re.match(pattern, email))


def validate_zip_code(zip_code: str) -> bool:
    """
    Validate ZIP code format.

    Accepts:
    - 12345
    - 12345-6789

    Args:
        zip_code: ZIP code to validate

    Returns:
        True if valid ZIP code format, False otherwise
    """
    if not zip_code or not isinstance(zip_code, str):
        return False

    # Remove whitespace
    zip_code = zip_code.strip()

    # Check pattern
    pattern = REGEX_PATTERNS["zip_code"]
    return bool(re.match(pattern, zip_code))


def validate_state(state: str) -> bool:
    """
    Validate state abbreviation.

    Must be a valid 2-letter US state code.

    Args:
        state: State abbreviation to validate

    Returns:
        True if valid state abbreviation, False otherwise
    """
    if not state or not isinstance(state, str):
        return False

    # Remove whitespace and convert to uppercase
    state = state.strip().upper()

    # Check if in valid states list
    return state in US_STATES


def validate_tax_id(tax_id: str) -> bool:
    """
    Validate Tax ID (EIN) format.

    Accepts:
    - 12-3456789
    - 123456789

    Args:
        tax_id: Tax ID to validate

    Returns:
        True if valid Tax ID format, False otherwise
    """
    if not tax_id or not isinstance(tax_id, str):
        return False

    # Remove whitespace
    tax_id = tax_id.strip()

    # Check pattern
    pattern = REGEX_PATTERNS["tax_id"]
    return bool(re.match(pattern, tax_id))


def normalize_ssn(ssn: str) -> Optional[str]:
    """
    Normalize SSN to standard format (XXX-XX-XXXX).

    Args:
        ssn: SSN to normalize

    Returns:
        Normalized SSN or None if invalid
    """
    if not validate_ssn(ssn):
        return None

    # Remove all non-digit characters
    digits = re.sub(r'\D', '', ssn)

    # Format as XXX-XX-XXXX
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


def normalize_npi(npi: str) -> Optional[str]:
    """
    Normalize NPI to standard format (10 digits).

    Args:
        npi: NPI to normalize

    Returns:
        Normalized NPI or None if invalid
    """
    if not validate_npi(npi):
        return None

    # Remove all non-digit characters
    return re.sub(r'\D', '', npi)


def normalize_phone(phone: str) -> Optional[str]:
    """
    Normalize phone to standard format (XXX-XXX-XXXX).

    Args:
        phone: Phone number to normalize

    Returns:
        Normalized phone or None if invalid
    """
    if not validate_phone(phone):
        return None

    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)

    # Take last 10 digits (removes country code if present)
    digits = digits[-10:]

    # Format as XXX-XXX-XXXX
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


def normalize_zip_code(zip_code: str) -> Optional[str]:
    """
    Normalize ZIP code to standard format.

    Args:
        zip_code: ZIP code to normalize

    Returns:
        Normalized ZIP code or None if invalid
    """
    if not validate_zip_code(zip_code):
        return None

    # Remove all non-digit characters
    digits = re.sub(r'\D', '', zip_code)

    # Format as XXXXX or XXXXX-XXXX
    if len(digits) == 5:
        return digits
    elif len(digits) == 9:
        return f"{digits[:5]}-{digits[5:]}"
    else:
        return None


def normalize_tax_id(tax_id: str) -> Optional[str]:
    """
    Normalize Tax ID to standard format (XX-XXXXXXX).

    Args:
        tax_id: Tax ID to normalize

    Returns:
        Normalized Tax ID or None if invalid
    """
    if not validate_tax_id(tax_id):
        return None

    # Remove all non-digit characters
    digits = re.sub(r'\D', '', tax_id)

    # Format as XX-XXXXXXX
    return f"{digits[:2]}-{digits[2:]}"


def mask_ssn(ssn: str) -> str:
    """
    Mask SSN for logging/display (XXX-XX-1234).

    Args:
        ssn: SSN to mask

    Returns:
        Masked SSN
    """
    if not ssn or not isinstance(ssn, str):
        return "***-**-****"

    # Normalize first
    normalized = normalize_ssn(ssn)
    if not normalized:
        return "***-**-****"

    # Show only last 4 digits
    return f"***-**-{normalized[-4:]}"


def mask_phi(value: str, field_name: str) -> str:
    """
    Mask PHI (Protected Health Information) for logging.

    Args:
        value: Value to mask
        field_name: Name of the field

    Returns:
        Masked value
    """
    if not value:
        return "[REDACTED]"

    # SSN gets special masking
    if field_name.lower() in ["ssn", "social_security_number"]:
        return mask_ssn(value)

    # For other PHI, show only first and last characters
    if len(value) <= 2:
        return "*" * len(value)

    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"
