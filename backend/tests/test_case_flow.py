import pytest
import concurrent.futures
from fastapi.testclient import TestClient
from app.main import app
from app.core.state_machine import CaseStatus, validate_transition, InvalidStateTransitionError
from app.schemas.document import validate_magic_bytes

client = TestClient(app)

TOKEN_PATIENT = "Bearer mock-token-patient-1"
TOKEN_CLINICIAN_1 = "Bearer mock-token-clinician-verified"
TOKEN_CLINICIAN_2 = "Bearer claims.eyJ1aWQiOiJjbGluaWNpYW5fMl92ZXJpZmllZCIsInJvbGUiOiJjbGluaWNpYW4iLCJpc192ZXJpZmllZF9jbGluaWNpYW4iOnRydWV9"


def test_health_endpoint():
    # Test root-level /health
    res_root = client.get("/health")
    assert res_root.status_code == 200
    data_root = res_root.json()
    assert data_root["status"] == "healthy"
    assert data_root["service"] == "MedBridge AI"

    # Test api_v1 /api/v1/health
    res_v1 = client.get("/api/v1/health")
    assert res_v1.status_code == 200
    data_v1 = res_v1.json()
    assert data_v1["status"] == "healthy"
    assert data_v1["service"] == "MedBridge AI"


def test_state_machine_valid_transitions():
    # DRAFT -> SUBMITTED
    validate_transition(CaseStatus.DRAFT, CaseStatus.SUBMITTED)
    # SUBMITTED -> MATCHING
    validate_transition(CaseStatus.SUBMITTED, CaseStatus.MATCHING)
    # MATCHING -> ACCEPTED
    validate_transition(CaseStatus.MATCHING, CaseStatus.ACCEPTED)
    # ACCEPTED -> IN_CONSULTATION
    validate_transition(CaseStatus.ACCEPTED, CaseStatus.IN_CONSULTATION)
    # IN_CONSULTATION -> COMPLETED
    validate_transition(CaseStatus.IN_CONSULTATION, CaseStatus.COMPLETED)


def test_state_machine_invalid_jumps():
    # Cannot jump DRAFT -> COMPLETED
    with pytest.raises(InvalidStateTransitionError):
        validate_transition(CaseStatus.DRAFT, CaseStatus.COMPLETED)

    # Cannot jump SUBMITTED -> ACCEPTED directly
    with pytest.raises(InvalidStateTransitionError):
        validate_transition(CaseStatus.SUBMITTED, CaseStatus.ACCEPTED)

    # Cannot transition out of COMPLETED
    with pytest.raises(InvalidStateTransitionError):
        validate_transition(CaseStatus.COMPLETED, CaseStatus.MATCHING)


def test_case_creation_and_idempotency():
    payload = {
        "patientId": "pat_101",
        "chiefComplaint": "Severe chest pain radiating to left arm for 45 minutes",
        "duration": "45 mins",
        "requestedUrgency": "emergency",
        "patientLanguage": "en",
        "idempotencyKey": "idem_unique_key_001",
    }
    
    # First creation call
    res1 = client.post("/api/v1/cases", json=payload, headers={"Authorization": TOKEN_PATIENT})
    assert res1.status_code == 201
    data1 = res1.json()
    case_id_1 = data1["caseId"]
    assert data1["status"] == "DRAFT"

    # Duplicate call with identical idempotencyKey
    res2 = client.post("/api/v1/cases", json=payload, headers={"Authorization": TOKEN_PATIENT})
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["caseId"] == case_id_1  # Must return identical case ID


def test_concurrency_race_condition_on_case_acceptance():
    """
    Simulates two clinicians attempting to accept the exact same case simultaneously.
    Proves that one clinician wins (200 OK) and the other gets a clear 409 Conflict.
    """
    # 1. Create a case
    payload = {
        "chiefComplaint": "High fever with chills and vomiting",
        "duration": "2 days",
        "requestedUrgency": "urgent",
        "patientLanguage": "hi",
        "idempotencyKey": "idem_race_test_002",
    }
    res = client.post("/api/v1/cases", json=payload, headers={"Authorization": TOKEN_PATIENT})
    assert res.status_code == 201
    case_id = res.json()["caseId"]

    # 2. Transition through SUBMITTED -> MATCHING
    sub_res = client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT})
    assert sub_res.status_code == 200
    match_res = client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT})
    assert match_res.status_code == 200
    assert match_res.json()["status"] == "MATCHING"

    # 3. Simulate two concurrent clinicians trying to claim the case
    def attempt_accept(token):
        return client.post(
            f"/api/v1/cases/{case_id}/accept",
            headers={"Authorization": token},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_accept, TOKEN_CLINICIAN_1)
        f2 = executor.submit(attempt_accept, TOKEN_CLINICIAN_2)
        r1 = f1.result()
        r2 = f2.result()

    status_codes = [r1.status_code, r2.status_code]
    assert 200 in status_codes, f"At least one must succeed: {status_codes}"
    assert 409 in status_codes, f"The other must receive HTTP 409 Conflict: {status_codes}"

    # Verify that the case is now ACCEPTED and assigned to exactly one clinician
    final_res = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT})
    final_case = final_res.json()
    assert final_case["status"] == "ACCEPTED"
    assert final_case["assignedClinicianId"] in ["clinician_verified_1", "clinician_2_verified"]


def test_magic_byte_validation():
    # Valid PDF bytes
    valid_pdf = b"%PDF-1.4 header bytes and stream"
    assert validate_magic_bytes(valid_pdf, "application/pdf") is True

    # Valid JPEG bytes
    valid_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    assert validate_magic_bytes(valid_jpg, "image/jpeg") is True

    # Valid PNG bytes
    valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    assert validate_magic_bytes(valid_png, "image/png") is True

    # Fake spoofed file (text disguised as PDF)
    fake_pdf = b"Hello, I am a text file pretending to be PDF"
    assert validate_magic_bytes(fake_pdf, "application/pdf") is False
