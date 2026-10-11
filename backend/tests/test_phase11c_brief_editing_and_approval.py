import json
import uuid
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.case_service import case_service
from app.services.brief_service import brief_service
from app.core.state_machine import CaseStatus
from app.schemas.case import CaseCreate, RequestedUrgency

client = TestClient(app)

TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_CLINICIAN_VERIFIED = "Bearer mock-token-clinician-verified"
TOKEN_ADMIN = "Bearer mock-token-admin"


@pytest.fixture(autouse=True)
def reset_brief_state():
    brief_service._case_rate_limits.clear()
    brief_service.set_client_for_testing(None)
    yield
    brief_service._case_rate_limits.clear()
    brief_service.set_client_for_testing(None)


def _mock_gemini_output():
    return {
        "timelineAndDetails": "Original: 3 days epigastric discomfort after meals.",
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
        "clarificationQuestions": ["Does the pain radiate to your back?"],
        "sourceReferences": [
            {"sourceType": "PATIENT_REPORTED", "reference": "chiefComplaint"},
        ],
    }


def _create_patient1_case_with_brief():
    idem_key = f"idem_11c_edit_{uuid.uuid4().hex[:12]}"
    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Epigastric discomfort",
            duration="3 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey=idem_key,
            metadata={"knownConditions": "Hypertension"},
        ),
        actor_id="patient_demo_1",
    )

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(_mock_gemini_output())
    mock_client.models.generate_content.return_value = mock_resp
    brief_service.set_client_for_testing(mock_client)

    res_gen = client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_1},
        json={"confirmRegenerate": False},
    )
    assert res_gen.status_code == 200
    return case, res_gen.json()


def test_save_brief_edits_and_verify_persisted_values():
    """
    Phase 11C Task 2:
    - Patient saves brief edits via PUT /api/v1/cases/{case_id}/brief.
    - Transitions briefStatus to EDITED, increments version counter to 2.
    - Stores previous version snapshot.
    - Persisted values verified via subsequent GET.
    """
    case, initial_brief = _create_patient1_case_with_brief()
    assert initial_brief["version"] == 1
    assert initial_brief["briefStatus"] == "DRAFT_AI"

    edit_payload = {
        "timelineAndDetails": "Corrected: 4 days epigastric burning pain radiating to sternum.",
        "relevantHistory": [
            {"fact": "Hypertension diagnosed 2021, controlled", "source": "PATIENT_REPORTED", "reference": "patient:manual_correction"},
            {"fact": "GERD diagnosed 2019", "source": "PATIENT_REPORTED", "reference": "patient:manual_correction"},
        ],
        "currentMedications": [
            {"fact": "Amlodipine 5mg OD morning", "source": "PATIENT_REPORTED", "reference": "patient:manual_correction"},
            {"fact": "Omeprazole 20mg OD before breakfast", "source": "PATIENT_REPORTED", "reference": "patient:manual_correction"},
        ],
        "patientReportedAllergies": [
            {"fact": "Penicillin (rash)", "source": "PATIENT_REPORTED", "reference": "patient:manual_correction"},
        ],
        "vitals": [
            {"name": "Blood Pressure", "value": "128/82", "unit": "mmHg", "source": "PATIENT_PROVIDED", "reference": "patient:manual_correction"},
            {"name": "Heart Rate", "value": "76", "unit": "bpm", "source": "PATIENT_PROVIDED", "reference": "patient:manual_correction"},
        ],
    }

    res_edit = client.put(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_PATIENT_1},
        json=edit_payload,
    )

    assert res_edit.status_code == 200, f"Expected 200, got {res_edit.status_code}: {res_edit.text}"
    edited_brief = res_edit.json()

    assert edited_brief["briefStatus"] == "EDITED"
    assert edited_brief["version"] == 2
    assert edited_brief["lastEditedBy"] == "patient_demo_1"
    assert edited_brief["lastEditedAt"] is not None
    assert edited_brief["timelineAndDetails"] == edit_payload["timelineAndDetails"]
    assert len(edited_brief["relevantHistory"]) == 2
    assert len(edited_brief["currentMedications"]) == 2
    assert len(edited_brief["vitals"]) == 2

    # Verify previous version snapshot
    assert len(edited_brief["previousVersions"]) == 1
    assert edited_brief["previousVersions"][0]["version"] == 1
    assert edited_brief["previousVersions"][0]["briefStatus"] == "DRAFT_AI"

    # Verify Firestore persistence via GET
    res_get = client.get(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_get.status_code == 200
    persisted = res_get.json()
    assert persisted["briefStatus"] == "EDITED"
    assert persisted["version"] == 2
    assert persisted["timelineAndDetails"] == edit_payload["timelineAndDetails"]


def test_reject_unauthorized_cross_patient_edits():
    """
    Phase 11C Task 2:
    - Patient 2 cannot edit Patient 1's brief (HTTP 403).
    - Unauthenticated caller cannot edit (HTTP 401).
    - Unassigned clinician cannot edit while in DRAFT (HTTP 403).
    """
    case, _ = _create_patient1_case_with_brief()

    # Patient 2 cross-patient edit attempt
    res_cross = client.put(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_PATIENT_2},
        json={"timelineAndDetails": "Malicious modification"},
    )
    assert res_cross.status_code == 403
    assert "Forbidden" in res_cross.json()["detail"]

    # Unauthenticated edit attempt
    res_unauth = client.put(
        f"/api/v1/cases/{case.caseId}/brief",
        json={"timelineAndDetails": "Unauthenticated modification"},
    )
    assert res_unauth.status_code == 401

    # Clinician edit attempt while case is in DRAFT
    res_clinician = client.put(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_CLINICIAN_VERIFIED},
        json={"timelineAndDetails": "Premature clinician edit"},
    )
    assert res_clinician.status_code == 403


def test_successful_patient_approval_and_persisted_status():
    """
    Phase 11C Task 2:
    - Patient approves brief via POST /api/v1/cases/{case_id}/brief/approve.
    - Transitions briefStatus to PATIENT_APPROVED.
    - Records approvedBy and approvedAt timestamp.
    - Verified persisted in Firestore.
    """
    case, _ = _create_patient1_case_with_brief()

    res_app = client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_1},
        json={"notes": "Patient verified all clinical facts"},
    )
    assert res_app.status_code == 200
    app_data = res_app.json()
    assert app_data["briefStatus"] == "PATIENT_APPROVED"
    assert app_data["approvedBy"] == "patient_demo_1"
    assert app_data["approvedAt"] is not None

    # Verify Firestore persistence
    res_get = client.get(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_get.status_code == 200
    assert res_get.json()["briefStatus"] == "PATIENT_APPROVED"
    assert res_get.json()["approvedBy"] == "patient_demo_1"


def test_reject_unauthorized_cross_patient_approval():
    """
    Phase 11C Task 2:
    - Patient 2 cannot approve Patient 1's brief (HTTP 403).
    - Unauthenticated caller cannot approve (HTTP 401).
    """
    case, _ = _create_patient1_case_with_brief()

    # Patient 2 approval attempt
    res_cross = client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_2},
        json={"notes": "Cross patient attempt"},
    )
    assert res_cross.status_code == 403
    assert "Forbidden" in res_cross.json()["detail"]

    # Unauthenticated approval attempt
    res_unauth = client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        json={"notes": "Unauthenticated attempt"},
    )
    assert res_unauth.status_code == 401


def test_edit_invalidates_prior_patient_approval():
    """
    Phase 11C Task 2:
    - If a brief is PATIENT_APPROVED, any subsequent edit must revert
      briefStatus to EDITED, requiring re-approval before case submission.
    """
    case, _ = _create_patient1_case_with_brief()

    # 1. Approve brief
    res_app1 = client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_app1.status_code == 200
    assert res_app1.json()["briefStatus"] == "PATIENT_APPROVED"

    # 2. Edit brief
    res_edit = client.put(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_PATIENT_1},
        json={"timelineAndDetails": "Added new symptom: mild nausea"},
    )
    assert res_edit.status_code == 200
    assert res_edit.json()["briefStatus"] == "EDITED"
    assert res_edit.json()["version"] == 2

    # 3. Patient approves the edited brief
    res_app2 = client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_app2.status_code == 200
    assert res_app2.json()["briefStatus"] == "PATIENT_APPROVED"
    assert res_app2.json()["version"] == 2


def test_invalid_state_transitions_edit_and_approve_rejected_after_submission():
    """
    Phase 11C Task 2:
    - Once a case is submitted, patients are strictly locked from editing or approving the brief.
    - Returns HTTP 403 Forbidden.
    """
    case, _ = _create_patient1_case_with_brief()

    # Approve brief
    client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_1},
    )

    # Submit case
    res_sub = client.post(
        f"/api/v1/cases/{case.caseId}/submit",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_sub.status_code == 200
    assert res_sub.json()["status"] == "SUBMITTED"

    # Late edit attempt -> 403 Forbidden
    res_late_edit = client.put(
        f"/api/v1/cases/{case.caseId}/brief",
        headers={"Authorization": TOKEN_PATIENT_1},
        json={"timelineAndDetails": "Late patient correction after submit"},
    )
    assert res_late_edit.status_code == 403
    assert "submission" in res_late_edit.json()["detail"].lower()

    # Late approve attempt -> 403 Forbidden
    res_late_app = client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_late_app.status_code == 403
    assert "submission" in res_late_app.json()["detail"].lower()


def test_duplicate_approval_and_submission_idempotency():
    """
    Phase 11C Task 2:
    - Duplicate approval calls are safe and idempotent (HTTP 200 with PATIENT_APPROVED).
    - Duplicate submission calls are safe and idempotent (HTTP 200 with SUBMITTED).
    """
    case, _ = _create_patient1_case_with_brief()

    # First approval
    res_app1 = client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_app1.status_code == 200
    assert res_app1.json()["briefStatus"] == "PATIENT_APPROVED"

    # Duplicate approval
    res_app2 = client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_app2.status_code == 200
    assert res_app2.json()["briefStatus"] == "PATIENT_APPROVED"

    # First submission
    res_sub1 = client.post(
        f"/api/v1/cases/{case.caseId}/submit",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_sub1.status_code == 200
    assert res_sub1.json()["status"] == "SUBMITTED"

    # Duplicate submission
    res_sub2 = client.post(
        f"/api/v1/cases/{case.caseId}/submit",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_sub2.status_code == 200
    assert res_sub2.json()["status"] == "SUBMITTED"


def test_approval_does_not_enqueue_matching_and_matching_triggered_at_most_once():
    """
    Phase 11C Task 2:
    - Approving brief does NOT enqueue matching (case remains in DRAFT).
    - No matching side-effects occur upon brief approval.
    - When enqueued into matching after submission, re-enqueueing is rejected by state machine.
    """
    case, _ = _create_patient1_case_with_brief()

    # 1. Approve brief
    res_app = client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_app.status_code == 200

    # Verify case status has NOT transitioned to MATCHING or SUBMITTED
    refreshed_case = case_service.get_case(case.caseId)
    assert refreshed_case.status == CaseStatus.DRAFT

    # 2. Submit case
    res_sub = client.post(
        f"/api/v1/cases/{case.caseId}/submit",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_sub.status_code == 200
    assert res_sub.json()["status"] == "SUBMITTED"

    # 3. Enqueue for matching
    res_match1 = client.post(
        f"/api/v1/cases/{case.caseId}/matching",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_match1.status_code == 200
    assert res_match1.json()["status"] == "MATCHING"

    # 4. Attempt second enqueue into matching -> rejected by state machine (HTTP 400)
    res_match2 = client.post(
        f"/api/v1/cases/{case.caseId}/matching",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_match2.status_code == 400
    assert "Invalid state transition" in res_match2.json()["detail"]


def test_edit_and_approve_nonexistent_and_ungenerated_cases():
    """
    Phase 11C Task 2:
    - Editing or approving non-existent case -> HTTP 404.
    - Editing or approving case with no generated brief -> HTTP 404.
    """
    # Non-existent case
    res_edit_no_case = client.put(
        "/api/v1/cases/case_nonexistent_999/brief",
        headers={"Authorization": TOKEN_PATIENT_1},
        json={"timelineAndDetails": "Nonexistent"},
    )
    assert res_edit_no_case.status_code == 404

    res_app_no_case = client.post(
        "/api/v1/cases/case_nonexistent_999/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_app_no_case.status_code == 404

    # Case exists, but brief not generated yet
    idem = f"idem_no_brief_{uuid.uuid4().hex[:8]}"
    case_no_brief = case_service.create_case(
        CaseCreate(
            chiefComplaint="Headache",
            duration="1 day",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey=idem,
        ),
        actor_id="patient_demo_1",
    )

    res_edit_no_brief = client.put(
        f"/api/v1/cases/{case_no_brief.caseId}/brief",
        headers={"Authorization": TOKEN_PATIENT_1},
        json={"timelineAndDetails": "Premature edit"},
    )
    assert res_edit_no_brief.status_code == 404
    assert "not found" in res_edit_no_brief.json()["detail"].lower()

    res_app_no_brief = client.post(
        f"/api/v1/cases/{case_no_brief.caseId}/brief/approve",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_app_no_brief.status_code == 404
    assert "not found" in res_app_no_brief.json()["detail"].lower()
