"""
Field-specific extraction and post-processing functions.

Consolidates field-specific logic that was scattered throughout _extract_using_label function,
making the main extraction logic cleaner and more maintainable.
"""

import re
from typing import List, Tuple, Optional
from datetime import datetime, timedelta


def extract_practice_location_multiline(
    text: str,
    label_end: int,
    max_distance: int
) -> Tuple[Optional[str], float]:
    """
    Extract practice location name that may span multiple lines.

    Handles cases where practice names span 2-3 lines after the label.
    Consolidated from field_extractor.py lines 358-420.

    Args:
        text: Text to search in
        label_end: Position where label ends
        max_distance: Maximum distance to search

    Returns:
        Tuple of (extracted_value, confidence)
    """
    # Define stop patterns for multi-line extraction
    stop_patterns = [
        r'Street\s*Address',  # Added specific "Street Address" pattern
        r'Street\s*\d',
        r'Street\s*:',
        r'^\d{3,5}\s',
        r'Tax\s+ID',
        r':\s*:',
        r'Phone\s+Number',
        r'Appointment\s+Phone',
        r'City\s*:',
        r'County\s*:',
        r'Zip\s*Code',
        r'Country\s*:',
        r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
        r'^[A-Z]{2}\s+\d{5}',
        r'^\([0-9]{3}\)',
        r'^\d{3}[-.]?\d{3}[-.]?\d{4}',
        r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
        r'\d{1,2}:\d{2}\s*(AM|PM|am|pm)',
    ]

    # Extract lines after label
    after_text = text[label_end:label_end + max_distance]
    lines = after_text.split('\n')

    collected_lines = []
    for i, line in enumerate(lines[:3]):  # Max 3 lines
        line = line.strip()
        if not line:
            continue

        # Check for stop patterns
        stop = False
        for stop_pattern in stop_patterns:
            if re.search(stop_pattern, line, re.IGNORECASE):
                stop = True
                break

        if stop:
            break

        # Clean the line
        line = re.sub(r'[:\-]\s*$', '', line)
        line = re.sub(r'\s*:\s*', ' ', line)

        if line and len(line) > 1:
            collected_lines.append(line)

    if collected_lines:
        value = ' '.join(collected_lines)
        # Higher confidence if we collected multiple lines coherently
        confidence = 0.85 if len(collected_lines) > 1 else 0.80
        return value, confidence

    return None, 0.0


def validate_medicaid_id_context(
    value: str,
    text: str,
    position: int,
    window: int = 50
) -> bool:
    """
    Validate Medicaid ID by checking surrounding context for NPI indicators.

    Consolidated from field_extractor.py lines 454-498.

    Args:
        value: Potential Medicaid ID value
        text: Full text to check context
        position: Position of the value in text
        window: Context window size

    Returns:
        True if context suggests this is NOT an NPI (i.e., likely Medicaid ID)
    """
    # If position not found, assume it's valid (don't reject)
    if position == -1:
        return True

    # Check context for NPI indicators
    context_start = max(0, position - window)
    context_end = min(len(text), position + len(value) + window)
    context = text[context_start:context_end].lower()

    # NPI indicators that suggest this is NOT a Medicaid ID
    # Only look for explicit NPI mentions very close to the number
    npi_indicators = [
        r'npi\s*:\s*' + re.escape(value),  # "NPI: 1234567890"
        r'individual\s+npi\s*:\s*' + re.escape(value),  # "Individual NPI: 1234567890"
    ]

    for indicator in npi_indicators:
        if re.search(indicator, context, re.IGNORECASE):
            return False  # Context suggests this is an NPI

    return True  # No strong NPI indicators found, likely a Medicaid ID


def filter_future_license_dates(
    candidates: List[Tuple[str, float, int, str]],
    date_formats: List[str]
) -> List[Tuple[str, float, int, str]]:
    """
    Filter license expiration dates to only include future dates.

    Consolidated from field_extractor.py lines 500-576.

    Args:
        candidates: List of (value, confidence, distance, direction) tuples
        date_formats: List of date format strings to try

    Returns:
        Filtered list of candidates with only future dates
    """
    future_candidates = []
    past_candidates = []
    today = datetime.now()

    for value, conf, dist, direction in candidates:
        # Try to parse as date
        parsed_date = None
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue

        if parsed_date:
            if parsed_date > today:
                # Future date - boost confidence
                future_candidates.append((value, min(1.0, conf + 0.10), dist, direction))
            else:
                # Past date - reduce confidence
                past_candidates.append((value, conf * 0.70, dist, direction))
        else:
            # Couldn't parse - keep as-is but with reduced confidence
            future_candidates.append((value, conf * 0.90, dist, direction))

    # Prefer future dates, fall back to past if none found
    return future_candidates if future_candidates else past_candidates


def extract_value_before_label(
    text: str,
    label_start: int,
    pattern: str,
    max_distance: int
) -> List[Tuple[str, float, int, str]]:
    """
    Search for values BEFORE a label.

    Args:
        text: Full text
        label_start: Where the label starts
        pattern: Regex pattern to match
        max_distance: Max distance to search before label

    Returns:
        List of (value, confidence, distance, direction) tuples
    """
    candidates = []

    # Search before label
    before_start = max(0, label_start - max_distance)
    before_region = text[before_start:label_start]

    if pattern:
        # Find all matches before label
        matches = list(re.finditer(pattern, before_region, re.IGNORECASE))
        # Take the closest match (last one before label)
        if matches:
            match = matches[-1]
            value = match.group().strip()
            distance = len(before_region) - match.end()
            # Confidence decreases with distance
            base_conf = max(0, 0.90 - (distance / max_distance * 0.20))
            candidates.append((value, base_conf, distance, 'before'))

    return candidates


def extract_value_after_label(
    text: str,
    label_end: int,
    pattern: str,
    max_distance: int,
    field_name: str
) -> List[Tuple[str, float, int, str]]:
    """
    Search for values AFTER a label.

    Args:
        text: Full text
        label_end: Where the label ends
        pattern: Regex pattern to match
        max_distance: Max distance to search after label
        field_name: Name of the field (for special handling)

    Returns:
        List of (value, confidence, distance, direction) tuples
    """
    candidates = []

    # Search after label
    after_region = text[label_end:label_end + max_distance]

    if pattern:
        if field_name == "professional_license_expiration_date":
            # Special case: find ALL dates for license expiration
            matches = list(re.finditer(pattern, after_region, re.IGNORECASE))
            for match in matches:
                value = match.group().strip()
                distance = match.start()
                base_conf = max(0, 0.90 - (distance / max_distance * 0.20))
                candidates.append((value, base_conf, distance, 'after'))
        else:
            # Standard case: find first match
            match = re.search(pattern, after_region, re.IGNORECASE)
            if match:
                value = match.group().strip()
                distance = match.start()
                base_conf = max(0, 0.90 - (distance / max_distance * 0.20))
                candidates.append((value, base_conf, distance, 'after'))

    return candidates


def extract_insurance_fields(text: str) -> dict:
    """
    Extract ALL insurance fields from the insurance policy with the furthest expiration date.

    According to CAQH Cheat Sheet, providers may have multiple insurance policies.
    We need to select the one with the greatest (furthest) expiration date and extract
    all fields from that policy.

    Args:
        text: Full PDF text content

    Returns:
        Dictionary with extracted insurance fields:
        {
            'insurance_policy_number': str,
            'insurance_covered_location': str,
            'insurance_current_effective_date': str,
            'insurance_current_expiration_date': str,
            'insurance_carrier_name': str,
            'insurance_address_street_1': str,
            'insurance_address_street_2': str,
            'insurance_address_city': str,
            'insurance_address_state': str,
            'insurance_address_country': str,
            'insurance_address_zip': str,
        }
    """
    # Find the INSURANCE INFORMATION section
    insurance_section_pattern = r'INSURANCE\s+INFORMATION'
    section_match = re.search(insurance_section_pattern, text, re.IGNORECASE)

    if not section_match:
        # No insurance section found - return all None
        return {field: None for field in [
            'insurance_policy_number',
            'insurance_covered_location',
            'insurance_current_effective_date',
            'insurance_current_expiration_date',
            'insurance_carrier_name',
            'insurance_address_street_1',
            'insurance_address_street_2',
            'insurance_address_city',
            'insurance_address_state',
            'insurance_address_country',
            'insurance_address_zip',
        ]}

    section_start = section_match.end()

    # Find the next major section (to limit our search area)
    next_section_pattern = r'\n\s*[A-Z\s]{15,}\n'
    next_section_match = re.search(next_section_pattern, text[section_start:])
    if next_section_match:
        section_end = section_start + next_section_match.start()
    else:
        section_end = len(text)

    insurance_section = text[section_start:section_end]

    # Extract ALL insurance policies in this section
    # A policy starts with "Policy Number" and contains multiple fields
    policy_pattern = r'Policy\s+Number\s*:?\s*([A-Z0-9\-]+)'
    policy_matches = list(re.finditer(policy_pattern, insurance_section, re.IGNORECASE))

    if not policy_matches:
        # No policies found
        return {field: None for field in [
            'insurance_policy_number',
            'insurance_covered_location',
            'insurance_current_effective_date',
            'insurance_current_expiration_date',
            'insurance_carrier_name',
            'insurance_address_street_1',
            'insurance_address_street_2',
            'insurance_address_city',
            'insurance_address_state',
            'insurance_address_country',
            'insurance_address_zip',
        ]}

    # Extract all policies with their expiration dates
    policies = []

    for i, policy_match in enumerate(policy_matches):
        policy_start = policy_match.start()

        # Find where this policy ends (start of next policy or end of section)
        if i + 1 < len(policy_matches):
            policy_end = policy_matches[i + 1].start()
        else:
            policy_end = len(insurance_section)

        policy_text = insurance_section[policy_start:policy_end]

        # Extract policy fields
        policy_data = _extract_single_policy(policy_text)

        # Parse expiration date to determine which policy to use
        if policy_data.get('insurance_current_expiration_date'):
            exp_date_str = policy_data['insurance_current_expiration_date']
            parsed_date = _parse_date(exp_date_str)
            policy_data['_parsed_expiration'] = parsed_date
            policies.append(policy_data)

    if not policies:
        # No valid policies found
        return {field: None for field in [
            'insurance_policy_number',
            'insurance_covered_location',
            'insurance_current_effective_date',
            'insurance_current_expiration_date',
            'insurance_carrier_name',
            'insurance_address_street_1',
            'insurance_address_street_2',
            'insurance_address_city',
            'insurance_address_state',
            'insurance_address_country',
            'insurance_address_zip',
        ]}

    # Select the policy with the furthest expiration date
    # Sort by expiration date (furthest first), with None dates last
    policies_with_dates = [p for p in policies if p.get('_parsed_expiration')]
    policies_without_dates = [p for p in policies if not p.get('_parsed_expiration')]

    if policies_with_dates:
        policies_with_dates.sort(key=lambda p: p['_parsed_expiration'], reverse=True)
        selected_policy = policies_with_dates[0]
    elif policies_without_dates:
        # No dates found, just use the first policy
        selected_policy = policies_without_dates[0]
    else:
        # Shouldn't happen, but just in case
        selected_policy = policies[0]

    # Remove the temporary _parsed_expiration field
    if '_parsed_expiration' in selected_policy:
        del selected_policy['_parsed_expiration']

    return selected_policy


def _extract_single_policy(policy_text: str) -> dict:
    """
    Extract all fields from a single insurance policy.

    Args:
        policy_text: Text containing a single insurance policy

    Returns:
        Dictionary with extracted fields
    """
    extracted = {}

    # Policy Number
    policy_num_match = re.search(r'Policy\s+Number\s*:?\s*([A-Z0-9\-]+)', policy_text, re.IGNORECASE)
    extracted['insurance_policy_number'] = policy_num_match.group(1).strip() if policy_num_match else None

    # Covered Practice Location (may be empty)
    # This field is often empty, so be careful not to capture the next field label
    covered_loc_match = re.search(
        r'Covered\s+Practice\s+Locations?\s*:?\s*([^\n:]+)',
        policy_text,
        re.IGNORECASE
    )
    if covered_loc_match:
        loc = covered_loc_match.group(1).strip()
        # Don't capture field labels (Original, Current, Carrier, etc.)
        if not re.match(r'^(Original|Current|Carrier|Street|City|State)', loc, re.IGNORECASE):
            extracted['insurance_covered_location'] = loc if loc and len(loc) > 2 else None
        else:
            extracted['insurance_covered_location'] = None
    else:
        extracted['insurance_covered_location'] = None

    # Current Effective Date
    eff_date_match = re.search(
        r'Current\s+Effective\s+Date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        policy_text,
        re.IGNORECASE
    )
    extracted['insurance_current_effective_date'] = eff_date_match.group(1).strip() if eff_date_match else None

    # Current Expiration Date
    exp_date_match = re.search(
        r'Current\s+Expiration\s+Date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        policy_text,
        re.IGNORECASE
    )
    extracted['insurance_current_expiration_date'] = exp_date_match.group(1).strip() if exp_date_match else None

    # Carrier/Self Insured Name (may span multiple lines)
    # Due to OCR quirks, carrier name may appear BEFORE the label
    # Try multiple patterns to handle different layouts

    # Pattern 1: Text after "Carrier/Self Insured Name" label
    carrier_match = re.search(
        r'Carrier/Self\s+Insured\s+Name\s*:?\s*([^\n:]+)',
        policy_text,
        re.IGNORECASE
    )

    if carrier_match:
        carrier_name = carrier_match.group(1).strip()

        # Check if this is just "Inc." or similar suffix (too short to be full name)
        if len(carrier_name) < 10:
            # Look for carrier name BEFORE the label (OCR quirk)
            # Search between expiration date and carrier label
            before_carrier_match = re.search(
                r'Current\s+Expiration\s+Date\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{4}\s*:?\s*([^\n]+)\s*Carrier/Self\s+Insured\s+Name',
                policy_text,
                re.IGNORECASE | re.DOTALL
            )
            if before_carrier_match:
                before_text = before_carrier_match.group(1).strip()
                # Clean up and combine
                carrier_name = before_text + ' ' + carrier_name

        extracted['insurance_carrier_name'] = carrier_name.strip() if carrier_name and len(carrier_name.strip()) > 2 else None
    else:
        # Pattern 2: If no match, search between expiration date and street address
        fallback_match = re.search(
            r'Current\s+Expiration\s+Date.*?(\d{1,2}[/-]\d{1,2}[/-]\d{4}).*?([A-Za-z][^\n:]{3,100}?)(?=\s+Street\s+1|\s+City\s*:)',
            policy_text,
            re.IGNORECASE | re.DOTALL
        )
        if fallback_match:
            carrier_name = fallback_match.group(2).strip()
            # Remove common labels if accidentally captured
            carrier_name = re.sub(r'Carrier/Self\s+Insured\s+Name\s*:?\s*', '', carrier_name, flags=re.IGNORECASE)
            extracted['insurance_carrier_name'] = carrier_name if carrier_name and len(carrier_name) > 2 else None
        else:
            extracted['insurance_carrier_name'] = None

    # Insurance Address Street 1
    street1_match = re.search(r'Street\s+1\s*:?\s*([^\n:]+)', policy_text, re.IGNORECASE)
    extracted['insurance_address_street_1'] = street1_match.group(1).strip() if street1_match else None

    # Insurance Address Street 2
    street2_match = re.search(r'Street\s+2\s*:?\s*([^\n:]+?)(?=\n|City|$)', policy_text, re.IGNORECASE)
    if street2_match:
        street2 = street2_match.group(1).strip()
        extracted['insurance_address_street_2'] = street2 if street2 and len(street2) > 1 else None
    else:
        extracted['insurance_address_street_2'] = None

    # Insurance Address City
    city_match = re.search(r'City\s*:?\s*([A-Za-z\s\-\']+?)(?=\s+Province|State|$|\n)', policy_text, re.IGNORECASE)
    extracted['insurance_address_city'] = city_match.group(1).strip() if city_match else None

    # Insurance Address State
    state_match = re.search(r'State\s*:?\s*([A-Z]{2})', policy_text, re.IGNORECASE)
    extracted['insurance_address_state'] = state_match.group(1).strip().upper() if state_match else None

    # Insurance Address Country
    country_match = re.search(r'Country\s*:?\s*([A-Za-z\s]+?)(?=\n|$|Zip)', policy_text, re.IGNORECASE)
    if country_match:
        country = country_match.group(1).strip()
        extracted['insurance_address_country'] = country if country and len(country) > 2 else None
    else:
        extracted['insurance_address_country'] = None

    # Insurance Address Zip Code
    zip_match = re.search(r'Zip\s+Code\s*:?\s*(\d{5}(?:-\d{4})?)', policy_text, re.IGNORECASE)
    extracted['insurance_address_zip'] = zip_match.group(1).strip() if zip_match else None

    return extracted


def _parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse a date string into a datetime object.

    Tries multiple common date formats.

    Args:
        date_str: Date string to parse

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None

    date_formats = [
        "%m/%d/%Y",  # 12/31/2025
        "%m-%d-%Y",  # 12-31-2025
        "%Y-%m-%d",  # 2025-12-31
        "%d/%m/%Y",  # 31/12/2025 (European format)
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None