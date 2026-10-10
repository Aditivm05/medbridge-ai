import pytest
import io
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.document import MAX_FILE_SIZE_BYTES, MAX_DOCUMENTS_PER_CASE

client = TestClient(app)

TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_CLINICIAN = "Bearer mock-token-clinician-verified"

# Standard valid magic byte payloads
VALID_PDF_BYTES = b"%PDF-1.4\n%Demo PDF synthetic report\n%%EOF"
VALID_JPG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb"
VALID_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"


def create_test_case(patient_token: str = TOKEN_PATIENT_1, key_suffix: str = "doc_test") -> str:
    """Helper to create a fresh DRAFT case."""
    payload = {
        "chiefComplaint": "Patient upload test intake concern",
        "duration": "1 day",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_test_case_{key_suffix}_{id(key_suffix)}",
    }
    res = client.post("/api/v1/cases", json=payload, headers={"Authorization": patient_token})
    assert res.status_code == 201, f"Failed to create test case: {res.text}"
    return res.json()["caseId"]


def test_valid_pdf_upload_succeeds():
    case_id = create_test_case(key_suffix="valid_pdf")
    files = {"file": ("cbc_report.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["caseId"] == case_id
    assert data["fileName"] == "cbc_report.pdf"
    assert data["mimeType"] == "application/pdf"
    assert data["magicBytesValidated"] is True
    assert data["sizeBytes"] == len(VALID_PDF_BYTES)


def test_valid_jpeg_and_png_uploads_succeed():
    case_id = create_test_case(key_suffix="valid_images")

    # JPEG upload
    files_jpg = {"file": ("ultrasound.jpg", io.BytesIO(VALID_JPG_BYTES), "image/jpeg")}
    res_jpg = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files_jpg,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_jpg.status_code == 200
    assert res_jpg.json()["mimeType"] == "image/jpeg"

    # PNG upload
    files_png = {"file": ("scan_chart.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
    res_png = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files_png,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_png.status_code == 200
    assert res_png.json()["mimeType"] == "image/png"


def test_invalid_extension_rejected():
    case_id = create_test_case(key_suffix="bad_ext")
    # Disallowed extension .exe
    files = {"file": ("malicious.exe", io.BytesIO(b"executable content"), "application/pdf")}
    res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 400
    assert "not permitted" in res.json()["detail"].lower()


def test_mismatched_extension_and_mime_rejected():
    case_id = create_test_case(key_suffix="mismatch_ext")
    # File named .pdf but sent as image/png
    files = {"file": ("report.pdf", io.BytesIO(VALID_PNG_BYTES), "image/png")}
    res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 400
    assert "does not match mime type" in res.json()["detail"].lower()


def test_unsupported_mime_type_rejected():
    case_id = create_test_case(key_suffix="bad_mime")
    files = {"file": ("notes.txt", io.BytesIO(b"plain notes text"), "text/plain")}
    res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 400
    assert "not permitted" in res.json()["detail"].lower() or "invalid mime type" in res.json()["detail"].lower()


def test_magic_byte_spoofing_rejected():
    case_id = create_test_case(key_suffix="spoof_magic")
    # File named .pdf and declared application/pdf, but containing fake text content
    fake_pdf_bytes = b"Hello, I am a plain text file pretending to be a medical report."
    files = {"file": ("fake_report.pdf", io.BytesIO(fake_pdf_bytes), "application/pdf")}
    res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 400
    assert "magic bytes check failed" in res.json()["detail"].lower()


def test_empty_file_rejected():
    case_id = create_test_case(key_suffix="empty_file")
    files = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
    res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_10mb_limit_exceeded_rejected():
    case_id = create_test_case(key_suffix="oversized_file")
    # 10 MB + 1 byte
    oversized_bytes = b"%PDF-" + b"0" * (MAX_FILE_SIZE_BYTES - 4) + b"OVER"
    assert len(oversized_bytes) > MAX_FILE_SIZE_BYTES

    files = {"file": ("huge_report.pdf", io.BytesIO(oversized_bytes), "application/pdf")}
    res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 400
    assert "exceeds" in res.json()["detail"].lower() and "10 mb" in res.json()["detail"].lower()


def test_max_5_documents_per_case_limit_enforced():
    case_id = create_test_case(key_suffix="max_5_docs")

    # Upload 5 files successfully
    for i in range(1, MAX_DOCUMENTS_PER_CASE + 1):
        files = {"file": (f"report_{i}.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
        res = client.post(
            f"/api/v1/cases/{case_id}/documents/upload-and-verify",
            files=files,
            headers={"Authorization": TOKEN_PATIENT_1},
        )
        assert res.status_code == 200, f"File {i} failed: {res.text}"

    # 6th upload attempt must be rejected with HTTP 400
    files_6th = {"file": ("report_6.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    res_6th = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files_6th,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_6th.status_code == 400
    assert "maximum limit of 5 documents" in res_6th.json()["detail"].lower()

    # Upload intent for 6th file must also be rejected
    intent_payload = {
        "fileName": "report_intent_6.pdf",
        "mimeType": "application/pdf",
        "sizeBytes": 1024,
    }
    intent_res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-intent",
        json=intent_payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert intent_res.status_code == 400
    assert "maximum limit of 5 documents" in intent_res.json()["detail"].lower()


def test_upload_intent_validations():
    case_id = create_test_case(key_suffix="intent_val")

    # 1. Valid intent
    valid_payload = {
        "fileName": "diagnostic_lab.pdf",
        "mimeType": "application/pdf",
        "sizeBytes": 204800,
    }
    res_valid = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-intent",
        json=valid_payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_valid.status_code == 200
    data = res_valid.json()
    assert data["caseId"] == case_id
    assert "uploadUrl" in data
    assert "storagePath" in data

    # 2. Unsupported MIME type
    invalid_mime = {
        "fileName": "diagnostic_lab.txt",
        "mimeType": "text/plain",
        "sizeBytes": 1024,
    }
    res_mime = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-intent",
        json=invalid_mime,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_mime.status_code == 400
    assert "not supported" in res_mime.json()["detail"].lower()

    # 3. Mismatched extension
    mismatch_ext = {
        "fileName": "diagnostic_lab.jpg",
        "mimeType": "application/pdf",
        "sizeBytes": 1024,
    }
    res_ext = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-intent",
        json=mismatch_ext,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_ext.status_code == 400
    assert "does not match mime type" in res_ext.json()["detail"].lower()

    # 4. Exceeds 10 MB limit
    oversized = {
        "fileName": "diagnostic_lab.pdf",
        "mimeType": "application/pdf",
        "sizeBytes": 15 * 1024 * 1024,
    }
    res_size = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-intent",
        json=oversized,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    # Pydantic or router rejects oversized payload
    assert res_size.status_code in (400, 422)


def test_document_ownership_isolation():
    # Case belongs to Patient 1
    case_id = create_test_case(patient_token=TOKEN_PATIENT_1, key_suffix="ownership_doc")

    # Patient 2 attempts to upload to Patient 1's case -> 403 Forbidden
    files = {"file": ("snoop.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res.status_code == 403
    assert "own medical cases" in res.json()["detail"].lower()


def test_unauthenticated_upload_rejected():
    case_id = create_test_case(key_suffix="unauth_doc")
    files = {"file": ("report.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
    )
    assert res.status_code == 401


def test_nonexistent_case_upload_rejected():
    files = {"file": ("report.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    res = client.post(
        "/api/v1/cases/case_nonexistent_9999/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 404
