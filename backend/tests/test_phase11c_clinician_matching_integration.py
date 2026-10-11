import json
import uuid
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.case_service import case_service
from app.services.brief_service import brief_service
from app.services.clinician_service import clinician_service
from app.core.state_machine import CaseStatus
from app.schemas.case import CaseCreate, RequestedUrgency

client = TestClient(app)

TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_CLINICIAN_VERIFIED = "Bearer mock-token-clinician-verified"
TOKEN_CLINICIAN_UNVERIFIED = "Bearer mock-token-clinician-unverified"
TOKEN_ADMIN = "Bearer mock-token-admin"


@pytest.fixture(autouse=True)
def reset_state():
    """Resets rate limits, mock clients, and seeds demo clinicians."""
    brief_service._case_rate_limits.clear()
    brief_service.set_client_for_testing(None)
    clinician_service.seed_default_clinicians()
    yield
    brief_service._case_rate_limits.clear()
    brief_service.set_client_for_testing(None)


def _mock_gemini_output():
    return {
        "timelineAndDetails": "Fever and mild cough for 2 days.",
        "relevantHistory": [
            {"fact": "Asthma in childhood", "source": "PATIENT_REPORTED", "reference": "intake:knownConditions"}
        ],
        "currentMedications": [
            {"fact": "Inhaler as needed", "source": "PATIENT_REPORTED", "reference": "intake:medications"}
        ],
        "patientReportedAllergies": [
            {"fact": "Sulfa drugs", "source": "PATIENT_REPORTED", "reference": "intake:allergies"}
        ],
        "vitals": [
            {"name": "Temperature", "value": "100.4", "unit": "F", "source": "PATIENT_PROVIDED", "reference": "intake:vitals"}
        ],
        "documentFindings": [],
        "conflicts": [],
        "missingInformation": ["Current oxygen saturation unknown"],
        "clarificationQuestions": ["Any wheezing or shortness of breath?"],
        "sourceReferences": [
            {"sourceType": "PATIENT_REPORTED", "reference": "chiefComplaint"},
        ],
    }


def _create_case_and_approved_brief(patient_token=TOKEN_PATIENT_1, patient_lang="en", specialty=None):
    idem_key = f"idem_matching_test_{uuid.uuid4().hex[:12]}"
    meta = {}
    if specialty:
        meta["preferredSpecialty"] = specialty

    case_payload = {
        "chiefComplaint": "Persistent moderate fever and dry cough",
        "duration": "2 days",
        "requestedUrgency": "urgent",
        "patientLanguage": patient_lang,
        "idempotencyKey": idem_key,
        "metadata": meta,
    }

    create_res = client.post("/api/v1/cases", json=case_payload, headers={"Authorization": patient_token})
    assert create_res.status_code == 201
    case_data = create_res.json()
    case_id = case_data["caseId"]

    # Mock Gemini generation
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(_mock_gemini_output())
    mock_model.generate_content.return_value = mock_response
    mock_genai_client = MagicMock()
    mock_genai_client.models.generate_content.return_value = mock_response
    brief_service.set_client_for_testing(mock_genai_client)

    gen_res = client.post(f"/api/v1/cases/{case_id}/brief/generate", headers={"Authorization": patient_token})
    assert gen_res.status_code == 200
    assert gen_res.json()["briefStatus"] == "DRAFT_AI"

    # Approve brief
    appr_res = client.post(f"/api/v1/cases/{case_id}/brief/approve", headers={"Authorization": patient_token})
    assert appr_res.status_code == 200
    assert appr_res.json()["briefStatus"] == "PATIENT_APPROVED"

    return case_id


def test_full_brief_approval_submission_and_matching_flow():
    """
    Requirement 1, 2, 3, 4:
    A valid patient edits and approves their brief, submits the case (DRAFT -> SUBMITTED),
    and triggers matching (SUBMITTED -> MATCHING). Verified candidate clinicians are returned.
    """
    case_id = _create_case_and_approved_brief()

    # Verify case is still in DRAFT status after brief approval
    case_snap = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT_1}).json()
    assert case_snap["status"] == "DRAFT"

    # Step 1: Submit case (DRAFT -> SUBMITTED)
    sub_res = client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    assert sub_res.status_code == 200, sub_res.text
    submitted_case = sub_res.json()
    assert submitted_case["status"] == "SUBMITTED"
    assert submitted_case["submittedAt"] is not None

    # Step 2: Trigger clinician matching (SUBMITTED -> MATCHING)
    match_res = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})
    assert match_res.status_code == 200, match_res.text
    match_data = match_res.json()

    assert match_data["caseId"] == case_id
    assert match_data["status"] == "MATCHING"
    assert match_data["matchedCount"] > 0
    assert len(match_data["matches"]) == match_data["matchedCount"]

    top_match = match_data["matches"][0]
    assert "[DEMO / SIMULATED]" in top_match["fullName"]
    assert top_match["isDemo"] is True
    assert top_match["availability"] == "available"
    assert top_match["matchScore"] > 0
    assert "en" in top_match["languages"]

    # Verify database state
    final_case = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT_1}).json()
    assert final_case["status"] == "MATCHING"
    assert "matchedClinicianIds" in final_case["metadata"]
    assert len(final_case["metadata"]["matchedClinicianIds"]) > 0


def test_direct_match_on_draft_case_rejected_by_state_machine():
    """
    Requirement 8:
    Direct jump from DRAFT to MATCHING without submission is rejected by state machine.
    """
    case_id = _create_case_and_approved_brief()

    # Attempt to match directly on DRAFT case
    res = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})
    assert res.status_code == 400
    assert "Invalid state transition" in res.json()["detail"]


def test_submission_and_matching_idempotency_without_duplicate_operations():
    """
    Requirement 5:
    Repeated submission and matching requests are idempotent and safely return current state.
    """
    case_id = _create_case_and_approved_brief()

    # First submission
    sub1 = client.post(
        f"/api/v1/cases/{case_id}/submit",
        json={"idempotencyKey": "test_idem_1"},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert sub1.status_code == 200
    assert sub1.json()["status"] == "SUBMITTED"

    # Repeated submission (idempotent 200)
    sub2 = client.post(
        f"/api/v1/cases/{case_id}/submit",
        json={"idempotencyKey": "test_idem_1"},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert sub2.status_code == 200
    assert sub2.json()["status"] == "SUBMITTED"

    # First match
    match1 = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})
    assert match1.status_code == 200
    assert match1.json()["status"] == "MATCHING"

    # Repeated match call while already MATCHING (safely queries matches without failing)
    match2 = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})
    assert match2.status_code == 200
    assert match2.json()["status"] == "MATCHING"
    assert match2.json()["matchedCount"] == match1.json()["matchedCount"]


def test_cross_patient_submission_and_matching_forbidden():
    """
    Requirement 6:
    Another patient cannot submit or match a case they do not own.
    """
    case_id = _create_case_and_approved_brief(patient_token=TOKEN_PATIENT_1)

    # Patient 2 tries to submit Patient 1's case
    sub_res = client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_2})
    assert sub_res.status_code == 403
    assert "Only the owning patient can submit this case" in sub_res.json()["detail"]

    # Patient 1 legitimately submits
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})

    # Patient 2 tries to trigger matching on Patient 1's case
    match_res = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_2})
    assert match_res.status_code == 403

    # Unauthenticated request returns 401
    unauth_sub = client.post(f"/api/v1/cases/{case_id}/submit")
    assert unauth_sub.status_code == 401
    unauth_match = client.post(f"/api/v1/cases/{case_id}/match")
    assert unauth_match.status_code == 401


def test_unverified_clinician_cannot_access_matching_or_brief():
    """
    Requirement 7:
    An unverified clinician cannot access protected matching information or briefs.
    """
    case_id = _create_case_and_approved_brief(patient_token=TOKEN_PATIENT_1)
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})

    # Unverified clinician attempts to trigger/query matching
    res_match = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_CLINICIAN_UNVERIFIED})
    assert res_match.status_code == 403
    assert "Only verified clinicians" in res_match.json()["detail"]

    # Unverified clinician attempts to read Doctor Brief
    res_brief = client.get(f"/api/v1/cases/{case_id}/brief", headers={"Authorization": TOKEN_CLINICIAN_UNVERIFIED})
    assert res_brief.status_code == 403


def test_matching_with_no_eligible_clinicians_returns_legitimate_empty_state():
    """
    Requirement 10:
    When no verified clinician matches (e.g. unsupported language),
    transitions case to NO_CLINICIAN_AVAILABLE and returns honest empty matches without fabricating providers.
    """
    # Create case with language 'ta' (Tamil), for which no seeded demo doctor speaks
    case_id = _create_case_and_approved_brief(patient_token=TOKEN_PATIENT_1, patient_lang="ta")
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})

    match_res = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})
    assert match_res.status_code == 200
    data = match_res.json()

    assert data["caseId"] == case_id
    assert data["status"] == "NO_CLINICIAN_AVAILABLE"
    assert data["matchedCount"] == 0
    assert data["matches"] == []

    # Database case status must be authoritative NO_CLINICIAN_AVAILABLE
    server_case = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT_1}).json()
    assert server_case["status"] == "NO_CLINICIAN_AVAILABLE"

    # Retrying matching is allowed (allowed state transition NO_CLINICIAN_AVAILABLE -> MATCHING)
    retry_res = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})
    assert retry_res.status_code == 200
    assert retry_res.json()["status"] == "NO_CLINICIAN_AVAILABLE"


def test_invalid_state_transitions_rejected():
    """
    Requirement 8:
    Terminal or illegal status transitions (e.g. submitting a cancelled case) are rejected.
    """
    case_id = _create_case_and_approved_brief()

    # Cancel case
    cancel_res = client.delete(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT_1})
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Submitting a CANCELLED case is rejected with 400
    sub_res = client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    assert sub_res.status_code == 400
    assert "Invalid state transition" in sub_res.json()["detail"]

    # Matching a CANCELLED case is rejected with 400
    match_res = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})
    assert match_res.status_code == 400


def test_nonexistent_case_submit_and_match_returns_404():
    """
    Nonexistent case IDs return 404 Not Found cleanly.
    """
    res_sub = client.post("/api/v1/cases/case_nonexistent_999/submit", headers={"Authorization": TOKEN_PATIENT_1})
    assert res_sub.status_code == 404

    res_match = client.post("/api/v1/cases/case_nonexistent_999/match", headers={"Authorization": TOKEN_PATIENT_1})
    assert res_match.status_code == 404
