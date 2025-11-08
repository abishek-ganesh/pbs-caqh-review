"""
PBS Practice Location Name Extractor

Specialized extractor for handling PBS organization names that are split
across multiple lines in CAQH PDFs. These names follow the pattern:
"Positive Behavior Supports Corporation - [Region]"

Common split patterns in PDFs:
1. 'Practice  Positive Behavior Supports\nName :\nCorporation Central Florida\n-\n'
2. 'Positive Behavior Supports\nCorporation - Central Florida'
3. 'Practice Name: Positive Behavior Supports Corporation - Central Florida'
"""

import re
from typing import Optional, Tuple


def _clean_region_name(region: str) -> str:
    """
    Clean junk text from extracted region name (BUG #2B FIX).

    Removes common section headers and labels that get appended:
    - INSURANCE INFORMATION
    - PROFESSIONAL IDENTIFICATION
    - EDUCATION, WORK HISTORY, etc.
    - Other all-caps section headers

    Args:
        region: Extracted region name (may contain junk)

    Returns:
        Cleaned region name without trailing section headers
    """
    if not region:
        return region

    # List of common section headers/keywords to remove
    junk_keywords = [
        'INSURANCE INFORMATION',
        'INSURANCE',
        'PROFESSIONAL IDENTIFICATION',
        'PROFESSIONAL',
        'EDUCATION',
        'WORK HISTORY',
        'HOSPITAL PRIVILEGES',
        'MALPRACTICE',
        'DISCLOSURE',
        'ATTESTATION',
        'PRACTICE LOCATIONS',
        'LOCATION',
        'INFORMATION'
    ]

    # Remove junk keywords (case-insensitive)
    cleaned = region
    for keyword in junk_keywords:
        # Remove keyword if it appears (with optional dash/separator before it)
        cleaned = re.sub(
            rf'\s*[-–]?\s*{re.escape(keyword)}\s*$',
            '',
            cleaned,
            flags=re.IGNORECASE
        )

    # Remove trailing all-caps words (likely section headers we missed)
    # Pattern: Remove 2+ consecutive all-caps words at end
    cleaned = re.sub(r'\s*[-–]?\s*[A-Z]{2,}(?:\s+[A-Z]{2,})+\s*$', '', cleaned)

    # Clean up whitespace
    cleaned = ' '.join(cleaned.split())

    return cleaned


def normalize_pbs_name(raw_value: str) -> Optional[str]:
    """
    Normalize variations of PBS organization names to standard format.

    Handles OCR variations and missing dashes, consolidating logic from
    field_extractor.py lines 588-662.

    Args:
        raw_value: Raw extracted value that may need normalization

    Returns:
        Normalized PBS name or None if not a PBS organization
    """
    if not raw_value:
        return None

    # Check if this is a PBS organization
    is_pbs = re.search(r'Positive\s+Behavior\s+Supports', raw_value, re.IGNORECASE)
    if not is_pbs:
        return None

    # Try to normalize to proper format: "Positive Behavior Supports Corporation - {Region}"

    # First try strict pattern match (with dash)
    strict_pattern = r'Positive\s+Behavior\s+Supports\s+Corporation\s*-\s*([A-Za-z][A-Za-z\s&]+)'
    strict_match = re.search(strict_pattern, raw_value, re.IGNORECASE)
    if strict_match:
        region = strict_match.group(1).strip()
        region = _clean_region_name(region)
        if region:
            return f"Positive Behavior Supports Corporation - {region}"

    # Try to extract region from various OCR variations
    # Common issues:
    # 1. Missing dash: "Positive Behavior Supports Corporation Emerald Coast"
    # 2. Swapped words: "Positive Behavior Supports Emerald Corporation Coast"

    # Extract region by finding text after "Corporation" or "Supports"
    region_match = re.search(
        r'Positive\s+Behavior\s+Supports\s+(?:Corporation\s+)?(.+?)$',
        raw_value,
        re.IGNORECASE
    )
    if region_match:
        region = region_match.group(1).strip()
        # Remove "Corporation" if it appears in the region (swapped words case)
        region = re.sub(r'\b(?:Corporation|Corp\.?)\b', '', region, flags=re.IGNORECASE).strip()
        region = _clean_region_name(region)
        if region:
            return f"Positive Behavior Supports Corporation - {region}"

    # If we can't extract a proper region, return None
    return None


def clean_practice_location_name(value: str) -> str:
    """
    Clean common junk prefixes and artifacts from practice location names.

    Consolidates cleanup logic from field_extractor.py lines 633-662.

    Args:
        value: Raw practice location name

    Returns:
        Cleaned practice location name
    """
    if not value:
        return value

    # Remove common junk prefixes
    junk_prefixes = [
        r'^.*?clinical\s+practice\s+including\s+special\s+',
        r'^.*?interests\s+',
        r'^.*?as\s+appears\s+on\s+',
    ]
    for prefix_pattern in junk_prefixes:
        match = re.search(prefix_pattern, value, re.IGNORECASE)
        if match:
            value = value[match.end():]
            break

    # Remove common OCR artifacts and form labels
    value = value.replace("as appears", "")
    value = value.replace("Name :", "")
    value = value.replace(":  :", "")
    value = value.replace("interests", "")

    # Remove trailing unwanted text (stop at common field indicators)
    stop_patterns = [
        r'\s+Street\s+.*$',
        r'\s+Address.*$',
        r'\s+Phone.*$',
        r'\s+Fax.*$',
        r'\s+more\s+text.*$',  # Handle "Houston more text"
        r'\s+indicate\s+.*$',   # Handle "indicate to which..."
        r'\s+which\s+.*$',
        r'\s+please\s+.*$',
    ]
    for pattern in stop_patterns:
        value = re.sub(pattern, '', value, flags=re.IGNORECASE)

    # Remove trailing colons and dashes
    value = re.sub(r'[:\-]\s*$', '', value)

    # Remove internal colons (but keep hyphens)
    value = re.sub(r'\s*:\s*', ' ', value)

    # Collapse multiple spaces to single space
    value = ' '.join(value.split())

    return value.strip()


def extract_pbs_practice_name_complete(text: str, pattern_required: bool = False) -> Tuple[Optional[str], float]:
    """
    Complete PBS practice location name extraction with all fallbacks and normalization.

    This is the single entry point for all PBS extraction, consolidating logic from:
    - field_extractor.py lines 119-140 (first attempt)
    - field_extractor.py lines 329-342 (second attempt)
    - field_extractor.py lines 588-662 (normalization)

    Args:
        text: Full text extracted from PDF (can be section-filtered)
        pattern_required: If True, only accept properly formatted PBS names

    Returns:
        Tuple of (practice_name, confidence) where:
        - practice_name is the full PBS name with region or None
        - confidence is 0.0 to 1.0
    """
    # First try the original extraction logic
    name, confidence = extract_pbs_practice_name(text)

    # If we got a high-confidence PBS name, return it
    if name and confidence >= 0.80:
        # Clean up any extra text after region
        cleaned = clean_practice_location_name(name)
        return cleaned, confidence

    # Try to find any mention of PBS or practice name even with OCR variations
    if not name:
        # Try with OCR variations (Behavioral vs Behavior)
        text_normalized = text.replace("Behavioral", "Behavior")
        name, confidence = extract_pbs_practice_name(text_normalized)

    # Try normalization on the extracted name if we have one
    if name:
        normalized = normalize_pbs_name(name)
        if normalized:
            return normalized, confidence

    # If pattern is required and we didn't find PBS format, return None
    if pattern_required:
        return None, 0.0

    # Try to extract ANY practice name (non-PBS)
    # Look for "Practice Name:" pattern
    practice_match = re.search(r'Practice\s+Name\s*:\s*([^\n]+)', text, re.IGNORECASE)
    if practice_match:
        practice_name = practice_match.group(1).strip()
        # Clean it up
        cleaned = clean_practice_location_name(practice_name)
        if cleaned and len(cleaned) > 3:  # Reasonable length check
            return cleaned, 0.70  # Lower confidence for non-PBS names

    # If no PBS name found and pattern not required, return None
    # (allows fallback to non-PBS extraction in field_extractor)
    return None, 0.0


def extract_pbs_practice_name(text: str) -> Tuple[Optional[str], float]:
    """
    Extract PBS practice location name from PDF text.

    Handles various split patterns where the organization name may be
    broken across multiple lines with labels interspersed.

    Args:
        text: Full text extracted from PDF

    Returns:
        Tuple of (practice_name, confidence) where:
        - practice_name is the full PBS name with region or None
        - confidence is 0.0 to 1.0
    """

    # Pattern 1: Look for "Practice" followed by "Positive Behavior Supports"
    # with potential line breaks and then capture the region
    pattern1 = re.compile(
        r'Practice\s+Positive\s+Behavior\s+Supports\s*\n*'
        r'.*?Name\s*:?\s*\n*'
        r'Corporation\s+(?:-\s*)?([A-Za-z\s]+?)(?:\n|$)',
        re.IGNORECASE | re.DOTALL
    )

    match = pattern1.search(text)
    if match:
        region = match.group(1).strip()
        # Clean up the region - remove extra whitespace and newlines
        region = ' '.join(region.split())
        # BUG #2B FIX: Clean junk text (section headers, etc.)
        region = _clean_region_name(region)
        if region:
            full_name = f"Positive Behavior Supports Corporation - {region}"
            return full_name, 0.95

    # Pattern 2: Look for the complete name potentially split across lines
    # but in the correct order
    # BUGFIX: Removed [A-Z]{2,}\s+[A-Z]{2,} stop pattern - was matching lowercase with IGNORECASE
    pattern2 = re.compile(
        r'Positive\s+Behavior\s+Supports\s+'
        r'Corporation\s*[-–]\s*([A-Za-z\s]+?)(?:\n|Street|Phone|Fax|$)',
        re.IGNORECASE | re.DOTALL
    )

    match = pattern2.search(text)
    if match:
        region = match.group(1).strip()
        region = ' '.join(region.split())
        # BUG #2B FIX: Clean junk text
        region = _clean_region_name(region)
        if region:
            full_name = f"Positive Behavior Supports Corporation - {region}"
            return full_name, 0.90

    # Pattern 3: Handle case where region is split between PBS and Corporation
    # Example: "Positive Behavior Supports\nPractice Name:\nEmerald\nCorporation Coast\n-"
    # This extracts both "Emerald" (between PBS and Corporation) and "Coast" (after Corporation)
    split_region_pattern = re.compile(
        r'Positive\s+Behavior\s+Supports\s*\n*'  # PBS
        r'.*?'  # Skip any labels like "Practice Name:"
        r'([A-Za-z\s]+?)\s*\n*'  # First part of region (e.g., "Emerald")
        r'Corporation\s+'  # Corporation
        r'([A-Za-z\s]+?)'  # Second part of region (e.g., "Coast")
        r'(?:\s*\n*[-–]|\n|Street|Phone|$)',  # Stop at dash, newline, or address fields
        re.IGNORECASE | re.DOTALL
    )

    match = split_region_pattern.search(text)
    if match:
        region_part1 = match.group(1).strip()
        region_part2 = match.group(2).strip()

        # Clean up - remove labels like "Practice Name", "Name", etc.
        region_part1 = re.sub(r'(Practice\s+Name|Name|Practice)\s*:?\s*', '', region_part1, flags=re.IGNORECASE).strip()

        # Combine the two parts
        if region_part1 and region_part2:
            # Remove any extraneous words
            region_part1_words = region_part1.split()
            region_part2_words = region_part2.split()

            # Filter out non-region words
            filtered_part1 = ' '.join([w for w in region_part1_words if len(w) > 1 and w.lower() not in ['practice', 'name', 'location']])
            filtered_part2 = ' '.join([w for w in region_part2_words if len(w) > 1])

            if filtered_part1 and filtered_part2:
                region = f"{filtered_part1} {filtered_part2}"
                # BUG #2B FIX: Clean junk text
                region = _clean_region_name(region)
                if region:
                    full_name = f"Positive Behavior Supports Corporation - {region}"
                    return full_name, 0.90
        elif region_part2:  # Only second part found
            region = ' '.join(region_part2.split())
            # BUG #2B FIX: Clean junk text
            region = _clean_region_name(region)
            if region and 2 <= len(region) <= 50:
                full_name = f"Positive Behavior Supports Corporation - {region}"
                return full_name, 0.85

    # Pattern 4: More flexible - find PBS anywhere and try to find region nearby
    pbs_pattern = re.compile(
        r'Positive\s+Behavior\s+Supports',
        re.IGNORECASE
    )

    pbs_matches = list(pbs_pattern.finditer(text))
    if pbs_matches:
        for match in pbs_matches:
            # Look for Corporation and region within 200 characters
            start = match.start()
            end = min(len(text), match.end() + 200)
            context = text[start:end]

            # Try to find "Corporation" followed by a region
            # BUGFIX: Removed [A-Z]{2,}\s+[A-Z]{2,} from stop pattern - was matching lowercase with IGNORECASE flag
            # Now relies on _clean_region_name() to remove trailing all-caps section headers
            corp_pattern = re.compile(
                r'Corporation\s*[-–]?\s*([A-Za-z][A-Za-z\s&]+?)(?:\n|Street|Phone|$)',
                re.IGNORECASE
            )
            corp_match = corp_pattern.search(context)
            if corp_match:
                region = corp_match.group(1).strip()
                region = ' '.join(region.split())
                # BUG #2B FIX: Clean junk text
                region = _clean_region_name(region)

                # Validate region looks reasonable (not too short, not too long)
                if region and 2 <= len(region) <= 50 and not region.lower().startswith('street'):
                    full_name = f"Positive Behavior Supports Corporation - {region}"
                    return full_name, 0.85

    # Pattern 5: Check for split pattern where Corporation appears before PBS
    # (happens in some OCR cases)
    reverse_pattern = re.compile(
        r'Corporation\s*[-–]?\s*([A-Za-z][A-Za-z\s&]+?)\s*\n*.*?'
        r'Positive\s+Behavior\s+Supports',
        re.IGNORECASE | re.DOTALL
    )

    match = reverse_pattern.search(text)
    if match:
        region = match.group(1).strip()
        region = ' '.join(region.split())
        # BUG #2B FIX: Clean junk text
        region = _clean_region_name(region)
        if region and len(region) > 2:
            full_name = f"Positive Behavior Supports Corporation - {region}"
            return full_name, 0.80

    # No PBS organization found
    return None, 0.0


def is_pbs_organization(name: str) -> bool:
    """
    Check if a name is a PBS organization.

    Args:
        name: Organization name to check

    Returns:
        True if this is a PBS organization, False otherwise
    """
    if not name:
        return False

    # Must contain "Positive Behavior Supports"
    if "Positive Behavior Supports" not in name:
        return False

    # Should have Corporation and a region
    if "Corporation" not in name:
        return False

    # Should have a dash separator
    if " - " not in name:
        return False

    return True

