"""
CAQH Data Summary Reviewer - Simple Testing App

This is a super simple web app for testing the POC without coding knowledge.
Just upload a PDF, and see the results!

Created for: Christian (non-coder testing)
Tech: Streamlit (zero frontend code needed)
Run: streamlit run app.py
"""

import streamlit as st
import time
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Import POC components
from src.extraction.pdf_reader import read_pdf_text
from src.extraction.field_extractor import extract_all_fields
from src.edge_cases.file_integrity import FileIntegrityChecker
from src.edge_cases.document_type_checker import DocumentTypeChecker
from src.validation.validation_engine import get_validation_engine
from src.utils.html_generator import generate_html_output

# ==============================================================================
# PAGE CONFIGURATION
# ==============================================================================

st.set_page_config(
    page_title="CAQH Data Summary Reviewer - POC",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_file_integrity_checker():
    """Get singleton file integrity checker."""
    if 'integrity_checker' not in st.session_state:
        st.session_state.integrity_checker = FileIntegrityChecker()
    return st.session_state.integrity_checker


def get_document_type_checker():
    """Get singleton document type checker."""
    if 'doc_checker' not in st.session_state:
        st.session_state.doc_checker = DocumentTypeChecker()
    return st.session_state.doc_checker


def process_pdf(pdf_path: str):
    """
    Process a PDF through the complete POC pipeline.

    Returns:
        dict: Processing results with status, fields, validation, etc.
    """
    result = {
        'final_status': 'ERROR',
        'rejection_reasons': [],
        'edge_cases': {
            'file_integrity': False,
            'document_type': False
        },
        'fields': {},
        'extraction_time': 0,
        'total_time': 0,
        'html_output': None,  # NEW: Enhanced HTML output
        'validation_result': None  # NEW: Full validation result object
    }

    start_total = time.time()

    try:
        # Extract PDF text (needed for all checks)
        pdf_text = read_pdf_text(pdf_path)

        # Step 1: File Integrity Check
        integrity_checker = get_file_integrity_checker()
        integrity_result = integrity_checker.validate_file(pdf_path, pdf_text)

        result['edge_cases']['file_integrity'] = integrity_result.is_valid

        if not integrity_result.is_valid:
            result['final_status'] = 'NEEDS_REVIEW'
            result['rejection_reasons'].append(f'File integrity issue: {integrity_result.corruption_type}')
            result['total_time'] = round(time.time() - start_total, 2)
            return result

        # Step 2: Document Type Check
        doc_checker = get_document_type_checker()
        doc_result = doc_checker.validate_document(pdf_path, pdf_text)

        result['edge_cases']['document_type'] = doc_result.is_valid_caqh

        if not doc_result.is_valid_caqh:
            result['final_status'] = 'REJECTED'
            result['rejection_reasons'].append('Wrong document type: Please upload your CAQH Data Summary')
            result['total_time'] = round(time.time() - start_total, 2)
            return result

        # Step 3: Extract Fields (5 POC critical fields)
        start_extraction = time.time()
        extraction_result = extract_all_fields(pdf_path)
        extraction_time = time.time() - start_extraction

        result['extraction_time'] = round(extraction_time, 2)

        # Build fields dictionary with values and confidence
        for field_result in extraction_result.field_results:
            result['fields'][field_result.field_name] = {
                'value': field_result.extracted_value,
                'confidence': field_result.confidence,
                'method': field_result.extraction_method
            }

        # Step 4: Validation - Check for missing critical fields

        # Check for missing Medicaid ID
        if result['fields'].get('medicaid_id', {}).get('value') is None:
            result['rejection_reasons'].append('Missing Medicaid ID')

        # Check for missing PBS Practice Location
        if result['fields'].get('practice_location_name', {}).get('value') is None:
            result['rejection_reasons'].append('Missing PBS Practice Location')

        # Determine final status
        if len(result['rejection_reasons']) > 0:
            result['final_status'] = 'REJECTED'
        else:
            result['final_status'] = 'APPROVED'

        # Step 5: Run validation and generate enhanced HTML output
        try:
            pdf_filename = Path(pdf_path).name
            validation_engine = get_validation_engine()
            validation_result = validation_engine.validate_document(extraction_result, pdf_filename)
            result['validation_result'] = validation_result

            # Generate enhanced HTML with dropdown templates and bulk rejection box
            html_output = generate_html_output(
                validation_result=validation_result,
                pdf_filename=pdf_filename,
                include_timestamp=True,
                include_confidence=True
            )
            result['html_output'] = html_output
        except Exception as html_error:
            # HTML generation failed but extraction succeeded - continue
            result['html_output'] = f"<p>HTML generation error: {str(html_error)}</p>"

        result['total_time'] = round(time.time() - start_total, 2)
        return result

    except Exception as e:
        result['final_status'] = 'ERROR'
        result['rejection_reasons'].append(f'Processing error: {str(e)}')
        result['total_time'] = round(time.time() - start_total, 2)
        return result


def display_status_badge(status: str):
    """Display status badge with appropriate color."""
    if status == 'APPROVED':
        st.success(f"✅ **{status}**")
    elif status == 'REJECTED':
        st.error(f"❌ **{status}**")
    elif status == 'NEEDS_REVIEW':
        st.warning(f"⚠️ **{status}**")
    else:  # ERROR
        st.error(f"🔴 **{status}**")


def mask_ssn(ssn: str) -> str:
    """
    Mask SSN for PHI protection - show only last 4 digits.

    Examples:
        "123-45-6789" -> "XXX-XX-6789"
        "123456789" -> "XXXXX6789"
    """
    if not ssn:
        return ssn

    # Remove any non-digit characters to get raw SSN
    digits_only = ''.join(c for c in str(ssn) if c.isdigit())

    if len(digits_only) >= 4:
        # Mask all but last 4 digits
        last_four = digits_only[-4:]

        # If original had dashes, maintain format
        if '-' in str(ssn):
            return f"XXX-XX-{last_four}"
        else:
            masked = 'X' * (len(digits_only) - 4) + last_four
            return masked

    # If less than 4 digits, mask everything
    return 'X' * len(digits_only)


def display_field(field_name: str, field_data: dict):
    """Display a single field with value only (no confidence/method)."""
    value = field_data.get('value')

    # Format field name (remove underscores, title case)
    display_name = field_name.replace('_', ' ').title()

    # Mask SSN for PHI protection
    if field_name == 'ssn' and value:
        value = mask_ssn(value)

    # Show value
    if value is None:
        st.markdown(f"**{display_name}:** `Not Found`")
    else:
        st.markdown(f"**{display_name}:** `{value}`")


# ==============================================================================
# MAIN APP UI
# ==============================================================================

# Header
st.title("📄 CAQH Data Summary Reviewer")
st.markdown("**POC Testing App** - Upload a PDF to see automated review results")
st.markdown("---")

# Instructions
with st.expander("ℹ️ How to Use This App", expanded=False):
    st.markdown("""
    ### Simple Instructions:

    1. **Click "Browse files"** below to upload a CAQH Data Summary PDF
    2. **Wait for processing** (~2-3 minutes for extraction)
    3. **View results** - Status, fields, validation, and rejection reasons

    ### What This App Does:

    - ✅ Checks file integrity (corrupted files)
    - ✅ Validates document type (correct CAQH format)
    - ✅ Extracts 10 critical fields (5 identification + 5 insurance fields)
    - ✅ Validates required fields
    - ✅ Determines final status (APPROVED/REJECTED/NEEDS_REVIEW)

    ### Status Meanings:

    - **APPROVED**: All critical fields extracted successfully, no validation issues
    - **REJECTED**: Missing critical fields or wrong document type
    - **NEEDS_REVIEW**: File integrity issues or low extraction confidence
    - **ERROR**: Unexpected processing error
    """)

st.markdown("---")

# File uploader
uploaded_file = st.file_uploader(
    "Upload CAQH Data Summary PDF",
    type=['pdf'],
    help="Select a PDF file from your computer"
)

# Process uploaded file
if uploaded_file is not None:
    # Save uploaded file temporarily
    temp_path = f"/tmp/{uploaded_file.name}"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.markdown("---")

    # Check if we already processed this file (avoid re-processing on button clicks)
    file_key = f"{uploaded_file.name}_{uploaded_file.size}"

    if 'processed_file_key' not in st.session_state or st.session_state.processed_file_key != file_key:
        # New file - process it
        with st.spinner("Processing PDF... This may take 2-3 minutes for field extraction..."):
            result = process_pdf(temp_path)
        # Cache the result
        st.session_state.processed_file_key = file_key
        st.session_state.cached_result = result
    else:
        # Same file - use cached result
        result = st.session_state.cached_result

    # Processing complete - show results header
    st.subheader(f"Results for: {uploaded_file.name}")
    st.success("✅ Processing complete!")
    st.markdown("---")

    # ========== FINAL STATUS ==========
    st.subheader("📊 Final Status")
    display_status_badge(result['final_status'])

    # ========== REJECTION REASONS ==========
    if result['rejection_reasons']:
        st.markdown("---")
        st.subheader("⚠️ Rejection Reasons")
        for i, reason in enumerate(result['rejection_reasons'], 1):
            st.error(f"{i}. {reason}")

    # ========== EXTRACTED FIELDS ==========
    st.markdown("---")
    st.subheader("📋 Extracted Fields (10 POC Fields)")

    if result['fields']:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("##### Identity & Professional")
            if 'medicaid_id' in result['fields']:
                display_field('medicaid_id', result['fields']['medicaid_id'])
            if 'ssn' in result['fields']:
                display_field('ssn', result['fields']['ssn'])
            if 'individual_npi' in result['fields']:
                display_field('individual_npi', result['fields']['individual_npi'])
            if 'practice_location_name' in result['fields']:
                display_field('practice_location_name', result['fields']['practice_location_name'])
            if 'professional_license_expiration_date' in result['fields']:
                display_field('professional_license_expiration_date', result['fields']['professional_license_expiration_date'])

        with col2:
            st.markdown("##### Professional Liability Insurance")
            if 'insurance_policy_number' in result['fields']:
                display_field('insurance_policy_number', result['fields']['insurance_policy_number'])
            if 'insurance_covered_location' in result['fields']:
                display_field('insurance_covered_location', result['fields']['insurance_covered_location'])
            if 'insurance_current_effective_date' in result['fields']:
                display_field('insurance_current_effective_date', result['fields']['insurance_current_effective_date'])
            if 'insurance_current_expiration_date' in result['fields']:
                display_field('insurance_current_expiration_date', result['fields']['insurance_current_expiration_date'])
            if 'insurance_carrier_name' in result['fields']:
                display_field('insurance_carrier_name', result['fields']['insurance_carrier_name'])
    else:
        st.info("No fields extracted (document failed early validation)")

    # ========== ENHANCED HTML OUTPUT ==========
    st.markdown("---")
    st.subheader("📄 Enhanced HTML Report")

    if result.get('html_output'):
        # Download button for HTML file
        html_filename = f"{uploaded_file.name.replace('.pdf', '')}_review.html"
        st.download_button(
            label="📥 Download HTML Report",
            data=result['html_output'],
            file_name=html_filename,
            mime="text/html",
            help="Download the enhanced HTML report with dropdown templates and bulk rejection text box",
            key="download_html_report"
        )

        # Preview HTML in expandable section
        with st.expander("👁️ Preview HTML Report", expanded=False):
            st.components.v1.html(result['html_output'], height=800, scrolling=True)
    else:
        st.info("HTML report not available")

    # ========== EDGE CASE CHECKS ==========
    st.markdown("---")
    st.subheader("🔍 Edge Case Checks")

    col1, col2 = st.columns(2)

    with col1:
        if result['edge_cases']['file_integrity']:
            st.success("✅ File Integrity: Passed")
        else:
            st.error("❌ File Integrity: Failed")

    with col2:
        if result['edge_cases']['document_type']:
            st.success("✅ Document Type: Valid CAQH")
        else:
            st.error("❌ Document Type: Not CAQH")

    # ========== PERFORMANCE METRICS ==========
    st.markdown("---")
    st.subheader("⚡ Performance Metrics")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Extraction Time", f"{result['extraction_time']}s")

    with col2:
        st.metric("Total Processing Time", f"{result['total_time']}s")

    # ========== RAW RESULTS (EXPANDABLE) ==========
    with st.expander("🔧 View Raw Results (JSON)", expanded=False):
        st.json(result)

    # Clean up temp file
    if os.path.exists(temp_path):
        os.remove(temp_path)

else:
    # No file uploaded yet
    st.info("👆 Upload a PDF file above to start processing")

# Footer
st.markdown("---")
st.caption("CAQH Data Summary Reviewer POC - October 2025")
st.caption("Automated first-pass review for behavior analyst credentialing")
