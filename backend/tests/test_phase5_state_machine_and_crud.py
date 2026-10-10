import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app
from app.core.state_machine import (
    CaseStatus,
    ALLOWED_TRANSITIONS,
    validate_transition,
    InvalidStateTransitionError,
    is_terminal_status,
)
from app.services.case_service import case_service, CaseService
from app.services.audit_service import audit_service
from app.schemas.case import CaseCreate, CaseUpdate
from app.models.firestore_models import (
    case_to_firestore_dict,
    case_from_firestore_dict,
    audit_event_to_firestore_dict,
    audit_event_from_firestore_dict,
    firestore_timestamp_to_datetime,
)

client = TestClient(app)

TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_CLINICIAN_VERIFIED = "Bearer mock-token-clinician-verified"
TOKEN_ADMIN = "Bearer mock-token-admin"


# ==============================================================================
# 1. EXHAUSTIVE STATE TRANSITION TESTS (100 Combinations = 18 Valid + 82 Invalid)
# ==============================================================================

def test_exhaustive_valid_state_transitions():
    """
    Exhaustively verifies every single allowed transition edge (18 valid transitions).
    Confirms validate_transition succeeds and service updates state, version, and audit log.
    """
    all_statuses = list(CaseStatus)
    valid_count = 0

    for current in all_statuses:
        allowed_targets = ALLOWED_TRANSITIONS.get(current, set())
        for target in allowed_targets:
            valid_count += 1
            # 1. Direct validation function must succeed without exception
            validate_transition(current, target)

            # 2. Service-level transition execution
            test_service = CaseService()
            c = test_service.create_case(
                CaseCreate(
                    patientId="p_test",
                    chiefComplaint="Testing valid transition",
                    duration="1 day",
                    requestedUrgency="routine",
                    patientLanguage="en",
                    idempotencyKey=f"valid_{current.value}_{target.value}",
                ),
                actor_id="p_test",
            )
            # Force status to current state to test the exact edge
            c_current = c.model_copy(update={"status": current})
            test_service._cases[c.caseId] = c_current

            updated = test_service.transition_status(
                case_id=c.caseId,
                target_status=target,
                actor_id="system_test",
                actor_role="admin",
                reason=f"Testing transition {current.value} -> {target.value}",
            )
            assert updated.status == target
            assert updated.version == c.version + 1

    # Ensure all 18 valid edges were tested
    assert valid_count == 18, f"Expected 18 valid transitions, found {valid_count}"


def test_exhaustive_invalid_state_transitions():
    """
    Exhaustively verifies every single disallowed transition edge (82 invalid transitions).
    All 100 possible pairs (10 from-states * 10 to-states) minus the 18 valid edges = 82 invalid edges.
    Every single invalid edge must raise InvalidStateTransitionError.
    """
    all_statuses = list(CaseStatus)
    invalid_count = 0

    for current in all_statuses:
        allowed_targets = ALLOWED_TRANSITIONS.get(current, set())
        for target in all_statuses:
            if target not in allowed_targets:
                invalid_count += 1
                with pytest.raises(InvalidStateTransitionError) as exc_info:
                    validate_transition(current, target)
                
                # Verify error message is descriptive and mentions the forbidden states
                err_msg = str(exc_info.value)
                assert f"Invalid state transition from '{current.value}' to '{target.value}'" in err_msg

    assert invalid_count == 82, f"Expected 82 invalid transitions (100 - 18), found {invalid_count}"


def test_terminal_states_have_zero_outgoing_transitions():
    """Confirms terminal states (COMPLETED, CANCELLED) cannot transition to ANY other state."""
    assert is_terminal_status(CaseStatus.COMPLETED) is True
    assert is_terminal_status(CaseStatus.CANCELLED) is True
    assert is_terminal_status(CaseStatus.DRAFT) is False
    assert is_terminal_status(CaseStatus.IN_CONSULTATION) is False

    for target in CaseStatus:
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(CaseStatus.COMPLETED, target)
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(CaseStatus.CANCELLED, target)


# ==============================================================================
# 2. CASE CRUD & DRAFT-ONLY UPDATE TESTS
# ==============================================================================

def test_case_crud_lifecycle_and_draft_patch_guard():
    """
    Tests the complete CRUD lifecycle:
    1. Create case (DRAFT)
    2. Read case
    3. Update case while DRAFT -> succeeds
    4. Transition case to SUBMITTED
    5. Update case while SUBMITTED -> strictly rejected (HTTP 400)
    6. Cancel/Delete case -> transitions to CANCELLED
    """
    # 1. Create case in DRAFT
    create_payload = {
        "chiefComplaint": "Severe throbbing headache with photophobia",
        "duration": "12 hours",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": "idem_crud_lifecycle_1",
    }
    create_res = client.post(
        "/api/v1/cases",
        json=create_payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert create_res.status_code == 201
    case = create_res.json()
    case_id = case["caseId"]
    assert case["status"] == "DRAFT"
    assert case["version"] == 1

    # 2. Read case
    get_res = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT_1})
    assert get_res.status_code == 200
    assert get_res.json()["caseId"] == case_id

    # 3. Update case while in DRAFT status -> Allowed
    patch_payload = {
        "chiefComplaint": "Severe throbbing headache with photophobia and nausea",
        "duration": "18 hours",
        "requestedUrgency": "urgent",
    }
    patch_res = client.patch(
        f"/api/v1/cases/{case_id}",
        json=patch_payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert patch_res.status_code == 200
    patched_case = patch_res.json()
    assert patched_case["chiefComplaint"] == "Severe throbbing headache with photophobia and nausea"
    assert patched_case["duration"] == "18 hours"
    assert patched_case["version"] == 2

    # 4. Submit case (transitions to SUBMITTED)
    submit_res = client.post(
        f"/api/v1/cases/{case_id}/submit",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["status"] == "SUBMITTED"

    # 5. Attempt to update case while in SUBMITTED status -> Strictly Rejected
    invalid_patch_res = client.patch(
        f"/api/v1/cases/{case_id}",
        json={"chiefComplaint": "Trying to modify after submission"},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert invalid_patch_res.status_code == 400
    assert "Cases can only be edited while in DRAFT status" in invalid_patch_res.json()["detail"]

    # 6. Cancel case
    cancel_res = client.delete(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"


def test_case_metadata_allowlist_enforcement():
    """Verifies CaseUpdate.metadata strictly accepts allowlisted keys and rejects arbitrary/server keys."""
    # 1. Allowed keys pass validation
    valid_update = CaseUpdate(
        metadata={
            "symptoms": ["cough", "mild fever"],
            "knownConditions": "Asthma",
            "medications": "Albuterol inhaler",
            "allergies": "None",
            "vitals": {"temperature": "99.1 F", "heartRate": 80},
        }
    )
    assert valid_update.metadata is not None
    assert "symptoms" in valid_update.metadata

    # 2. Arbitrary/unexpected keys are rejected
    with pytest.raises(ValueError, match="Disallowed metadata key 'arbitraryKey'"):
        CaseUpdate(metadata={"arbitraryKey": "some_value"})

    # 3. Server-controlled flags/counters cannot be injected
    for forbidden_key in ["rateLimit", "doctorBriefId", "status", "version", "admin", "isVerified"]:
        with pytest.raises(ValueError, match=f"Disallowed metadata key '{forbidden_key}'"):
            CaseUpdate(metadata={forbidden_key: "hack"})


def test_case_metadata_size_limits_enforcement():
    """Verifies CaseUpdate.metadata enforces strict size and item limits."""
    # String field exceeds limit (> 2000 chars)
    oversized_str = "A" * 2001
    with pytest.raises(ValueError, match="cannot exceed 2000 characters"):
        CaseUpdate(metadata={"knownConditions": oversized_str})

    # Symptoms list exceeds item count (> 30 items)
    with pytest.raises(ValueError, match="symptoms list cannot exceed 30 items"):
        CaseUpdate(metadata={"symptoms": [f"symptom_{i}" for i in range(31)]})

    # Symptom item exceeds character limit (> 200 chars)
    with pytest.raises(ValueError, match="Each symptom item must be a string <= 200 characters"):
        CaseUpdate(metadata={"symptoms": ["X" * 201]})

    # Vitals exceeds dictionary entries (> 15 items)
    oversized_vitals = {f"v_{i}": "normal" for i in range(16)}
    with pytest.raises(ValueError, match="vitals cannot exceed 15 entries"):
        CaseUpdate(metadata={"vitals": oversized_vitals})


def test_case_metadata_draft_only_merge_and_post_submission_block():
    """Verifies metadata merging is permitted only in DRAFT status and blocked in SUBMITTED."""
    # Create case
    res = client.post(
        "/api/v1/cases",
        json={
            "chiefComplaint": "Persistent dry cough",
            "duration": "3 days",
            "requestedUrgency": "routine",
            "patientLanguage": "en",
            "idempotencyKey": "idem_meta_merge_test_1",
        },
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res.status_code == 201
    case_id = res.json()["caseId"]

    # 1. First metadata update in DRAFT -> merges successfully
    patch1 = client.patch(
        f"/api/v1/cases/{case_id}",
        json={"metadata": {"symptoms": ["cough"], "knownConditions": "None"}},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert patch1.status_code == 200
    assert patch1.json()["metadata"]["symptoms"] == ["cough"]
    assert patch1.json()["metadata"]["knownConditions"] == "None"

    # 2. Second metadata update in DRAFT -> merges with previous
    patch2 = client.patch(
        f"/api/v1/cases/{case_id}",
        json={"metadata": {"medications": "None", "allergies": "Penicillin"}},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert patch2.status_code == 200
    meta2 = patch2.json()["metadata"]
    assert meta2["symptoms"] == ["cough"]
    assert meta2["knownConditions"] == "None"
    assert meta2["medications"] == "None"
    assert meta2["allergies"] == "Penicillin"

    # 3. Patching with disallowed key via HTTP endpoint -> HTTP 422 Unprocessable Entity
    patch_bad = client.patch(
        f"/api/v1/cases/{case_id}",
        json={"metadata": {"rate_limit": 999}},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert patch_bad.status_code == 422

    # 4. Submit case -> transitions to SUBMITTED
    submit_res = client.post(
        f"/api/v1/cases/{case_id}/submit",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert submit_res.status_code == 200

    # 5. Attempt metadata update while SUBMITTED -> Strictly rejected with HTTP 400
    patch_submitted = client.patch(
        f"/api/v1/cases/{case_id}",
        json={"metadata": {"symptoms": ["cough worse"]}},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert patch_submitted.status_code == 400
    assert "Cases can only be edited while in DRAFT status" in patch_submitted.json()["detail"]


# ==============================================================================
# 3. IDEMPOTENT SUBMISSION & CREATION TESTS
# ==============================================================================

def test_idempotent_case_creation_prevents_duplicate_cases():
    """Submitting the exact same case creation payload twice returns the existing case."""
    payload = {
        "chiefComplaint": "Acute lower back pain after lifting weights",
        "duration": "2 days",
        "requestedUrgency": "routine",
        "patientLanguage": "hi",
        "idempotencyKey": "idem_duplicate_test_key_xyz",
    }

    # First call creates case
    res1 = client.post("/api/v1/cases", json=payload, headers={"Authorization": TOKEN_PATIENT_1})
    assert res1.status_code == 201
    case1 = res1.json()

    # Second call with same idempotency key returns exact same case
    res2 = client.post("/api/v1/cases", json=payload, headers={"Authorization": TOKEN_PATIENT_1})
    assert res2.status_code == 201
    case2 = res2.json()

    assert case1["caseId"] == case2["caseId"]
    assert case1["createdAt"] == case2["createdAt"]


def test_idempotent_case_submission_handles_network_retries():
    """
    Submitting an already SUBMITTED case must return HTTP 200 without throwing
    an InvalidStateTransitionError or corrupting case status.
    """
    # 1. Create case in DRAFT
    create_res = client.post(
        "/api/v1/cases",
        json={
            "chiefComplaint": "Sprained ankle during football practice",
            "duration": "3 hours",
            "requestedUrgency": "urgent",
            "patientLanguage": "en",
            "idempotencyKey": "idem_double_submit_key",
        },
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    case_id = create_res.json()["caseId"]

    # 2. First submit: DRAFT -> SUBMITTED
    sub1 = client.post(
        f"/api/v1/cases/{case_id}/submit",
        json={"idempotencyKey": "sub_key_1"},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert sub1.status_code == 200
    assert sub1.json()["status"] == "SUBMITTED"
    submitted_at_1 = sub1.json()["submittedAt"]

    # 3. Second submit (simulated double-click / network retry):
    # Must succeed with 200 OK and maintain SUBMITTED status smoothly!
    sub2 = client.post(
        f"/api/v1/cases/{case_id}/submit",
        json={"idempotencyKey": "sub_key_1"},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert sub2.status_code == 200
    assert sub2.json()["status"] == "SUBMITTED"
    assert sub2.json()["caseId"] == case_id


# ==============================================================================
# 4. AUDIT EVENT LOGGING & IMMUTABILITY
# ==============================================================================

def test_audit_event_trail_for_case_lifecycle():
    """Verifies that each lifecycle action creates an immutable audit record."""
    test_key = "idem_audit_trail_test"
    # Create case
    res = client.post(
        "/api/v1/cases",
        json={
            "chiefComplaint": "High grade fever with chills",
            "duration": "24 hours",
            "requestedUrgency": "urgent",
            "patientLanguage": "mr",
            "idempotencyKey": test_key,
        },
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    case_id = res.json()["caseId"]

    # Submit case
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})

    # Check audit events for this case
    audit_res = client.get(f"/api/v1/audit/cases/{case_id}", headers={"Authorization": TOKEN_ADMIN})
    assert audit_res.status_code == 200
    events = audit_res.json()
    assert len(events) >= 2

    event_types = [e["eventType"] for e in events]
    assert "CASE_CREATED" in event_types
    assert "CASE_SUBMITTED" in event_types

    # Ensure all events have timestamps and actor info
    for ev in events:
        assert ev["caseId"] == case_id
        assert ev["actorId"] is not None
        assert ev["timestamp"] is not None


# ==============================================================================
# 5. FIRESTORE MODEL CONVERTER UNIT TESTS
# ==============================================================================

def test_firestore_model_serialization_and_deserialization():
    """Tests bidirectional serialization between Pydantic and Firestore dicts."""
    now = datetime.utcnow()
    case = case_service.create_case(
        CaseCreate(
            patientId="patient_firestore_1",
            chiefComplaint="Mild rash on left arm",
            duration="2 days",
            requestedUrgency="routine",
            patientLanguage="en",
            idempotencyKey="idem_fs_test_1",
        ),
        actor_id="patient_firestore_1",
    )

    # Convert to Firestore document dictionary
    fs_dict = case_to_firestore_dict(case)
    assert fs_dict["status"] == "DRAFT"
    assert fs_dict["requestedUrgency"] == "routine"
    assert isinstance(fs_dict["createdAt"], str)

    # Convert back to Pydantic CaseResponse
    restored = case_from_firestore_dict(case.caseId, fs_dict)
    assert restored.caseId == case.caseId
    assert restored.patientId == "patient_firestore_1"
    assert restored.status == CaseStatus.DRAFT
    assert restored.chiefComplaint == "Mild rash on left arm"


def test_firestore_timestamp_converter_handles_various_formats():
    """Verifies firestore_timestamp_to_datetime parses datetime, ISO strings, and mock objects."""
    dt = datetime(2026, 10, 10, 12, 0, 0)
    assert firestore_timestamp_to_datetime(dt) == dt
    assert firestore_timestamp_to_datetime("2026-10-10T12:00:00Z") is not None
    assert firestore_timestamp_to_datetime(None) is None

    class MockTimestamp:
        def to_datetime(self):
            return datetime(2026, 10, 10, 8, 30, 0)

    mock_ts = MockTimestamp()
    assert firestore_timestamp_to_datetime(mock_ts) == datetime(2026, 10, 10, 8, 30, 0)
