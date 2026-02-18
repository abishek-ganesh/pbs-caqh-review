"""
LLM-based field extraction using Azure OpenAI.

This module provides an alternative extraction method for complex fields
where rule-based regex extraction struggles (e.g., insurance fields with
complex multi-policy layouts).

Usage:
    from src.extraction.llm_extractor import LLMExtractor

    extractor = LLMExtractor()
    result = extractor.extract_fields(ocr_text, fields_to_extract)
"""

import os
import json
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMExtractionResult:
    """Result from LLM field extraction."""
    field_name: str
    value: Optional[str]
    confidence: float
    reasoning: Optional[str] = None


class LLMExtractor:
    """
    Extracts fields from OCR text using Azure OpenAI.

    Designed to handle complex cases where regex fails:
    - Insurance fields with multiple policies
    - Fields where OCR puts values before labels
    - Date confusion between similar field types
    """

    # Fields that benefit from LLM extraction
    SUPPORTED_FIELDS = [
        "insurance_policy_number",
        "insurance_carrier_name",
        "insurance_covered_location",
        "insurance_current_effective_date",
        "insurance_current_expiration_date",
        "professional_license_expiration_date",
        "license_expiration_date",
    ]

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        deployment_name: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        """
        Initialize the LLM extractor.

        Args:
            endpoint: Azure OpenAI endpoint URL
            api_key: Azure OpenAI API key
            deployment_name: Model deployment name (e.g., "gpt-4.1-mini")
            api_version: API version (e.g., "2024-02-15-preview")
        """
        self.endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.deployment_name = deployment_name or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

        self._client = None

    @property
    def client(self):
        """Lazy-load the Azure OpenAI client."""
        if self._client is None:
            if not self.endpoint or not self.api_key:
                raise ValueError(
                    "Azure OpenAI credentials not configured. "
                    "Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY environment variables."
                )

            try:
                from openai import AzureOpenAI
            except ImportError:
                raise ImportError(
                    "openai package not installed. Run: pip install openai"
                )

            self._client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
            )

        return self._client

    def is_configured(self) -> bool:
        """Check if Azure OpenAI credentials are configured."""
        return bool(self.endpoint and self.api_key)

    def extract_fields(
        self,
        ocr_text: str,
        fields: Optional[list[str]] = None,
    ) -> dict[str, LLMExtractionResult]:
        """
        Extract specified fields from OCR text using LLM.

        Args:
            ocr_text: The raw OCR text from the PDF
            fields: List of field names to extract (defaults to SUPPORTED_FIELDS)

        Returns:
            Dictionary mapping field names to extraction results
        """
        fields = fields or self.SUPPORTED_FIELDS

        # Build the extraction prompt
        prompt = self._build_extraction_prompt(ocr_text, fields)

        # Call Azure OpenAI
        response = self.client.chat.completions.create(
            model=self.deployment_name,
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
        )

        # Parse the response
        result_text = response.choices[0].message.content

        try:
            result_json = json.loads(result_text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response as JSON: {result_text}")
            return {}

        # Convert to LLMExtractionResult objects
        results = {}
        for field in fields:
            if field in result_json:
                field_data = result_json[field]
                if isinstance(field_data, dict):
                    results[field] = LLMExtractionResult(
                        field_name=field,
                        value=field_data.get("value"),
                        confidence=field_data.get("confidence", 0.0),
                        reasoning=field_data.get("reasoning"),
                    )
                else:
                    # Simple value without confidence
                    results[field] = LLMExtractionResult(
                        field_name=field,
                        value=field_data,
                        confidence=0.8,
                    )

        # Log token usage
        usage = response.usage
        logger.info(
            f"LLM extraction complete. "
            f"Tokens: {usage.prompt_tokens} in, {usage.completion_tokens} out, "
            f"Total: {usage.total_tokens}"
        )

        return results

    def extract_insurance_fields(self, ocr_text: str) -> dict[str, LLMExtractionResult]:
        """
        Extract insurance-specific fields.

        This is optimized for the insurance section which has complex
        multi-policy layouts that confuse regex extraction.
        """
        insurance_fields = [
            "insurance_policy_number",
            "insurance_carrier_name",
            "insurance_covered_location",
            "insurance_current_effective_date",
            "insurance_current_expiration_date",
        ]
        return self.extract_fields(ocr_text, insurance_fields)

    def _get_system_prompt(self) -> str:
        """Get the system prompt for field extraction."""
        return """You are an expert at extracting structured data from CAQH Provider Data Summary documents.

The text may be in HTML table format (from Mistral OCR) or raw text (from Tesseract OCR).
HTML format example: <tr><td>Policy Number :</td><td>6799172</td></tr>
Raw text may have values BEFORE or AFTER their labels on separate lines.

## INSURANCE FIELD RULES:
1. Look in "INSURANCE INFORMATION" section (NOT "Medicaid" section)
2. Policy numbers are typically 7-digit numbers like "6799172"
3. Carrier is usually "Lexington Insurance Company"
4. Extract "Current Effective Date" and "Current Expiration Date" (NOT "Original" dates)

## LICENSE FIELD RULES:
1. Look in "PROFESSIONAL IDENTIFICATION NUMBERS" → "Professional License" section
2. If provider has MULTIPLE licenses, prefer the one with Status = "Active"
3. License number formats vary by state (e.g., "1537", "0-23-14311")

## GENERAL RULES:
- Preserve exact date formats (MM/DD/YYYY or M/D/YYYY)
- Return null if field cannot be found
- Provide confidence scores based on certainty

Return a JSON object with this structure:
{
    "field_name": {
        "value": "extracted value or null",
        "confidence": 0.95,
        "reasoning": "brief explanation"
    }
}"""

    def _build_extraction_prompt(self, ocr_text: str, fields: list[str]) -> str:
        """Build the user prompt for field extraction."""
        field_descriptions = {
            "insurance_policy_number": "The policy number for the insurance coverage (e.g., '6799172')",
            "insurance_carrier_name": "The name of the insurance carrier (e.g., 'Lexington Insurance Company')",
            "insurance_covered_location": "The practice location covered by the insurance policy",
            "insurance_current_effective_date": "The current effective date of the insurance policy (MM/DD/YYYY)",
            "insurance_current_expiration_date": "The current expiration date of the insurance policy (MM/DD/YYYY)",
            "professional_license_expiration_date": "The expiration date of the professional license (MM/DD/YYYY)",
            "license_expiration_date": "The expiration date of the license (alias for professional_license_expiration_date)",
        }

        fields_text = "\n".join([
            f"- {field}: {field_descriptions.get(field, 'Extract this field')}"
            for field in fields
        ])

        return f"""Extract the following fields from this CAQH Data Summary OCR text:

{fields_text}

OCR TEXT:
```
{ocr_text}
```

Return a JSON object with the extracted values, confidence scores, and reasoning for each field."""


def test_connection() -> bool:
    """
    Test the Azure OpenAI connection.

    Returns True if successful, raises an exception otherwise.
    """
    extractor = LLMExtractor()

    if not extractor.is_configured():
        print("❌ Azure OpenAI not configured")
        print("   Set these environment variables:")
        print("   - AZURE_OPENAI_ENDPOINT")
        print("   - AZURE_OPENAI_API_KEY")
        print("   - AZURE_OPENAI_DEPLOYMENT_NAME (optional, defaults to 'gpt-5-mini')")
        return False

    try:
        # Simple test call
        response = extractor.client.chat.completions.create(
            model=extractor.deployment_name,
            messages=[{"role": "user", "content": "Say 'connected' if you can read this."}],
        )
        result = response.choices[0].message.content
        print(f"✅ Azure OpenAI connected successfully")
        print(f"   Deployment: {extractor.deployment_name}")
        print(f"   Response: {result}")
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


if __name__ == "__main__":
    # Quick test
    test_connection()
