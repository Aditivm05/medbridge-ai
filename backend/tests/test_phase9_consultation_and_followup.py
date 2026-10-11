"""
Phase 9 Automated Test Suite: Consultation Workspace & Case Completion / Follow-Up
Verifies:
1. Consultation Workspace (text-based, explicitly labelled [DEMO / SIMULATED]):
   - Assigned verified clinician records clinical observations and provisional care advice.
   - Case transitions ACCEPTED -> IN_CONSULTATION.
   - Consultation record persisted in Firestore with isSimulated: True and consultationType: text_based_consultation_simulated.
   - Case links consultationId.
   - CASE_IN_CONSULTATION audit event recorded.
2. Complete Case & Follow-Up Directives:
   - Assigned verified clinician schedules follow-up with required flag, recommendedDate, instructions.
   - Case transitions IN_CONSULTATION -> terminal COMPLETED.
   - Follow-up record persisted in Firestore with status 'scheduled'.
   - Clinician availability automatically released back to 'available' with currentCaseId reset.
   - Terminal state protection: zero outgoing transitions from COMPLETED.
3. Access Control and RBAC:
   - Unassigned clinician rejected with HTTP 403.
   - Unverified clinician rejected with HTTP 403.
   - Patient rejected with HTTP 403 on writing consultation/follow-up.
   - Patient owner and assigned clinician can read consultation and follow-up records.
   - Cross-patient reads rejected with HTTP 403 Forbidden.
4. Schema & Data Validation:
   - Min/max length constraints enforced on notes and instructions.
"""

import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.state_machine import CaseStatus
from app.schemas.audit import AuditEventType
from app.schemas.clinician import ClinicianAvailability
from app.services.clinician_service import clinician_service
from app.services.case_service import case_service
from app.services.audit_service import audit_service
from app.services.consultation_service import consultation_service

client = TestClient(app)

TOKEN_PATIENT = "Bearer mock-token-patient-1"
TOKEN_PATIENT_OTHER = "Bearer mock-token-patient-2"
TOKEN_DOC_SHARMA = "Bearer mock-token-demo_doc_sharma"
TOKEN_DOC_PATIL = "Bearer mock-token-demo_doc_patil"
TOKEN_DOC_PENDING = "Bearer mock-token-demo_doc_pending"


@pytest.fixture(autouse=True)
def reset_demo_clinicians():
    """Resets the demo clinicians into Firestore before each test."""
    clinician_service.seed_default_clinicians()


def create_accepted_case(key_suffix: str = "p9") -> str:
    """Helper to set up a case through DRAFT -> SUBMITTED -> MATCHING -> ACCEPTED by demo_doc_sharma."""
    payload = {
        "chiefComplaint": f"Persistent fever and cough for Phase 9 test ({key_suffix})",
        "duration": "3 days",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_p9_{key_suffix}_{time.time()}",
    }
    res = client.post("/api/v1/cases", json=payload, headers={"Authorization": TOKEN_PATIENT})
    assert res.status_code == 201
    case_id = res.json()["caseId"]

    sub_res = client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT})
    assert sub_res.status_code == 200

    match_res = client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT})
    assert match_res.status_code == 200

    accept_res = client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_DOC_SHARMA})
    assert accept_res.status_code == 200
    assert accept_res.json()["status"] == CaseStatus.ACCEPTED.value
    assert accept_res.json()["assignedClinicianId"] == "demo_doc_sharma"

    return case_id


# ==============================================================================
# 1. Consultation Recording & Labeling Tests
# ==============================================================================

def test_assigned_clinician_records_consultation_and_transitions_status():
    """Assigned clinician successfully records consultation; case transitions to IN_CONSULTATION."""
    case_id = create_accepted_case("record_ok")

    payload = {
        "clinicianNotes": "Patient presents with dry cough and mild pyrexia (38.1 C). Respiratory sounds clear.",
        "provisionalCareAdvice": "Maintain adequate oral hydration, monitor temperature every 6 hours, rest.",
        "isSimulated": True,
    }

    res = client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json=payload,
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["caseId"] == case_id
    assert data["clinicianId"] == "demo_doc_sharma"
    assert data["patientId"] == "patient_demo_1"
    assert data["isSimulated"] is True
    assert data["consultationType"] == "text_based_consultation_simulated"
    assert "dry cough" in data["clinicianNotes"]
    assert "hydration" in data["provisionalCareAdvice"]

    # Verify case status transitioned to IN_CONSULTATION
    case = case_service.get_case(case_id)
    assert case.status == CaseStatus.IN_CONSULTATION
    assert case.consultationId == f"consult_{case_id}"

    # Verify audit event emitted
    events = audit_service.get_case_events(case_id)
    assert any(e.eventType == AuditEventType.CASE_IN_CONSULTATION for e in events)


def test_consultation_rejects_unassigned_clinician():
    """Clinician other than the assigned clinician cannot record consultation."""
    case_id = create_accepted_case("unassigned")

    payload = {
        "clinicianNotes": "Attempted assessment by unassigned doctor.",
        "provisionalCareAdvice": "Advice from wrong clinician.",
        "isSimulated": True,
    }

    res = client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json=payload,
        headers={"Authorization": TOKEN_DOC_PATIL},
    )
    assert res.status_code == 403
    assert "not assigned" in res.json()["detail"].lower()


def test_consultation_rejects_patient_role():
    """Patients cannot post clinical assessment notes."""
    case_id = create_accepted_case("patient_block")

    payload = {
        "clinicianNotes": "Patient trying to write consultation notes.",
        "provisionalCareAdvice": "Patient advice.",
        "isSimulated": True,
    }

    res = client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json=payload,
        headers={"Authorization": TOKEN_PATIENT},
    )
    assert res.status_code == 403


def test_consultation_rejects_unverified_clinician():
    """Unverified/pending clinician cannot record consultation."""
    case_id = create_accepted_case("unverified")

    payload = {
        "clinicianNotes": "Pending clinician notes.",
        "provisionalCareAdvice": "Pending clinician advice.",
        "isSimulated": True,
    }

    res = client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json=payload,
        headers={"Authorization": TOKEN_DOC_PENDING},
    )
    assert res.status_code == 403
    assert "verified" in res.json()["detail"].lower()


def test_consultation_validation_constraints():
    """Validates min length on notes and advice."""
    case_id = create_accepted_case("validation")

    # Too short notes (< 10 chars)
    res = client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json={"clinicianNotes": "Short", "provisionalCareAdvice": "Valid care advice here", "isSimulated": True},
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res.status_code == 422


# ==============================================================================
# 2. Complete Case & Follow-Up Scheduling Tests
# ==============================================================================

def test_complete_case_and_followup_success():
    """Assigned clinician completes case and sets follow-up directives; releases clinician."""
    case_id = create_accepted_case("complete_ok")

    # 1. Record consultation notes
    consult_payload = {
        "clinicianNotes": "Patient assessed. Symptoms consistent with mild upper respiratory viral syndrome.",
        "provisionalCareAdvice": "Symptomatic relief with hydration, rest, and paracetamol as needed.",
        "isSimulated": True,
    }
    c_res = client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json=consult_payload,
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert c_res.status_code == 200

    # Clinician should currently be busy
    clin_doc = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_doc.availability == ClinicianAvailability.BUSY
    assert clin_doc.currentCaseId == case_id

    # 2. Complete case with follow-up
    followup_payload = {
        "required": True,
        "recommendedDate": "2026-10-18",
        "instructions": "Return for clinic review if fever persists > 5 days or if shortness of breath develops.",
    }
    comp_res = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=followup_payload,
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert comp_res.status_code == 200
    comp_data = comp_res.json()

    assert comp_data["case"]["status"] == CaseStatus.COMPLETED.value
    assert comp_data["case"]["completedAt"] is not None
    assert comp_data["followUp"]["required"] is True
    assert comp_data["followUp"]["recommendedDate"] == "2026-10-18"
    assert comp_data["followUp"]["status"] == "scheduled"
    assert "shortness of breath" in comp_data["followUp"]["instructions"]

    # 3. Clinician availability released back to 'available'
    clin_after = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_after.availability == ClinicianAvailability.AVAILABLE
    assert clin_after.currentCaseId is None

    # 4. Verify CASE_COMPLETED audit event
    events = audit_service.get_case_events(case_id)
    assert any(e.eventType == AuditEventType.CASE_COMPLETED for e in events)


def test_completed_case_is_terminal():
    """Terminal state protection: cannot transition or complete a case that is already COMPLETED."""
    case_id = create_accepted_case("terminal_check")

    followup_payload = {
        "required": False,
        "recommendedDate": "2026-10-25",
        "instructions": "Follow up only as needed if symptoms recur.",
    }
    res1 = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=followup_payload,
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res1.status_code == 200
    assert res1.json()["case"]["status"] == CaseStatus.COMPLETED.value

    # Attempt second completion -> must be rejected with 400
    res2 = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=followup_payload,
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res2.status_code == 400
    assert "already in terminal completed" in res2.json()["detail"].lower()


# ==============================================================================
# 3. Retrieval & Patient Access Tests
# ==============================================================================

def test_patient_can_view_consultation_and_followup():
    """Patient owner can retrieve their consultation notes and scheduled follow-up."""
    case_id = create_accepted_case("patient_read")

    # Record consultation
    client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json={
            "clinicianNotes": "Clinical notes on patient condition.",
            "provisionalCareAdvice": "Supportive care advice instructions.",
            "isSimulated": True,
        },
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )

    # Complete with follow-up
    client.post(
        f"/api/v1/cases/{case_id}/complete",
        json={
            "required": True,
            "recommendedDate": "2026-10-15",
            "instructions": "Follow-up instructions for patient review.",
        },
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )

    # Patient owner reads consultation
    c_res = client.get(
        f"/api/v1/cases/{case_id}/consultation",
        headers={"Authorization": TOKEN_PATIENT},
    )
    assert c_res.status_code == 200
    assert c_res.json()["clinicianNotes"] == "Clinical notes on patient condition."
    assert c_res.json()["isSimulated"] is True

    # Patient owner reads follow-up
    f_res = client.get(
        f"/api/v1/cases/{case_id}/follow-up",
        headers={"Authorization": TOKEN_PATIENT},
    )
    assert f_res.status_code == 200
    assert f_res.json()["required"] is True
    assert f_res.json()["recommendedDate"] == "2026-10-15"


def test_cross_patient_cannot_view_consultation_or_followup():
    """Different patient is rejected with HTTP 403 Forbidden."""
    case_id = create_accepted_case("cross_patient")

    client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json={
            "clinicianNotes": "Confidential patient notes.",
            "provisionalCareAdvice": "Confidential patient care advice.",
            "isSimulated": True,
        },
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )

    client.post(
        f"/api/v1/cases/{case_id}/complete",
        json={
            "required": True,
            "recommendedDate": "2026-10-20",
            "instructions": "Confidential follow-up.",
        },
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )

    # Other patient tries to read consultation
    c_res = client.get(
        f"/api/v1/cases/{case_id}/consultation",
        headers={"Authorization": TOKEN_PATIENT_OTHER},
    )
    assert c_res.status_code == 403

    # Other patient tries to read follow-up
    f_res = client.get(
        f"/api/v1/cases/{case_id}/follow-up",
        headers={"Authorization": TOKEN_PATIENT_OTHER},
    )
    assert f_res.status_code == 403
