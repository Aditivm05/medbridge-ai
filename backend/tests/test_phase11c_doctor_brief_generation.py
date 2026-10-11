import json
import uuid
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.case_service import case_service
from app.services.brief_service import brief_service
from app.schemas.case import CaseCreate, RequestedUrgency

client = TestClient(app)

TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_CLINICIAN_VERIFIED = "Bearer mock-token-clinician-verified"
TOKEN_ADMIN = "Bearer mock-token-admin"


@pytest.fixture(autouse=True)
def reset_brief_rate_limits():
    brief_service._case_rate_limits.clear()
    brief_service.set_client_for_testing(None)
    yield
    brief_service._case_rate_limits.clear()
    brief_service.set_client_for_testing(None)


def _mock_gemini_output():
    return {
        "timelineAndDetails": "Patient reports constant dull pain for 3 days, worsening after eating.",
        "relevantHistory": [
            {"fact": "Hypertension diagnosed 2021", "source": "PATIENT_REPORTED", "reference": "intake:knownConditions"}
        ],
        "currentMedications": [
            {"fact": "Amlodipine 5mg OD", "source": "PATIENT_REPORTED", "reference": "intake:medications"}
        ],
        "patientReportedAllergies": [
            {"fact": "Penicillin allergy", "source": "PATIENT_REPORTED", "reference": "intake:allergies"}
        ],
        "vitals": [
            {"name": "Blood Pressure", "value": "130/85", "unit": "mmHg", "source": "PATIENT_PROVIDED", "reference": "intake:vitals"}
        ],
        "documentFindings": [],
        "conflicts": [],
        "missingInformation": ["Fasting blood glucose level unknown"],
        "clarificationQuestions": ["Does the pain radiate to your back or shoulder?"],
        "sourceReferences": [
            {"sourceType": "PATIENT_REPORTED", "reference": "chiefComplaint"},
            {"sourceType": "PATIENT_REPORTED", "reference": "intake:medications"},
        ],
    }


def test_successful_doctor_brief_generation_canonical_contract():
    """
    Phase 11C Task 1:
    Patient 1 creates a case and successfully generates a Doctor Brief via POST /api/v1/cases/{case_id}/brief/generate.
    Verifies canonical case ID, response schema, and Firestore persistence.
    """
    idem_key = f"idem_11c_gen_{uuid.uuid4().hex[:12]}"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Recurrent severe epigastric discomfort after meals",
            duration="3 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey=idem_key,
            metadata={
                "knownConditions": "Hypertension diagnosed 2021",
                "medications": "Amlodipine 5mg OD",
                "allergies": "Penicillin allergy",
            },
        ),
        actor_id="patient_demo_1",
    )

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(_mock_gemini_output())
    mock_client.models.generate_content.return_value = mock_resp
    brief_service.set_client_for_testing(mock_client)

    res = client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_1},
        json={"confirmRegenerate": False},
    )

    assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.text}"
    brief_data = res.json()

    # Verify canonical case ID and contract
    assert brief_data["caseId"] == case.caseId
    assert "briefId" in brief_data
    assert brief_data["briefId"].startswith("brief_")
    assert brief_data["briefStatus"] == "DRAFT_AI"
    assert brief_data["version"] == 1
    assert brief_data["reasonForConsultation"] == case.chiefComplaint
    assert brief_data["timelineAndDetails"] == "Patient reports constant dull pain for 3 days, worsening after eating."
    assert len(brief_data["relevantHistory"]) == 1
    assert len(brief_data["currentMedications"]) == 1
    assert len(brief_data["patientReportedAllergies"]) == 1
    assert "disclaimer" in brief_data

    # Verify case was updated with doctorBriefId
    refreshed_case = case_service.get_case(case.caseId)
    assert refreshed_case.doctorBriefId == brief_data["briefId"]
    assert refreshed_case.status.value == "DRAFT"  # Case remains in DRAFT until submission


def test_doctor_brief_retrieval_by_patient_owner():
    """
    Phase 11C Task 1:
    Patient 1 retrieves the generated brief via GET /api/v1/cases/{case_id}/brief.
    """
    idem_key = f"idem_11c_get_{uuid.uuid4().hex[:12]}"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Mild headache and dizziness",
            duration="1 day",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey=idem_key,
        ),
        actor_id="patient_demo_1",
    )

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(_mock_gemini_output())
    mock_client.models.generate_content.return_value = mock_resp
    brief_service.set_client_for_testing(mock_client)

    gen_res = client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert gen_res.status_code == 200

    # Retrieve brief
    get_res = client.get(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert get_res.status_code == 200
    retrieved = get_res.json()
    assert retrieved["caseId"] == case.caseId
    assert retrieved["briefId"] == gen_res.json()["briefId"]
    assert retrieved["briefStatus"] == "DRAFT_AI"
    assert retrieved["reasonForConsultation"] == "Mild headache and dizziness"


def test_doctor_brief_retrieval_before_generation_returns_404():
    """
    Phase 11C Task 1:
    Attempting to retrieve a brief before it has been generated returns HTTP 404 NOT FOUND.
    """
    idem_key = f"idem_11c_404_{uuid.uuid4().hex[:12]}"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Knee stiffness following physical exercise",
            duration="5 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey=idem_key,
        ),
        actor_id="patient_demo_1",
    )

    res = client.get(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 404
    assert f"Doctor brief not found for case {case.caseId}" in res.json()["detail"]


def test_cross_patient_cannot_generate_doctor_brief():
    """
    Phase 11C Task 1:
    Patient 2 attempts to generate a brief for Patient 1's case -> Strictly rejected with HTTP 403 Forbidden.
    """
    idem_key = f"idem_11c_cross_gen_{uuid.uuid4().hex[:12]}"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Skin rash on forearms with itching",
            duration="2 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey=idem_key,
        ),
        actor_id="patient_demo_1",
    )

    res = client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_2},  # Patient 2 is not owner
    )
    assert res.status_code == 403
    assert "Only the owning patient can generate a Doctor Brief" in res.json()["detail"]


def test_cross_patient_cannot_retrieve_doctor_brief():
    """
    Phase 11C Task 1:
    Patient 2 attempts to view Patient 1's generated brief -> Strictly rejected with HTTP 403 Forbidden.
    """
    idem_key = f"idem_11c_cross_get_{uuid.uuid4().hex[:12]}"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Chronic fatigue and joint soreness",
            duration="2 weeks",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey=idem_key,
        ),
        actor_id="patient_demo_1",
    )

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(_mock_gemini_output())
    mock_client.models.generate_content.return_value = mock_resp
    brief_service.set_client_for_testing(mock_client)

    client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_1},
    )

    # Patient 2 attempts read
    res = client.get(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res.status_code == 403
    assert "Cannot access another patient's doctor brief" in res.json()["detail"]


def test_unassigned_clinician_cannot_access_draft_brief():
    """
    Phase 11C Task 1:
    A verified clinician attempts to view a brief while the case is in DRAFT -> Rejected with HTTP 403 Forbidden.
    """
    idem_key = f"idem_11c_clinician_draft_{uuid.uuid4().hex[:12]}"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Mild persistent cough without fever",
            duration="1 week",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey=idem_key,
        ),
        actor_id="patient_demo_1",
    )

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(_mock_gemini_output())
    mock_client.models.generate_content.return_value = mock_resp
    brief_service.set_client_for_testing(mock_client)

    client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_1},
    )

    # Clinician attempts read
    res = client.get(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_CLINICIAN_VERIFIED},
    )
    assert res.status_code == 403
    assert "Clinician is not assigned" in res.json()["detail"] or "Forbidden" in res.json()["detail"]


def test_unauthenticated_request_rejected():
    """
    Phase 11C Task 1:
    Unauthenticated caller attempting to generate or view brief gets HTTP 401 Unauthorized.
    """
    res_gen = client.post("/api/v1/cases/case_arbitrary_123/brief/generate")
    assert res_gen.status_code == 401

    res_get = client.get("/api/v1/cases/case_arbitrary_123/brief")
    assert res_get.status_code == 401


def test_nonexistent_case_generation_returns_404():
    """
    Phase 11C Task 1:
    Attempting to generate a brief for a non-existent case ID returns HTTP 404 Not Found.
    """
    res = client.post(
        "/api/v1/cases/case_nonexistent_9999/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_backend_generation_failure_does_not_crash_and_records_validation_warning():
    """
    Phase 11C Task 1:
    When upstream AI generation fails or is offline, backend does NOT crash with HTTP 500.
    It returns a structured DoctorBrief skeleton with validationWarnings indicating the failure.
    """
    idem_key = f"idem_11c_fallback_{uuid.uuid4().hex[:12]}"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Intermittent dizziness when standing quickly",
            duration="4 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey=idem_key,
        ),
        actor_id="patient_demo_1",
    )

    # Mock client raising an error to simulate AI failure
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("Simulated upstream network timeout")
    brief_service.set_client_for_testing(mock_client)

    res = client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_1},
    )

    assert res.status_code == 200, f"Expected 200 OK fallback skeleton, got {res.status_code}: {res.text}"
    brief_data = res.json()
    assert brief_data["caseId"] == case.caseId
    assert brief_data["briefStatus"] == "DRAFT_AI"
    assert brief_data["reasonForConsultation"] == case.chiefComplaint
    # Must contain validation warnings detailing the failure
    assert brief_data["validationWarnings"] is not None
    assert len(brief_data["validationWarnings"]) > 0
    assert any("AI generation failed" in w for w in brief_data["validationWarnings"])


def test_brief_rate_limit_enforcement():
    """
    Phase 11C Task 1:
    Rapid consecutive generation requests exceed the per-case rate limit and return HTTP 429.
    """
    idem_key = f"idem_11c_ratelimit_{uuid.uuid4().hex[:12]}"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Severe back stiffness",
            duration="2 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey=idem_key,
        ),
        actor_id="patient_demo_1",
    )

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(_mock_gemini_output())
    mock_client.models.generate_content.return_value = mock_resp
    brief_service.set_client_for_testing(mock_client)

    # First call succeeds
    res1 = client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_1},
        json={"confirmRegenerate": True},
    )
    assert res1.status_code == 200

    # Rapid second call without delay triggers MIN_GENERATION_INTERVAL_SECONDS throttling (HTTP 429)
    res2 = client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_1},
        json={"confirmRegenerate": True},
    )
    assert res2.status_code == 429
    assert "rate limit" in res2.json()["detail"].lower()
