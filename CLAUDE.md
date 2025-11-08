# CLAUDE.md

Project context and guidance for AI assistants working on this codebase.

---

## Project Overview

**CAQH Data Summary Review Automation** - AI-powered first-pass review of CAQH PDF Data Summaries for PBS credentialing team.

**Problem:** Reviewers spend 30-45 minutes manually validating 100+ fields per PDF (15-20 daily submissions).
**Solution:** AI extraction + validation → 70-80% time reduction (down to 2-3 minutes). Human final approval.

**Key Stakeholders:** Credentialing Reviewers (users) | Behavior Analysts (submitters) | PBS IT (infrastructure)

---

## ⚠️ CRITICAL: Always Update GAMEPLAN.md

**MANDATORY** after completing ANY task or making significant progress:

**Update GAMEPLAN.md with:**
- Date and what was accomplished
- Key results and metrics
- Files modified
- Challenges and solutions
- Next steps

**Why:** GAMEPLAN.md is the single source of truth for project status, todos, and progress tracking.

---

## Quick Reference

### Essential Documentation
- **GAMEPLAN.md** - Active todos, progress log, weekly plans ⭐ CHECK HERE FIRST
- **docs/ARCHITECTURE_DECISIONS.md** - Why complex logic exists, key design choices ⭐ READ BEFORE MODIFYING
- **docs/BUGS_TRACKING.md** - Bug tracking with lessons learned ⭐ CHECK BEFORE FIXING BUGS
- **docs/BUSINESS_RULES.md** - Critical business requirements and field validations
- **docs/COMMON_TASKS.md** - Development tasks, code patterns, testing workflow
- **docs/technical/CAQH_TECHNICAL_PLAN.md** - Detailed technical implementation specs
- **docs/CAQH_Cheat_Sheet.md** - Markdown version of validation source

### Test Data & Validation
- **examples/approved/** - 5 approved PDF samples
- **examples/rejected/** - 6 rejected PDF samples
- **data/GROUND_TRUTH.md** - Verified correct values for test PDFs
- **docs/CAQH_CheatSheet.pdf** - Original validation rules source (sole authority)

---

## Directory Structure

```
caqh-datasummaryreviewer-tool/
├── src/                         # Core codebase
│   ├── config/                  # Configuration and constants
│   │   ├── __init__.py          # Config module exports
│   │   ├── constants.py         # Enums: UserType, ValidationStatus, FieldCategory, ConfidenceLevel
│   │   └── validation_rules.yaml# Field validation rules and extraction config (YAML)
│   │
│   ├── extraction/              # PDF reading, field extraction, OCR
│   │   ├── __init__.py          # Extraction module exports
│   │   ├── field_extractor.py   # Main extraction orchestrator (956 lines)
│   │   ├── field_specific_extractors.py  # Field-specific extraction helpers (260 lines)
│   │   ├── pbs_name_extractor.py # PBS practice location name extraction (429 lines)
│   │   ├── pdf_reader.py        # PDF text extraction with Tesseract OCR fallback
│   │   └── cache_manager.py     # OCR caching for performance
│   │
│   ├── validation/              # Validation engine and field validators
│   │   ├── __init__.py          # Validation module exports
│   │   ├── validation_engine.py # Main validation orchestrator
│   │   ├── field_validators.py  # Individual field validation functions (1,720 lines)
│   │   ├── rule_loader.py       # Loads validation rules from YAML
│   │   └── confidence_scorer.py # Calculates confidence scores for extractions
│   │
│   ├── edge_cases/              # Edge case detection and handling
│   │   ├── __init__.py          # Edge cases module exports
│   │   ├── duplicate_detector.py# 15-minute duplicate submission detection (with logging)
│   │   ├── wrong_doc_detector.py# Wrong document format detection
│   │   └── file_integrity.py    # File corruption and integrity checks
│   │
│   ├── models/                  # Pydantic data models for type safety
│   │   ├── __init__.py          # Models module exports
│   │   ├── validation_result.py # FieldValidationResult, DocumentValidationResult
│   │   └── extraction_result.py # FieldExtractionResult, DocumentExtractionResult
│   │
│   ├── utils/                   # Utility functions and helpers
│   │   ├── __init__.py          # Utils module exports
│   │   ├── date_utils.py        # Date parsing and validation utilities
│   │   ├── format_utils.py      # SSN, NPI, phone, email format validators
│   │   ├── logger.py            # Centralized PHI-aware logging with rotation
│   │   ├── error_handler.py     # Standardized error handling utilities
│   │   └── reporting.py         # Comprehensive error reporting and templates
│   │
│   └── sharepoint/              # SharePoint integration (future implementation)
│       └── __init__.py          # SharePoint module placeholder
│
├── tests/                       # Test suite
│   ├── test_accuracy.py         # Accuracy testing against ground truth data
│   ├── test_pbs_extraction.py   # PBS name extraction edge case tests
│   ├── test_date_validation.py  # Date parsing and validation tests
│   ├── test_performance.py      # Full performance benchmark suite
│   ├── test_performance_simple.py # Quick performance smoke test
│   ├── ocr_cache/               # Cached OCR text for faster test runs
│   └── results/                 # Test results and accuracy reports
│       └── TEST_RESULTS.md      # Latest test results summary
│
├── docs/                        # All documentation
│   ├── ARCHITECTURE_DECISIONS.md # Why complex logic exists, key design choices
│   ├── BUGS_TRACKING.md         # Bug tracking with lessons learned
│   ├── BUSINESS_RULES.md        # Critical business requirements from CAQH Cheat Sheet
│   ├── COMMON_TASKS.md          # Development tasks, code patterns, testing workflow
│   ├── CAQH_CheatSheet.pdf      # ⭐ Validation source of truth (official CAQH doc)
│   ├── CAQH_Cheat_Sheet.md      # Markdown version of validation rules
│   ├── SETUP.md                 # Development environment setup instructions
│   ├── technical/               # Technical specs and implementation details
│   │   └── CAQH_TECHNICAL_PLAN.md # Detailed technical implementation plan
│   ├── meeting-notes/           # Stakeholder feedback and meeting notes
│   │   └── christian_feedback_nov7_2025.md # Christian's testing feedback (Nov 7)
│   └── templates/               # Email templates for rejections
│
├── data/
│   ├── ground_truth/            # Test answer keys (JSON format)
│   │   └── *.json               # Individual PDF ground truth files
│   ├── ground_truth_all.json    # Consolidated ground truth (all PDFs)
│   ├── GROUND_TRUTH.md          # Human-readable test answers with notes
│   ├── ocr_cache/               # OCR performance cache (persisted)
│   └── submission_history.json  # Duplicate detection history (runtime)
│
├── examples/
│   ├── approved/                # 5 approved CAQH PDF samples for testing
│   ├── rejected/                # 6 rejected/wrong format PDF samples
│   └── new_examples/            # Christian's test PDFs (JBrown, PParent, etc.)
│
├── archive/                     # Archived POC code and test results
│   ├── poc_final/               # Final POC deliverables (archived)
│   ├── poc_testing/             # POC testing scripts (archived)
│   └── test_results/            # Historical test results (archived)
│
├── app.py                       # Main Streamlit web application
├── requirements.txt             # Python dependencies (PyPDF2, pdfplumber, Tesseract, etc.)
├── CLAUDE.md                    # This file - AI assistant guidance
├── GAMEPLAN.md                  # Master plan, todos, and progress tracking
└── README.md                    # Project README (if exists)
```

---

## Tech Stack

**PDF Processing:** PyPDF2, pdfplumber, Tesseract OCR, Pillow
**Validation:** Pydantic, YAML config, regex patterns
**Backend:** Python 3.9+, async/await
**Integration:** SharePoint Lists, Power Automate, SQL Server (future)
**Web UI:** Streamlit (for testing/demos)

---

## Development Workflow

### Key Principles
1. **Validation Source:** ALL rules from CAQH Cheat Sheet ONLY (never PBS internal systems)
2. **Single-Pass Validation:** Validate all fields at once, comprehensive error reporting
3. **Confidence Scoring:** Every extraction has confidence score; low confidence → human review
4. **Human-in-the-Loop:** AI suggests, human decides (never auto-approve)

### Code Patterns
- Config-driven validation (rules in `src/config/validation_rules.yaml`)
- PHI masking in logs (never log full SSN/DOB)
- Comprehensive error messages (show correct value, not just "wrong")
- Confidence thresholds: ≥0.90 high, 0.70-0.89 medium, <0.70 → human review

*See docs/COMMON_TASKS.md for detailed patterns and examples*

---

## Success Metrics

- Extraction accuracy: >95%
- False positive rate: <1% (don't approve bad submissions)
- False negative rate: <2% (don't reject good submissions)
- Processing time: <3 minutes per PDF

---

## When to Update This File

CLAUDE.md should be **stable**. Update only when:
- Critical business rules change (also update docs/BUSINESS_RULES.md)
- Tech stack changes significantly
- Directory structure changes

**For todos, progress, status → Always use GAMEPLAN.md instead**

---

*Last Updated: November 8, 2025 (Late Night) - Major code cleanup complete*
*Active todos and project status: GAMEPLAN.md*
*Bug tracking and lessons learned: docs/BUGS_TRACKING.md*
*Directory structure: Cleaned and accurate as of Nov 8, 2025*
