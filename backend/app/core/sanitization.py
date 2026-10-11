"""
MedBridge AI — Centralized Sanitization and Redaction Module (Phase 10 — Stage 2B)

========================================================================================
CRITICAL PRIVACY & SAFETY NOTICE / LIMITATION OF LIABILITY:
This module provides automated, heuristic defense-in-depth pattern redaction to scrub
common direct identifiers (email addresses, telephone numbers, national IDs, medical
record numbers, and explicit self-introductions) from free-text patient narratives and
document extracts prior to transmission to Gemini.

IMPORTANT LIMITATION:
Regex-based heuristic pattern matching DOES NOT guarantee complete mathematical or
regulatory de-identification under HIPAA Safe Harbor (45 CFR § 164.514(b)(2)) or
GDPR (Recital 26). Complex clinical narratives may contain idiosyncratic, contextual,
or quasi-identifying details (e.g., rare conditions, specific geographical locations,
relative relationships) that cannot be detected by deterministic regular expressions alone.
In a real clinical production environment, dedicated NLP-based de-identification pipelines,
institutional compliance reviews (BAA), and patient consent are mandatory before sending
data to any external AI service.
========================================================================================
"""

import re
import logging
from typing import Optional, Any, Dict, List, Union

logger = logging.getLogger(__name__)

# Maximum permissible string length for free-text fields before sanitization (safeguard against ReDoS)
MAX_FREE_TEXT_LENGTH = 100_000

# 1. Email addresses (standard RFC-compliant pattern)
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# 2. National Identifiers:
# - US Social Security Number (SSN): 3-2-4 digits with hyphens
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# - Aadhaar Number (India): 4 4 4 digits with spaces or hyphens
_AADHAAR_PATTERN = re.compile(r"\b\d{4}[\s-]\d{4}[\s-]\d{4}\b")
# - UK NHS Number: 3 3 4 digits with spaces
_NHS_PATTERN = re.compile(r"\b\d{3}\s\d{3}\s\d{4}\b")

# 3. Medical Record Numbers / Patient IDs:
# Matches explicit labels followed by alphanumeric ID strings
_MRN_PATTERN = re.compile(
    r"\b(?:MRN|Medical Record Number|Patient ID|Account #|Acc #)[:\s#]+[A-Za-z0-9-]+\b",
    re.IGNORECASE,
)

# 4. Telephone Numbers:
# Targets standard telephone formatting (e.g. +1-555-123-4567, (555) 123-4567, 555-123-4567, +91 98765 43210, 10-digit mobile)
# Designed specifically to PRESERVE:
# - Blood pressures: 120/80 mmHg
# - Decimal vitals & labs: 98.6 F, 101.4 F, 13.5 g/dL, 1.1 mg/dL
# - Dosages: 500 mg, 10 mg, 0.5 ml
# - Timeline: 3 days, 24 hours, 2 weeks
# - Dates: 2026-10-11
_PHONE_FORMATTED_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"
)
_PHONE_INTL_SPACED_PATTERN = re.compile(
    r"\+\d{1,3}[\s-]\d{5}[\s-]\d{5}\b"
)
# Matches Indian phone numbers with country code (+91) or trunk prefix (0):
# e.g. +91-9876543210, +91 9876543210, +91 98765 43210, 09876543210, +91-98765-43210
_PHONE_INDIAN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:\+91[-.\s]?|0)[6-9]\d{4}[-.\s]?\d{5}\b(?![A-Za-z0-9])"
)
# Unprefixed 10-digit numbers (contiguous or 5-5 space-separated Indian mobile):
_PHONE_10DIGIT_RAW_PATTERN = re.compile(
    r"(?<![A-Za-z0-9./\-,])\b(?:\+1)?(?:[6-9]\d{4}\s\d{5}|\d{10})\b(?![A-Za-z0-9./\-,])"
)

# 5. Direct introductory name phrases:
# E.g. "My name is John Doe", "Patient: Jane Smith", "Name: Robert Johnson"
_NAME_INTRO_PATTERN = re.compile(
    r"(\b(?:My name is|Patient(?:\s+name)?(?:\s+is)?[:\s]+|Name:\s*))\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
)


class PrivacySanitizationError(Exception):
    """Raised when sanitization cannot safely proceed due to invalid or malformed data."""
    pass


def sanitize_text(text: Optional[str]) -> str:
    """
    Sanitizes free-text clinical narrative by redacting identifiable contact details
    and supported identifier patterns, while preserving clinically relevant terms,
    vitals, lab values, dosages, and timelines.

    Fail-safe behavior:
    - If text is None or empty, returns empty string.
    - If text exceeds MAX_FREE_TEXT_LENGTH, truncates safely with a warning placeholder.
    - If unexpected error occurs, raises PrivacySanitizationError to prevent sending unredacted data.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    if len(text) > MAX_FREE_TEXT_LENGTH:
        logger.warning(
            "Input text exceeded maximum length (%d > %d), truncating for safety.",
            len(text),
            MAX_FREE_TEXT_LENGTH,
        )
        text = text[:MAX_FREE_TEXT_LENGTH] + " ... [TRUNCATED_FOR_PRIVACY]"

    try:
        sanitized = text

        # 1. Emails
        sanitized = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", sanitized)

        # 2. National & ID Numbers (SSN, Aadhaar, NHS, MRN)
        sanitized = _SSN_PATTERN.sub("[REDACTED_ID]", sanitized)
        sanitized = _AADHAAR_PATTERN.sub("[REDACTED_ID]", sanitized)
        sanitized = _NHS_PATTERN.sub("[REDACTED_ID]", sanitized)
        sanitized = _MRN_PATTERN.sub("[REDACTED_ID]", sanitized)

        # 3. Telephone numbers
        sanitized = _PHONE_FORMATTED_PATTERN.sub("[REDACTED_PHONE]", sanitized)
        sanitized = _PHONE_INTL_SPACED_PATTERN.sub("[REDACTED_PHONE]", sanitized)
        sanitized = _PHONE_INDIAN_PATTERN.sub("[REDACTED_PHONE]", sanitized)
        sanitized = _PHONE_10DIGIT_RAW_PATTERN.sub("[REDACTED_PHONE]", sanitized)

        # 4. Direct introductory names
        sanitized = _NAME_INTRO_PATTERN.sub(r"\1 [REDACTED_NAME]", sanitized)

        return sanitized

    except Exception as e:
        logger.error("Sanitization failed unexpectedly: %s", type(e).__name__)
        raise PrivacySanitizationError(
            f"Unable to safely sanitize text content: {type(e).__name__}"
        ) from e


def sanitize_clinical_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Recursively sanitizes all string values within a clinical intake metadata dictionary
    (e.g., symptoms, knownConditions, medications, allergies, vitals).
    """
    if not metadata or not isinstance(metadata, dict):
        return {}

    sanitized_dict: Dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, str):
            sanitized_dict[key] = sanitize_text(value)
        elif isinstance(value, list):
            sanitized_dict[key] = [
                sanitize_text(item) if isinstance(item, str) else item
                for item in value
            ]
        elif isinstance(value, dict):
            sanitized_dict[key] = sanitize_clinical_metadata(value)
        else:
            sanitized_dict[key] = value

    return sanitized_dict


def safe_error_message(err: Union[Exception, str]) -> str:
    """
    Converts an exception or internal error string into a safe, generic client-facing
    message that never echoes raw patient complaints, document fragments, prompts, or API keys.
    """
    if isinstance(err, Exception):
        err_type = type(err).__name__
        err_str = str(err)
    else:
        err_type = "ServiceError"
        err_str = str(err)

    # Specific common error categories
    lower_str = err_str.lower()
    if "timed out" in lower_str or "timeout" in lower_str:
        return "AI brief generation timed out. Clinician review required."
    if "rate limit" in lower_str or "429" in lower_str:
        return "AI generation rate limit reached. Please wait before retrying."
    if "api key" in lower_str or "auth" in lower_str or "401" in lower_str or "403" in lower_str:
        return "AI service authentication error. Clinician review required."
    if "malformed" in lower_str or "json" in lower_str:
        return "AI structured output validation error. Clinician review required."

    return f"AI generation service error ({err_type}). Clinician review required."
