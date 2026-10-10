import pytest
import io
import pypdf
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.document import ExtractionStatus
from app.schemas.audit import AuditEventType
from app.services.audit_service import audit_service

client = TestClient(app)

TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_CLINICIAN = "Bearer mock-token-clinician-verified"


def make_text_pdf(text: str) -> bytes:
    """Generates valid minimal in-memory PDF binary containing text."""
    escaped = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
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


def make_multipage_pdf(texts: list) -> bytes:
    """Generates multi-page PDF with distinct text on each page."""
    writer = pypdf.PdfWriter()
    for t in texts:
        single_bytes = make_text_pdf(t)
        single_reader = pypdf.PdfReader(io.BytesIO(single_bytes))
        writer.add_page(single_reader.pages[0])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_blank_pdf(num_pages: int = 1) -> bytes:
    """Generates blank PDF with no text stream (simulating scanned document)."""
    writer = pypdf.PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_encrypted_pdf(password: str = "secretpass") -> bytes:
    """Generates password-encrypted PDF."""
    writer = pypdf.PdfWriter()
    base_bytes = make_text_pdf("Encrypted sensitive patient diagnosis data")
    reader = pypdf.PdfReader(io.BytesIO(base_bytes))
    writer.add_page(reader.pages[0])
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_corrupted_pdf() -> bytes:
    """Generates PDF with valid magic bytes but corrupted internal structure."""
    return b"%PDF-1.4\nBROKEN_OBJECT_DATA_CORRUPTED_STREAM_NO_XREF_%%EOF"


def create_test_case(patient_token: str = TOKEN_PATIENT_1, key_suffix: str = "extract_test") -> str:
    """Helper to create a fresh DRAFT case."""
    payload = {
        "chiefComplaint": "Patient symptom description for text extraction testing",
        "duration": "2 days",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_extract_{key_suffix}_{id(key_suffix)}",
    }
    res = client.post("/api/v1/cases", json=payload, headers={"Authorization": patient_token})
    assert res.status_code == 201
    return res.json()["caseId"]


def test_extract_single_page_pdf_text():
    case_id = create_test_case(key_suffix="single_page")
    clinical_text = "Complete Blood Count: Hemoglobin 14.2 g/dL, Platelets 220,000 /mcL, WBC 6,800 /mcL."
    pdf_bytes = make_text_pdf(clinical_text)

    # 1. Upload file (non-blocking)
    files = {"file": ("blood_report.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    upload_res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["documentId"]

    # 2. Inspect document record
    doc_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert doc_res.status_code == 200
    doc_data = doc_res.json()
    assert doc_data["extractionStatus"] == "EXTRACTED"
    assert doc_data["pageCount"] == 1
    assert len(doc_data["pages"]) == 1
    assert doc_data["pages"][0]["pageNumber"] == 1
    assert doc_data["pages"][0]["status"] == "EXTRACTED"
    assert "Hemoglobin 14.2 g/dL" in doc_data["pages"][0]["text"]

    # 3. Query /text endpoint
    text_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/text",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert text_res.status_code == 200
    text_data = text_res.json()
    assert text_data["extractionStatus"] == "EXTRACTED"
    assert text_data["pageCount"] == 1
    assert "Hemoglobin 14.2 g/dL" in text_data["fullText"]


def test_extract_multipage_pdf_per_page_text():
    case_id = create_test_case(key_suffix="multi_page")
    page_texts = [
        "Page 1: Patient Clinical Vitals - BP 120/80 mmHg, Pulse 76 bpm, Temp 98.6 F.",
        "Page 2: Serum Biochemistry - Blood Glucose 95 mg/dL, Serum Creatinine 0.85 mg/dL.",
        "Page 3: Diagnostic Assessment - Normal sinus rhythm, no acute ischemic changes.",
    ]
    pdf_bytes = make_multipage_pdf(page_texts)

    files = {"file": ("multipage_record.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    upload_res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["documentId"]

    # Verify per-page extraction
    text_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/text",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert text_res.status_code == 200
    text_data = text_res.json()
    assert text_data["extractionStatus"] == "EXTRACTED"
    assert text_data["pageCount"] == 3
    assert len(text_data["pages"]) == 3

    # Check that each page has its exact page number and text for verifiable citations
    assert text_data["pages"][0]["pageNumber"] == 1
    assert "BP 120/80 mmHg" in text_data["pages"][0]["text"]

    assert text_data["pages"][1]["pageNumber"] == 2
    assert "Serum Creatinine 0.85 mg/dL" in text_data["pages"][1]["text"]

    assert text_data["pages"][2]["pageNumber"] == 3
    assert "Normal sinus rhythm" in text_data["pages"][2]["text"]


def test_extract_empty_or_scanned_pdf_marked_needs_ocr():
    case_id = create_test_case(key_suffix="scanned_pdf")
    blank_pdf_bytes = make_blank_pdf(num_pages=2)

    files = {"file": ("scanned_document.pdf", io.BytesIO(blank_pdf_bytes), "application/pdf")}
    upload_res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["documentId"]

    # Verify status is NEEDS_OCR without guessing content
    doc_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert doc_res.status_code == 200
    doc_data = doc_res.json()
    assert doc_data["extractionStatus"] == "NEEDS_OCR"
    assert doc_data["pageCount"] == 2
    assert doc_data["pages"][0]["status"] == "NEEDS_OCR"
    assert doc_data["pages"][1]["status"] == "NEEDS_OCR"
    # Content must not be guessed
    assert doc_data["pages"][0]["text"] == ""


def test_corrupted_pdf_handled_gracefully():
    case_id = create_test_case(key_suffix="corrupt_pdf")
    corrupt_bytes = make_corrupted_pdf()

    files = {"file": ("corrupted.pdf", io.BytesIO(corrupt_bytes), "application/pdf")}
    upload_res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    # Magic bytes %PDF- passed, upload returns 200 without crashing
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["documentId"]

    # Extraction handles corruption gracefully
    doc_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert doc_res.status_code == 200
    doc_data = doc_res.json()
    assert doc_data["extractionStatus"] == "FAILED"
    assert doc_data["errorMessage"] is not None
    assert "corrupted" in doc_data["errorMessage"].lower() or "invalid" in doc_data["errorMessage"].lower()


def test_encrypted_pdf_handled_gracefully():
    case_id = create_test_case(key_suffix="encrypted_pdf")
    enc_bytes = make_encrypted_pdf(password="clinic_pass_123")

    files = {"file": ("encrypted_notes.pdf", io.BytesIO(enc_bytes), "application/pdf")}
    upload_res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["documentId"]

    # Extraction handles encryption gracefully
    doc_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert doc_res.status_code == 200
    doc_data = doc_res.json()
    assert doc_data["extractionStatus"] == "FAILED"
    assert "password" in doc_data["errorMessage"].lower() or "encrypted" in doc_data["errorMessage"].lower()


def test_oversized_page_count_handled_gracefully():
    case_id = create_test_case(key_suffix="long_pdf")
    # Generate 35 pages (limit is 30)
    page_texts = [f"Page {i}: Test record text contents exceeding limit" for i in range(1, 36)]
    oversized_bytes = make_multipage_pdf(page_texts)

    files = {"file": ("oversized_35_pages.pdf", io.BytesIO(oversized_bytes), "application/pdf")}
    upload_res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["documentId"]

    doc_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert doc_res.status_code == 200
    doc_data = doc_res.json()
    assert doc_data["extractionStatus"] == "FAILED"
    assert "30 pages" in doc_data["errorMessage"] or "maximum limit" in doc_data["errorMessage"].lower()


def test_unauthorized_access_to_extracted_text_rejected():
    # Case belongs to Patient 1
    case_id = create_test_case(patient_token=TOKEN_PATIENT_1, key_suffix="sec_text_doc")
    pdf_bytes = make_text_pdf("Confidential Patient 1 clinical findings")

    files = {"file": ("confidential.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    upload_res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["documentId"]

    # 1. Patient 2 attempts to read Patient 1's extracted text -> 403 Forbidden
    res_cross = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/text",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res_cross.status_code == 403
    assert "own medical cases" in res_cross.json()["detail"].lower()

    # 2. Unauthenticated request -> 401 Unauthorized
    res_unauth = client.get(f"/api/v1/cases/{case_id}/documents/{doc_id}/text")
    assert res_unauth.status_code == 401

    # 3. Patient 1 (owner) can read -> 200 OK
    res_owner = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}/text",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_owner.status_code == 200


def test_audit_events_for_extraction():
    case_id = create_test_case(key_suffix="audit_doc")
    pdf_bytes = make_text_pdf("Audit test clinical data for Phase 6c verification")

    files = {"file": ("audit_report.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    upload_res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["documentId"]

    # Verify audit events for this case include DOC_TEXT_EXTRACTED
    events = audit_service.get_events_for_case(case_id)
    event_types = [e.eventType for e in events]
    assert AuditEventType.DOC_UPLOADED in event_types
    assert AuditEventType.DOC_TEXT_EXTRACTED in event_types


def test_image_upload_marked_needs_ocr_without_gemini():
    case_id = create_test_case(key_suffix="img_ocr")
    valid_jpg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb"

    files = {"file": ("ultrasound_scan.jpg", io.BytesIO(valid_jpg_bytes), "image/jpeg")}
    upload_res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["documentId"]

    # Image should be marked NEEDS_OCR without calling Gemini in Phase 6c
    doc_res = client.get(
        f"/api/v1/cases/{case_id}/documents/{doc_id}",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert doc_res.status_code == 200
    doc_data = doc_res.json()
    assert doc_data["extractionStatus"] == "NEEDS_OCR"
    assert doc_data["pageCount"] == 1
    assert doc_data["pages"][0]["status"] == "NEEDS_OCR"
