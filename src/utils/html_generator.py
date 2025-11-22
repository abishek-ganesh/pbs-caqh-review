#!/usr/bin/env python3
"""
HTML Output Generator for CAQH Data Summary Review Results

Generates clean, color-coded HTML output that can be embedded in SharePoint column.
Designed for Christian's credentialing team to review extraction results.

Author: Abishek Ganesh
Created: November 14, 2025
"""

from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from src.models.validation_result import DocumentValidationResult, FieldValidationResult
from src.config.constants import ValidationStatus, FieldCategory


def generate_html_output(
    validation_result: DocumentValidationResult,
    pdf_filename: str,
    include_timestamp: bool = True,
    include_confidence: bool = True,
) -> str:
    """
    Generate HTML output for CAQH extraction and validation results.

    Args:
        validation_result: DocumentValidationResult object with all field results
        pdf_filename: Name of the PDF file being reviewed
        include_timestamp: Whether to include processing timestamp (default: True)
        include_confidence: Whether to show confidence scores (default: True)

    Returns:
        str: Complete HTML document as string
    """

    # Determine overall status
    overall_status = validation_result.overall_status
    status_class = _get_status_class(overall_status)
    status_text = _get_status_text(overall_status)

    # Get all field results (we'll display them in a single table for now)
    all_fields = validation_result.field_results

    # Count errors
    error_count = len([f for f in validation_result.field_results
                      if not f.is_valid and f.errors])
    review_count = len([f for f in validation_result.field_results
                       if f.warnings or (not f.is_valid and not f.errors)])

    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CAQH Review - {pdf_filename}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 20px;
            background-color: #f5f5f5;
            margin: 0;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        h1 {{
            color: #2c3e50;
            margin-top: 0;
            font-size: 24px;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}

        h2 {{
            color: #34495e;
            font-size: 18px;
            margin-top: 25px;
            margin-bottom: 15px;
        }}

        .header-info {{
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}

        .header-info p {{
            margin: 5px 0;
            font-size: 14px;
        }}

        .status-badge {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 16px;
            margin: 10px 0;
        }}

        .status-approved {{
            background-color: #27ae60;
            color: white;
        }}

        .status-rejected {{
            background-color: #e74c3c;
            color: white;
        }}

        .status-needs-review {{
            background-color: #f39c12;
            color: white;
        }}

        .summary-stats {{
            display: flex;
            gap: 15px;
            margin: 15px 0;
            flex-wrap: wrap;
        }}

        .stat-box {{
            background-color: #ecf0f1;
            padding: 10px 15px;
            border-radius: 5px;
            flex: 1;
            min-width: 150px;
        }}

        .stat-label {{
            font-size: 12px;
            color: #7f8c8d;
            text-transform: uppercase;
        }}

        .stat-value {{
            font-size: 20px;
            font-weight: bold;
            color: #2c3e50;
            margin-top: 5px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            font-size: 14px;
        }}

        th {{
            background-color: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}

        td {{
            padding: 12px;
            border-bottom: 1px solid #ddd;
            vertical-align: top;
        }}

        tr:hover {{
            background-color: #f8f9fa;
        }}

        .field-name {{
            font-weight: 600;
            color: #2c3e50;
        }}

        .field-value {{
            font-family: 'Courier New', monospace;
            color: #555;
        }}

        .confidence-score {{
            font-size: 12px;
            color: #7f8c8d;
            font-weight: normal;
        }}

        .row-approved {{
            background-color: #d5f4e6;
            border-left: 4px solid #27ae60;
        }}

        .row-rejected {{
            background-color: #fadbd8;
            border-left: 4px solid #e74c3c;
        }}

        .row-needs-review {{
            background-color: #fef5e7;
            border-left: 4px solid #f39c12;
        }}

        .status-icon {{
            font-size: 18px;
            margin-right: 5px;
        }}

        .error-message {{
            color: #c0392b;
            font-size: 13px;
            margin-top: 5px;
            font-style: italic;
        }}

        .notes-section {{
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin-top: 20px;
            border-radius: 4px;
        }}

        .notes-section h3 {{
            margin-top: 0;
            color: #856404;
            font-size: 16px;
        }}

        .notes-section ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}

        .notes-section li {{
            margin: 5px 0;
            color: #856404;
        }}

        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            font-size: 12px;
            color: #7f8c8d;
            text-align: center;
        }}

        /* Dropdown Template Styles */
        .template-dropdown {{
            margin-top: 8px;
        }}

        .dropdown-toggle {{
            background-color: #3498db;
            color: white;
            border: none;
            padding: 4px 10px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
            transition: background-color 0.2s;
        }}

        .dropdown-toggle:hover {{
            background-color: #2980b9;
        }}

        .dropdown-toggle.active {{
            background-color: #2c3e50;
        }}

        .dropdown-content {{
            display: none;
            margin-top: 8px;
            padding: 10px;
            background-color: #f8f9fa;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 13px;
        }}

        .dropdown-content.show {{
            display: block;
        }}

        .template-text {{
            background-color: white;
            border: 1px solid #ccc;
            padding: 8px;
            border-radius: 3px;
            margin-bottom: 8px;
            font-family: inherit;
            line-height: 1.4;
        }}

        .copy-btn {{
            background-color: #27ae60;
            color: white;
            border: none;
            padding: 5px 12px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
            margin-right: 5px;
        }}

        .copy-btn:hover {{
            background-color: #219a52;
        }}

        .add-to-bulk-btn {{
            background-color: #9b59b6;
            color: white;
            border: none;
            padding: 5px 12px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
        }}

        .add-to-bulk-btn:hover {{
            background-color: #8e44ad;
        }}

        .copy-feedback {{
            display: inline-block;
            margin-left: 8px;
            color: #27ae60;
            font-size: 12px;
            opacity: 0;
            transition: opacity 0.3s;
        }}

        .copy-feedback.show {{
            opacity: 1;
        }}

        /* Bulk Rejection Box Styles */
        .bulk-rejection-section {{
            background-color: #f0f4f8;
            border: 2px solid #3498db;
            border-radius: 8px;
            padding: 20px;
            margin-top: 25px;
        }}

        .bulk-rejection-section h3 {{
            margin-top: 0;
            color: #2c3e50;
            font-size: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .bulk-rejection-textarea {{
            width: 100%;
            min-height: 150px;
            padding: 12px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-family: inherit;
            font-size: 14px;
            line-height: 1.5;
            resize: vertical;
            box-sizing: border-box;
        }}

        .bulk-rejection-textarea:focus {{
            outline: none;
            border-color: #3498db;
            box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
        }}

        .bulk-actions {{
            margin-top: 12px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}

        .bulk-copy-btn {{
            background-color: #27ae60;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
        }}

        .bulk-copy-btn:hover {{
            background-color: #219a52;
        }}

        .bulk-clear-btn {{
            background-color: #e74c3c;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
        }}

        .bulk-clear-btn:hover {{
            background-color: #c0392b;
        }}

        .bulk-helper-text {{
            font-size: 12px;
            color: #7f8c8d;
            margin-top: 8px;
        }}

        @media print {{
            body {{
                background-color: white;
            }}
            .container {{
                box-shadow: none;
            }}
            .dropdown-toggle, .copy-btn, .add-to-bulk-btn, .bulk-actions {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 CAQH Data Summary - AI Review Results</h1>

        <div class="header-info">
            <p><strong>PDF File:</strong> {pdf_filename}</p>"""

    if include_timestamp:
        html += f"""
            <p><strong>Processed:</strong> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>"""

    html += f"""
        </div>

        <div class="status-badge {status_class}">
            {_get_status_icon(overall_status)} Overall Status: {status_text}
        </div>

        <div class="summary-stats">
            <div class="stat-box">
                <div class="stat-label">Fields Checked</div>
                <div class="stat-value">{validation_result.total_fields_checked}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Fields Passed</div>
                <div class="stat-value" style="color: #27ae60;">{validation_result.fields_passed}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Errors Found</div>
                <div class="stat-value" style="color: #e74c3c;">{error_count}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Need Review</div>
                <div class="stat-value" style="color: #f39c12;">{review_count}</div>
            </div>
        </div>
"""

    # All Fields Table
    if all_fields:
        # Reset dropdown counter for each new HTML document
        global _dropdown_counter
        _dropdown_counter = 0

        html += f"""
        <h2>📋 Extracted Fields</h2>
        <table>
            <thead>
                <tr>
                    <th style="width: 25%;">Field</th>
                    <th style="width: 35%;">Value</th>
                    <th style="width: 40%;">Status</th>
                </tr>
            </thead>
            <tbody>
"""
        for field in all_fields:
            html += _generate_field_row(field, include_confidence)

        html += """
            </tbody>
        </table>
"""

    # Notes section if there are errors or reviews needed
    if error_count > 0 or review_count > 0:
        html += f"""
        <div class="notes-section">
            <h3>⚠️ Review Notes</h3>
            <ul>
"""
        if error_count > 0:
            html += f"""
                <li><strong>{error_count} error(s) found</strong> - These fields failed validation and need correction before approval.</li>
"""
        if review_count > 0:
            html += f"""
                <li><strong>{review_count} field(s) need manual review</strong> - Low confidence or unable to validate automatically.</li>
"""
        html += """
                <li><strong>AI Recommendation:</strong> Manual review required before final decision.</li>
            </ul>
        </div>
"""

    # Add bulk rejection text box if there are errors or reviews needed
    if error_count > 0 or review_count > 0:
        html += """
        <div class="bulk-rejection-section">
            <h3>📧 Bulk Rejection Text</h3>
            <p class="bulk-helper-text">Click "Add to Bulk" on individual fields above, or type directly. Copy all text at once for your rejection email.</p>
            <textarea class="bulk-rejection-textarea" id="bulk-rejection-text" placeholder="Rejection reasons will appear here when you click 'Add to Bulk' on individual fields above.

You can also type or edit text directly in this box.

Example format:
- Medicaid ID: Please update your Medicaid ID in CAQH...
- License Expiration: Your license expiration date must be a future date..."></textarea>
            <div class="bulk-actions">
                <button class="bulk-copy-btn" onclick="copyBulkText()">📋 Copy All Text</button>
                <button class="bulk-clear-btn" onclick="clearBulkText()">🗑️ Clear</button>
                <span class="copy-feedback" id="bulk-copy-feedback">✓ Copied!</span>
            </div>
        </div>
"""

    # Add JavaScript for dropdown and copy functionality
    html += """
    <script>
        // Toggle dropdown visibility
        function toggleDropdown(dropdownId) {
            const dropdown = document.getElementById(dropdownId);
            const button = document.getElementById('btn-' + dropdownId);

            // Close all other dropdowns first
            document.querySelectorAll('.dropdown-content.show').forEach(function(el) {
                if (el.id !== dropdownId) {
                    el.classList.remove('show');
                    document.getElementById('btn-' + el.id).classList.remove('active');
                }
            });

            // Toggle this dropdown
            dropdown.classList.toggle('show');
            button.classList.toggle('active');
        }

        // Copy text to clipboard and show feedback
        function copyText(textId, feedbackId) {
            const textElement = document.getElementById(textId);
            const text = textElement.innerText || textElement.textContent;

            navigator.clipboard.writeText(text).then(function() {
                // Show feedback
                const feedback = document.getElementById(feedbackId);
                feedback.classList.add('show');
                setTimeout(function() {
                    feedback.classList.remove('show');
                }, 2000);
            }).catch(function(err) {
                console.error('Failed to copy text: ', err);
                alert('Failed to copy. Please select and copy manually.');
            });
        }

        // Add text to bulk rejection textarea
        function addToBulk(textId) {
            const textElement = document.getElementById(textId);
            const text = textElement.innerText || textElement.textContent;
            const bulkTextarea = document.getElementById('bulk-rejection-text');

            if (bulkTextarea) {
                // Add bullet point and text
                const currentText = bulkTextarea.value.trim();
                const newText = '• ' + text;

                if (currentText) {
                    bulkTextarea.value = currentText + '\\n\\n' + newText;
                } else {
                    bulkTextarea.value = newText;
                }

                // Scroll to bottom of textarea
                bulkTextarea.scrollTop = bulkTextarea.scrollHeight;

                // Flash the textarea to show something was added
                bulkTextarea.style.backgroundColor = '#d5f4e6';
                setTimeout(function() {
                    bulkTextarea.style.backgroundColor = '';
                }, 300);
            }
        }

        // Copy all bulk rejection text
        function copyBulkText() {
            const bulkTextarea = document.getElementById('bulk-rejection-text');
            const text = bulkTextarea.value;

            if (!text.trim()) {
                alert('No text to copy. Add rejection reasons first.');
                return;
            }

            navigator.clipboard.writeText(text).then(function() {
                const feedback = document.getElementById('bulk-copy-feedback');
                feedback.classList.add('show');
                setTimeout(function() {
                    feedback.classList.remove('show');
                }, 2000);
            }).catch(function(err) {
                console.error('Failed to copy text: ', err);
                // Fallback for older browsers
                bulkTextarea.select();
                document.execCommand('copy');
                alert('Text copied!');
            });
        }

        // Clear bulk rejection textarea
        function clearBulkText() {
            const bulkTextarea = document.getElementById('bulk-rejection-text');
            if (bulkTextarea.value.trim() && !confirm('Clear all rejection text?')) {
                return;
            }
            bulkTextarea.value = '';
        }

        // Close dropdowns when clicking outside
        document.addEventListener('click', function(event) {
            if (!event.target.closest('.template-dropdown')) {
                document.querySelectorAll('.dropdown-content.show').forEach(function(el) {
                    el.classList.remove('show');
                    document.getElementById('btn-' + el.id).classList.remove('active');
                });
            }
        });
    </script>
"""

    html += f"""
        <div class="footer">
            Generated by PBS CAQH Data Summary Review Tool (AI-Powered) | For credentialing review purposes only
        </div>
    </div>
</body>
</html>
"""

    return html


# Global counter for generating unique dropdown IDs
_dropdown_counter = 0


def _generate_field_row(field: FieldValidationResult, include_confidence: bool) -> str:
    """Generate HTML table row for a single field."""
    global _dropdown_counter

    # Determine validation status from field properties
    if field.is_valid:
        validation_status = ValidationStatus.AI_REVIEWED_LOOKS_GOOD
    elif field.errors:
        validation_status = ValidationStatus.AI_REJECTED
    else:
        validation_status = ValidationStatus.NEEDS_HUMAN_REVIEW

    # Determine row class based on validation status
    row_class = _get_row_class(validation_status)

    # Format field name (convert snake_case to Title Case)
    field_display_name = field.field_name.replace('_', ' ').title()

    # Format field value
    if field.extracted_value is None:
        field_value = '<em style="color: #999;">Not found</em>'
    else:
        field_value = str(field.extracted_value)

    # Add confidence score if requested
    confidence_html = ""
    if include_confidence and field.confidence is not None:
        confidence_pct = int(field.confidence * 100)
        confidence_html = f' <span class="confidence-score">({confidence_pct}% confident)</span>'

    # Format status
    status_icon = _get_status_icon(validation_status)
    status_text = _get_status_text(validation_status)

    # Add error message if rejected
    error_html = ""
    if validation_status == ValidationStatus.AI_REJECTED:
        if field.errors:
            error_messages = " | ".join(field.errors)
            error_html = f'<div class="error-message">⚠️ {error_messages}</div>'
    elif validation_status == ValidationStatus.NEEDS_HUMAN_REVIEW:
        if field.warnings:
            warning_messages = " | ".join(field.warnings)
            error_html = f'<div class="error-message" style="color: #d68910;">ℹ️ {warning_messages}</div>'
        elif field.notes:
            error_html = f'<div class="error-message" style="color: #d68910;">ℹ️ {field.notes}</div>'

    # Generate dropdown template for rejected/needs-review fields
    dropdown_html = ""
    if validation_status in (ValidationStatus.AI_REJECTED, ValidationStatus.NEEDS_HUMAN_REVIEW):
        _dropdown_counter += 1
        dropdown_id = f"dropdown-{_dropdown_counter}"

        # Generate placeholder rejection text (will be replaced with real templates from Christian)
        placeholder_template = _get_placeholder_template(field.field_name, field.errors or field.warnings or [])

        dropdown_html = f'''
                    <div class="template-dropdown">
                        <button class="dropdown-toggle" onclick="toggleDropdown('{dropdown_id}')" id="btn-{dropdown_id}">
                            📋 Rejection Template
                        </button>
                        <div class="dropdown-content" id="{dropdown_id}">
                            <div class="template-text" id="text-{dropdown_id}">{placeholder_template}</div>
                            <button class="copy-btn" onclick="copyText('text-{dropdown_id}', 'feedback-{dropdown_id}')">📋 Copy</button>
                            <button class="add-to-bulk-btn" onclick="addToBulk('text-{dropdown_id}')">➕ Add to Bulk</button>
                            <span class="copy-feedback" id="feedback-{dropdown_id}">✓ Copied!</span>
                        </div>
                    </div>'''

    return f"""
                <tr class="{row_class}">
                    <td class="field-name">{field_display_name}</td>
                    <td class="field-value">{field_value}{confidence_html}</td>
                    <td>{status_icon} {status_text}{error_html}{dropdown_html}</td>
                </tr>
"""


def _get_placeholder_template(field_name: str, errors: List[str]) -> str:
    """
    Generate placeholder rejection template text for a field.

    This will be replaced with Christian's actual templates once received.
    For now, generates sensible placeholder text based on field name and errors.
    """
    field_display = field_name.replace('_', ' ').title()

    # Default placeholder templates by field type
    placeholders = {
        'medicaid_id': 'Please update your Medicaid ID in CAQH. The Medicaid ID field must be completed with your valid state Medicaid provider number.',
        'ssn': 'Please verify and update your Social Security Number in CAQH. The SSN must be in the correct format (XXX-XX-XXXX).',
        'individual_npi': 'Please verify your Individual NPI number in CAQH. The NPI must be a valid 10-digit number.',
        'practice_location_name': 'Please verify your Practice Location Name in CAQH. The practice location must match "Positive Behavior Supports Corporation" followed by the region.',
        'professional_license_expiration_date': 'Please update your Professional License information in CAQH. Your license expiration date must be a future date - expired licenses cannot be accepted.',
        'insurance_policy_number': 'Please verify your Insurance Policy Number in CAQH.',
        'insurance_covered_location': 'Please verify your Insurance Covered Location in CAQH.',
        'insurance_current_effective_date': 'Please verify your Insurance Effective Date in CAQH.',
        'insurance_current_expiration_date': 'Please verify your Insurance Expiration Date in CAQH.',
        'insurance_carrier_name': 'Please verify your Insurance Carrier Name in CAQH.',
    }

    # Return field-specific placeholder or generic one
    if field_name in placeholders:
        return placeholders[field_name]
    else:
        error_text = errors[0] if errors else "validation issue"
        return f'Please review and update the {field_display} field in CAQH. Issue: {error_text}'


def _get_status_class(status: ValidationStatus) -> str:
    """Get CSS class for validation status."""
    if status in (ValidationStatus.APPROVED, ValidationStatus.AI_REVIEWED_LOOKS_GOOD):
        return "status-approved"
    elif status in (ValidationStatus.REJECTED, ValidationStatus.AI_REJECTED):
        return "status-rejected"
    else:
        return "status-needs-review"


def _get_row_class(status: ValidationStatus) -> str:
    """Get CSS class for table row based on validation status."""
    if status in (ValidationStatus.APPROVED, ValidationStatus.AI_REVIEWED_LOOKS_GOOD):
        return "row-approved"
    elif status in (ValidationStatus.REJECTED, ValidationStatus.AI_REJECTED):
        return "row-rejected"
    else:
        return "row-needs-review"


def _get_status_text(status: ValidationStatus) -> str:
    """Get human-readable text for validation status."""
    if status in (ValidationStatus.APPROVED, ValidationStatus.AI_REVIEWED_LOOKS_GOOD):
        return "APPROVED"
    elif status in (ValidationStatus.REJECTED, ValidationStatus.AI_REJECTED):
        return "REJECTED"
    else:
        return "NEEDS REVIEW"


def _get_status_icon(status: ValidationStatus) -> str:
    """Get emoji icon for validation status."""
    if status in (ValidationStatus.APPROVED, ValidationStatus.AI_REVIEWED_LOOKS_GOOD):
        return "✅"
    elif status in (ValidationStatus.REJECTED, ValidationStatus.AI_REJECTED):
        return "❌"
    else:
        return "⚠️"


def save_html_output(html_content: str, output_path: str) -> None:
    """
    Save HTML content to file.

    Args:
        html_content: HTML string to save
        output_path: Path to save HTML file
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html_content, encoding='utf-8')


if __name__ == "__main__":
    print("HTML Generator module - Use generate_html_output() to create HTML from validation results")
