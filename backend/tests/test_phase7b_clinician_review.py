import json
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.state_machine import CaseStatus
from app.schemas.case import CaseCreate, RequestedUrgency
from app.schemas.doctor_brief import BriefStatus
from app.schemas.audit import AuditEventType
from app.services.case_service import case_service
from app.services.brief_service import brief_service
from app.services.audit_service import audit_service

client = TestClient(app)


import base64

def auth_header(uid: str, role: str = "patient", is_verified_clinician: bool = True):
    payload = {
        "uid": uid,
        "email": f"{uid}@example.com",
        "role": role,
        "is_verified_clinician": is_verified_clinician if role == "clinician" else False,
    }
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return {"Authorization": f"Bearer claims.{b64}"}


@pytest.fixture(autouse=True)
def setup_mock_gemini():
    """Ensure Gemini client does not make outbound network calls during tests."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "timelineAndDetails": "Fever for 48 hours",
        "relevantHistory": [],
        "currentMedications": [],
        "patientReportedAllergies": [],
        "vitals": [],
        "documentFindings": [],
        "conflicts": [],
        "missingInformation": [],
        "clarificationQuestions": [],
        "sourceReferences": [],
    })
    mock_client.models.generate_content.return_value = mock_resp
    brief_service.set_client_for_testing(mock_client)


def test_clinician_review_success_on_patient_approved_brief():
    """
    Phase 7b Task:
    - Verified assigned clinician submits review through POST /api/v1/cases/{case_id}/brief/review.
    - Transitions briefStatus to CLINICIAN_REVIEWED.
    - Records reviewedBy, reviewedAt, and audit trail event.
    """
    patient_uid = "patient_7b_success"
    clinician_uid = "clinician_7b_assigned"

    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Acute abdominal pain for 36 hours",
            duration="36 hours",
            requestedUrgency=RequestedUrgency.URGENT,
            patientLanguage="en",
            idempotencyKey="idem_7b_success",
        ),
        actor_id=patient_uid,
    )

    # 1. Patient generates brief
    res_gen = client.post(
        f"/api/v1/cases/{case.caseId}/brief/generate",
        headers=auth_header(patient_uid),
    )
    assert res_gen.status_code == 200
    assert res_gen.json()["briefStatus"] == "DRAFT_AI"

    # 2. Patient approves brief -> PATIENT_APPROVED
    res_app = client.post(
        f"/api/v1/cases/{case.caseId}/brief/approve",
        json={"notes": "Symptoms verified"},
        headers=auth_header(patient_uid),
    )
    assert res_app.status_code == 200
    assert res_app.json()["briefStatus"] == "PATIENT_APPROVED"

    # 3. Case submitted, enqueued into matching, accepted by clinician
    case_service.submit_case(case.caseId, actor_id=patient_uid, actor_role="patient")
    case_service.transition_status(case.caseId, target_status=CaseStatus.MATCHING, actor_id=patient_uid, actor_role="patient")
    case_service.accept_case_atomic(case.caseId, clinician_id=clinician_uid)

    # 4. Verified assigned clinician reviews brief with clinical notes
    review_notes = "Reviewed ultrasound and CBC findings. Patient verified history."
    res_rev = client.post(
        f"/api/v1/cases/{case.caseId}/brief/review",
        json={"clinicianNotes": review_notes},
        headers=auth_header(clinician_uid, role="clinician", is_verified_clinician=True),
    )
    assert res_rev.status_code == 200
    data = res_rev.json()
    assert data["briefStatus"] == "CLINICIAN_REVIEWED"
    assert data["reviewedBy"] == clinician_uid
    assert data["reviewedAt"] is not None

    # 5. Check audit trail preserves the transition with details
    trail = audit_service.get_events_for_case(case.caseId)
    review_events = [e for e in trail if e.eventType == AuditEventType.BRIEF_CLINICIAN_REVIEWED]
    assert len(review_events) == 1
    assert review_events[0].actorId == clinician_uid
    assert review_events[0].actorRole == "clinician"
    assert review_events[0].details.get("clinicianNotes") == review_notes


def test_duplicate_clinician_review_blocked():
    """
    Phase 7b Task:
    - Prevent duplicate transitions: reviewing an already-reviewed brief returns HTTP 400.
    - Preserves audit trail integrity.
    """
    patient_uid = "patient_7b_dup"
    clinician_uid = "clinician_7b_dup"

    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Persistent migraine",
            duration="2 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey="idem_7b_dup",
        ),
        actor_id=patient_uid,
    )

    client.post(f"/api/v1/cases/{case.caseId}/brief/generate", headers=auth_header(patient_uid))
    client.post(f"/api/v1/cases/{case.caseId}/brief/approve", headers=auth_header(patient_uid))

    case_service.submit_case(case.caseId, actor_id=patient_uid, actor_role="patient")
    case_service.transition_status(case.caseId, target_status=CaseStatus.MATCHING, actor_id=patient_uid, actor_role="patient")
    case_service.accept_case_atomic(case.caseId, clinician_id=clinician_uid)

    # First review succeeds
    res_1 = client.post(
        f"/api/v1/cases/{case.caseId}/brief/review",
        headers=auth_header(clinician_uid, role="clinician", is_verified_clinician=True),
    )
    assert res_1.status_code == 200
    assert res_1.json()["briefStatus"] == "CLINICIAN_REVIEWED"

    # Second review call rejected with 400
    res_2 = client.post(
        f"/api/v1/cases/{case.caseId}/brief/review",
        headers=auth_header(clinician_uid, role="clinician", is_verified_clinician=True),
    )
    assert res_2.status_code == 400
    assert "already been reviewed" in res_2.json()["detail"].lower()


def test_unverified_clinician_cannot_review():
    """
    Phase 7b Acceptance Criteria:
    - Unverified clinicians cannot perform clinician review (HTTP 403 Forbidden).
    """
    patient_uid = "patient_7b_unver"
    clinician_uid = "clinician_7b_unver"

    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Chest congestion",
            duration="3 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey="idem_7b_unver",
        ),
        actor_id=patient_uid,
    )
    client.post(f"/api/v1/cases/{case.caseId}/brief/generate", headers=auth_header(patient_uid))
    client.post(f"/api/v1/cases/{case.caseId}/brief/approve", headers=auth_header(patient_uid))
    case_service.submit_case(case.caseId, actor_id=patient_uid, actor_role="patient")
    case_service.transition_status(case.caseId, target_status=CaseStatus.MATCHING, actor_id=patient_uid, actor_role="patient")
    case_service.accept_case_atomic(case.caseId, clinician_id=clinician_uid)

    # Unverified clinician call -> 403
    res = client.post(
        f"/api/v1/cases/{case.caseId}/brief/review",
        headers=auth_header(clinician_uid, role="clinician", is_verified_clinician=False),
    )
    assert res.status_code == 403


def test_patient_cannot_review():
    """
    Phase 7b Acceptance Criteria:
    - Patients cannot perform clinician review (HTTP 403 Forbidden).
    """
    patient_uid = "patient_7b_pat_rev"

    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="High fever",
            duration="1 day",
            requestedUrgency=RequestedUrgency.URGENT,
            patientLanguage="en",
            idempotencyKey="idem_7b_pat_rev",
        ),
        actor_id=patient_uid,
    )
    client.post(f"/api/v1/cases/{case.caseId}/brief/generate", headers=auth_header(patient_uid))

    res = client.post(
        f"/api/v1/cases/{case.caseId}/brief/review",
        headers=auth_header(patient_uid, role="patient"),
    )
    assert res.status_code == 403


def test_unassigned_clinician_cannot_review():
    """
    Phase 7b Acceptance Criteria:
    - Verified clinician who is not assigned to the case cannot review (HTTP 403 Forbidden).
    """
    patient_uid = "patient_7b_unassigned"
    assigned_doc = "clinician_7b_assigned_doc"
    unassigned_doc = "clinician_7b_stranger_doc"

    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Sprained ankle",
            duration="1 day",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey="idem_7b_unassigned",
        ),
        actor_id=patient_uid,
    )
    client.post(f"/api/v1/cases/{case.caseId}/brief/generate", headers=auth_header(patient_uid))
    client.post(f"/api/v1/cases/{case.caseId}/brief/approve", headers=auth_header(patient_uid))
    case_service.submit_case(case.caseId, actor_id=patient_uid, actor_role="patient")
    case_service.transition_status(case.caseId, target_status=CaseStatus.MATCHING, actor_id=patient_uid, actor_role="patient")
    case_service.accept_case_atomic(case.caseId, clinician_id=assigned_doc)

    res = client.post(
        f"/api/v1/cases/{case.caseId}/brief/review",
        headers=auth_header(unassigned_doc, role="clinician", is_verified_clinician=True),
    )
    assert res.status_code == 403
    assert "assigned" in res.json()["detail"].lower()


def test_review_blocked_on_invalid_case_status():
    """
    Phase 7b Acceptance Criteria:
    - Enforce valid lifecycle transitions on the backend: review blocked while case is DRAFT or MATCHING.
    """
    patient_uid = "patient_7b_status"
    clinician_uid = "clinician_7b_status"

    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Mild cough",
            duration="2 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey="idem_7b_status",
        ),
        actor_id=patient_uid,
    )
    client.post(f"/api/v1/cases/{case.caseId}/brief/generate", headers=auth_header(patient_uid))

    # Case is still DRAFT
    res_draft = client.post(
        f"/api/v1/cases/{case.caseId}/brief/review",
        headers=auth_header(clinician_uid, role="clinician", is_verified_clinician=True),
    )
    assert res_draft.status_code == 403


def test_review_persists_in_firestore():
    """
    Phase 7b Acceptance Criteria:
    - Review action persists through the backend and survives retrieval / page refresh.
    """
    patient_uid = "patient_7b_persist"
    clinician_uid = "clinician_7b_persist"

    case = case_service.create_case(
        CaseCreate(
            chiefComplaint="Rash on forearm",
            duration="5 days",
            requestedUrgency=RequestedUrgency.ROUTINE,
            patientLanguage="en",
            idempotencyKey="idem_7b_persist",
        ),
        actor_id=patient_uid,
    )
    client.post(f"/api/v1/cases/{case.caseId}/brief/generate", headers=auth_header(patient_uid))
    client.post(f"/api/v1/cases/{case.caseId}/brief/approve", headers=auth_header(patient_uid))
    case_service.submit_case(case.caseId, actor_id=patient_uid, actor_role="patient")
    case_service.transition_status(case.caseId, target_status=CaseStatus.MATCHING, actor_id=patient_uid, actor_role="patient")
    case_service.accept_case_atomic(case.caseId, clinician_id=clinician_uid)

    # Perform review
    res_rev = client.post(
        f"/api/v1/cases/{case.caseId}/brief/review",
        json={"clinicianNotes": "Erythematous maculopapular rash, no anaphylaxis signs"},
        headers=auth_header(clinician_uid, role="clinician", is_verified_clinician=True),
    )
    assert res_rev.status_code == 200

    # Fresh read via GET /cases/{caseId}/brief (simulating page reload)
    res_get = client.get(
        f"/api/v1/cases/{case.caseId}/brief",
        headers=auth_header(clinician_uid, role="clinician", is_verified_clinician=True),
    )
    assert res_get.status_code == 200
    brief_data = res_get.json()
    assert brief_data["briefStatus"] == "CLINICIAN_REVIEWED"
    assert brief_data["reviewedBy"] == clinician_uid
    assert brief_data["reviewedAt"] is not None
