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
    # Handle both normal text ("INSURANCE INFORMATION") and concatenated PDF text ("INSURANCEINFORMATION")
    insurance_section_pattern = r'INSURANCE\s*INFORMATION'
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
    # Handle OCR split and concatenated text:
    #   - "Policy Number : 6799172" (normal)
    #   - "PolicyNumber:  6799172" (concatenated PDF text)
    #   - "Policy  6799172\nNumber :" (OCR split - value between Policy and Number)
    policy_patterns = [
        r'Policy\s*Number\s*:?\s*([A-Z0-9\-]+)',  # Normal + concatenated: PolicyNumber : VALUE
        r'Policy\s+([A-Z0-9\-]{5,})\s*\n?\s*Number\s*:',  # OCR split: Policy VALUE \n Number :
    ]

    policy_matches = []
    for pattern in policy_patterns:
        matches = list(re.finditer(pattern, insurance_section, re.IGNORECASE))
        policy_matches.extend(matches)

    # Deduplicate by position (keep earliest match for overlapping patterns)
    if policy_matches:
        policy_matches = sorted(policy_matches, key=lambda m: m.start())
        # Remove duplicates that are too close together (within 50 chars)
        deduped = [policy_matches[0]]
        for m in policy_matches[1:]:
            if m.start() - deduped[-1].start() > 50:
                deduped.append(m)
        policy_matches = deduped

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

    # === PBS POLICY PRIORITIZATION ===
    # For PBS credentialing, we need to find the policy with "Positive Behavior" or "PBS"
    # in the covered location. This ensures we get the correct insurance for PBS employees.

    def is_pbs_policy(policy: dict) -> bool:
        """Check if this is a PBS-related insurance policy."""
        covered_loc = policy.get('insurance_covered_location', '') or ''
        covered_loc_lower = covered_loc.lower()
        return 'positive behavior' in covered_loc_lower or 'pbs' in covered_loc_lower

    # Separate PBS policies from non-PBS policies
    pbs_policies = [p for p in policies if is_pbs_policy(p)]
    non_pbs_policies = [p for p in policies if not is_pbs_policy(p)]

    # Prefer PBS policies; fall back to non-PBS if none found
    candidate_policies = pbs_policies if pbs_policies else non_pbs_policies

    # Among candidates, select the one with furthest expiration date
    policies_with_dates = [p for p in candidate_policies if p.get('_parsed_expiration')]
    policies_without_dates = [p for p in candidate_policies if not p.get('_parsed_expiration')]

    if policies_with_dates:
        policies_with_dates.sort(key=lambda p: p['_parsed_expiration'], reverse=True)
        selected_policy = policies_with_dates[0]
    elif policies_without_dates:
        # No dates found, just use the first policy
        selected_policy = policies_without_dates[0]
    else:
        # Shouldn't happen, but just in case - fall back to any policy
        selected_policy = policies[0] if policies else {}

    # Remove the temporary _parsed_expiration field
    if '_parsed_expiration' in selected_policy:
        del selected_policy['_parsed_expiration']

    return selected_policy


def _extract_date_near_label(
    text: str,
    label_variants: List[str],
    exclude_labels: List[str] = None,
    search_distance: int = 100
) -> Optional[str]:
    """
    Extract a date near a label, handling multiline OCR formatting.

    OCR often splits labels across lines, e.g.:
    - "Current  11/01/2026\\nExpiration Date :" (value BEFORE label)
    - "Current Effective Date :\\n01/31/2025" (value AFTER label)

    This function searches both before and after the label for dates.

    Args:
        text: Text to search in
        label_variants: List of label variations to search for (in priority order)
        exclude_labels: Labels that indicate we found the WRONG date
        search_distance: How far before/after the label to search

    Returns:
        Extracted date string or None
    """
    if exclude_labels is None:
        exclude_labels = []

    date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{4}'

    for label in label_variants:
        # Find the label in text (case insensitive, flexible whitespace including zero-width)
        # Handle concatenated PDF text where spaces may be missing
        label_pattern = re.escape(label).replace(r'\ ', r'\s*')
        label_match = re.search(label_pattern, text, re.IGNORECASE)

        if not label_match:
            continue

        label_start = label_match.start()
        label_end = label_match.end()

        # Search AFTER label (traditional)
        after_region = text[label_end:label_end + search_distance]
        after_date_match = re.search(date_pattern, after_region)

        # Search BEFORE label (handles OCR split where date appears before label)
        before_start = max(0, label_start - search_distance)
        before_region = text[before_start:label_start]
        # Find the LAST date before the label (closest to label)
        before_dates = list(re.finditer(date_pattern, before_region))

        # Decide which date to use
        candidates = []

        if after_date_match:
            after_date = after_date_match.group()
            after_distance = after_date_match.start()
            # Check if excluded label appears between label and date
            between_text = after_region[:after_date_match.start()].lower()
            is_excluded = any(excl.lower() in between_text for excl in exclude_labels)
            if not is_excluded:
                candidates.append((after_date, after_distance, 'after'))

        if before_dates:
            before_date_match = before_dates[-1]  # Last (closest) date before label
            before_date = before_date_match.group()
            before_distance = label_start - before_start - before_date_match.end()
            # Check context - make sure we're not grabbing a date from a different field
            between_text = before_region[before_date_match.end():].lower()
            is_excluded = any(excl.lower() in between_text for excl in exclude_labels)
            if not is_excluded:
                candidates.append((before_date, before_distance, 'before'))

        # Return the best date candidate
        # STRONGLY prefer AFTER dates because:
        # - The date directly after a label is most reliably associated with that label
        # - BEFORE dates may belong to a preceding field (e.g., effective date before expiration label)
        if candidates:
            # Separate after and before candidates
            after_candidates = [c for c in candidates if c[2] == 'after']
            before_candidates = [c for c in candidates if c[2] == 'before']

            # If we have an AFTER date, use it (unless BEFORE is dramatically closer)
            if after_candidates:
                after_candidates.sort(key=lambda x: x[1])
                best_after = after_candidates[0]

                # Only consider BEFORE if it's at least 3x closer than AFTER
                if before_candidates:
                    before_candidates.sort(key=lambda x: x[1])
                    best_before = before_candidates[0]
                    if best_before[1] * 3 < best_after[1]:  # BEFORE is 3x closer
                        return best_before[0]

                return best_after[0]
            elif before_candidates:
                before_candidates.sort(key=lambda x: x[1])
                return before_candidates[0][0]

    return None


def _extract_single_policy(policy_text: str) -> dict:
    """
    Extract all fields from a single insurance policy.

    Args:
        policy_text: Text containing a single insurance policy

    Returns:
        Dictionary with extracted fields
    """
    extracted = {}

    # Policy Number (handle concatenated text: "PolicyNumber:")
    policy_num_match = re.search(r'Policy\s*Number\s*:?\s*([A-Z0-9\-]+)', policy_text, re.IGNORECASE)
    extracted['insurance_policy_number'] = policy_num_match.group(1).strip() if policy_num_match else None

    # Covered Practice Location (may be empty or split across lines)
    # OCR sometimes splits this field with part BEFORE and part AFTER the label:
    #   "Positive Behavior Supports"        <- before label
    #   "Covered Practice Locations :"
    #   "Corporation Central Florida"       <- after label
    # We need to capture and combine both parts.

    covered_label_match = re.search(r'Covered\s*Practice\s*Locations?\s*:?', policy_text, re.IGNORECASE)

    if covered_label_match:
        label_start = covered_label_match.start()
        label_end = covered_label_match.end()

        # === PART 1: Look BEFORE the label ===
        # Search between policy number and covered label for organization names
        before_text = policy_text[:label_start]
        # Get the last few lines before the label (skip policy number and empty lines)
        before_lines = before_text.strip().split('\n')
        before_value = ''
        for line in reversed(before_lines[-3:]):  # Last 3 lines before label
            line = line.strip()
            # Skip empty lines, colons, and field labels
            if not line or line == ':' or re.match(r'^(Policy|Self|Individual|No|Yes)\s', line, re.IGNORECASE):
                continue
            # Skip if it's a number or date
            if re.match(r'^[\d\-/]+$', line):
                continue
            # This looks like part of the location name
            before_value = line
            break

        # === PART 2: Look AFTER the label ===
        after_text = policy_text[label_end:label_end + 150]
        after_lines = after_text.strip().split('\n')
        after_parts = []
        for line in after_lines[:3]:  # Up to 3 lines after label
            line = line.strip()
            # Skip empty lines and colons
            if not line or line == ':':
                continue
            # Stop at field labels (Original, Current, Carrier, etc.)
            if re.match(r'^(Original|Current|Carrier|Street|City|State|Self)', line, re.IGNORECASE):
                break
            # Skip if it's just a date
            if re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$', line):
                break
            # Clean dashes that are separators
            line = re.sub(r'^[-\s]+', '', line)
            if line:
                after_parts.append(line)

        after_value = ' '.join(after_parts)

        # === COMBINE: before + after ===
        def normalize_location(loc: str) -> str:
            """Normalize covered location - standardize dashes and spaces."""
            if not loc:
                return loc
            # Normalize multiple spaces
            loc = re.sub(r'\s+', ' ', loc).strip()
            # Standardize dash/hyphen with spaces around it (handle various dash types)
            loc = re.sub(r'\s*[-–—]\s*', ' - ', loc)
            return loc

        # If we have both parts, combine them
        if before_value and after_value:
            combined = f"{before_value} {after_value}"
            extracted['insurance_covered_location'] = normalize_location(combined)
        elif before_value:
            extracted['insurance_covered_location'] = normalize_location(before_value)
        elif after_value:
            # Don't capture field labels
            if not re.match(r'^(Original|Current|Carrier|Street|City|State)', after_value, re.IGNORECASE):
                extracted['insurance_covered_location'] = normalize_location(after_value)
            else:
                extracted['insurance_covered_location'] = None
        else:
            extracted['insurance_covered_location'] = None
    else:
        extracted['insurance_covered_location'] = None

    # Current Effective Date - handle multiline OCR formatting
    # OCR may split "Current Effective Date : 01/31/2025" across lines
    extracted['insurance_current_effective_date'] = _extract_date_near_label(
        policy_text,
        ['Current Effective Date', 'Current Effective', 'Effective Date'],
        exclude_labels=['Original Effective', 'Expiration']
    )

    # Current Expiration Date - handle multiline OCR formatting
    # OCR may output: "Current  11/01/2026\nExpiration Date :"
    # So we need to search BEFORE "Expiration Date" label as well as after
    extracted['insurance_current_expiration_date'] = _extract_date_near_label(
        policy_text,
        ['Current Expiration Date', 'Expiration Date', 'Current Expiration'],
        exclude_labels=['Original', 'Effective Date']
    )

    # Carrier/Self Insured Name extraction
    # Handles various OCR quirks where carrier may appear BEFORE label,
    # label may be split across lines, or carrier name itself may be split
    extracted['insurance_carrier_name'] = _extract_carrier_name(policy_text)

    # Insurance Address Street 1 (handle concatenated text)
    street1_match = re.search(r'Street\s*1\s*:?\s*([^\n:]+)', policy_text, re.IGNORECASE)
    extracted['insurance_address_street_1'] = street1_match.group(1).strip() if street1_match else None

    # Insurance Address Street 2
    street2_match = re.search(r'Street\s*2\s*:?\s*([^\n:]+?)(?=\n|City|$)', policy_text, re.IGNORECASE)
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

    # Insurance Address Zip Code (handle concatenated text: "ZipCode:")
    zip_match = re.search(r'Zip\s*Code\s*:?\s*(\d{5}(?:-\d{4})?)', policy_text, re.IGNORECASE)
    extracted['insurance_address_zip'] = zip_match.group(1).strip() if zip_match else None

    # Amount of Coverage Per Occurrence (e.g., "$1,000,000.00")
    # Handle concatenated: "Amountofcoverageperoccurrence: $1,000,000.00"
    occurrence_match = re.search(
        r'(?:Amount\s*of\s*)?coverage\s*per\s*occurrence\s*:?\s*(\$?[\d,]+(?:\.\d{2})?)',
        policy_text, re.IGNORECASE
    )
    extracted['insurance_each_occurrence'] = occurrence_match.group(1).strip() if occurrence_match else None

    # Amount of Coverage Aggregate (e.g., "$3,000,000.00")
    # Handle concatenated: "Amountofcoverageaggregate: $3,000,000.00"
    aggregate_match = re.search(
        r'coverage\s*aggregate\s*:?\s*(\$?[\d,]+(?:\.\d{2})?)',
        policy_text, re.IGNORECASE
    )
    extracted['insurance_general_aggregate'] = aggregate_match.group(1).strip() if aggregate_match else None

    # Individual Coverage (Yes/No)
    # Handle concatenated: "IndividualCoverage:  No"
    individual_match = re.search(
        r'Individual\s*Coverage\s*:?\s*(Yes|No|Y|N)',
        policy_text, re.IGNORECASE
    )
    extracted['insurance_individual_coverage'] = individual_match.group(1).strip() if individual_match else None

    # Self-Insured (Yes/No)
    # Handle: "Self-Insured?  No" or "Self Insured: No"
    self_insured_match = re.search(
        r'Self[\s-]*Insured\s*\??\s*:?\s*(Yes|No|Y|N)',
        policy_text, re.IGNORECASE
    )
    extracted['insurance_self_insured'] = self_insured_match.group(1).strip() if self_insured_match else None

    return extracted


def _extract_carrier_name(policy_text: str) -> Optional[str]:
    """
    Extract Carrier/Self Insured Name handling various OCR formatting issues.

    OCR can produce various layouts:
    1. Normal: "Carrier/Self Insured Name : Lexington Insurance Company"
    2. Carrier BEFORE label: "Lexington Insurance Company\\nCarrier/Self Insured Name :"
    3. Label SPLIT: "Carrier/Self Insured  Lexington Insurance Company\\nName :"
    4. Carrier SPLIT: "Lexington  Company\\nCarrier/Self Insured Name  Insurance"

    Args:
        policy_text: Text of a single insurance policy

    Returns:
        Carrier name string or None
    """
    # Known insurance company patterns to validate extraction
    insurance_keywords = [
        'insurance', 'company', 'inc', 'llc', 'corp', 'corporation',
        'agency', 'group', 'indemnity', 'mutual', 'associates'
    ]

    def looks_like_carrier(text: str) -> bool:
        """Check if text looks like an insurance company name."""
        if not text or len(text) < 5:
            return False
        text_lower = text.lower()
        return any(kw in text_lower for kw in insurance_keywords)

    def clean_carrier_name(name: str) -> str:
        """Clean up extracted carrier name."""
        name = re.sub(r'^[\s:]+|[\s:]+$', '', name)
        name = re.sub(r'Carrier/Self\s+Insured\s+Name\s*:?\s*', '', name, flags=re.IGNORECASE)
        name = re.sub(r'^Name\s*:?\s*', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*(Street|City|Province|State)\s*[\d:].+$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    candidates = []

    # === PATTERN 1: Normal - carrier name AFTER label on same line ===
    # Handle concatenated text: "Carrier/SelfInsured" or "Carrier/Self Insured"
    match1 = re.search(
        r'Carrier/Self\s*Insured(?:\s*Name)?\s*:?\s+([A-Za-z][^\n]{5,80})',
        policy_text,
        re.IGNORECASE
    )
    if match1:
        name = clean_carrier_name(match1.group(1))
        if looks_like_carrier(name):
            candidates.append((name, 1, match1.start()))

    # === PATTERN 2: Carrier BEFORE label ===
    label_match = re.search(r'Carrier/Self\s*Insured', policy_text, re.IGNORECASE)
    if label_match:
        before_text = policy_text[:label_match.start()]
        lines_before = before_text.strip().split('\n')
        for i, line in enumerate(reversed(lines_before[-3:])):
            line = line.strip()
            if not line or line == ':' or re.match(r'^[\d\-/:]+$', line):
                continue
            if re.match(r'^(Current|Original|Policy|Self|Do |Type |Amount )', line, re.IGNORECASE):
                continue
            name = clean_carrier_name(line)
            if looks_like_carrier(name):
                candidates.append((name, 2, label_match.start() - i))
                break

    # === PATTERN 3: Label SPLIT with carrier in middle ===
    match3 = re.search(
        r'Carrier/Self\s+Insured\s+([A-Za-z][^\n]{5,80})\s*\n\s*Name\s*:',
        policy_text,
        re.IGNORECASE
    )
    if match3:
        name = clean_carrier_name(match3.group(1))
        if looks_like_carrier(name):
            candidates.append((name, 1, match3.start()))

    # === PATTERN 4: Carrier SPLIT across lines with label in middle ===
    if label_match:
        before_region = policy_text[max(0, label_match.start()-100):label_match.start()]
        after_region = policy_text[label_match.end():label_match.end()+100]

        before_partial = re.search(r'([A-Za-z][\w\s]{3,30}\s+(?:Ins|Insurance|Company|Co))\s*$', before_region)
        after_partial = re.search(r'^[\s:Name]*\s*([A-Za-z][\w\s]{3,30}(?:Insurance|Company|Inc|LLC|Corp))', after_region, re.IGNORECASE)

        if before_partial and after_partial:
            combined = before_partial.group(1).strip() + ' ' + after_partial.group(1).strip()
            combined = clean_carrier_name(combined)
            if looks_like_carrier(combined):
                candidates.append((combined, 3, label_match.start()))
        elif after_partial:
            name = clean_carrier_name(after_partial.group(1))
            if looks_like_carrier(name):
                candidates.append((name, 2, label_match.end()))

    # === PATTERN 5: Fallback - search for known insurance company patterns ===
    fallback_match = re.search(
        r'([A-Za-z][\w\s]{3,40}(?:Insurance\s+Company|Insurance\s+Co|Ins\s+Co|Agency\s+LLC|Insurance))',
        policy_text,
        re.IGNORECASE
    )
    if fallback_match:
        name = clean_carrier_name(fallback_match.group(1))
        if looks_like_carrier(name) and len(name) > 10:
            candidates.append((name, 4, fallback_match.start()))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[1], x[2]))
    best_name = candidates[0][0]

    if looks_like_carrier(best_name) and len(best_name) >= 5:
        return best_name

    return None


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