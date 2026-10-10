import io
import time
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.state_machine import CaseStatus
from app.schemas.audit import AuditEventType
from app.services.audit_service import audit_service
from app.services.case_service import case_service
from app.services.document_service import document_service, get_stream_signing_secret
from app.core.firestore_client import ensure_emulator_storage_bucket

client = TestClient(app)

TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_CLINICIAN_1 = "Bearer mock-token-clinician-verified"
TOKEN_CLINICIAN_UNVERIFIED = "Bearer mock-token-clinician-unverified"
TOKEN_CLINICIAN_2 = "Bearer claims.eyJ1aWQiOiJjbGluaWNpYW5fMl92ZXJpZmllZCIsInJvbGUiOiJjbGluaWNpYW4iLCJpc192ZXJpZmllZF9jbGluaWNpYW4iOnRydWV9"
TOKEN_ADMIN = "Bearer mock-token-admin"


def make_test_pdf_bytes(content: str = "Test medical report binary content") -> bytes:
    escaped = content.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    stream_content = f'BT\n/F1 12 Tf\n72 712 Td\n({escaped}) Tj\nET\n'.encode('utf-8')
    stream_len = len(stream_content)
    pdf = f'''%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length {stream_len} >> stream
'''.encode('utf-8') + stream_content + b'''endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000366 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
443
%%EOF
'''
    return pdf


def make_test_jpeg_bytes() -> bytes:
    # Minimal JPEG binary starting with \xff\xd8\xff
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\n\x0b\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xbf\x00\xff\xd9"


def setup_case_with_document(patient_token: str = TOKEN_PATIENT_1, key_suffix: str = "signed_url_test", is_image: bool = False):
    """Helper to create a case and upload a document."""
    payload = {
        "chiefComplaint": "Patient complaint for Phase 6d download URL access testing",
        "duration": "3 days",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_phase6d_{key_suffix}_{id(key_suffix)}_{time.time()}",
    }
    case_res = client.post("/api/v1/cases", json=payload, headers={"Authorization": patient_token})
    assert case_res.status_code == 201
    case_id = case_res.json()["caseId"]

    if is_image:
        file_bytes = make_test_jpeg_bytes()
        filename = "skin_rash.jpg"
        mime = "image/jpeg"
    else:
        file_bytes = make_test_pdf_bytes("Clinical Lab Report Page 1 Results")
        filename = "lab_report.pdf"
        mime = "application/pdf"

    upload_res = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"file": (filename, io.BytesIO(file_bytes), mime)},
        headers={"Authorization": patient_token},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["documentId"]

    return case_id, doc_id, file_bytes


def test_owner_allowed_download_url():
    """Requirement: Owner allowed download URL, returns 200, short-lived, DOC_VIEWED logged, no token in audit log."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "owner_allowed")

    res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["documentId"] == doc_id
    assert data["caseId"] == case_id
    assert data["fileName"] == "lab_report.pdf"
    assert data["expiresInSeconds"] == 300
    assert data["isEmulatorFallback"] is True
    assert "token=" in data["downloadUrl"]
    # Never expose raw bucket path (cases/...) or permanent public URL
    assert not data["downloadUrl"].startswith("cases/")
    assert not data["downloadUrl"].startswith("gs://")

    # Check audit events: DOC_VIEWED logged
    view_events = [
        e for e in audit_service.list_events()
        if e.caseId == case_id and e.eventType == AuditEventType.DOC_VIEWED
    ]
    assert len(view_events) >= 1
    latest = view_events[-1]
    assert latest.actorId == "patient_demo_1"
    assert latest.details.get("documentId") == doc_id
    # Critical: Stream token MUST NEVER be logged
    assert "token" not in str(latest.details).lower()


def test_other_patient_denied_download_url():
    """Requirement: Other patient denied download URL (HTTP 403), DOC_VIEW_DENIED logged."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "other_patient_denied")

    res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res.status_code == 403
    assert "Patients can only access documents from their own cases" in res.json()["detail"]

    # Check audit events: DOC_VIEW_DENIED logged
    denied_events = [
        e for e in audit_service.list_events()
        if e.caseId == case_id and e.eventType == AuditEventType.DOC_VIEW_DENIED
    ]
    assert len(denied_events) >= 1
    latest = denied_events[-1]
    assert latest.actorId == "patient_demo_2"
    assert latest.details.get("documentId") == doc_id


def test_assigned_clinician_allowed_in_accepted_in_consultation_completed():
    """
    Requirement 3: Assigned clinician may access documents only when case status
    is ACCEPTED, IN_CONSULTATION or COMPLETED.
    """
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "clinician_statuses")

    # Progress case: DRAFT -> SUBMITTED -> MATCHING -> ACCEPTED (by clinician 1)
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})
    accept_res = client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_CLINICIAN_1})
    assert accept_res.status_code == 200
    assert accept_res.json()["status"] == CaseStatus.ACCEPTED

    # 1. Status is ACCEPTED -> Allowed
    res_accepted = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_CLINICIAN_1},
    )
    assert res_accepted.status_code == 200
    assert res_accepted.json()["documentId"] == doc_id

    # 2. Status is IN_CONSULTATION -> Allowed
    consult_res = client.post(
        f"/api/v1/cases/{case_id}/status",
        json={"targetStatus": CaseStatus.IN_CONSULTATION},
        headers={"Authorization": TOKEN_CLINICIAN_1},
    )
    assert consult_res.status_code == 200
    res_in_consult = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_CLINICIAN_1},
    )
    assert res_in_consult.status_code == 200

    # 3. Status is COMPLETED -> Allowed
    comp_res = client.post(
        f"/api/v1/cases/{case_id}/status",
        json={"targetStatus": CaseStatus.COMPLETED},
        headers={"Authorization": TOKEN_CLINICIAN_1},
    )
    assert comp_res.status_code == 200
    res_completed = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_CLINICIAN_1},
    )
    assert res_completed.status_code == 200


def test_assigned_clinician_denied_on_cancelled_case():
    """Requirement 3: Clinician on a cancelled case is denied (HTTP 403)."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "clinician_cancelled")

    # Progress case: DRAFT -> SUBMITTED -> MATCHING -> ACCEPTED
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_CLINICIAN_1})

    # Patient cancels the case
    del_res = client.delete(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT_1})
    assert del_res.status_code == 200
    assert del_res.json()["status"] == CaseStatus.CANCELLED

    # Assigned clinician attempts to access document on cancelled case -> 403
    res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_CLINICIAN_1},
    )
    assert res.status_code == 403
    assert "CANCELLED" in res.json()["detail"]

    # Audit event logged
    denied_events = [
        e for e in audit_service.list_events()
        if e.caseId == case_id and e.eventType == AuditEventType.DOC_VIEW_DENIED
    ]
    assert len(denied_events) >= 1
    assert denied_events[-1].actorId == "clinician_verified_1"


def test_clinician_on_reassigned_case_denied():
    """Requirement 3: Clinician on a reassigned case is denied (HTTP 403)."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "clinician_reassigned")

    # Progress case: DRAFT -> SUBMITTED -> MATCHING -> ACCEPTED (by Clinician 1)
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_CLINICIAN_1})

    # Clinician 1 initially allowed
    res_init = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_CLINICIAN_1},
    )
    assert res_init.status_code == 200

    # Simulate reassigning the case to Clinician 2 in Firestore
    case = case_service.get_case(case_id)
    updated = case.model_copy(update={"assignedClinicianId": "clinician_2_verified"})
    from app.models.firestore_models import case_to_firestore_dict
    case_service.db.collection("cases").document(case_id).set(case_to_firestore_dict(updated))

    # Clinician 1 now attempts access on the reassigned case -> 403 Forbidden
    res_reassigned = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_CLINICIAN_1},
    )
    assert res_reassigned.status_code == 403
    assert "not assigned" in res_reassigned.json()["detail"].lower()


def test_unassigned_clinician_denied_download_url():
    """Requirement: Unassigned clinician denied download URL (HTTP 403)."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "unassigned_clinician")

    # Case accepted by Clinician 1
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_CLINICIAN_1})

    # Clinician 2 (verified, but NOT assigned to this case) requests download URL -> 403
    res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_CLINICIAN_2},
    )
    assert res.status_code == 403
    assert "not assigned" in res.json()["detail"]


def test_unverified_clinician_denied_download_url():
    """Requirement: Unverified clinician denied download URL (HTTP 403)."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "unverified_clinician")

    res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_CLINICIAN_UNVERIFIED},
    )
    assert res.status_code == 403
    assert "Only verified clinicians" in res.json()["detail"]


def test_admin_allowed_download_url():
    """Requirement: Admin allowed download URL (HTTP 200)."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "admin_allowed")

    res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_ADMIN},
    )
    assert res.status_code == 200
    assert res.json()["documentId"] == doc_id


def test_unauthenticated_request_denied():
    """Requirement: Unauthenticated request denied (HTTP 401)."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "unauth_denied")

    res = client.get(f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url")
    assert res.status_code == 401


def test_invalid_case_or_document_id_returns_404():
    """Requirement: Invalid document ID or case ID returns 404."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "not_found_test")

    # Non-existent case
    res1 = client.get(
        f"/api/v1/cases/case_nonexistent_9999/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res1.status_code == 404

    # Non-existent document on valid case
    res2 = client.get(
        f"/api/v1/cases/{case_id}/documents/doc_nonexistent_9999/download-url",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res2.status_code == 404


def test_stream_endpoint_pdf_headers():
    """
    Requirement 2: Stream response headers:
    X-Content-Type-Options: nosniff, Cache-Control: no-store, sanitized filename in Content-Disposition.
    Use inline only for PDFs, attachment for images.
    """
    case_id, doc_id, expected_bytes = setup_case_with_document(TOKEN_PATIENT_1, "stream_pdf_headers", is_image=False)

    # 1. Get download URL
    url_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert url_res.status_code == 200
    stream_url = url_res.json()["downloadUrl"]

    # 2. Call stream endpoint
    stream_res = client.get(stream_url)
    assert stream_res.status_code == 200
    assert stream_res.headers["X-Content-Type-Options"] == "nosniff"
    assert stream_res.headers["Cache-Control"] == "no-store"
    assert stream_res.headers["Content-Type"] == "application/pdf"
    # PDF must use inline
    assert stream_res.headers["Content-Disposition"].startswith("inline;")
    assert 'filename="lab_report.pdf"' in stream_res.headers["Content-Disposition"]
    assert stream_res.content == expected_bytes


def test_stream_endpoint_image_headers():
    """Requirement 2: Image files must use attachment disposition type."""
    case_id, doc_id, expected_bytes = setup_case_with_document(TOKEN_PATIENT_1, "stream_image_headers", is_image=True)

    url_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert url_res.status_code == 200
    stream_url = url_res.json()["downloadUrl"]

    stream_res = client.get(stream_url)
    assert stream_res.status_code == 200
    assert stream_res.headers["X-Content-Type-Options"] == "nosniff"
    assert stream_res.headers["Cache-Control"] == "no-store"
    assert stream_res.headers["Content-Type"] == "image/jpeg"
    # Images must use attachment
    assert stream_res.headers["Content-Disposition"].startswith("attachment;")
    assert 'filename="skin_rash.jpg"' in stream_res.headers["Content-Disposition"]
    assert stream_res.content == expected_bytes


def test_stream_token_swapped_to_different_document_rejected():
    """Requirement 1: Stream token swapped to a different document is rejected (HTTP 403)."""
    case_id, doc_id_1, _ = setup_case_with_document(TOKEN_PATIENT_1, "swap_doc_1")
    # Upload second document to the same case
    doc_res_2 = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"file": ("second_doc.pdf", io.BytesIO(make_test_pdf_bytes("Doc 2")), "application/pdf")},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert doc_res_2.status_code == 200
    doc_id_2 = doc_res_2.json()["documentId"]

    # Generate token for doc_id_1
    url_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id_1}/download-url",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert url_res.status_code == 200
    stream_url_1 = url_res.json()["downloadUrl"]

    # Extract query params from doc_id_1's stream URL
    query_part = stream_url_1.split("?")[1]

    # Swap: attempt to use doc_id_1's token to access doc_id_2
    swapped_url = f"/api/v1/cases/{case_id}/documents/{doc_id_2}/stream?{query_part}"
    swapped_res = client.get(swapped_url)
    assert swapped_res.status_code == 403
    assert "Invalid or expired download token" in swapped_res.json()["detail"]


def test_stream_token_expired_rejected():
    """Requirement 1: Expired stream token rejected (HTTP 403)."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "expired_test")

    # Generate token with expiry 60 seconds in the past
    past_expiry = int(time.time()) - 60
    expired_token = document_service.generate_stream_token(
        case_id=case_id,
        document_id=doc_id,
        user_id="patient_demo_1",
        expiry=past_expiry,
    )

    expired_url = (
        f"/api/v1/cases/{case_id}/documents/{doc_id}/stream"
        f"?token={expired_token}&expires={past_expiry}&userId=patient_demo_1"
    )
    res = client.get(expired_url)
    assert res.status_code == 403
    assert "Invalid or expired download token" in res.json()["detail"]


def test_stream_token_never_logged(caplog):
    """Requirement 1: Stream token must never be logged."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "never_logged")

    url_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    stream_url = url_res.json()["downloadUrl"]
    token_str = stream_url.split("token=")[1].split("&")[0]

    # Perform stream fetch
    stream_res = client.get(stream_url)
    assert stream_res.status_code == 200

    # 1. Audit events: Ensure token does not appear in any audit event details
    events = audit_service.list_events()
    for ev in events:
        details_str = str(ev.details)
        assert token_str not in details_str, f"Token was found leaked in audit event {ev.eventId}!"

    # 2. Logger records: Ensure token does not appear in caplog
    for record in caplog.records:
        assert token_str not in record.getMessage(), "Token was found leaked in standard logging output!"


def test_assigned_clinician_stream_access_denied_if_case_cancelled():
    """Requirement 3: Stream access is denied if case is cancelled before token consumption."""
    case_id, doc_id, _ = setup_case_with_document(TOKEN_PATIENT_1, "stream_cancelled")

    # Progress case to ACCEPTED
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_CLINICIAN_1})

    # Get download URL for clinician
    url_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/download-url",
        headers={"Authorization": TOKEN_CLINICIAN_1},
    )
    assert url_res.status_code == 200
    stream_url = url_res.json()["downloadUrl"]

    # Now case is cancelled
    client.delete(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT_1})

    # Clinician uses their stream URL -> 403 Forbidden
    res = client.get(stream_url)
    assert res.status_code == 403
    assert "CANCELLED" in res.json()["detail"]


def test_startup_bucket_creation_error_handling():
    """Requirement 5: Create bucket on startup only when emulator host is set; log clear error if fails; never swallow."""
    # When emulator host is not set: no-op
    with patch.dict("os.environ", {"STORAGE_EMULATOR_HOST": ""}, clear=False):
        with patch("app.core.config.settings.FIREBASE_STORAGE_EMULATOR_HOST", None):
            ensure_emulator_storage_bucket()

    # When emulator host is set, but storage client raises error -> raises RuntimeError (not swallowed)
    with patch.dict("os.environ", {"STORAGE_EMULATOR_HOST": "127.0.0.1:9199"}):
        with patch("app.core.firestore_client.is_testing_environment", return_value=False):
            with patch("app.core.firestore_client.get_storage_client", side_effect=Exception("Storage daemon connection refused")):
                with pytest.raises(RuntimeError) as exc_info:
                    ensure_emulator_storage_bucket()
                assert "Storage daemon connection refused" in str(exc_info.value)


def test_startup_validates_stream_secret_outside_testing():
    """Requirement 1: Secret required at startup outside TESTING, never hardcoded."""
    with patch("app.services.document_service.is_testing_environment", return_value=False):
        with patch.dict("os.environ", {"DOC_STREAM_SECRET": ""}, clear=False):
            with patch("app.core.config.settings.DOC_STREAM_SECRET", None):
                with pytest.raises(RuntimeError) as exc:
                    get_stream_signing_secret()
                assert "DOC_STREAM_SECRET environment variable is required" in str(exc.value)


def test_stream_access_log_filter_redacts_tokens():
    """Requirement: uvicorn's access log never prints stream tokens or query strings."""
    import logging
    from app.main import StreamAccessLogFilter

    log_filter = StreamAccessLogFilter()
    secret_token = "secret-stream-token-xyz-12345"
    raw_path_with_token = f"/api/v1/cases/case_001/documents/doc_001/stream?token={secret_token}&expires=1791599999"

    # 1. Test standard uvicorn access record args: (client_addr, method, full_path, http_version, status_code)
    record_args = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="uvicorn/protocols/http/h11_impl.py",
        lineno=100,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:54321", "GET", raw_path_with_token, "1.1", 200),
        exc_info=None,
    )

    result = log_filter.filter(record_args)
    assert result is True

    # Assert secret token and query string are absent from record.args
    filtered_path = record_args.args[2]
    assert secret_token not in filtered_path
    assert "?token=" not in filtered_path
    assert filtered_path == "/api/v1/cases/case_001/documents/doc_001/stream"

    # Assert formatted message does not leak the token
    formatted_msg = record_args.getMessage()
    assert secret_token not in formatted_msg
    assert "?token=" not in formatted_msg
    assert "GET /api/v1/cases/case_001/documents/doc_001/stream HTTP/1.1" in formatted_msg

    # 2. Test pre-formatted message or non-args string record
    record_msg = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="uvicorn/access.py",
        lineno=50,
        msg=f'127.0.0.1:54321 - "GET {raw_path_with_token} HTTP/1.1" 200',
        args=(),
        exc_info=None,
    )
    log_filter.filter(record_msg)
    formatted_direct = record_msg.getMessage()
    assert secret_token not in formatted_direct
    assert "?token=" not in formatted_direct
    assert "GET /api/v1/cases/case_001/documents/doc_001/stream HTTP/1.1" in formatted_direct

