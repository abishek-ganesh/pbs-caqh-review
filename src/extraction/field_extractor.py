"""
Field Extraction Module

High-level field extraction from PDF text using label-proximity approach.
Extracts specific fields based on configuration in validation_rules.yaml.

Extraction Strategy:
1. Load field extraction configuration from YAML
2. Search for field labels in PDF text
3. Extract value near label using proximity + pattern matching
4. Calculate confidence score based on match quality
5. Return structured extraction results
"""

import re
import time
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..models.extraction_result import (
    FieldExtractionResult,
    DocumentExtractionResult,
    ExtractionSummary,
    get_extraction_summary
)
from .pdf_reader import read_pdf_text, validate_pdf_file, WrongDocumentTypeError


# Path to validation rules configuration
CONFIG_PATH = Path(__file__).parent.parent / "config" / "validation_rules.yaml"


def load_extraction_config() -> dict:
    """
    Load extraction configuration from validation_rules.yaml.

    Returns:
        Dictionary of field configurations with extraction hints
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Validation rules file not found: {CONFIG_PATH}")

    with open(CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f)

    return config


def extract_field(
    text: str,
    field_name: str,
    field_config: dict
) -> FieldExtractionResult:
    """
    Extract a single field from PDF text using label-proximity approach.

    Algorithm:
    1. Search for field label in text
    2. Extract text within max_distance characters after label
    3. Apply regex pattern to extract value
    4. Calculate confidence based on match quality

    Args:
        text: Full PDF text content
        field_name: Name of field to extract
        field_config: Field configuration from validation_rules.yaml

    Returns:
        FieldExtractionResult with extracted value and confidence score
    """
    extraction_config = field_config.get("extraction", {})

    # === SECTION-AWARE FILTERING (BUG #2A FIX) ===
    # Do section filtering FIRST, before any extraction attempts
    # This prevents extracting from wrong sections (e.g., Billing Department vs Practice Locations)
    section_name = extraction_config.get("section")
    search_text = text
    section_offset = 0

    if section_name:
        # Try to find the section in the PDF
        # Common section headers: "PRACTICE LOCATIONS", "PRACTICE LOCATION", "Practice Locations", etc.
        section_patterns = [
            section_name.upper().replace("_", r"\s+"),
            section_name.title().replace("_", " "),
            section_name.replace("_", r"\s+")
        ]

        for sect_pattern in section_patterns:
            # Look for section header (may have "SECTION" prefix or numbering)
            section_header_match = re.search(
                rf"(?:SECTION\s+\d+\s*:?\s*)?{sect_pattern}",
                text,
                re.IGNORECASE
            )

            if section_header_match:
                section_start = section_header_match.end()
                # Find next section or use rest of document
                # Look for next major section header (e.g., "EDUCATION", "DISCLOSURE", etc.)
                next_section_pattern = r"\n\s*(?:SECTION\s+\d+|[A-Z][A-Z\s]{10,})\s*\n"
                next_section_match = re.search(next_section_pattern, text[section_start:])

                if next_section_match:
                    section_end = section_start + next_section_match.start()
                else:
                    section_end = len(text)

                # Use section text for search
                search_text = text[section_start:section_end]
                section_offset = section_start
                break

    # === SPECIAL HANDLING: Insurance Fields ===
    # For insurance fields, extract all fields at once from the policy with furthest expiration date
    # This is more efficient and accurate than extracting each field separately
    if field_name.startswith("insurance_"):
        try:
            from .field_specific_extractors import extract_insurance_fields

            # Extract all insurance fields at once (cached globally to avoid re-extraction)
            # Use a cache to avoid extracting multiple times when processing multiple insurance fields
            if not hasattr(extract_field, '_insurance_cache'):
                extract_field._insurance_cache = {}

            # Cache key is the text hash (to handle different PDFs)
            import hashlib
            text_hash = hashlib.md5(text.encode()).hexdigest()[:16]

            if text_hash not in extract_field._insurance_cache:
                # First insurance field request - extract all fields
                extract_field._insurance_cache[text_hash] = extract_insurance_fields(text)

            insurance_data = extract_field._insurance_cache[text_hash]
            extracted_value = insurance_data.get(field_name)

            # Calculate confidence based on whether value was found
            if extracted_value:
                confidence = 0.90  # High confidence for successful insurance extraction
            else:
                confidence = 0.0

            return FieldExtractionResult(
                field_name=field_name,
                extracted_value=extracted_value,
                confidence=confidence,
                extraction_method="insurance_extractor",
                notes=f"Extracted from policy with furthest expiration date" if extracted_value else "No insurance data found"
            )
        except Exception as e:
            # Insurance extractor failed - return error
            return FieldExtractionResult(
                field_name=field_name,
                extracted_value=None,
                confidence=0.0,
                extraction_method="insurance_extractor_failed",
                errors=[f"Insurance extraction failed: {str(e)}"]
            )

    # === SPECIAL HANDLING: Practice Location Name ===
    # For practice_location_name, use consolidated PBS extractor
    if field_name == "practice_location_name":
        try:
            from src.extraction.pbs_name_extractor import extract_pbs_practice_name_complete
            # Use the consolidated function with pattern_required from config
            pattern_required = extraction_config.get("pattern_required", False)
            pbs_name, pbs_confidence = extract_pbs_practice_name_complete(search_text, pattern_required)

            if pbs_name and pbs_confidence >= 0.80:
                # PBS name found with good confidence - return immediately
                return FieldExtractionResult(
                    field_name=field_name,
                    extracted_value=pbs_name,
                    confidence=pbs_confidence,
                    extraction_method="pbs_extractor",
                    notes=f"PBS organization detected: {pbs_name}" + (f" (in {section_name} section)" if section_name else "")
                )
            # Fall through to regular extraction for non-PBS organizations
        except ImportError:
            # PBS extractor not available - continue with regular extraction
            pass

    if not extraction_config:
        return FieldExtractionResult(
            field_name=field_name,
            extracted_value=None,
            confidence=0.0,
            extraction_method="no_config",
            errors=[f"No extraction configuration found for {field_name}"]
        )

    labels = extraction_config.get("labels", [])
    pattern = extraction_config.get("pattern", "")
    max_distance = extraction_config.get("max_distance", 50)

    if not labels:
        return FieldExtractionResult(
            field_name=field_name,
            extracted_value=None,
            confidence=0.0,
            extraction_method="no_labels",
            errors=[f"No extraction labels defined for {field_name}"]
        )

    # Try each label in order until one succeeds
    for label in labels:
        result = _extract_using_label(
            search_text, field_name, label, pattern, max_distance, extraction_config
        )

        # If extraction succeeded (found value), return it
        if result.extracted_value:
            return result

    # No label matched
    return FieldExtractionResult(
        field_name=field_name,
        extracted_value=None,
        confidence=0.0,
        extraction_method="label_proximity",
        errors=[f"Could not find any of the labels: {', '.join(labels)}"],
        notes=f"Tried labels: {', '.join(labels)}"
    )


def _extract_using_label(
    text: str,
    field_name: str,
    label: str,
    pattern: str,
    max_distance: int,
    extraction_config: dict
) -> FieldExtractionResult:
    """
    Extract field value using a specific label with bidirectional search.

    Simplified version using field-specific helper functions.

    Args:
        text: PDF text content
        field_name: Name of field
        label: Label to search for
        pattern: Regex pattern to extract value
        max_distance: Max characters before/after label to search
        extraction_config: Full extraction configuration

    Returns:
        FieldExtractionResult
    """
    from src.extraction.field_specific_extractors import (
        extract_practice_location_multiline,
        validate_medicaid_id_context,
        filter_future_license_dates,
        extract_value_before_label,
        extract_value_after_label
    )

    # Build label search pattern (case-insensitive, flexible whitespace)
    label_pattern = re.escape(label).replace(r"\ ", r"\s*")

    # Add word boundary at start for short labels to avoid matching inside words
    # e.g., "Name :" should not match "First Name :"
    if len(label.split()[0]) <= 6:  # Short first word (like "Name", "Tax", "SSN")
        label_pattern = r"(?<!\w)" + label_pattern  # Negative lookbehind for word char

    label_pattern = label_pattern + r"\s*:?\s*"  # Optional colon, flexible whitespace

    # Note: section filtering already done in calling function (extract_field lines 74-113)
    # The 'text' parameter passed here is already section-filtered if section was specified
    # For backward compatibility with existing code, alias it as search_text
    search_text = text
    section_name = extraction_config.get("section")  # For error messages

    # Search for label in text (section-aware if section was found)
    # For practice_location_name, find ALL matches and filter out Tax Information subsection
    if field_name == "practice_location_name":
        all_matches = list(re.finditer(label_pattern, search_text, re.IGNORECASE))

        # Filter out matches in Tax Information subsection (check 200 chars before match)
        filtered_matches = []
        for match in all_matches:
            context_before = search_text[max(0, match.start() - 200):match.start()]
            context_after = search_text[match.start():min(len(search_text), match.end() + 50)]

            # Skip if preceded by "Tax Information" or contains "W-9" (Tax subsection indicator)
            if "Tax Information" in context_before or "tax information" in context_before.lower():
                continue
            if "W-9" in context_after or "w-9" in context_after.lower():
                continue
            if "appears on" in context_after.lower():
                continue

            filtered_matches.append(match)

        if filtered_matches:
            label_match = filtered_matches[0]  # Take first non-Tax match
        else:
            # All matches were in Tax section - skip this label, try next one
            label_match = None
    else:
        label_match = re.search(label_pattern, search_text, re.IGNORECASE)

    if not label_match:
        return FieldExtractionResult(
            field_name=field_name,
            extracted_value=None,
            confidence=0.0,
            extraction_method="bidirectional_search",
            errors=[f"Label '{label}' not found in document" + (f" (searched in {section_name} section)" if section_name else "")]
        )

    # BIDIRECTIONAL SEARCH: Check both before and after label
    label_start = label_match.start()
    label_end = label_match.end()

    # Region after label (traditional approach)
    after_region_start = label_end
    after_region_end = min(len(search_text), label_end + max_distance)
    after_region = search_text[after_region_start:after_region_end]

    # Region before label (handles reversed label-value pairs)
    before_region_start = max(0, label_start - max_distance)
    before_region_end = label_start
    before_region = search_text[before_region_start:before_region_end]

    candidates = []

    # SPECIAL CASE: For professional_license_expiration_date, find ALL date matches (not just first)
    # This ensures we can filter to future dates even if past dates appear first
    if pattern and field_name == "professional_license_expiration_date":
        # Find ALL matches in after region
        after_matches = list(re.finditer(pattern, after_region))
        for after_match in after_matches:
            value = after_match.group().strip()
            distance = after_match.start()
            base_conf = max(0, 0.90 - (distance / max_distance * 0.20))
            candidates.append((value, base_conf, distance, 'after'))

        # Find ALL matches in before region
        before_matches = list(re.finditer(pattern, before_region))
        for before_match in before_matches:
            value = before_match.group().strip()
            distance = len(before_region) - before_match.end()
            base_conf = max(0, 0.85 - (distance / max_distance * 0.25))
            candidates.append((value, base_conf, distance, 'before'))

    # STANDARD CASE: For other fields, find first/closest match only
    elif pattern:
        # Try to find pattern match AFTER label (higher priority)
        after_match = re.search(pattern, after_region)
        if after_match:
            value = after_match.group().strip()
            distance = after_match.start()
            # Higher base confidence for values after label (expected location)
            base_conf = max(0, 0.90 - (distance / max_distance * 0.20))
            candidates.append((value, base_conf, distance, 'after'))

        # Try to find pattern match BEFORE label (lower priority)
        # Search in reverse for most recent value before label
        before_matches = list(re.finditer(pattern, before_region))
        if before_matches:
            # Take the last (closest) match to the label
            before_match = before_matches[-1]
            value = before_match.group().strip()
            distance = len(before_region) - before_match.end()
            # Lower base confidence for values before label (unusual location)
            base_conf = max(0, 0.85 - (distance / max_distance * 0.25))
            candidates.append((value, base_conf, distance, 'before'))

    # If no pattern or no pattern matches, try line-based extraction
    # BUT: Skip line-based fallback if pattern_required=true (prevents false positives for numeric fields)
    pattern_required = extraction_config.get("pattern_required", False)

    if not candidates:
        # If no candidates and pattern is required, return None
        if not candidates and pattern_required and pattern:
            return FieldExtractionResult(
                field_name=field_name,
                extracted_value=None,
                confidence=0.0,
                extraction_method="bidirectional_search",
                errors=[f"Label '{label}' found but value doesn't match required pattern: {pattern}"],
                notes=f"Pattern required but not matched (pattern_required=true)"
            )

        # Try after label first
        after_lines = after_region.split('\n')

        # For practice_location_name, do bidirectional extraction if PBS extractor didn't find anything
        if field_name == "practice_location_name" and not candidates:
            # Delimiters that indicate end of practice name
            # Made more flexible to catch OCR variations
            stop_patterns = [
                r'Street\s*\d',  # "Street 2051" or "Street1" or "Street 1"
                r'Street\s*:',   # "Street :" or "Street:"
                r'^\d{3,5}\s',   # Line starting with 3-5 digits (address number)
                r'Tax\s+ID',
                r':\s*:',  # Common form delimiter
                r'Phone\s+Number',
                r'Appointment\s+Phone',
                r'City\s*:',
                r'County\s*:',
                r'Zip\s*Code',
                r'Country\s*:'
            ]

            # For practice names, we need BOTH before and after label content
            # because OCR often splits "Practice Name :" across multiple lines

            # Collect lines BEFORE label (e.g., "Practice  Positive Behavior Supports")
            before_lines = before_region.split('\n')
            before_collected = []
            for line in reversed(before_lines[-3:]):  # Check last 3 lines before label
                line_stripped = line.strip()
                # Skip empty lines and pure label lines
                if line_stripped and len(line_stripped) > 1:
                    if not re.match(r'^(Practice|Name|Location)\s*:?\s*$', line_stripped, re.IGNORECASE):
                        before_collected.insert(0, line_stripped)  # Insert at start to maintain order

            # Collect lines AFTER label (e.g., "Corporation Central Florida", "-")
            after_collected = []
            for i, line in enumerate(after_lines[:8]):  # Check first 8 lines (increased from 5)
                line_stripped = line.strip().rstrip(':').strip()

                # Check if we hit a stop pattern
                hit_delimiter = any(re.search(pattern, line, re.IGNORECASE) for pattern in stop_patterns)
                if hit_delimiter:
                    break

                # Add non-empty lines to collection (including single-char like "-")
                if line_stripped and len(line_stripped) >= 1:  # Changed from > 1 to >= 1
                    # Only skip exact label matches, not content
                    if not re.match(r'^(Name\s*:?|Practice\s*:?)$', line_stripped, re.IGNORECASE):
                        after_collected.append(line_stripped)

            # Combine before + after lines
            all_collected = before_collected + after_collected

            if all_collected:
                # Join with spaces
                multi_line_value = ' '.join(all_collected)

                # Clean up: ensure proper " - " spacing for region suffix
                # Handle cases like "Corporation Central Florida -" or "Corporation -Central Florida"
                multi_line_value = re.sub(r'\s+-\s*', ' - ', multi_line_value)  # Normalize dash spacing
                multi_line_value = re.sub(r'-\s+', '- ', multi_line_value)  # Fix "- Region" to "- Region"

                distance = 0
                # Higher confidence if we captured content from both sides
                base_conf = 0.85 if (before_collected and after_collected) else 0.80
                candidates.append((multi_line_value, base_conf, distance, 'bidirectional'))
        else:
            # Standard single-line extraction for other fields
            for i, line in enumerate(after_lines[:3]):  # Check first 3 lines
                line_stripped = line.strip().rstrip(':').strip()
                if line_stripped and len(line_stripped) > 1:
                    distance = i
                    base_conf = max(0, 0.75 - (distance * 0.15))
                    candidates.append((line_stripped, base_conf, distance, 'after'))
                    break

        # Try before label if nothing found after
        if not candidates:
            before_lines = before_region.split('\n')
            for i, line in enumerate(reversed(before_lines[-3:])):  # Check last 3 lines
                line_stripped = line.strip().rstrip(':').strip()
                if line_stripped and len(line_stripped) > 1:
                    distance = i
                    base_conf = max(0, 0.70 - (distance * 0.15))
                    candidates.append((line_stripped, base_conf, distance, 'before'))
                    break

    # No value found in either direction
    if not candidates:
        return FieldExtractionResult(
            field_name=field_name,
            extracted_value=None,
            confidence=0.3,
            extraction_method="bidirectional_search",
            raw_text_context=after_region[:50] if after_region else before_region[-50:],
            errors=[f"Label '{label}' found but no value extracted in either direction"],
            warnings=[f"Expected pattern: {pattern}"] if pattern else []
        )

    # SPECIAL VALIDATION: For medicaid_id, filter out NPI-labeled numbers (prevents false positives)
    if field_name == "medicaid_id" and candidates:
        # Check context around each candidate for NPI indicators
        filtered_candidates = []
        for value, conf, dist, direc in candidates:
            # Get context around the value
            if direc == 'after':
                context_start = max(0, label_end - 50)
                context_end = min(len(search_text), label_end + dist + len(value) + 50)
            else:  # 'before' or 'bidirectional'
                context_start = max(0, label_start - dist - len(value) - 50)
                context_end = min(len(search_text), label_start + 50)

            context = search_text[context_start:context_end]

            # Reject if context contains NPI labels near the extracted value
            # Common NPI patterns: "NPI:", "NPI Number", "(Type 2) NPI", "Individual NPI", "Group NPI"
            npi_indicators = [
                r'\bNPI\s*:',  # "NPI:"
                r'\bNPI\s+Number',  # "NPI Number"
                r'\(Type\s+\d+\)\s*NPI',  # "(Type 2) NPI"
                r'\bGroup\s+NPI',  # "Group NPI"
                r'\bIndividual\s+NPI',  # "Individual NPI"
                r'National\s+Provider\s+Identifier',  # Full name
            ]

            has_npi_context = any(re.search(pattern, context, re.IGNORECASE) for pattern in npi_indicators)

            if not has_npi_context:
                # No NPI indicators - this is likely a legitimate Medicaid ID
                filtered_candidates.append((value, conf, dist, direc))

        # Use filtered candidates
        if filtered_candidates:
            candidates = filtered_candidates
        else:
            # All candidates were NPI-labeled - return None
            return FieldExtractionResult(
                field_name=field_name,
                extracted_value=None,
                confidence=0.0,
                extraction_method="bidirectional_search",
                errors=[f"Found numeric values but all were labeled as NPI (not Medicaid ID)"],
                notes=f"Rejected {len(candidates)} NPI-labeled number(s) to prevent false positive"
            )

    # SPECIAL VALIDATION: For professional_license_expiration_date, filter to future dates only (BUG #1 FIX)
    if field_name == "professional_license_expiration_date" and candidates:
        from datetime import datetime

        # Get date formats from extraction config
        date_formats = extraction_config.get("date_formats", ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"])
        today = datetime.now().date()

        future_candidates = []
        for value, conf, dist, direc in candidates:
            # Try to parse the date using configured formats
            parsed_date = None
            for date_format in date_formats:
                try:
                    parsed_date = datetime.strptime(value, date_format).date()
                    break
                except ValueError:
                    continue

            # Only keep dates that are in the future
            if parsed_date and parsed_date > today:
                # Boost confidence for future dates
                boosted_conf = min(1.0, conf + 0.10)
                future_candidates.append((value, boosted_conf, dist, direc, parsed_date))

        if future_candidates:
            # Sort by parsed date (furthest future first), then confidence
            future_candidates.sort(key=lambda x: (-x[4].toordinal(), -x[1]))
            # Convert back to original format (without parsed_date)
            candidates = [(val, conf, dist, direc) for val, conf, dist, direc, _ in future_candidates]
        else:
            # All dates were in the past - extract most recent expired date with WARNING
            # ISSUE #2 FIX: Better UX - show expired date with warning instead of returning None
            past_candidates = []
            for value, conf, dist, direc in candidates:
                # Try to parse the date
                parsed_date = None
                for date_format in date_formats:
                    try:
                        parsed_date = datetime.strptime(value, date_format).date()
                        break
                    except ValueError:
                        continue

                if parsed_date:
                    # Lower confidence for past dates
                    lowered_conf = max(0.3, conf - 0.20)
                    past_candidates.append((value, lowered_conf, dist, direc, parsed_date))

            if past_candidates:
                # Sort by most recent (closest to today), then confidence
                past_candidates.sort(key=lambda x: (-x[4].toordinal(), -x[1]))
                # Get most recent past date
                best_past = past_candidates[0]
                extracted_value, confidence, distance, direction, parsed_date = best_past
                days_ago = (today - parsed_date).days

                # Return with WARNING
                return FieldExtractionResult(
                    field_name=field_name,
                    extracted_value=extracted_value,
                    confidence=confidence,
                    extraction_method="bidirectional_search",
                    errors=[],
                    warnings=[f"⚠️ LICENSE EXPIRED: This license expired {days_ago} days ago on {extracted_value}. Current license required."],
                    notes=f"Extracted expired license date. Found {len(past_candidates)} past date(s), selected most recent."
                )
            else:
                # Couldn't parse any dates - return None
                return FieldExtractionResult(
                    field_name=field_name,
                    extracted_value=None,
                    confidence=0.0,
                    extraction_method="bidirectional_search",
                    errors=["Found date(s) but could not parse them"],
                    notes="Date parsing failed for all candidates"
                )

    # Sort candidates by confidence (highest first), then distance (closest first)
    candidates.sort(key=lambda x: (-x[1], x[2]))

    # Take best candidate
    extracted_value, confidence, distance, direction = candidates[0]

    # Boost confidence if pattern matched
    if pattern:
        confidence = min(1.0, confidence + 0.05)

    # Post-process: Clean up practice location names
    if field_name == "practice_location_name":
        # Import cleanup functions from PBS extractor
        from src.extraction.pbs_name_extractor import normalize_pbs_name, clean_practice_location_name

        # Try to normalize if it's a PBS organization
        normalized_pbs = normalize_pbs_name(extracted_value)
        if normalized_pbs:
            extracted_value = normalized_pbs
        else:
            # Not PBS - clean up using general cleanup function
            extracted_value = clean_practice_location_name(extracted_value)

        # ALWAYS: Collapse multiple spaces/newlines to single space
        extracted_value = ' '.join(extracted_value.split())

    # Check for warnings
    warnings = _check_extraction_warnings(extracted_value, extraction_config)

    # Determine context region for display
    if direction == 'after':
        context_region = after_region[:100]
    else:
        context_region = before_region[-100:]

    return FieldExtractionResult(
        field_name=field_name,
        extracted_value=extracted_value,
        confidence=confidence,
        extraction_method="bidirectional_search",
        raw_text_context=context_region,
        warnings=warnings,
        notes=f"Extracted using label: '{label}' (found {direction} label, distance: {distance})"
    )


def _calculate_confidence(
    label_found: bool,
    pattern_matched: bool,
    value_length: int,
    extraction_config: dict
) -> float:
    """
    Calculate confidence score for extraction.

    Factors:
    - Label found: +0.5
    - Pattern matched: +0.4
    - Reasonable value length: +0.1

    Args:
        label_found: Whether field label was found
        pattern_matched: Whether regex pattern matched
        value_length: Length of extracted value
        extraction_config: Field extraction configuration

    Returns:
        Confidence score (0.0 - 1.0)
    """
    confidence = 0.0

    if not label_found:
        return 0.0

    # Base confidence for finding label
    confidence += 0.50

    # Boost for pattern match
    if pattern_matched:
        confidence += 0.40

    # Small boost for reasonable value length
    if 2 <= value_length <= 200:
        confidence += 0.10
    elif value_length < 2:
        confidence -= 0.10  # Very short values lower confidence

    # Check against configured threshold
    threshold = extraction_config.get("confidence_threshold", 0.85)

    return min(confidence, 1.0)  # Cap at 1.0


def _check_extraction_warnings(value: str, extraction_config: dict) -> List[str]:
    """
    Check for extraction quality warnings.

    Args:
        value: Extracted value
        extraction_config: Field extraction configuration

    Returns:
        List of warning messages
    """
    warnings = []

    # Check value length
    if len(value) < 2:
        warnings.append("Extracted value is very short - may be incomplete")

    # Field-specific warnings from config
    config_warnings = extraction_config.get("warnings", {})

    if "short_name" in config_warnings and len(value) < 3:
        warnings.append(config_warnings["short_name"])

    return warnings


def extract_all_fields(
    pdf_path: str,
    field_names: Optional[List[str]] = None
) -> DocumentExtractionResult:
    """
    Extract all configured fields from a PDF document.

    Args:
        pdf_path: Path to PDF file
        field_names: Optional list of specific fields to extract.
                    If None, extracts all critical POC fields.

    Returns:
        DocumentExtractionResult with all extraction results
    """
    start_time = time.time()
    pdf_file = Path(pdf_path)

    # Validate PDF file
    is_valid, error_message = validate_pdf_file(pdf_path)
    if not is_valid:
        return DocumentExtractionResult(
            pdf_path=str(pdf_path),
            pdf_filename=pdf_file.name,
            total_fields_attempted=0,
            fields_extracted=0,
            field_results=[],
            extraction_time=time.time() - start_time,
            extraction_method="validation_failed",
            is_caqh_document=False,
            errors=[error_message]
        )

    # Read PDF text
    try:
        text = read_pdf_text(pdf_path)
    except Exception as e:
        return DocumentExtractionResult(
            pdf_path=str(pdf_path),
            pdf_filename=pdf_file.name,
            total_fields_attempted=0,
            fields_extracted=0,
            field_results=[],
            extraction_time=time.time() - start_time,
            extraction_method="read_failed",
            errors=[f"Failed to read PDF: {e}"]
        )

    # === WRONG DOCUMENT DETECTION ===
    # Check if this is a valid CAQH Data Summary document
    # If not, return None for all fields
    from src.edge_cases.document_type_checker import DocumentTypeChecker
    doc_checker = DocumentTypeChecker()
    doc_type_result = doc_checker.validate_document(pdf_path, text)

    if not doc_type_result.is_valid_caqh:
        # Wrong document type - return None for all fields
        # Create field results with None values for all requested fields
        if field_names is None:
            field_names = [
                "medicaid_id",
                "ssn",
                "individual_npi",
                "practice_location_name",
                "professional_license_expiration_date"
            ]

        field_results = []
        for field_name in field_names:
            field_results.append(FieldExtractionResult(
                field_name=field_name,
                extracted_value=None,
                confidence=0.0,
                extraction_method="wrong_document",
                errors=[doc_type_result.message],
                notes=f"Wrong document type: {doc_type_result.document_type}"
            ))

        return DocumentExtractionResult(
            pdf_path=str(pdf_path),
            pdf_filename=pdf_file.name,
            total_fields_attempted=len(field_names),
            fields_extracted=0,
            field_results=field_results,
            extraction_time=time.time() - start_time,
            extraction_method="wrong_document",
            is_caqh_document=False,
            errors=[doc_type_result.message],
            notes=f"Document type: {doc_type_result.document_type}"
        )

    # Load extraction configuration
    try:
        config = load_extraction_config()
    except Exception as e:
        return DocumentExtractionResult(
            pdf_path=str(pdf_path),
            pdf_filename=pdf_file.name,
            total_fields_attempted=0,
            fields_extracted=0,
            field_results=[],
            extraction_time=time.time() - start_time,
            extraction_method="config_failed",
            errors=[f"Failed to load extraction config: {e}"]
        )

    # Determine which fields to extract
    if field_names is None:
        # Default: Extract 5 critical POC fields
        field_names = [
            "medicaid_id",
            "ssn",
            "individual_npi",
            "practice_location_name",
            "professional_license_expiration_date"
        ]

    # Extract each field
    field_results = []
    for field_name in field_names:
        field_config = config.get(field_name, {})

        if not field_config:
            field_results.append(FieldExtractionResult(
                field_name=field_name,
                extracted_value=None,
                confidence=0.0,
                extraction_method="no_config",
                errors=[f"No configuration found for field: {field_name}"]
            ))
            continue

        result = extract_field(text, field_name, field_config)
        field_results.append(result)

    # Count successful extractions
    fields_extracted = sum(1 for r in field_results if r.extracted_value is not None)

    # Determine primary extraction method (native_pdf or ocr)
    extraction_method = "native_pdf"  # Default
    if any("OCR" in text for page in text.split("--- Page")):
        extraction_method = "ocr"

    extraction_time = time.time() - start_time

    return DocumentExtractionResult(
        pdf_path=str(pdf_path),
        pdf_filename=pdf_file.name,
        total_fields_attempted=len(field_names),
        fields_extracted=fields_extracted,
        field_results=field_results,
        extraction_time=extraction_time,
        extraction_method=extraction_method,
        is_caqh_document=True
    )


# Convenience function for extracting just the 5 POC critical fields
def extract_all_fields_from_text(
    text: str,
    pdf_path: str = "unknown.pdf",
    field_names: Optional[List[str]] = None
) -> DocumentExtractionResult:
    """
    Extract all configured fields from pre-extracted text (e.g., cached OCR).

    This is useful for:
    - Testing with cached text to avoid repeated PDF extraction
    - Processing text that was extracted and cached previously
    - Working with text from OCR or other extraction methods

    Args:
        text: Pre-extracted text content from PDF
        pdf_path: Original PDF path (for reference/metadata)
        field_names: Optional list of specific fields to extract.
                    If None, extracts all critical POC fields.

    Returns:
        DocumentExtractionResult with all extraction results
    """
    start_time = time.time()
    pdf_file = Path(pdf_path)

    # Load extraction configuration
    try:
        config = load_extraction_config()
    except Exception as e:
        return DocumentExtractionResult(
            pdf_path=str(pdf_path),
            pdf_filename=pdf_file.name,
            total_fields_attempted=0,
            fields_extracted=0,
            field_results=[],
            extraction_time=time.time() - start_time,
            extraction_method="config_failed",
            errors=[f"Failed to load extraction config: {e}"]
        )

    # Determine which fields to extract
    if field_names is None:
        # Default: Extract 5 critical POC fields
        field_names = [
            "medicaid_id",
            "ssn",
            "individual_npi",
            "practice_location_name",
            "professional_license_expiration_date"
        ]

    # Extract each field from the provided text
    field_results = []
    for field_name in field_names:
        field_config = config.get(field_name, {})

        if not field_config:
            field_results.append(FieldExtractionResult(
                field_name=field_name,
                extracted_value=None,
                confidence=0.0,
                extraction_method="no_config",
                errors=[f"No configuration found for field: {field_name}"]
            ))
            continue

        result = extract_field(text, field_name, field_config)
        field_results.append(result)

    # Count successful extractions
    fields_extracted = sum(1 for r in field_results if r.extracted_value is not None)

    # Determine primary extraction method
    extraction_method = "cached_text"  # Since we're working with pre-extracted text

    extraction_time = time.time() - start_time

    return DocumentExtractionResult(
        pdf_path=str(pdf_path),
        pdf_filename=pdf_file.name,
        total_fields_attempted=len(field_names),
        fields_extracted=fields_extracted,
        field_results=field_results,
        extraction_time=extraction_time,
        extraction_method=extraction_method,
        is_caqh_document=True  # Assume true for now, caller should validate
    )


def extract_poc_fields(pdf_path: str) -> DocumentExtractionResult:
    """
    Extract only the 5 critical POC fields from a PDF.

    POC Fields:
    1. Medicaid ID
    2. SSN
    3. Individual NPI
    4. Practice Location Name
    5. Professional License Expiration Date

    Args:
        pdf_path: Path to PDF file

    Returns:
        DocumentExtractionResult with 5 field results
    """
    poc_fields = [
        "medicaid_id",
        "ssn",
        "individual_npi",
        "practice_location_name",
        "professional_license_expiration_date"
    ]

    return extract_all_fields(pdf_path, field_names=poc_fields)
