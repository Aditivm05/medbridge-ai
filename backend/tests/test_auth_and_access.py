import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Test Tokens
TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_CLINICIAN_VERIFIED = "Bearer mock-token-clinician-verified"
TOKEN_CLINICIAN_UNVERIFIED = "Bearer mock-token-clinician-unverified"
TOKEN_ADMIN = "Bearer mock-token-admin"


def test_unauthenticated_requests_return_401():
    """Requests without token or with malformed token must be rejected with 401 Unauthorized."""
    # No Authorization header
    res1 = client.get("/api/v1/cases")
    assert res1.status_code == 401
    assert "Missing Authorization header" in res1.json()["detail"]

    # Malformed/empty token
    res2 = client.get("/api/v1/cases", headers={"Authorization": "Bearer "})
    assert res2.status_code == 401

    res3 = client.get("/api/v1/cases/case_nonexistent", headers={"Authorization": "Bearer invalid_garbage_token"})
    assert res3.status_code == 401


def test_patient_can_create_and_read_own_case():
    """A patient can successfully create and read their own medical case."""
    payload = {
        "chiefComplaint": "Persistent dry cough and low-grade fever for 3 days",
        "duration": "3 days",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": "idem_patient_1_own_case",
    }

    # 1. Patient 1 creates case
    create_res = client.post(
        "/api/v1/cases",
        json=payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert create_res.status_code == 201
    case_data = create_res.json()
    case_id = case_data["caseId"]
    assert case_data["patientId"] == "patient_demo_1"

    # 2. Patient 1 reads their own case
    get_res = client.get(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert get_res.status_code == 200
    assert get_res.json()["caseId"] == case_id
    assert get_res.json()["patientId"] == "patient_demo_1"


def test_patient_cannot_read_another_patients_case():
    """
    CRITICAL ACCESS TEST:
    Patient 2 must NOT be able to view Patient 1's medical case (HTTP 403 Forbidden).
    """
    # 1. Patient 1 creates a case
    payload = {
        "chiefComplaint": "Acute epigastric pain radiating to back",
        "duration": "6 hours",
        "requestedUrgency": "urgent",
        "patientLanguage": "mr",
        "idempotencyKey": "idem_patient_1_private_case",
    }
    create_res = client.post(
        "/api/v1/cases",
        json=payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert create_res.status_code == 201
    case_id = create_res.json()["caseId"]

    # 2. Patient 2 attempts to read Patient 1's case
    forbidden_res = client.get(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert forbidden_res.status_code == 403
    assert "Patients can only access their own medical cases" in forbidden_res.json()["detail"]


def test_unverified_clinician_cannot_accept_case():
    """
    CRITICAL CLINICAL RESTRICTION TEST:
    An unverified clinician must be blocked from accepting cases (HTTP 403 Forbidden).
    """
    # 1. Patient 1 creates a case and enqueues to MATCHING pool
    payload = {
        "chiefComplaint": "Suspected fracture of right wrist following a fall",
        "duration": "1 hour",
        "requestedUrgency": "urgent",
        "patientLanguage": "hi",
        "idempotencyKey": "idem_unverified_clinician_test",
    }
    create_res = client.post(
        "/api/v1/cases",
        json=payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert create_res.status_code == 201
    case_id = create_res.json()["caseId"]

    # Transition to MATCHING
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})

    # 2. Unverified clinician attempts to accept case
    accept_res = client.post(
        f"/api/v1/cases/{case_id}/accept",
        headers={"Authorization": TOKEN_CLINICIAN_UNVERIFIED},
    )
    assert accept_res.status_code == 403
    assert "Only verified clinicians with validated medical licenses can accept cases" in accept_res.json()["detail"]


def test_verified_clinician_can_accept_case():
    """A verified clinician can successfully accept an unassigned case in MATCHING pool."""
    # 1. Patient 1 creates case and moves to MATCHING
    payload = {
        "chiefComplaint": "Severe sore throat with difficulty swallowing",
        "duration": "2 days",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": "idem_verified_clinician_test",
    }
    create_res = client.post(
        "/api/v1/cases",
        json=payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert create_res.status_code == 201
    case_id = create_res.json()["caseId"]

    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})

    # 2. Verified clinician accepts case
    accept_res = client.post(
        f"/api/v1/cases/{case_id}/accept",
        headers={"Authorization": TOKEN_CLINICIAN_VERIFIED},
    )
    assert accept_res.status_code == 200
    accepted_data = accept_res.json()
    assert accepted_data["status"] == "ACCEPTED"
    assert accepted_data["assignedClinicianId"] == "clinician_verified_1"


def test_custom_claims_inspection_and_updates():
    """Verifies that /auth/me returns decoded claims and /auth/claims updates claims."""
    # Test GET /auth/me for verified clinician
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": TOKEN_CLINICIAN_VERIFIED})
    assert me_res.status_code == 200
    data = me_res.json()
    assert data["uid"] == "clinician_verified_1"
    assert data["role"] == "clinician"
    assert data["isVerifiedClinician"] is True

    # Test POST /auth/claims
    claims_payload = {
        "uid": "new_doc_test",
        "role": "clinician",
        "is_verified_clinician": True,
        "extra_claims": {"license": "MH-2026-TEST"},
    }
    claims_res = client.post(
        "/api/v1/auth/claims",
        json=claims_payload,
        headers={"Authorization": TOKEN_ADMIN},
    )
    assert claims_res.status_code == 200
    assert claims_res.json()["status"] == "success"
