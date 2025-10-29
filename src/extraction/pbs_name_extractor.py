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
        if region:
            full_name = f"Positive Behavior Supports Corporation - {region}"
            return full_name, 0.95

    # Pattern 2: Look for the complete name potentially split across lines
    # but in the correct order
    pattern2 = re.compile(
        r'Positive\s+Behavior\s+Supports\s+'
        r'Corporation\s*[-–]\s*([A-Za-z\s]+?)(?:\n|Street|Phone|Fax|$)',
        re.IGNORECASE | re.DOTALL
    )

    match = pattern2.search(text)
    if match:
        region = match.group(1).strip()
        region = ' '.join(region.split())
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
                full_name = f"Positive Behavior Supports Corporation - {region}"
                return full_name, 0.90
        elif region_part2:  # Only second part found
            region = ' '.join(region_part2.split())
            if 2 <= len(region) <= 50:
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
            corp_pattern = re.compile(
                r'Corporation\s*[-–]?\s*([A-Za-z][A-Za-z\s&]+?)(?:\n|Street|Phone|$)',
                re.IGNORECASE
            )
            corp_match = corp_pattern.search(context)
            if corp_match:
                region = corp_match.group(1).strip()
                region = ' '.join(region.split())

                # Validate region looks reasonable (not too short, not too long)
                if 2 <= len(region) <= 50 and not region.lower().startswith('street'):
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


# Test the extractor
if __name__ == "__main__":
    # Test cases based on actual PDF patterns
    test_cases = [
        # Pattern from KD.pdf
        """
        Practice  Positive Behavior Supports
        Name :
        Corporation Central Florida
        -
        Street 1:  907 Outer Rd
        """,

        # Pattern from MEchenique.pdf
        """
        Practice Name: Positive Behavior Supports
        Corporation - Suwannee River
        """,

        # Pattern from LM.pdf
        """
        Organization: Positive Behavior Supports Corporation - Emerald Coast
        """,

        # Non-PBS organization
        """
        Practice Name: Neuro Dverse LLC
        Street: 123 Main St
        """
    ]

    for i, test_text in enumerate(test_cases, 1):
        name, confidence = extract_pbs_practice_name(test_text)
        print(f"Test {i}:")
        print(f"  Extracted: {name}")
        print(f"  Confidence: {confidence:.2f}")
        print(f"  Is PBS: {is_pbs_organization(name)}")
        print()