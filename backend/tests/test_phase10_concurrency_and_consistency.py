"""
Phase 10 — Stage 2C: Concurrency and Data-Consistency Regression Test Suite

Verifies:
1. Concurrent duplicate completion requests:
   - Simultaneous completion requests on the same case do not duplicate follow-ups
     or repeat state transitions; exactly one wins and the second is rejected cleanly.
2. Repeated completion after success:
   - Calling completion on an already COMPLETED case returns HTTP 400 deterministically
     without modifying state or logging duplicate audit events.
3. Transactional atomic rollback on partial failure:
   - Failure saving follow-up rolls back case transition and clinician release.
   - Failure updating case status rolls back follow-up and clinician release.
   - Failure releasing clinician availability rolls back follow-up and case status.
4. Clinician multi-case retention invariant:
   - A clinician who has another active assigned case (ACCEPTED or IN_CONSULTATION)
     is NOT released to 'available' when completing one of their cases.
   - Clinician is released to 'available' once their last active case is completed.
5. Role and Assignment Authorization:
   - Unassigned verified clinician receives HTTP 403.
   - Unverified clinician receives HTTP 403.
   - Patient caller receives HTTP 403.
   - Authorized administrator can successfully complete the case and release the assigned clinician.
6. Audit event integrity:
   - CASE_COMPLETED audit event is emitted strictly post-commit on success.
   - No CASE_COMPLETED event is emitted when completion fails or is rejected.
7. Recovery and retry:
   - A retry after a transient commit error succeeds completely without corrupted state.
"""

import concurrent.futures
import time
from typing import Dict, Any, List
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
from app.core.firestore_client import get_firestore_client, FakeTransaction

client = TestClient(app, raise_server_exceptions=False)

TOKEN_PATIENT = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_DOC_SHARMA = "Bearer mock-token-demo_doc_sharma"
TOKEN_DOC_PATIL = "Bearer mock-token-demo_doc_patil"
TOKEN_DOC_PENDING = "Bearer mock-token-demo_doc_pending"
TOKEN_ADMIN = "Bearer mock-token-admin"


@pytest.fixture(autouse=True)
def isolate_test_environment():
    """Resets the demo clinicians and clears cases/consultations/follow-ups before each test."""
    db = get_firestore_client()
    if hasattr(db, "is_fake") and db.is_fake:
        for k in list(db._store.keys()):
            if (
                k.startswith("cases/")
                or k.startswith("consultations/")
                or k.startswith("follow_ups/")
                or k.startswith("audit_events/")
                or k.startswith("idempotency_keys/")
            ):
                del db._store[k]
    clinician_service.seed_default_clinicians()


def _create_accepted_case(key_suffix: str = "c2c", doctor_token: str = TOKEN_DOC_SHARMA) -> str:
    """Helper to create and advance a case to ACCEPTED status."""
    payload = {
        "chiefComplaint": f"Acute consultation for Stage 2C test ({key_suffix})",
        "duration": "2 days",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_2c_{key_suffix}_{time.time()}",
    }
    res = client.post("/api/v1/cases", json=payload, headers={"Authorization": TOKEN_PATIENT})
    assert res.status_code == 201
    case_id = res.json()["caseId"]

    sub_res = client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT})
    assert sub_res.status_code == 200

    match_res = client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT})
    assert match_res.status_code == 200

    accept_res = client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": doctor_token})
    assert accept_res.status_code == 200
    assert accept_res.json()["status"] == CaseStatus.ACCEPTED.value
    return case_id


def _advance_to_in_consultation(case_id: str, doctor_token: str = TOKEN_DOC_SHARMA) -> None:
    """Helper to record consultation notes, transitioning case from ACCEPTED to IN_CONSULTATION."""
    payload = {
        "clinicianNotes": "Clinical assessment completed. Patient stable.",
        "provisionalCareAdvice": "Hydration and symptomatic rest advised.",
        "isSimulated": True,
    }
    res = client.post(f"/api/v1/cases/{case_id}/consultation", json=payload, headers={"Authorization": doctor_token})
    assert res.status_code == 200


# ==============================================================================
# 1. Concurrent Duplicate Completion Requests
# ==============================================================================

def test_concurrent_duplicate_completion_requests():
    """
    Two simultaneous completion requests on the same case:
    - Exactly one must succeed (HTTP 200).
    - The other request must be rejected (HTTP 400 already completed, or HTTP 409 conflict).
    - Exactly one follow-up record is persisted.
    - Exactly one CASE_COMPLETED audit event is emitted.
    - Final case version is incremented exactly once for completion.
    """
    case_id = _create_accepted_case("concurrent_test")
    _advance_to_in_consultation(case_id)

    case_before = case_service.get_case(case_id)
    version_before = case_before.version

    followup_payload = {
        "required": True,
        "recommendedDate": "2026-10-22",
        "instructions": "Follow up directives for concurrent race verification.",
    }

    def _do_complete():
        return client.post(
            f"/api/v1/cases/{case_id}/complete",
            json=followup_payload,
            headers={"Authorization": TOKEN_DOC_SHARMA},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_do_complete)
        f2 = executor.submit(_do_complete)
        r1 = f1.result()
        r2 = f2.result()

    statuses = [r1.status_code, r2.status_code]
    assert 200 in statuses, f"Expected at least one 200 OK, got {statuses}"
    # The loser should receive HTTP 400 (case already terminal COMPLETED) or 409 (conflict)
    other_code = r2.status_code if r1.status_code == 200 else r1.status_code
    assert other_code in (400, 409), f"Expected loser to be 400 or 409, got {other_code}"

    # Assert final persisted state
    final_case = case_service.get_case(case_id)
    assert final_case.status == CaseStatus.COMPLETED
    assert final_case.completedAt is not None
    assert final_case.version == version_before + 1

    # Follow-up persisted exactly once
    db = get_firestore_client()
    followup_snap = db.collection("follow_ups").document(case_id).get()
    assert followup_snap.exists
    f_data = followup_snap.to_dict()
    assert f_data["caseId"] == case_id
    assert f_data["status"] == "scheduled"
    assert f_data["recommendedDate"] == "2026-10-22"

    # Clinician released to available
    clin = clinician_service.get_clinician("demo_doc_sharma")
    assert clin.availability == ClinicianAvailability.AVAILABLE
    assert clin.currentCaseId is None

    # Audit trail: exactly ONE CASE_COMPLETED event
    events = audit_service.get_case_events(case_id)
    completed_events = [e for e in events if e.eventType == AuditEventType.CASE_COMPLETED]
    assert len(completed_events) == 1, f"Expected exactly 1 CASE_COMPLETED event, got {len(completed_events)}"


# ==============================================================================
# 2. Repeated Completion After Success (Idempotent / Deterministic Rejection)
# ==============================================================================

def test_repeated_completion_after_success():
    """Sequential duplicate completion request returns HTTP 400 without state mutation."""
    case_id = _create_accepted_case("repeated_test")
    _advance_to_in_consultation(case_id)

    payload = {
        "required": False,
        "recommendedDate": "2026-10-25",
        "instructions": "Initial follow up instructions.",
    }
    res1 = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=payload,
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res1.status_code == 200
    case_v1 = case_service.get_case(case_id)

    # Second call with different payload must fail deterministically
    payload2 = {
        "required": True,
        "recommendedDate": "2026-11-01",
        "instructions": "Overriding instructions should NOT be accepted.",
    }
    res2 = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=payload2,
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res2.status_code == 400
    assert "already in terminal completed" in res2.json()["detail"].lower()

    # Case state unchanged
    case_v2 = case_service.get_case(case_id)
    assert case_v2.status == CaseStatus.COMPLETED
    assert case_v2.version == case_v1.version
    assert case_v2.updatedAt == case_v1.updatedAt

    # Follow-up record unchanged
    followup = consultation_service.get_follow_up(case_id)
    assert followup.required is False
    assert followup.recommendedDate == "2026-10-25"
    assert "Initial follow up" in followup.instructions

    # Exactly 1 CASE_COMPLETED event
    events = audit_service.get_case_events(case_id)
    completed_events = [e for e in events if e.eventType == AuditEventType.CASE_COMPLETED]
    assert len(completed_events) == 1


# ==============================================================================
# 3. Transactional Failure & Rollback Tests
# ==============================================================================

def test_failure_while_saving_followup_rolls_back():
    """
    Simulated failure saving follow-up record inside transaction:
    - Entire transaction must abort and roll back.
    - Case must NOT be marked COMPLETED.
    - Follow-up document must NOT be created.
    - Clinician must NOT be released.
    - Zero CASE_COMPLETED audit events emitted.
    """
    case_id = _create_accepted_case("fail_followup")
    _advance_to_in_consultation(case_id)

    case_before = case_service.get_case(case_id)
    clin_before = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_before.availability == ClinicianAvailability.BUSY

    # Monkeypatch FakeTransaction.set to fail when writing follow_ups
    original_set = FakeTransaction.set

    def _failing_set(self, doc_ref, data, merge=False):
        if "follow_ups" in doc_ref.path:
            raise RuntimeError("Database I/O failure persisting follow-up document")
        return original_set(self, doc_ref, data, merge=merge)

    FakeTransaction.set = _failing_set
    try:
        payload = {
            "required": True,
            "recommendedDate": "2026-10-20",
            "instructions": "Test instructions",
        }
        res = client.post(
            f"/api/v1/cases/{case_id}/complete",
            json=payload,
            headers={"Authorization": TOKEN_DOC_SHARMA},
        )
        assert res.status_code == 500
    finally:
        FakeTransaction.set = original_set

    # Assert complete rollback in Firestore
    case_after = case_service.get_case(case_id)
    assert case_after.status == CaseStatus.IN_CONSULTATION
    assert case_after.completedAt is None
    assert case_after.version == case_before.version

    # Follow-up does not exist
    assert consultation_service.get_follow_up(case_id) is None

    # Clinician is still busy
    clin_after = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_after.availability == ClinicianAvailability.BUSY
    assert clin_after.currentCaseId == case_id

    # No CASE_COMPLETED audit event
    events = audit_service.get_case_events(case_id)
    assert not any(e.eventType == AuditEventType.CASE_COMPLETED for e in events)


def test_failure_while_updating_case_status_rolls_back():
    """
    Simulated failure updating case document inside transaction:
    - Follow-up must NOT remain orphaned.
    - Case status must NOT be updated.
    - Clinician must NOT be released.
    - Zero CASE_COMPLETED audit events emitted.
    """
    case_id = _create_accepted_case("fail_case_status")
    _advance_to_in_consultation(case_id)

    original_update = FakeTransaction.update

    def _failing_update(self, doc_ref, data):
        if f"cases/{case_id}" in doc_ref.path:
            raise RuntimeError("Database storage timeout updating case record")
        return original_update(self, doc_ref, data)

    FakeTransaction.update = _failing_update
    try:
        payload = {
            "required": True,
            "recommendedDate": "2026-10-20",
            "instructions": "Test instructions",
        }
        res = client.post(
            f"/api/v1/cases/{case_id}/complete",
            json=payload,
            headers={"Authorization": TOKEN_DOC_SHARMA},
        )
        assert res.status_code == 500
    finally:
        FakeTransaction.update = original_update

    # Assert rollback
    case_after = case_service.get_case(case_id)
    assert case_after.status == CaseStatus.IN_CONSULTATION
    assert consultation_service.get_follow_up(case_id) is None

    clin_after = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_after.availability == ClinicianAvailability.BUSY

    events = audit_service.get_case_events(case_id)
    assert not any(e.eventType == AuditEventType.CASE_COMPLETED for e in events)


def test_failure_while_releasing_clinician_rolls_back():
    """
    Simulated failure updating clinician record inside transaction:
    - Case must NOT transition to COMPLETED without atomic clinician release.
    - Follow-up must NOT be orphaned.
    - Zero CASE_COMPLETED audit events emitted.
    """
    case_id = _create_accepted_case("fail_clin_release")
    _advance_to_in_consultation(case_id)

    original_update = FakeTransaction.update

    def _failing_update(self, doc_ref, data):
        if "clinicians/demo_doc_sharma" in doc_ref.path:
            raise RuntimeError("Database error updating clinician availability")
        return original_update(self, doc_ref, data)

    FakeTransaction.update = _failing_update
    try:
        payload = {
            "required": True,
            "recommendedDate": "2026-10-20",
            "instructions": "Test instructions",
        }
        res = client.post(
            f"/api/v1/cases/{case_id}/complete",
            json=payload,
            headers={"Authorization": TOKEN_DOC_SHARMA},
        )
        assert res.status_code == 500
    finally:
        FakeTransaction.update = original_update

    # Assert rollback
    case_after = case_service.get_case(case_id)
    assert case_after.status == CaseStatus.IN_CONSULTATION
    assert consultation_service.get_follow_up(case_id) is None

    clin_after = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_after.availability == ClinicianAvailability.BUSY

    events = audit_service.get_case_events(case_id)
    assert not any(e.eventType == AuditEventType.CASE_COMPLETED for e in events)


# ==============================================================================
# 4. Multi-Case Clinician Retention Invariant
# ==============================================================================

def test_clinician_with_multiple_active_cases_not_released_until_all_completed():
    """
    Invariant: A clinician must not be released to AVAILABLE while they still have
    another active assigned case (ACCEPTED or IN_CONSULTATION).
    When the last active case is completed, availability is released to AVAILABLE.
    """
    # 1. Setup Case A
    case_a = _create_accepted_case("multi_case_a")
    _advance_to_in_consultation(case_a)

    # 2. Setup Case B and assign to the same clinician
    # Create and submit Case B
    payload_b = {
        "chiefComplaint": "Concurrent symptom evaluation for Multi-Case B",
        "duration": "1 day",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_2c_multi_b_{time.time()}",
    }
    res_b = client.post("/api/v1/cases", json=payload_b, headers={"Authorization": TOKEN_PATIENT_2})
    assert res_b.status_code == 201
    case_b = res_b.json()["caseId"]
    client.post(f"/api/v1/cases/{case_b}/submit", headers={"Authorization": TOKEN_PATIENT_2})

    # Simulate admin or emergency assigning Case B to demo_doc_sharma
    db = get_firestore_client()
    db.collection("cases").document(case_b).update({
        "status": CaseStatus.IN_CONSULTATION.value,
        "assignedClinicianId": "demo_doc_sharma",
    })

    # Clinician is busy with both cases
    clin = clinician_service.get_clinician("demo_doc_sharma")
    assert clin.availability == ClinicianAvailability.BUSY

    # 3. Complete Case A
    res_comp_a = client.post(
        f"/api/v1/cases/{case_a}/complete",
        json={
            "required": True,
            "recommendedDate": "2026-10-28",
            "instructions": "Follow up for Case A",
        },
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res_comp_a.status_code == 200

    # Case A is completed
    assert case_service.get_case(case_a).status == CaseStatus.COMPLETED
    assert consultation_service.get_follow_up(case_a) is not None

    # CRITICAL INVARIANT: Clinician is NOT released because Case B is still active!
    clin_after_a = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_after_a.availability == ClinicianAvailability.BUSY, (
        "Clinician was prematurely released to AVAILABLE while Case B was still active!"
    )

    # Audit event reflects clinicianReleased: False
    events_a = audit_service.get_case_events(case_a)
    event_comp_a = next(e for e in events_a if e.eventType == AuditEventType.CASE_COMPLETED)
    assert event_comp_a.details.get("clinicianReleased") is False

    # 4. Now complete Case B
    res_comp_b = client.post(
        f"/api/v1/cases/{case_b}/complete",
        json={
            "required": False,
            "recommendedDate": "2026-10-30",
            "instructions": "Follow up for Case B",
        },
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res_comp_b.status_code == 200
    assert case_service.get_case(case_b).status == CaseStatus.COMPLETED

    # NOW Clinician IS released because all assigned active cases are complete!
    clin_after_b = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_after_b.availability == ClinicianAvailability.AVAILABLE
    assert clin_after_b.currentCaseId is None

    events_b = audit_service.get_case_events(case_b)
    event_comp_b = next(e for e in events_b if e.eventType == AuditEventType.CASE_COMPLETED)
    assert event_comp_b.details.get("clinicianReleased") is True


# ==============================================================================
# 5. Role and Assignment Authorization Tests
# ==============================================================================

def test_unassigned_clinician_cannot_complete_case():
    """Verified clinician who is not assigned to the case receives HTTP 403 Forbidden."""
    case_id = _create_accepted_case("unassigned_test")
    _advance_to_in_consultation(case_id)

    payload = {
        "required": True,
        "recommendedDate": "2026-10-20",
        "instructions": "Attempted completion by unassigned doctor",
    }
    # TOKEN_DOC_PATIL is verified, but not assigned to case_id (assigned to demo_doc_sharma)
    res = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=payload,
        headers={"Authorization": TOKEN_DOC_PATIL},
    )
    assert res.status_code == 403
    assert "not assigned" in res.json()["detail"].lower()

    # Case remains in consultation
    assert case_service.get_case(case_id).status == CaseStatus.IN_CONSULTATION
    assert consultation_service.get_follow_up(case_id) is None


def test_unverified_clinician_cannot_complete_case():
    """Unverified clinician caller receives HTTP 403 Forbidden."""
    case_id = _create_accepted_case("unverified_test")
    _advance_to_in_consultation(case_id)

    payload = {
        "required": True,
        "recommendedDate": "2026-10-20",
        "instructions": "Attempted completion by unverified doctor",
    }
    res = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=payload,
        headers={"Authorization": TOKEN_DOC_PENDING},
    )
    assert res.status_code == 403
    assert "verified clinicians" in res.json()["detail"].lower()


def test_patient_cannot_complete_case():
    """Patient caller receives HTTP 403 Forbidden."""
    case_id = _create_accepted_case("patient_comp_test")
    _advance_to_in_consultation(case_id)

    payload = {
        "required": False,
        "recommendedDate": "2026-10-20",
        "instructions": "Patient trying to complete their own case",
    }
    res = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=payload,
        headers={"Authorization": TOKEN_PATIENT},
    )
    assert res.status_code == 403
    assert "clinician or admin role required" in res.json()["detail"].lower()


def test_admin_can_complete_case():
    """Authorized administrator can finalize case coordination and release assigned clinician."""
    case_id = _create_accepted_case("admin_complete_test")
    _advance_to_in_consultation(case_id)

    payload = {
        "required": True,
        "recommendedDate": "2026-10-25",
        "instructions": "Administrative closure and follow-up directive",
    }
    res = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=payload,
        headers={"Authorization": TOKEN_ADMIN},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["case"]["status"] == CaseStatus.COMPLETED.value
    assert data["followUp"]["status"] == "scheduled"
    assert data["followUp"]["clinicianId"] == "demo_doc_sharma"

    # Assigned clinician is released
    clin = clinician_service.get_clinician("demo_doc_sharma")
    assert clin.availability == ClinicianAvailability.AVAILABLE
    assert clin.currentCaseId is None

    # Audit event logged with admin actor
    events = audit_service.get_case_events(case_id)
    comp_event = next(e for e in events if e.eventType == AuditEventType.CASE_COMPLETED)
    assert comp_event.actorRole == "admin"


# ==============================================================================
# 6. Audit Trail & Recovery / Retry Tests
# ==============================================================================

def test_audit_event_logged_only_on_success():
    """Audit event CASE_COMPLETED is never emitted if completion is rejected or fails."""
    # Attempting to complete a DRAFT case directly
    payload = {
        "chiefComplaint": "Draft case",
        "duration": "1 day",
        "requestedUrgency": "routine",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_draft_{time.time()}",
    }
    res_create = client.post("/api/v1/cases", json=payload, headers={"Authorization": TOKEN_PATIENT})
    draft_id = res_create.json()["caseId"]

    res_fail = client.post(
        f"/api/v1/cases/{draft_id}/complete",
        json={"required": False, "recommendedDate": "2026-10-20", "instructions": "Valid follow-up instructions string."},
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res_fail.status_code in (400, 403)

    events = audit_service.get_case_events(draft_id)
    assert not any(e.eventType == AuditEventType.CASE_COMPLETED for e in events)


def test_retry_after_transient_failure_succeeds():
    """
    Simulated transient commit failure followed by a clean retry:
    - First attempt fails and leaves zero side-effects.
    - Second attempt succeeds cleanly (HTTP 200).
    - Final state is 100% consistent.
    """
    case_id = _create_accepted_case("retry_transient")
    _advance_to_in_consultation(case_id)

    fail_counter = {"attempts": 0}
    original_commit = FakeTransaction.commit

    def _failing_first_commit(self):
        if fail_counter["attempts"] == 0:
            fail_counter["attempts"] += 1
            raise RuntimeError("Transient network abort during transaction commit")
        return original_commit(self)

    FakeTransaction.commit = _failing_first_commit
    payload = {
        "required": True,
        "recommendedDate": "2026-10-22",
        "instructions": "Instructions for retry recovery verification.",
    }

    try:
        # Attempt 1: Fails
        res1 = client.post(
            f"/api/v1/cases/{case_id}/complete",
            json=payload,
            headers={"Authorization": TOKEN_DOC_SHARMA},
        )
        assert res1.status_code == 500
        assert case_service.get_case(case_id).status == CaseStatus.IN_CONSULTATION

        # Attempt 2: Retry succeeds
        res2 = client.post(
            f"/api/v1/cases/{case_id}/complete",
            json=payload,
            headers={"Authorization": TOKEN_DOC_SHARMA},
        )
        assert res2.status_code == 200
    finally:
        FakeTransaction.commit = original_commit

    # State after successful retry
    final_case = case_service.get_case(case_id)
    assert final_case.status == CaseStatus.COMPLETED
    assert consultation_service.get_follow_up(case_id) is not None

    clin = clinician_service.get_clinician("demo_doc_sharma")
    assert clin.availability == ClinicianAvailability.AVAILABLE

    events = audit_service.get_case_events(case_id)
    comp_events = [e for e in events if e.eventType == AuditEventType.CASE_COMPLETED]
    assert len(comp_events) == 1


# ==============================================================================
# 7. Stage 2C.2: Transaction Races, Atomic Audit & Availability Regression Tests
# ==============================================================================

def test_completion_retry_after_clinician_doc_change():
    """
    Completion transaction retry after another operation changes the clinician document:
    - Attempt 0 simulates a concurrent modification on clinicians/demo_doc_sharma.
    - Transaction detects optimistic concurrency conflict on the clinician doc.
    - Transaction automatically retries via @firestore_transactional.
    - Retry succeeds, final case is COMPLETED, clinician is released.
    - Exactly ONE deterministic audit document exists in Firestore and audit service.
    """
    case_id = _create_accepted_case("tx_retry_clin")
    _advance_to_in_consultation(case_id)

    db = get_firestore_client()
    conflict_injected = {"done": False}
    original_get = FakeTransaction.get

    def _get_with_clinician_conflict(self, doc_ref):
        snap = original_get(self, doc_ref)
        if doc_ref.path == "clinicians/demo_doc_sharma" and not conflict_injected["done"]:
            conflict_injected["done"] = True
            # Simulate a concurrent writer modifying the clinician document
            with db._lock:
                db._store["clinicians/demo_doc_sharma"]["updatedAt"] = "2026-10-11T12:00:00Z"
                db._versions["clinicians/demo_doc_sharma"] = db._versions.get("clinicians/demo_doc_sharma", 0) + 1
        return snap

    FakeTransaction.get = _get_with_clinician_conflict
    payload = {
        "required": True,
        "recommendedDate": "2026-10-25",
        "instructions": "Follow-up instructions after simulated clinician doc concurrency retry.",
    }

    try:
        res = client.post(
            f"/api/v1/cases/{case_id}/complete",
            json=payload,
            headers={"Authorization": TOKEN_DOC_SHARMA},
        )
        assert res.status_code == 200
        assert conflict_injected["done"] is True
    finally:
        FakeTransaction.get = original_get

    # Verify final persisted state
    final_case = case_service.get_case(case_id)
    assert final_case.status == CaseStatus.COMPLETED
    assert consultation_service.get_follow_up(case_id) is not None

    clin = clinician_service.get_clinician("demo_doc_sharma")
    assert clin.availability == ClinicianAvailability.AVAILABLE
    assert clin.currentCaseId is None

    # Atomic audit document verification
    audit_snap = db.collection("audit_events").document(f"audit_completed_{case_id}").get()
    assert audit_snap.exists
    audit_data = audit_snap.to_dict()
    assert audit_data["eventType"] == AuditEventType.CASE_COMPLETED.value
    assert audit_data["caseId"] == case_id
    assert audit_data["details"]["clinicianReleased"] is True

    events = audit_service.get_case_events(case_id)
    comp_events = [e for e in events if e.eventType == AuditEventType.CASE_COMPLETED]
    assert len(comp_events) == 1


def test_concurrent_acceptance_during_completion_preserves_new_assignment():
    """
    Concurrent acceptance of another case while a completion request is in progress:
    - Clinician Sharma has Case A in IN_CONSULTATION.
    - Case B is in MATCHING status.
    - Right before completion of Case A writes to clinician doc, Case B is accepted by Clinician Sharma.
    - Completion of Case A must NOT overwrite Clinician Sharma's new assignment (Case B).
    - Case A is completed, but Clinician Sharma remains BUSY with currentCaseId == case_b.
    """
    case_a = _create_accepted_case("comp_race_a")
    _advance_to_in_consultation(case_a)

    # Setup Case B for Patient 2
    payload_b = {
        "chiefComplaint": "Symptom check for concurrent acceptance race test",
        "duration": "1 day",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_race_b_{time.time()}",
    }
    res_b = client.post("/api/v1/cases", json=payload_b, headers={"Authorization": TOKEN_PATIENT_2})
    assert res_b.status_code == 201
    case_b = res_b.json()["caseId"]
    client.post(f"/api/v1/cases/{case_b}/submit", headers={"Authorization": TOKEN_PATIENT_2})
    client.post(f"/api/v1/cases/{case_b}/matching", headers={"Authorization": TOKEN_PATIENT_2})

    db = get_firestore_client()
    acceptance_injected = {"done": False}
    original_get = FakeTransaction.get

    def _get_with_concurrent_accept(self, doc_ref):
        snap = original_get(self, doc_ref)
        if doc_ref.path == f"cases/{case_a}" and not acceptance_injected["done"]:
            acceptance_injected["done"] = True
            # Concurrently accept Case B for Clinician Sharma
            db._store["clinicians/demo_doc_sharma"]["availability"] = "available"
            db._store["clinicians/demo_doc_sharma"]["currentCaseId"] = None
            db._versions["clinicians/demo_doc_sharma"] = db._versions.get("clinicians/demo_doc_sharma", 0) + 1
            case_service.accept_case_atomic(case_b, "demo_doc_sharma")
        return snap

    FakeTransaction.get = _get_with_concurrent_accept
    payload_comp = {
        "required": True,
        "recommendedDate": "2026-10-30",
        "instructions": "Completed Case A instructions",
    }

    try:
        res = client.post(
            f"/api/v1/cases/{case_a}/complete",
            json=payload_comp,
            headers={"Authorization": TOKEN_DOC_SHARMA},
        )
        assert res.status_code == 200
        assert acceptance_injected["done"] is True
    finally:
        FakeTransaction.get = original_get

    # Invariants:
    # 1. Case A is COMPLETED
    assert case_service.get_case(case_a).status == CaseStatus.COMPLETED
    assert consultation_service.get_follow_up(case_a) is not None

    # 2. Case B remains ACCEPTED with demo_doc_sharma
    case_b_record = case_service.get_case(case_b)
    assert case_b_record.status == CaseStatus.ACCEPTED
    assert case_b_record.assignedClinicianId == "demo_doc_sharma"

    # 3. Clinician Sharma is STILL BUSY and assigned to Case B (NOT cleared to None/available!)
    clin = clinician_service.get_clinician("demo_doc_sharma")
    assert clin.availability == ClinicianAvailability.BUSY
    assert clin.currentCaseId == case_b

    # 4. Case A audit event indicates clinician was not released
    audit_snap = db.collection("audit_events").document(f"audit_completed_{case_a}").get()
    assert audit_snap.exists
    assert audit_snap.to_dict()["details"]["clinicianReleased"] is False


def test_completion_never_clears_another_cases_current_case_id():
    """
    Ensuring completion never clears another case's currentCaseId:
    - Clinician Sharma's profile has currentCaseId = 'case_concurrent_assigned'.
    - Case A is completed (e.g. by admin or doctor).
    - Completion of Case A must NEVER clear currentCaseId to None.
    """
    case_id = _create_accepted_case("never_clear_other")
    _advance_to_in_consultation(case_id)

    db = get_firestore_client()
    # Clinician's currentCaseId is manually set to a different active case
    db.collection("clinicians").document("demo_doc_sharma").update({
        "currentCaseId": "case_concurrent_assigned",
        "availability": "busy",
    })

    payload = {
        "required": False,
        "recommendedDate": "2026-10-27",
        "instructions": "Standard follow-up instructions",
    }
    res = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=payload,
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res.status_code == 200

    # Case A is completed
    assert case_service.get_case(case_id).status == CaseStatus.COMPLETED

    # Clinician Sharma's currentCaseId remains 'case_concurrent_assigned'
    clin = clinician_service.get_clinician("demo_doc_sharma")
    assert clin.currentCaseId == "case_concurrent_assigned"
    assert clin.availability == ClinicianAvailability.BUSY


def test_update_availability_cannot_make_clinician_available_while_active_assignment_exists():
    """
    update_availability cannot make a clinician available while an active assignment exists:
    - Clinician Sharma has Case A in IN_CONSULTATION.
    - Calling PATCH /clinicians/{id}/availability to 'available' returns HTTP 400.
    - Persisted state remains BUSY with currentCaseId == case_a.
    - Completing Case A allows setting availability to 'available'.
    """
    case_id = _create_accepted_case("avail_lock")
    _advance_to_in_consultation(case_id)

    clin = clinician_service.get_clinician("demo_doc_sharma")
    assert clin.availability == ClinicianAvailability.BUSY
    assert clin.currentCaseId == case_id

    # 1. Attempt to set available while active assignment exists -> HTTP 400
    res_bad = client.patch(
        "/api/v1/clinicians/demo_doc_sharma/availability",
        json={"availability": "available"},
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res_bad.status_code == 400
    assert "Cannot set clinician 'demo_doc_sharma' to AVAILABLE while assigned to active case" in res_bad.json()["detail"]

    # Invariant: State is preserved
    clin_check = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_check.availability == ClinicianAvailability.BUSY
    assert clin_check.currentCaseId == case_id

    # 2. Attempt to clear currentCaseId via availability update while active -> Preserved
    res_busy_none = client.patch(
        "/api/v1/clinicians/demo_doc_sharma/availability",
        json={"availability": "busy", "currentCaseId": None},
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res_busy_none.status_code == 200
    clin_check2 = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_check2.currentCaseId == case_id, "Active case assignment was improperly cleared!"

    # 3. Complete the case
    res_comp = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json={"required": False, "recommendedDate": "2026-10-31", "instructions": "Final closure"},
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res_comp.status_code == 200

    # 4. Now updating availability to available succeeds
    res_ok = client.patch(
        "/api/v1/clinicians/demo_doc_sharma/availability",
        json={"availability": "available"},
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res_ok.status_code == 200
    clin_final = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_final.availability == ClinicianAvailability.AVAILABLE
    assert clin_final.currentCaseId is None


def test_failed_completion_transaction_creates_neither_completion_nor_audit_records():
    """
    Failed completion transactions create neither completion nor audit records:
    - Inject commit failure into completion transaction.
    - Assert that transaction aborts cleanly.
    - Case remains IN_CONSULTATION, follow-up does not exist, and audit_events doc does not exist.
    """
    case_id = _create_accepted_case("tx_abort_clean")
    _advance_to_in_consultation(case_id)

    db = get_firestore_client()
    original_commit = FakeTransaction.commit

    def _always_fail_commit(self):
        raise RuntimeError("Simulated unexpected transaction commit abort")

    FakeTransaction.commit = _always_fail_commit
    payload = {
        "required": True,
        "recommendedDate": "2026-10-22",
        "instructions": "Will fail and abort atomically",
    }

    try:
        res = client.post(
            f"/api/v1/cases/{case_id}/complete",
            json=payload,
            headers={"Authorization": TOKEN_DOC_SHARMA},
        )
        assert res.status_code == 500
    finally:
        FakeTransaction.commit = original_commit

    # Assert 100% atomic rollback across all collections:
    # 1. Case remains IN_CONSULTATION
    persisted_case = case_service.get_case(case_id)
    assert persisted_case.status == CaseStatus.IN_CONSULTATION

    # 2. Follow-up does not exist
    followup_snap = db.collection("follow_ups").document(case_id).get()
    assert not followup_snap.exists

    # 3. Clinician remains BUSY
    clin = clinician_service.get_clinician("demo_doc_sharma")
    assert clin.availability == ClinicianAvailability.BUSY
    assert clin.currentCaseId == case_id

    # 4. Audit document does NOT exist in Firestore
    audit_snap = db.collection("audit_events").document(f"audit_completed_{case_id}").get()
    assert not audit_snap.exists

    # 5. Audit service in-memory query has zero CASE_COMPLETED events
    events = audit_service.get_case_events(case_id)
    assert not any(e.eventType == AuditEventType.CASE_COMPLETED for e in events)


def test_audit_write_failure_aborts_all_state():
    """
    Atomic audit event write failure injection:
    - If the staged audit write fails, the entire transaction rolls back.
    - Neither the case status transition, follow-up record, nor clinician release are committed.
    """
    case_id = _create_accepted_case("audit_write_fail")
    _advance_to_in_consultation(case_id)

    db = get_firestore_client()
    original_set = FakeTransaction.set

    def _fail_on_audit_set(self, doc_ref, data, merge=False):
        if doc_ref.path.startswith("audit_events/"):
            raise RuntimeError("Simulated disk error staging audit event")
        return original_set(self, doc_ref, data, merge=merge)

    FakeTransaction.set = _fail_on_audit_set
    payload = {
        "required": True,
        "recommendedDate": "2026-10-25",
        "instructions": "Instructions that trigger audit write failure injection",
    }

    try:
        res = client.post(
            f"/api/v1/cases/{case_id}/complete",
            json=payload,
            headers={"Authorization": TOKEN_DOC_SHARMA},
        )
        assert res.status_code == 500
    finally:
        FakeTransaction.set = original_set

    # Assert no partial commit:
    # Case status unchanged
    assert case_service.get_case(case_id).status == CaseStatus.IN_CONSULTATION
    # Follow-up does not exist
    assert not db.collection("follow_ups").document(case_id).get().exists
    # Clinician is still busy
    assert clinician_service.get_clinician("demo_doc_sharma").availability == ClinicianAvailability.BUSY
    # Audit event does not exist
    assert not db.collection("audit_events").document(f"audit_completed_{case_id}").get().exists


def test_successful_completion_creates_exactly_one_deterministic_audit_event():
    """
    Successful completion creates exactly one deterministic audit event:
    - Assert persisted Firestore document audit_events/audit_completed_{case_id}.
    - Repeated completion calls (rejected with HTTP 400) do NOT duplicate the audit document.
    """
    case_id = _create_accepted_case("single_audit")
    _advance_to_in_consultation(case_id)

    db = get_firestore_client()
    payload = {
        "required": True,
        "recommendedDate": "2026-10-26",
        "instructions": "Single audit event test instructions",
    }

    res1 = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=payload,
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res1.status_code == 200

    # 1. Assert persisted in Firestore audit_events collection
    audit_snap = db.collection("audit_events").document(f"audit_completed_{case_id}").get()
    assert audit_snap.exists
    audit_dict = audit_snap.to_dict()
    assert audit_dict["eventId"] == f"audit_completed_{case_id}"
    assert audit_dict["eventType"] == AuditEventType.CASE_COMPLETED.value
    assert audit_dict["actorId"] == "demo_doc_sharma"

    # 2. Repeat completion call -> rejected with HTTP 400
    res2 = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json=payload,
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res2.status_code == 400

    # 3. Assert exactly 1 CASE_COMPLETED audit event in both Firestore and audit service
    case_audit_events = audit_service.get_case_events(case_id)
    comp_events = [e for e in case_audit_events if e.eventType == AuditEventType.CASE_COMPLETED]
    assert len(comp_events) == 1


def test_seed_default_clinicians_preserves_active_case_assignments():
    """
    seed_default_clinicians must preserve active assignments:
    - A clinician with an active assignment retains BUSY and currentCaseId when re-seeded.
    """
    case_id = _create_accepted_case("seed_preserve")
    _advance_to_in_consultation(case_id)

    clin_before = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_before.availability == ClinicianAvailability.BUSY
    assert clin_before.currentCaseId == case_id

    # Admin calls seed endpoint
    res = client.post("/api/v1/clinicians/seed", headers={"Authorization": TOKEN_ADMIN})
    assert res.status_code == 200

    # Invariant: Clinician Sharma's active assignment was preserved
    clin_after = clinician_service.get_clinician("demo_doc_sharma")
    assert clin_after.availability == ClinicianAvailability.BUSY
    assert clin_after.currentCaseId == case_id

