"""
Application Constants and Enumerations

Defines constants used throughout the application including user types,
validation statuses, field categories, and other enums.

KEY DESIGN PRINCIPLES (per Christian's feedback, Sept 9, 2025):

1. NO HUMAN INTERPRETATION NEEDED:
   - "None of the fields should require human interpretation"
   - "The Cheat Sheet shows exactly what the user should put in almost every case"
   - If AI cannot reliably validate a field → remove it from AI tool, route to human

2. ALL-AT-ONCE VALIDATION:
   - Validate ALL fields in a single pass
   - Show users everything wrong on first review
   - Don't do multiple automated passes (causes confusion)

3. CLEAR PASS/FAIL CRITERIA:
   - All validations have definitive right/wrong answers
   - No fuzzy matching or ambiguous rules
   - Low confidence → human review (never guess)
"""

from enum import Enum


class UserType(str, Enum):
    """CAQH user types based on Analyst Level"""
    BCBA = "BCBA"
    BCBA_D = "BCBA-D"
    BCABA = "BCaBA"
    LBHC = "LBHC"
    RBT = "RBT"


class ValidationStatus(str, Enum):
    """Validation result statuses"""
    PENDING = "Pending"
    AI_REVIEWED_LOOKS_GOOD = "AI Reviewed - Looks Good"
    AI_REJECTED = "AI Rejected"
    NEEDS_HUMAN_REVIEW = "Needs Human Review"
    APPROVED = "Approved"  # Final human approval
    REJECTED = "Rejected"  # Final human rejection


class FieldCategory(str, Enum):
    """CAQH Data Summary field categories"""
    PERSONAL_INFORMATION = "Personal Information"
    PROFESSIONAL_IDS = "Professional IDs"
    EDUCATION_TRAINING = "Education & Professional Training"
    SPECIALTIES = "Specialties"
    PRACTICE_LOCATIONS = "Practice Locations"
    HOSPITAL_AFFILIATIONS = "Hospital Affiliations"
    CREDENTIALING_CONTACTS = "Credentialing Contacts"
    PROFESSIONAL_LIABILITY_INSURANCE = "Professional Liability Insurance"
    EMPLOYMENT_INFORMATION = "Employment Information"
    PROFESSIONAL_REFERENCES = "Professional References"
    DISCLOSURE = "Disclosure"


class ValidationType(str, Enum):
    """Types of validation checks"""
    REQUIRED = "required"
    FORMAT = "format"
    DATE_PAST = "date_past"
    DATE_FUTURE = "date_future"
    DATE_RANGE = "date_range"
    EXACT_MATCH = "exact_match"
    PATTERN_MATCH = "pattern_match"
    LOOKUP = "lookup"
    ENUM = "enum"
    BOOLEAN = "boolean"
    NUMERIC_RANGE = "numeric_range"
    CONDITIONAL = "conditional"


class ConfidenceLevel(str, Enum):
    """Confidence levels for extracted fields"""
    HIGH = "high"  # >= 0.9
    MEDIUM = "medium"  # 0.7 - 0.89
    LOW = "low"  # < 0.7


class RejectionReason(str, Enum):
    """Standard rejection reasons"""
    MISSING_REQUIRED_FIELD = "Missing required field"
    INVALID_FORMAT = "Invalid format"
    EXPIRED_DATE = "Expired date (must be future)"
    PAST_DATE_INVALID = "Invalid past date"
    PRACTICE_LOCATION_INCORRECT = "Practice Location Name incorrect"
    TAX_ID_MISMATCH = "Tax ID does not match expected value"
    NPI_MISMATCH = "Organizational NPI does not match expected value"
    PBS_CORP_MISSING = "PBS Corp name not mentioned"
    DISCLOSURE_RED_FLAG = "Disclosure question answered Yes"
    LOW_CONFIDENCE = "Low confidence extraction - needs human review"
    WRONG_DOCUMENT_TYPE = "Wrong document type"
    CORRUPTED_PDF = "Corrupted or unreadable PDF"
    DUPLICATE_SUBMISSION = "Duplicate submission"


# Regex patterns for format validation
REGEX_PATTERNS = {
    "ssn": r"^\d{3}-?\d{2}-?\d{4}$",
    "npi": r"^\d{10}$",
    "phone": r"^(\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}$",
    "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    "zip_code": r"^\d{5}(-\d{4})?$",
    "state": r"^[A-Z]{2}$",
    "tax_id": r"^\d{2}-?\d{7}$",
}


# US State abbreviations
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
]


# Critical fields for POC (First 5)
POC_CRITICAL_FIELDS_TIER_1 = [
    "medicaid_id",
    "ssn",
    "individual_npi",
    "practice_location_name",
    "professional_license_expiration_date",
]


# Critical fields for POC (Expand to 15)
POC_CRITICAL_FIELDS_TIER_2 = POC_CRITICAL_FIELDS_TIER_1 + [
    "license_number",
    "license_state",
    "practice_location_address",
    "practice_location_phone",
    "tax_id",
    "organizational_npi",
    "practice_location_email",
    "primary_specialty",
    "insurance_expiration_date",
    "insurance_policy_number",
]


# Duplicate detection window (minutes)
# Per Christian (Sept 9, 2025): "True duplicates are usually uploaded within 1-5 minutes.
# If >15 minutes apart with same filename, probably not a duplicate (user likely made changes)"
DUPLICATE_WINDOW_MINUTES = 15


# Confidence threshold for human review
DEFAULT_CONFIDENCE_THRESHOLD = 0.85


# Daily volume (per Christian Sept 9, 2025)
DAILY_PDF_VOLUME_MIN = 15
DAILY_PDF_VOLUME_MAX = 20


# Processing trigger options (per Christian Sept 9, 2025)
PROCESSING_TRIGGER_REALTIME = "realtime"  # Preferred: trigger on upload
PROCESSING_TRIGGER_BATCH = "batch"  # Fallback: 1-2x daily if realtime too taxing


# Practice Location Name pattern
PRACTICE_LOCATION_NAME_PREFIX = "Positive Behavior Supports Corporation"


# PHI fields to mask in logs
PHI_FIELDS = [
    "ssn",
    "social_security_number",
    "birth_date",
    "home_address",
    "personal_email",
]
