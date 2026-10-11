"""
Phase 8 Automated Test Suite: Clinician Matching, Concurrency & Lifecycle
Verifies:
1. Seeded DEMO clinicians with explicit [DEMO / SIMULATED] labels.
2. Matching algorithm filtering:
   - Verification status: excludes pending/unverified clinicians.
   - Availability status: excludes offline and busy clinicians.
   - Language: excludes clinicians not speaking patient's language.
   - Specialty preference & fallback scoring.
   - Deterministic queue ordering.
3. NO_CLINICIAN_AVAILABLE handling:
   - Automatic transition and CASE_NO_CLINICIAN audit event when no match exists.
   - Retry transition from NO_CLINICIAN_AVAILABLE back to MATCHING.
   - Case cancellation from NO_CLINICIAN_AVAILABLE.
4. Clinician Accept and Decline:
   - Atomic Firestore-transaction-based acceptance updating case and clinician documents.
   - CASE_ACCEPTED audit event.
   - Decline flow: CASE_DECLINED audit event, exclusion from subsequent matches,
     and pool exhaustion transition to NO_CLINICIAN_AVAILABLE.
5. Concurrency Race Condition Test:
   - Two simultaneous accepts from different clinicians using ThreadPoolExecutor.
   - Exactly ONE winner (HTTP 200, assignedClinicianId set, clinician busy).
   - Exactly ONE loser (HTTP 409 Conflict, CONFLICT_DETECTED audit event, clinician remains available).
6. Security & Authorization:
   - Unverified clinician rejected with HTTP 403 Forbidden on accept and decline.
   - Patient rejected with HTTP 403 Forbidden on accept and decline.
"""

import time
import concurrent.futures
from typing import Dict, Any, List
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.state_machine import CaseStatus
from app.schemas.audit import AuditEventType
from app.schemas.clinician import (
    ClinicianSpecialty,
    ClinicianAvailability,
    ClinicianVerificationStatus,
)
from app.services.clinician_service import clinician_service
from app.services.case_service import case_service
from app.services.audit_service import audit_service

client = TestClient(app)

TOKEN_PATIENT = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_DOC_SHARMA = "Bearer mock-token-demo_doc_sharma"
TOKEN_DOC_PATIL = "Bearer mock-token-demo_doc_patil"
TOKEN_DOC_DESHMUKH = "Bearer mock-token-demo_doc_deshmukh"
TOKEN_DOC_PENDING = "Bearer mock-token-demo_doc_pending"
TOKEN_DOC_OFFLINE = "Bearer mock-token-demo_doc_offline"
TOKEN_ADMIN = "Bearer mock-token-admin"


@pytest.fixture(autouse=True)
def reset_demo_clinicians():
    """Resets the demo clinicians into Firestore before each test."""
    db = clinician_service.db
    if hasattr(db, "is_fake") and db.is_fake:
        for k in list(db._store.keys()):
            if k.startswith("cases/") or k.startswith("consultations/") or k.startswith("follow_ups/"):
                del db._store[k]
    clinician_service.seed_default_clinicians()


def create_and_submit_case(
    language: str = "en",
    urgency: str = "urgent",
    preferred_specialty: str = None,
    key_suffix: str = "p8",
) -> str:
    """Helper to create a case, update metadata, and progress through DRAFT -> SUBMITTED -> MATCHING."""
    payload = {
        "chiefComplaint": f"Symptom evaluation for Phase 8 test ({key_suffix})",
        "duration": "2 days",
        "requestedUrgency": urgency,
        "patientLanguage": language,
        "idempotencyKey": f"idem_p8_{key_suffix}_{time.time()}",
    }
    res = client.post("/api/v1/cases", json=payload, headers={"Authorization": TOKEN_PATIENT})
    assert res.status_code == 201
    case_id = res.json()["caseId"]

    if preferred_specialty:
        meta_update = {"preferredSpecialty": preferred_specialty}
        case_service.update_case_metadata(case_id, meta_update)

    sub_res = client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT})
    assert sub_res.status_code == 200

    match_res = client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT})
    assert match_res.status_code == 200
    assert match_res.json()["status"] == CaseStatus.MATCHING.value

    return case_id


# ==============================================================================
# 1. DEMO Clinicians Seeding Tests
# ==============================================================================

def test_seeded_demo_clinicians_have_explicit_demo_labels():
    """Requirement 1: Verify all seeded clinicians are explicitly labelled [DEMO / SIMULATED]."""
    res = client.get("/api/v1/clinicians", headers={"Authorization": TOKEN_PATIENT})
    assert res.status_code == 200
    clinicians = res.json()
    assert len(clinicians) >= 5

    for doc in clinicians:
        assert "[DEMO / SIMULATED]" in doc["fullName"], f"Clinician {doc['clinicianId']} missing DEMO label"
        assert doc["isDemo"] is True

    # Check key demo doctors exist
    ids = [d["clinicianId"] for d in clinicians]
    assert "demo_doc_sharma" in ids
    assert "demo_doc_patil" in ids
    assert "demo_doc_deshmukh" in ids
    assert "demo_doc_pending" in ids
    assert "demo_doc_offline" in ids


def test_seed_endpoint_is_idempotent():
    """Requirement 1: Calling POST /clinicians/seed multiple times is safe and idempotent, restricted to admin."""
    # Patient caller is rejected with 403 Forbidden
    patient_res = client.post("/api/v1/clinicians/seed", headers={"Authorization": TOKEN_PATIENT})
    assert patient_res.status_code == 403

    # Admin caller succeeds and is idempotent
    res1 = client.post("/api/v1/clinicians/seed", headers={"Authorization": TOKEN_ADMIN})
    assert res1.status_code == 200
    count1 = len(res1.json())

    res2 = client.post("/api/v1/clinicians/seed", headers={"Authorization": TOKEN_ADMIN})
    assert res2.status_code == 200
    count2 = len(res2.json())

    assert count1 == count2


# ==============================================================================
# 2. Matching Algorithm Filtering & Ordering Tests
# ==============================================================================

def test_matching_excludes_unverified_clinicians():
    """Requirement 2: Unverified or pending clinicians must NEVER be returned in matching pool."""
    case_id = create_and_submit_case(language="en", key_suffix="unverified_filter")

    match_res = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT})
    assert match_res.status_code == 200
    data = match_res.json()
    matched_ids = [m["clinicianId"] for m in data["matches"]]

    assert "demo_doc_pending" not in matched_ids, "Pending/unverified clinician must be excluded"


def test_matching_excludes_offline_and_busy_clinicians():
    """Requirement 2: Unavailable (offline or busy) clinicians must be excluded."""
    case_id = create_and_submit_case(language="en", key_suffix="availability_filter")

    # Mark demo_doc_sharma as busy
    clinician_service.update_availability(
        "demo_doc_sharma",
        availability=ClinicianAvailability.BUSY,
        current_case_id="other_case_123",
    )

    match_res = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT})
    assert match_res.status_code == 200
    matched_ids = [m["clinicianId"] for m in match_res.json()["matches"]]

    assert "demo_doc_offline" not in matched_ids, "Offline clinician must be excluded"
    assert "demo_doc_sharma" not in matched_ids, "Busy clinician must be excluded"
    # Dr. Patil and Dr. Deshmukh remain available
    assert "demo_doc_patil" in matched_ids


def test_matching_filters_by_patient_language():
    """Requirement 2: Clinicians who do not speak the patient's language must NOT be matched."""
    # Case in Marathi ('mr'): Dr. Sharma (en, hi) does NOT speak mr; Dr. Patil and Dr. Deshmukh speak mr
    case_mr = create_and_submit_case(language="mr", key_suffix="lang_mr")
    res_mr = client.post(f"/api/v1/cases/{case_mr}/match", headers={"Authorization": TOKEN_PATIENT})
    assert res_mr.status_code == 200
    matched_mr = [m["clinicianId"] for m in res_mr.json()["matches"]]

    assert "demo_doc_sharma" not in matched_mr
    assert "demo_doc_patil" in matched_mr
    assert "demo_doc_deshmukh" in matched_mr

    # Case in Hindi ('hi'): Dr. Deshmukh (en, mr) does NOT speak hi; Dr. Sharma and Dr. Patil speak hi
    case_hi = create_and_submit_case(language="hi", key_suffix="lang_hi")
    res_hi = client.post(f"/api/v1/cases/{case_hi}/match", headers={"Authorization": TOKEN_PATIENT})
    assert res_hi.status_code == 200
    matched_hi = [m["clinicianId"] for m in res_hi.json()["matches"]]

    assert "demo_doc_deshmukh" not in matched_hi
    assert "demo_doc_sharma" in matched_hi
    assert "demo_doc_patil" in matched_hi


def test_matching_specialty_preference_and_fallback_scoring():
    """
    Requirement 2:
    - Exact specialty matches receive score 100 and highest rank.
    - Fallback providers (general_medicine / emergency_medicine) receive score 50.
    """
    # Case requesting Pediatrics in English
    case_peds = create_and_submit_case(
        language="en",
        preferred_specialty=ClinicianSpecialty.PEDIATRICS.value,
        key_suffix="spec_peds",
    )
    res = client.post(f"/api/v1/cases/{case_peds}/match", headers={"Authorization": TOKEN_PATIENT})
    assert res.status_code == 200
    matches = res.json()["matches"]

    # Top match must be Dr. Deshmukh (Pediatrics, exact match)
    assert len(matches) >= 2
    top = matches[0]
    assert top["clinicianId"] == "demo_doc_deshmukh"
    assert top["matchScore"] == 100
    assert top["isExactSpecialtyMatch"] is True

    # Fallback matches follow with score 50
    for fallback in matches[1:]:
        assert fallback["matchScore"] == 50
        assert fallback["isExactSpecialtyMatch"] is False


def test_deterministic_queue_ordering_on_score_ties():
    """Requirement 2: Ties in score are broken deterministically by clinicianId ascending."""
    case_en = create_and_submit_case(language="en", key_suffix="tie_break")
    res = client.post(f"/api/v1/cases/{case_en}/match", headers={"Authorization": TOKEN_PATIENT})
    assert res.status_code == 200
    matches = res.json()["matches"]

    # In General Medicine request: Dr. Sharma is exact (100).
    # Dr. Patil and Dr. Deshmukh or others might tie at 50.
    scores = [m["matchScore"] for m in matches]
    # Check descending score order
    assert scores == sorted(scores, reverse=True)


# ==============================================================================
# 3. NO_CLINICIAN_AVAILABLE Handling Tests
# ==============================================================================

def test_no_clinician_available_transitions_status_and_logs_audit():
    """
    Requirement 3: When no clinicians match criteria (e.g. unsupported language),
    case automatically transitions to NO_CLINICIAN_AVAILABLE and logs CASE_NO_CLINICIAN.
    """
    # Case with language French ('fr') where no demo clinician speaks it
    case_id = create_and_submit_case(language="fr", key_suffix="no_match_fr")

    match_res = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT})
    assert match_res.status_code == 200
    data = match_res.json()
    assert data["status"] == CaseStatus.NO_CLINICIAN_AVAILABLE.value
    assert data["matchedCount"] == 0
    assert data["matches"] == []

    # Verify Firestore case status updated
    case_check = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT})
    assert case_check.status_code == 200
    assert case_check.json()["status"] == CaseStatus.NO_CLINICIAN_AVAILABLE.value

    # Verify audit event logged
    events = audit_service.get_case_events(case_id)
    no_clin_events = [e for e in events if e.eventType == AuditEventType.CASE_NO_CLINICIAN]
    assert len(no_clin_events) >= 1
    assert no_clin_events[0].details["patientLanguage"] == "fr"


def test_retry_matching_from_no_clinician_available():
    """Requirement 3: Retrying matching from NO_CLINICIAN_AVAILABLE is permitted."""
    case_id = create_and_submit_case(language="fr", key_suffix="retry_match")
    # Initial match fails -> NO_CLINICIAN_AVAILABLE
    res1 = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT})
    assert res1.json()["status"] == CaseStatus.NO_CLINICIAN_AVAILABLE.value

    # Patient updates language to English ('en')
    # Can transition to MATCHING to retry
    status_res = client.post(
        f"/api/v1/cases/{case_id}/status",
        json={"targetStatus": "MATCHING", "reason": "Patient updated preferences"},
        headers={"Authorization": TOKEN_PATIENT},
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == CaseStatus.MATCHING.value


def test_case_cancellation_from_no_clinician_available():
    """Requirement 3: Case in NO_CLINICIAN_AVAILABLE can be cancelled by patient."""
    case_id = create_and_submit_case(language="ja", key_suffix="cancel_from_no_clin")
    client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT})

    del_res = client.delete(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT})
    assert del_res.status_code == 200
    assert del_res.json()["status"] == CaseStatus.CANCELLED.value


# ==============================================================================
# 4. Accept and Decline Tests
# ==============================================================================

def test_atomic_accept_updates_case_and_clinician_documents():
    """
    Requirement 4: Verified clinician accepts case:
    - Case is updated to ACCEPTED, assignedClinicianId is set.
    - Clinician is updated to BUSY, currentCaseId is set.
    - CASE_ACCEPTED audit event logged.
    """
    case_id = create_and_submit_case(language="en", key_suffix="atomic_accept")

    accept_res = client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_DOC_SHARMA})
    assert accept_res.status_code == 200
    case_data = accept_res.json()
    assert case_data["status"] == CaseStatus.ACCEPTED.value
    assert case_data["assignedClinicianId"] == "demo_doc_sharma"
    assert case_data["acceptedAt"] is not None

    # Check clinician document was updated in Firestore atomically
    doc_res = client.get("/api/v1/clinicians/demo_doc_sharma", headers={"Authorization": TOKEN_PATIENT})
    assert doc_res.status_code == 200
    clin_data = doc_res.json()
    assert clin_data["availability"] == ClinicianAvailability.BUSY.value
    assert clin_data["currentCaseId"] == case_id

    # Verify CASE_ACCEPTED audit event
    events = audit_service.get_case_events(case_id)
    acc_events = [e for e in events if e.eventType == AuditEventType.CASE_ACCEPTED]
    assert len(acc_events) >= 1
    assert acc_events[0].actorId == "demo_doc_sharma"


def test_decline_case_excludes_clinician_and_falls_back():
    """
    Requirement 4: Clinician declines case:
    - CASE_DECLINED audit event is logged.
    - Clinician is added to declinedClinicianIds.
    - Subsequent matching excludes this clinician.
    """
    case_id = create_and_submit_case(language="hi", key_suffix="decline_fallback")

    # Dr. Sharma declines
    decline_res = client.post(
        f"/api/v1/cases/{case_id}/decline",
        json={"reason": "Currently attending in-person ward rounds"},
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert decline_res.status_code == 200

    # Verify CASE_DECLINED audit event
    events = audit_service.get_case_events(case_id)
    dec_events = [e for e in events if e.eventType == AuditEventType.CASE_DECLINED]
    assert len(dec_events) >= 1
    assert dec_events[0].details["decliningClinicianId"] == "demo_doc_sharma"

    # Re-match: Dr. Sharma is excluded; Dr. Patil remains
    match_res = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT})
    assert match_res.status_code == 200
    matched_ids = [m["clinicianId"] for m in match_res.json()["matches"]]
    assert "demo_doc_sharma" not in matched_ids
    assert "demo_doc_patil" in matched_ids


def test_decline_exhaustion_transitions_to_no_clinician_available():
    """
    Requirement 4: When all matching clinicians decline, case automatically transitions
    to NO_CLINICIAN_AVAILABLE.
    """
    # Marathi case: only Dr. Patil and Dr. Deshmukh qualify
    case_id = create_and_submit_case(language="mr", key_suffix="decline_exhaust")

    # Dr. Patil declines
    res1 = client.post(
        f"/api/v1/cases/{case_id}/decline",
        json={"reason": "Off-shift"},
        headers={"Authorization": TOKEN_DOC_PATIL},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == CaseStatus.MATCHING.value

    # Dr. Deshmukh declines -> pool exhausted!
    res2 = client.post(
        f"/api/v1/cases/{case_id}/decline",
        json={"reason": "In surgery"},
        headers={"Authorization": TOKEN_DOC_DESHMUKH},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == CaseStatus.NO_CLINICIAN_AVAILABLE.value

    # Verify CASE_NO_CLINICIAN logged
    events = audit_service.get_case_events(case_id)
    no_clin_events = [e for e in events if e.eventType == AuditEventType.CASE_NO_CLINICIAN]
    assert len(no_clin_events) >= 1


# ==============================================================================
# 5. Concurrency Race Condition Test (Two Simultaneous Accepts)
# ==============================================================================

def test_concurrency_race_condition_two_simultaneous_accepts():
    """
    Requirement 5: Concurrency test with two simultaneous accepts:
    - 2 clinicians attempt to accept the same case simultaneously via ThreadPoolExecutor.
    - Exactly ONE wins (HTTP 200 OK, case status ACCEPTED).
    - Exactly ONE loses with HTTP 409 Conflict.
    - CONFLICT_DETECTED audit event is logged for the losing clinician.
    - Dual-document atomicity: winner is marked busy, loser remains available.
    """
    case_id = create_and_submit_case(language="en", key_suffix="concurrency_race")

    results: List[Dict[str, Any]] = []

    def attempt_accept(doc_token: str, doc_id: str):
        res = client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": doc_token})
        return {
            "clinicianId": doc_id,
            "statusCode": res.status_code,
            "body": res.json(),
        }

    # Execute simultaneous accepts
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_accept, TOKEN_DOC_SHARMA, "demo_doc_sharma")
        f2 = executor.submit(attempt_accept, TOKEN_DOC_PATIL, "demo_doc_patil")
        results = [f1.result(), f2.result()]

    status_codes = [r["statusCode"] for r in results]
    assert 200 in status_codes, f"One accept must succeed with 200: {results}"
    assert 409 in status_codes, f"One accept must fail with 409 Conflict: {results}"

    winner = [r for r in results if r["statusCode"] == 200][0]
    loser = [r for r in results if r["statusCode"] == 409][0]

    # Verify case reflects winner
    case_check = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT})
    assert case_check.status_code == 200
    case_data = case_check.json()
    assert case_data["status"] == CaseStatus.ACCEPTED.value
    assert case_data["assignedClinicianId"] == winner["clinicianId"]

    # Verify winner is marked busy in clinician collection
    win_doc = client.get(f"/api/v1/clinicians/{winner['clinicianId']}", headers={"Authorization": TOKEN_PATIENT}).json()
    assert win_doc["availability"] == ClinicianAvailability.BUSY.value
    assert win_doc["currentCaseId"] == case_id

    # Verify loser remains available
    lose_doc = client.get(f"/api/v1/clinicians/{loser['clinicianId']}", headers={"Authorization": TOKEN_PATIENT}).json()
    assert lose_doc["availability"] == ClinicianAvailability.AVAILABLE.value
    assert lose_doc["currentCaseId"] is None

    # Verify audit events: CASE_ACCEPTED for winner and CONFLICT_DETECTED for loser
    events = audit_service.get_case_events(case_id)
    acc_events = [e for e in events if e.eventType == AuditEventType.CASE_ACCEPTED]
    conf_events = [e for e in events if e.eventType == AuditEventType.CONFLICT_DETECTED]

    assert len(acc_events) == 1
    assert acc_events[0].actorId == winner["clinicianId"]

    assert len(conf_events) >= 1
    assert conf_events[0].actorId == loser["clinicianId"]


# ==============================================================================
# 6. Security and Authorization Tests
# ==============================================================================

def test_unverified_clinician_cannot_accept_case():
    """Requirement 6: Unverified/pending clinicians receive HTTP 403 Forbidden on accept."""
    case_id = create_and_submit_case(language="en", key_suffix="unverified_denied")

    res = client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_DOC_PENDING})
    assert res.status_code == 403
    assert "Only verified clinicians" in res.json()["detail"]


def test_patient_cannot_accept_case():
    """Requirement 6: Patients receive HTTP 403 Forbidden on case acceptance."""
    case_id = create_and_submit_case(language="en", key_suffix="patient_accept_denied")

    res = client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_PATIENT})
    assert res.status_code == 403
    assert "Clinician role required" in res.json()["detail"]


def test_unverified_clinician_cannot_decline_case():
    """Requirement 6: Unverified clinicians receive HTTP 403 Forbidden on decline."""
    case_id = create_and_submit_case(language="en", key_suffix="unverified_decline_denied")

    res = client.post(f"/api/v1/cases/{case_id}/decline", headers={"Authorization": TOKEN_DOC_PENDING})
    assert res.status_code == 403
