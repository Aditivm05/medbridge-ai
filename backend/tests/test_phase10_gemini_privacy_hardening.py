"""
Phase 10 - Stage 2B: Gemini Privacy Hardening Test Suite
Verifies:
1. Centralized sanitization:
   - Redaction of representative email, phone, and supported identifier formats (SSN, Aadhaar, NHS, MRN).
   - Redaction of explicit patient names in direct introductory phrases.
   - Strict preservation of clinically relevant vitals, lab values, dosages, and timelines.
2. Prevention of sensitive content appearing in captured application logs.
3. Prevention of sensitive content leaking through API errors or validationWarnings.
4. Transmission boundary safeguards:
   - Text PDFs processed locally via pypdf without sending binary to Gemini.
   - OCR-extracted text and fields sanitized through sanitize_text before storage.
   - ALLOW_REMOTE_OCR policy gating for zero-outbound transmission environments.
5. Safe failure handling when sanitization or privacy checks encounter pathological input.
"""

import io
import json
import logging
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.sanitization import (
    sanitize_text,
    sanitize_clinical_metadata,
    safe_error_message,
    PrivacySanitizationError,
)
from app.schemas.case import CaseCreate, RequestedUrgency
from app.schemas.document import ExtractionStatus, PageText, ExtractedField
from app.services.case_service import case_service
from app.services.brief_service import brief_service
from app.services.gemini_service import gemini_ocr_service
from app.services.document_service import document_service

client = TestClient(app)

TOKEN_PATIENT = "Bearer mock-token-patient-1"


@pytest.fixture(autouse=True)
def cleanup_testing_clients():
    """Ensure testing clients are cleanly reset before and after each test."""
    gemini_ocr_service.set_client_for_testing(None)
    brief_service.set_client_for_testing(None)
    yield
    gemini_ocr_service.set_client_for_testing(None)
    brief_service.set_client_for_testing(None)


# ==============================================================================
# 1. Redaction of Identifiers & Preservation of Clinical Information
# ==============================================================================

def test_sanitization_redacts_contact_details_and_national_ids():
    """Requirement: Redact representative email, phone, and supported identifier formats."""
    # Email redactions
    assert sanitize_text("Contact me at patient.doe@example.com for follow-up") == "Contact me at [REDACTED_EMAIL] for follow-up"
    assert sanitize_text("Emails: alice.smith@hospital.org and bob-123@sub.domain.co.uk") == "Emails: [REDACTED_EMAIL] and [REDACTED_EMAIL]"

    # Phone number redactions
    assert sanitize_text("Call 555-123-4567 if severe") == "Call [REDACTED_PHONE] if severe"
    assert sanitize_text("Mobile: (555) 123-4567 or +1-555-987-6543") == "Mobile: [REDACTED_PHONE] or [REDACTED_PHONE]"
    assert sanitize_text("Intl: +91 98765 43210 urgently") == "Intl: [REDACTED_PHONE] urgently"
    assert sanitize_text("Direct line: 9876543210") == "Direct line: [REDACTED_PHONE]"

    # National & medical IDs
    assert sanitize_text("Patient SSN is 123-45-6789") == "Patient SSN is [REDACTED_ID]"
    assert sanitize_text("Aadhaar: 1234 5678 9012 on record") == "Aadhaar: [REDACTED_ID] on record"
    assert sanitize_text("NHS Number: 123 456 7890") == "NHS Number: [REDACTED_ID]"
    assert sanitize_text("Hospital MRN: MRN-987654321") == "Hospital [REDACTED_ID]"
    assert sanitize_text("Patient ID: PID-44211") == "[REDACTED_ID]"


def test_indian_phone_number_redaction_and_clinical_preservation():
    """
    Requirement (Stage 2B.2 Fix 1): Redact +91-9876543210, +91 9876543210,
    +91 98765 43210, 09876543210, and unprefixed 10-digit Indian mobile numbers.
    Strictly preserve ISO dates (2026-10-11), clinical ranges (10-20 mg, 60000-80000 /uL),
    and clinical measurements.
    """
    # 1. Verification of all Indian phone number formats
    phone_cases = [
        "+91-9876543210",
        "+91 9876543210",
        "+91 98765 43210",
        "09876543210",
        "9876543210",
        "98765 43210",
        "+91-98765-43210",
    ]
    for phone in phone_cases:
        res = sanitize_text(f"Patient contact is {phone} for immediate follow up.")
        assert "[REDACTED_PHONE]" in res, f"Expected redaction for {phone}, got: {res}"
        assert phone not in res, f"Raw phone number leaked for {phone}"

    # 2. Verification of clinical controls (zero false-positive destruction)
    clinical_cases = [
        "Date of presentation: 2026-10-11",
        "Prescribed 10-20 mg PO daily",
        "Amoxicillin 500 mg twice daily",
        "Recorded BP 120/80 mmHg",
        "Oral temperature 38.5 C (temp 98.6 F baseline)",
        "WBC 11,000 /uL and platelets 60000-80000 /uL",
        "Heart rate 70-90 bpm",
        "Symptom duration 3 days and timeline 48 hours",
        "Suspected COVID-19 with ICD-10 J06.9",
        "Recommended 100-200 mg / day",
        "Resting SpO2 98%",
    ]
    for clinical in clinical_cases:
        sanitized = sanitize_text(clinical)
        assert sanitized == clinical, f"Clinical meaning altered: {clinical} -> {sanitized}"
        assert "[REDACTED" not in sanitized


def test_sanitization_redacts_direct_introductory_names():
    """Requirement: Redact explicit self-identifications without removing clinical context."""
    text = "My name is John Doe and I have severe migraine since yesterday."
    sanitized = sanitize_text(text)
    assert "[REDACTED_NAME]" in sanitized
    assert "John Doe" not in sanitized
    assert "severe migraine since yesterday" in sanitized

    text_intro = "Patient name: Jane Smith, presenting with dyspnea."
    sanitized_intro = sanitize_text(text_intro)
    assert "[REDACTED_NAME]" in sanitized_intro
    assert "Jane Smith" not in sanitized_intro
    assert "presenting with dyspnea" in sanitized_intro


def test_sanitization_preserves_clinical_vitals_labs_and_dosages():
    """
    Requirement: Strict preservation of clinically relevant terms, vitals,
    blood pressures, lab values, dosages, and timelines.
    """
    clinical_narrative = (
        "BP: 120/80 mmHg, pulse: 72 bpm, temp: 98.6 F (or 101.4 F peak), SpO2: 98%. "
        "WBC: 11,000 /uL, Hemoglobin: 13.5 g/dL, Creatinine: 1.1 mg/dL, Glucose: 110 mg/dL. "
        "Taking Amoxicillin 500mg TID and Lisinopril 10mg daily for 3 days. "
        "Symptom duration: 48 hours."
    )
    sanitized = sanitize_text(clinical_narrative)

    # All clinical metrics must remain exactly intact
    assert "120/80 mmHg" in sanitized
    assert "72 bpm" in sanitized
    assert "98.6 F" in sanitized
    assert "101.4 F" in sanitized
    assert "SpO2: 98%" in sanitized
    assert "11,000 /uL" in sanitized
    assert "13.5 g/dL" in sanitized
    assert "1.1 mg/dL" in sanitized
    assert "110 mg/dL" in sanitized
    assert "Amoxicillin 500mg TID" in sanitized
    assert "Lisinopril 10mg daily" in sanitized
    assert "3 days" in sanitized
    assert "48 hours" in sanitized
    assert "[REDACTED" not in sanitized  # No false-positive redaction of clinical values!


def test_sanitize_clinical_metadata_recursively():
    """Requirement: Metadata dictionary values (symptoms, allergies, medications, vitals) are sanitized."""
    raw_meta = {
        "symptoms": ["dry cough", "fever, reached out via patient.smith@mail.com"],
        "knownConditions": "Hypertension (diagnosed at Dr. Brown office 555-999-0000)",
        "medications": "Metformin 500mg",
        "allergies": "Penicillin (Patient SSN: 999-11-2222)",
        "vitals": {
            "bp": "130/85 mmHg",
            "notes": "Emergency contact: 555-888-7777",
        },
    }
    sanitized = sanitize_clinical_metadata(raw_meta)

    assert sanitized["symptoms"][0] == "dry cough"
    assert "[REDACTED_EMAIL]" in sanitized["symptoms"][1]
    assert "patient.smith@mail.com" not in sanitized["symptoms"][1]

    assert "[REDACTED_PHONE]" in sanitized["knownConditions"]
    assert "555-999-0000" not in sanitized["knownConditions"]

    assert sanitized["medications"] == "Metformin 500mg"

    assert "[REDACTED_ID]" in sanitized["allergies"]
    assert "999-11-2222" not in sanitized["allergies"]

    assert sanitized["vitals"]["bp"] == "130/85 mmHg"
    assert "[REDACTED_PHONE]" in sanitized["vitals"]["notes"]


# ==============================================================================
# 2. Privacy Boundary at Gemini Brief Prompt Construction
# ==============================================================================

def test_brief_service_payload_construction_redacts_pii():
    """
    Requirement: Minimize data sent to Gemini.
    Chief complaint, metadata, and document text must have PII redacted before prompt construction.
    """
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="My name is Alice Walker, call 555-123-4567, email alice@sample.net with severe dysuria for 2 days",
            duration="2 days (contact: 555-987-6543)",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey="idem_privacy_payload_test",
        ),
        actor_id="patient_privacy_1",
    )
    case_service.update_case_metadata(
        case.caseId,
        {
            "knownConditions": "Diabetes, MRN: MRN-123456",
            "medications": "Insulin 10 units, call doc at 555-444-3333",
        },
    )
    fresh_case = case_service.get_case(case.caseId)

    # Mock doc with PII in extracted page
    mock_doc = MagicMock()
    mock_doc.documentId = "doc_mock_priv"
    mock_doc.extractionStatus = ExtractionStatus.EXTRACTED
    mock_page = PageText(
        pageNumber=1,
        text="Clinical lab report for patient SSN 000-11-2222. Hemoglobin 12.0 g/dL. Emergency: +1-555-000-1111.",
        charCount=80,
        status=ExtractionStatus.EXTRACTED,
        source="PDF_TEXT",
    )
    mock_doc.pages = [mock_page]

    payload = brief_service._prepare_sanitized_case_payload(fresh_case, [mock_doc])

    # Assert PII is redacted in the payload
    assert "Alice Walker" not in payload
    assert "alice@sample.net" not in payload
    assert "555-123-4567" not in payload
    assert "555-987-6543" not in payload
    assert "555-444-3333" not in payload
    assert "000-11-2222" not in payload
    assert "+1-555-000-1111" not in payload
    assert "MRN-123456" not in payload

    # Assert clinical content is preserved
    assert "severe dysuria for 2 days" in payload
    assert "Diabetes" in payload
    assert "Insulin 10 units" in payload
    assert "Hemoglobin 12.0 g/dL" in payload

    # Assert identifiers like patientId and caseId are never in the prompt payload
    assert fresh_case.patientId not in payload
    assert fresh_case.caseId not in payload


# ==============================================================================
# 3. Prevention of Sensitive Information in Captured Logs
# ==============================================================================

def test_logs_do_not_contain_patient_complaints_or_model_response(caplog):
    """
    Requirement: Avoid logging raw patient complaints, document text, prompts,
    model responses, API keys, or raw exception strings containing medical data.
    """
    patient_uid = "patient_privacy_logger"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Extremely sensitive condition: rectal bleeding with email patient_secret@priv.com",
            duration="1 day",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey="idem_privacy_log_test",
        ),
        actor_id=patient_uid,
    )

    mock_client = MagicMock()
    # Mock Gemini returning malformed JSON that contains sensitive clinical text
    mock_resp = MagicMock()
    mock_resp.text = "{malformed_json_with_sensitive_clinical_findings: true}"
    mock_client.models.generate_content.return_value = mock_resp
    brief_service.set_client_for_testing(mock_client)

    with caplog.at_level(logging.DEBUG):
        res = client.post(
            f"/api/v1/cases/{case.caseId}/brief/generate",
            headers={"Authorization": f"Bearer mock-token-{patient_uid}"},
        )
        assert res.status_code == 200

    captured_logs = caplog.text

    # Verify no raw patient complaint or sensitive email in log output
    assert "rectal bleeding" not in captured_logs
    assert "patient_secret@priv.com" not in captured_logs
    assert "{malformed_json_with_sensitive_clinical_findings" not in captured_logs


def test_gemini_client_init_failure_does_not_log_canaries(caplog):
    """
    Requirement (Stage 2B.2 Fix 2): In gemini_service.py, replace raw exception-string
    logging during Gemini client initialization with safe exception-type logging.
    Ensure exception message, credentials, and request data cannot enter the log.
    """
    canary_secret = "CANARY_SECRET_API_KEY_EXPOSURE_VAL_777"
    internal_endpoint = "https://sensitive.internal.auth.corp/v1"
    synthetic_exception = RuntimeError(
        f"Handshake failed with credentials {canary_secret} targeting {internal_endpoint}"
    )

    gemini_ocr_service.set_client_for_testing(None)
    with caplog.at_level(logging.DEBUG):
        with patch.object(settings, "GEMINI_API_KEY", "dummy_key"):
            with patch("app.services.gemini_service.genai.Client", side_effect=synthetic_exception):
                client_obj = gemini_ocr_service.get_client()
                assert client_obj is None

    captured_logs = caplog.text
    # Canary credentials and message must NEVER appear in logs
    assert canary_secret not in captured_logs
    assert internal_endpoint not in captured_logs
    # Safe exception type MUST be logged
    assert "RuntimeError" in captured_logs
    assert "Failed to initialize Gemini client: RuntimeError" in captured_logs


# ==============================================================================
# 4. Prevention of Sensitive Content Leaking in validationWarnings
# ==============================================================================

def test_validation_warnings_do_not_embed_sensitive_patient_data():
    """
    Requirement: Return safe, generic client-facing errors and non-sensitive
    validation warnings. Do not embed rejected patient data or raw validation exception details.
    """
    patient_uid = "patient_privacy_warnings"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Sensitive complaint with phone 555-432-1098 and email sec@mail.org",
            duration="3 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey="idem_privacy_warn_test",
        ),
        actor_id=patient_uid,
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("External Gemini server error with internal state dump")
    brief_service.set_client_for_testing(mock_client)

    res = client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers={"Authorization": f"Bearer mock-token-{patient_uid}"},
    )
    assert res.status_code == 200
    brief_data = res.json()

    warnings = brief_data.get("validationWarnings", [])
    assert len(warnings) >= 1

    # Warning must be clean and generic
    for w in warnings:
        assert "555-432-1098" not in w
        assert "sec@mail.org" not in w
        assert "internal state dump" not in w
        assert "AI generation failed" in w


# ==============================================================================
# 5. Transmission Boundary: OCR & ALLOW_REMOTE_OCR Gate
# ==============================================================================

def test_ocr_extracted_text_and_fields_are_sanitized_before_storage():
    """
    Requirement: OCR of uploaded documents must sanitize extracted text and fields
    immediately upon ingestion.
    """
    doc_id = "doc_ocr_sanitize_test"
    case_id = "case_ocr_sanitize_test"
    file_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb"

    # Pre-register document
    from app.schemas.document import DocumentResponse
    from datetime import datetime
    initial_doc = DocumentResponse(
        documentId=doc_id,
        caseId=case_id,
        patientId="patient_demo_1",
        fileName="lab_photo.jpg",
        mimeType="image/jpeg",
        sizeBytes=len(file_bytes),
        storagePath=f"cases/{case_id}/{doc_id}_lab.jpg",
        magicBytesValidated=True,
        extractionStatus=ExtractionStatus.NEEDS_OCR,
        uploadedAt=datetime.utcnow(),
    )
    document_service.register_document(initial_doc)

    # Gemini OCR mock returns text with embedded patient phone and email
    mock_client = MagicMock()
    mock_resp = MagicMock()
    ocr_payload = {
        "pages": [
            {
                "pageNumber": 1,
                "text": "Clinic Report: Call Dr. Adams at 555-901-2345 or email adams@clinic.com. BP 120/80 mmHg.",
            }
        ],
        "fields": [
            {
                "fieldName": "Doctor Contact",
                "value": "555-901-2345",
                "unit": None,
                "pageNumber": 1,
                "modelReportedLegibility": "high",
            },
            {
                "fieldName": "Blood Pressure",
                "value": "120/80",
                "unit": "mmHg",
                "pageNumber": 1,
                "modelReportedLegibility": "high",
            },
        ],
        "unreadableNotes": None,
    }
    mock_resp.text = json.dumps(ocr_payload)
    mock_client.models.generate_content.return_value = mock_resp
    gemini_ocr_service.set_client_for_testing(mock_client)

    result_doc = document_service.process_gemini_ocr(
        document_id=doc_id,
        file_bytes=file_bytes,
        case_id=case_id,
    )

    assert result_doc.extractionStatus == ExtractionStatus.EXTRACTED
    # Extracted page text must have phone and email redacted
    assert "555-901-2345" not in result_doc.extractedText
    assert "adams@clinic.com" not in result_doc.extractedText
    assert "[REDACTED_PHONE]" in result_doc.extractedText
    assert "[REDACTED_EMAIL]" in result_doc.extractedText
    # Clinical BP preserved
    assert "120/80 mmHg" in result_doc.extractedText

    # Structured fields sanitized
    fields_map = {f.fieldName: f.value for f in result_doc.extractedFields}
    assert fields_map["Doctor Contact"] == "[REDACTED_PHONE]"
    assert fields_map["Blood Pressure"] == "120/80"


def test_allow_remote_ocr_disabled_blocks_outbound_binary_transmission(monkeypatch):
    """
    Requirement: When ALLOW_REMOTE_OCR is disabled by configuration policy,
    no document bytes leave the application, and the document safely transitions to FAILED
    with a clear manual review notice.
    """
    monkeypatch.setattr(settings, "ALLOW_REMOTE_OCR", False)

    mock_client = MagicMock()
    gemini_ocr_service.set_client_for_testing(mock_client)

    success, extraction, error_msg = gemini_ocr_service.extract_document_ocr(
        file_bytes=b"fake_image_bytes",
        mime_type="image/jpeg",
    )

    assert success is False
    assert extraction is None
    assert "disabled by policy" in error_msg
    # Ensure Gemini client was NOT called
    assert mock_client.models.generate_content.call_count == 0


# ==============================================================================
# 6. Safe Failure Handling for Sanitization Boundary
# ==============================================================================

def test_sanitization_safe_failure_handling():
    """Requirement: Fail safely when sanitization encounters pathological inputs."""
    # None returns empty string safely
    assert sanitize_text(None) == ""

    # Numeric or boolean values converted to string and handled safely
    assert sanitize_text(12345) == "12345"

    # Extreme length input is truncated safely with privacy indicator
    huge_input = "A" * 150_000 + " contact 555-123-4567"
    sanitized = sanitize_text(huge_input)
    assert "[TRUNCATED_FOR_PRIVACY]" in sanitized
    assert len(sanitized) < 110_000

    # safe_error_message maps various exceptions to clean generic strings
    assert "timed out" in safe_error_message(TimeoutError("Internal network timed out on port 443"))
    assert "rate limit" in safe_error_message("Rate limit error (429): Quota exceeded")
    assert "authentication error" in safe_error_message("API key invalid")
    assert "validation error" in safe_error_message("Malformed JSON response")
    assert "AI generation service error" in safe_error_message(KeyError("missing_internal_key"))
