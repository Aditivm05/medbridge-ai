import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_CLINICIAN_VERIFIED = "Bearer mock-token-clinician-verified"


def test_successful_case_creation_with_metadata_mapping():
    """
    Phase 11B: Patient case creation via POST /api/v1/cases persists required fields
    and maps clinical metadata (symptoms, conditions, medications, allergies).
    """
    idem_key = f"idem_phase11b_success_{uuid.uuid4().hex[:12]}"
    payload = {
        "chiefComplaint": "Severe sharp right lower quadrant abdominal pain with fever",
        "duration": "24 hours",
        "requestedUrgency": "urgent",
        "patientLanguage": "hi",
        "idempotencyKey": idem_key,
        "metadata": {
            "symptoms": ["Sharp Abdominal Pain", "High Fever (102°F+)", "Nausea / Vomiting"],
            "knownConditions": "Type 2 Diabetes (controlled)",
            "medications": "Metformin 500mg BID",
            "allergies": "Amoxicillin (mild rash)",
        },
    }

    res = client.post(
        "/api/v1/cases",
        json=payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )

    assert res.status_code == 201, f"Expected 201 Created, got {res.status_code}: {res.text}"
    data = res.json()
    assert "caseId" in data
    assert data["caseId"].startswith("case_")
    assert data["status"] == "DRAFT"
    assert data["patientId"] == "patient_demo_1"
    assert data["chiefComplaint"] == payload["chiefComplaint"]
    assert data["duration"] == payload["duration"]
    assert data["requestedUrgency"] == "urgent"
    assert data["patientLanguage"] == "hi"
    assert data["idempotencyKey"] == idem_key

    # Validate metadata mapping
    metadata = data.get("metadata", {})
    assert metadata.get("symptoms") == payload["metadata"]["symptoms"]
    assert metadata.get("knownConditions") == payload["metadata"]["knownConditions"]
    assert metadata.get("medications") == payload["metadata"]["medications"]
    assert metadata.get("allergies") == payload["metadata"]["allergies"]


def test_case_creation_missing_and_invalid_required_fields():
    """
    Phase 11B: Backend strictly validates required fields and lengths.
    Missing or malformed fields return 422 Unprocessable Entity.
    """
    # 1. Missing chiefComplaint
    res1 = client.post(
        "/api/v1/cases",
        json={
            "duration": "2 days",
            "requestedUrgency": "routine",
            "idempotencyKey": f"idem_val_1_{uuid.uuid4().hex[:8]}",
        },
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res1.status_code == 422

    # 2. chiefComplaint too short (< 5 chars)
    res2 = client.post(
        "/api/v1/cases",
        json={
            "chiefComplaint": "Pain",
            "duration": "2 days",
            "requestedUrgency": "routine",
            "idempotencyKey": f"idem_val_2_{uuid.uuid4().hex[:8]}",
        },
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res2.status_code == 422

    # 3. Missing duration
    res3 = client.post(
        "/api/v1/cases",
        json={
            "chiefComplaint": "Persistent headache and fever",
            "requestedUrgency": "urgent",
            "idempotencyKey": f"idem_val_3_{uuid.uuid4().hex[:8]}",
        },
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res3.status_code == 422

    # 4. duration too short (< 2 chars)
    res4 = client.post(
        "/api/v1/cases",
        json={
            "chiefComplaint": "Persistent headache and fever",
            "duration": "1",
            "requestedUrgency": "urgent",
            "idempotencyKey": f"idem_val_4_{uuid.uuid4().hex[:8]}",
        },
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res4.status_code == 422

    # 5. Invalid requestedUrgency
    res5 = client.post(
        "/api/v1/cases",
        json={
            "chiefComplaint": "Persistent headache and fever",
            "duration": "2 days",
            "requestedUrgency": "ultra-critical",
            "idempotencyKey": f"idem_val_5_{uuid.uuid4().hex[:8]}",
        },
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res5.status_code == 422

    # 6. Missing idempotencyKey
    res6 = client.post(
        "/api/v1/cases",
        json={
            "chiefComplaint": "Persistent headache and fever",
            "duration": "2 days",
            "requestedUrgency": "routine",
        },
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res6.status_code == 422


def test_case_creation_disallowed_metadata_rejected():
    """
    Phase 11B: Medical metadata keys must belong to allowed set
    and not exceed maximum size constraints.
    """
    res = client.post(
        "/api/v1/cases",
        json={
            "chiefComplaint": "Persistent headache and fever",
            "duration": "2 days",
            "requestedUrgency": "routine",
            "idempotencyKey": f"idem_meta_disallow_{uuid.uuid4().hex[:8]}",
            "metadata": {
                "unauthorizedInternalField": "hacker_payload",
            },
        },
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 422


def test_idempotent_retry_behavior():
    """
    Phase 11B: Retrying a submission with the same idempotencyKey returns
    the canonical existing case and does not create duplicates.
    """
    idem_key = f"idem_retry_test_{uuid.uuid4().hex[:12]}"
    payload = {
        "chiefComplaint": "Severe throbbing migraine with nausea",
        "duration": "12 hours",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": idem_key,
        "metadata": {
            "symptoms": ["Severe Headache", "Nausea / Vomiting"],
        },
    }

    # Initial creation
    res1 = client.post(
        "/api/v1/cases",
        json=payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res1.status_code == 201
    case1 = res1.json()
    canonical_case_id = case1["caseId"]

    # Retried submission with identical idempotencyKey
    res2 = client.post(
        "/api/v1/cases",
        json=payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res2.status_code in (200, 201)
    case2 = res2.json()
    assert case2["caseId"] == canonical_case_id
    assert case2["idempotencyKey"] == idem_key


def test_patient_specific_case_isolation():
    """
    Phase 11B: Ensure strict multi-persona isolation.
    - Patient 1 only receives Patient 1's cases via GET /api/v1/cases.
    - Patient 2 only receives Patient 2's cases via GET /api/v1/cases.
    - Cross-patient direct access returns 403 Forbidden.
    """
    # 1. Patient 1 creates a case
    p1_payload = {
        "chiefComplaint": "Patient 1 isolated case: Acute epigastric distress",
        "duration": "4 hours",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_p1_iso_{uuid.uuid4().hex[:10]}",
    }
    p1_res = client.post("/api/v1/cases", json=p1_payload, headers={"Authorization": TOKEN_PATIENT_1})
    assert p1_res.status_code == 201
    p1_case_id = p1_res.json()["caseId"]

    # 2. Patient 2 creates a case
    p2_payload = {
        "chiefComplaint": "Patient 2 isolated case: Bilateral ankle swelling",
        "duration": "5 days",
        "requestedUrgency": "routine",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_p2_iso_{uuid.uuid4().hex[:10]}",
    }
    p2_res = client.post("/api/v1/cases", json=p2_payload, headers={"Authorization": TOKEN_PATIENT_2})
    assert p2_res.status_code == 201
    p2_case_id = p2_res.json()["caseId"]

    # 3. Patient 1 lists cases -> must see p1_case_id, but NEVER p2_case_id
    p1_list_res = client.get("/api/v1/cases", headers={"Authorization": TOKEN_PATIENT_1})
    assert p1_list_res.status_code == 200
    p1_cases = p1_list_res.json()
    p1_case_ids = [c["caseId"] for c in p1_cases]
    assert p1_case_id in p1_case_ids
    assert p2_case_id not in p1_case_ids

    # 4. Patient 2 lists cases -> must see p2_case_id, but NEVER p1_case_id
    p2_list_res = client.get("/api/v1/cases", headers={"Authorization": TOKEN_PATIENT_2})
    assert p2_list_res.status_code == 200
    p2_cases = p2_list_res.json()
    p2_case_ids = [c["caseId"] for c in p2_cases]
    assert p2_case_id in p2_case_ids
    assert p1_case_id not in p2_case_ids

    # 5. Cross-patient direct case access must return 403 Forbidden
    cross_res_1 = client.get(f"/api/v1/cases/{p1_case_id}", headers={"Authorization": TOKEN_PATIENT_2})
    assert cross_res_1.status_code == 403, f"Expected 403 Forbidden, got {cross_res_1.status_code}"

    cross_res_2 = client.get(f"/api/v1/cases/{p2_case_id}", headers={"Authorization": TOKEN_PATIENT_1})
    assert cross_res_2.status_code == 403, f"Expected 403 Forbidden, got {cross_res_2.status_code}"


def test_patient_identity_derived_from_authenticated_claims():
    """
    Phase 11B: Backend MUST derive patient identity from authenticated claims,
    and never trust a spoofed patientId sent in the request body.
    """
    spoofed_payload = {
        "patientId": "victim_patient_123",  # Attacker attempts to spoof ownership
        "chiefComplaint": "Spoof attempt: Fever and abdominal discomfort",
        "duration": "1 day",
        "requestedUrgency": "routine",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_spoof_{uuid.uuid4().hex[:10]}",
    }

    res = client.post(
        "/api/v1/cases",
        json=spoofed_payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 201
    created_case = res.json()
    # Must be assigned to authenticated user (patient_demo_1), not victim_patient_123
    assert created_case["patientId"] == "patient_demo_1"
    assert created_case["patientId"] != "victim_patient_123"


def test_unauthenticated_requests_rejected():
    """Phase 11B: Unauthenticated case operations must be rejected with 401."""
    res_get = client.get("/api/v1/cases")
    assert res_get.status_code == 401

    res_post = client.post(
        "/api/v1/cases",
        json={
            "chiefComplaint": "Unauthenticated test complaint",
            "duration": "1 day",
            "requestedUrgency": "routine",
            "idempotencyKey": "idem_unauth_001",
        },
    )
    assert res_post.status_code == 401
