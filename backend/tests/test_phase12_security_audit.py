"""
MedBridge AI — Phase 12 Security Audit & Data Integrity Regression Suite
Validates:
1. Production environment safety locks (disabling test tokens and mock persistence in production).
2. Strict tenant isolation & patient ownership enforcement across case and Doctor Brief routes.
3. Clinician verification restrictions & assignment boundaries.
4. Concurrency-safe atomic case claiming and collision rejection.
5. State machine transition invariants (rejecting invalid skips or retroactive transitions).
6. Submission idempotency guarantees without duplicate state corruption.
7. Clean handling of missing, malformed, or stale case IDs (HTTP 404).
8. Accurate labeling of simulated demo data.
"""

import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.state_machine import CaseStatus
from app.core.auth import is_demo_auth_enabled
from app.services.case_service import case_service
from app.services.clinician_service import clinician_service
from app.services.brief_service import brief_service
from app.schemas.clinician import ClinicianAvailabilityUpdateRequest, ClinicianAvailability

client = TestClient(app)

TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_DOC_PATIL = "Bearer mock-token-demo_doc_patil"
TOKEN_DOC_SHARMA = "Bearer mock-token-demo_doc_sharma"
TOKEN_DOC_UNVERIFIED = "Bearer mock-token-clinician-unverified"
TOKEN_ADMIN = "Bearer mock-token-admin"


@pytest.fixture(autouse=True)
def reset_db_state():
    """Ensure clean test database state and seeded demo clinicians."""
    db = clinician_service.db
    if hasattr(db, "is_fake") and db.is_fake:
        for k in list(db._store.keys()):
            if k.startswith("cases/") or k.startswith("consultations/") or k.startswith("follow_ups/") or k.startswith("doctorBriefs/"):
                del db._store[k]
    clinician_service.seed_default_clinicians()


def _create_patient_case(token: str, suffix: str = "p12") -> str:
    payload = {
        "chiefComplaint": f"Acute symptom consultation for Phase 12 security audit ({suffix})",
        "duration": "2 days",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "metadata": {
            "symptoms": ["headache", "fever"],
            "allergies": "Sulfa",
        },
        "idempotencyKey": f"idem_p12_{suffix}_{time.time()}",
    }
    res = client.post("/api/v1/cases", json=payload, headers={"Authorization": token})
    assert res.status_code == 201
    return res.json()["caseId"]


# ==============================================================================
# 1. Production Environment Safety Locks
# ==============================================================================

def test_production_mode_strictly_disables_demo_auth(monkeypatch):
    """In production mode, mock/dev tokens are strictly forbidden."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("TESTING", raising=False)
    assert is_demo_auth_enabled() is False


def test_production_mode_aborts_startup_if_demo_auth_configured(monkeypatch):
    """FastAPI lifespan refuses to boot if DEMO_AUTH_ENABLED=true in production."""
    from app.main import lifespan
    import asyncio

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEMO_AUTH_ENABLED", "true")
    monkeypatch.delenv("TESTING", raising=False)

    async def _test():
        with pytest.raises(RuntimeError, match="DEMO_AUTH_ENABLED cannot be enabled"):
            async with lifespan(app):
                pass

    asyncio.run(_test())


# ==============================================================================
# 2. Strict Tenant Isolation & Patient Ownership Enforcement
# ==============================================================================

def test_cross_patient_case_read_and_patch_blocked():
    """Patient 2 cannot view or update Patient 1's case."""
    case_id = _create_patient_case(token=TOKEN_PATIENT_1, suffix="isolation_read")

    # Read attempt by Patient 2
    res_get = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_PATIENT_2})
    assert res_get.status_code == 403
    assert "Forbidden" in res_get.json()["detail"]

    # Patch attempt by Patient 2
    res_patch = client.patch(
        f"/api/v1/cases/{case_id}",
        json={"chiefComplaint": "Malicious modification attempt"},
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res_patch.status_code == 403


def test_cross_patient_brief_access_and_edits_blocked():
    """Patient 2 cannot access, synthesize, edit, or approve Patient 1's brief."""
    case_id = _create_patient_case(token=TOKEN_PATIENT_1, suffix="isolation_brief")

    # Generate brief as Patient 1
    gen_res = client.post(
        f"/api/v1/cases/{case_id}/brief/generate",
        json={"confirmRegenerate": False},
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert gen_res.status_code == 200

    # Patient 2 attempts to read Patient 1's brief
    get_res = client.get(f"/api/v1/cases/{case_id}/brief", headers={"Authorization": TOKEN_PATIENT_2})
    assert get_res.status_code == 403

    # Patient 2 attempts to edit Patient 1's brief
    put_res = client.put(
        f"/api/v1/cases/{case_id}/brief",
        json={"timelineAndDetails": "Unauthorized overwrite"},
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert put_res.status_code == 403

    # Patient 2 attempts to approve Patient 1's brief
    approve_res = client.post(
        f"/api/v1/cases/{case_id}/brief/approve",
        json={"notes": "Malicious approval"},
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert approve_res.status_code == 403


# ==============================================================================
# 3. Clinician Verification Restrictions & Assignment Boundaries
# ==============================================================================

def test_unverified_clinician_cannot_query_candidates_or_claim_cases():
    """Unverified clinician cannot query matching candidates or accept cases."""
    case_id = _create_patient_case(token=TOKEN_PATIENT_1, suffix="unv_clinician")

    # Patient approves & submits
    client.post(f"/api/v1/cases/{case_id}/brief/generate", json={"confirmRegenerate": False}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/brief/approve", json={"notes": "Approved"}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/submit", json={}, headers={"Authorization": TOKEN_PATIENT_1})

    # Unverified clinician attempts to query matching candidates
    res_match = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_DOC_UNVERIFIED})
    assert res_match.status_code == 403
    assert "verified" in res_match.json()["detail"].lower()

    # Move case to MATCHING as patient
    client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})

    # Unverified clinician attempts to claim
    res_accept = client.post(f"/api/v1/cases/{case_id}/accept", json={}, headers={"Authorization": TOKEN_DOC_UNVERIFIED})
    assert res_accept.status_code == 403


def test_unassigned_clinician_cannot_record_consultation_or_complete_case():
    """Clinician B cannot access consultation or complete a case assigned to Clinician A."""
    case_id = _create_patient_case(token=TOKEN_PATIENT_1, suffix="clinician_assignment")

    # Workflow to MATCHING
    client.post(f"/api/v1/cases/{case_id}/brief/generate", json={"confirmRegenerate": False}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/brief/approve", json={"notes": "Approved"}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/submit", json={}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})

    # Claimed by Clinician Patil
    res_claim = client.post(f"/api/v1/cases/{case_id}/accept", json={}, headers={"Authorization": TOKEN_DOC_PATIL})
    assert res_claim.status_code == 200

    # Clinician Sharma attempts to record consultation notes
    res_unassigned_consult = client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json={
            "clinicianNotes": "Interfering consultation notes from unassigned doctor",
            "provisionalCareAdvice": "General hydration advice",
            "isSimulated": True,
        },
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res_unassigned_consult.status_code == 403

    # Assigned clinician Patil records consultation
    res_assigned_consult = client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json={
            "clinicianNotes": "Legitimate assessment observations by assigned doctor",
            "provisionalCareAdvice": "Rest in quiet room and stay hydrated",
            "isSimulated": True,
        },
        headers={"Authorization": TOKEN_DOC_PATIL},
    )
    assert res_assigned_consult.status_code == 200

    # Clinician Sharma attempts to read consultation notes
    res_unassigned_get = client.get(f"/api/v1/cases/{case_id}/consultation", headers={"Authorization": TOKEN_DOC_SHARMA})
    assert res_unassigned_get.status_code == 403

    # Clinician Sharma attempts to complete the case
    res_unassigned_comp = client.post(
        f"/api/v1/cases/{case_id}/complete",
        json={"required": True, "recommendedDate": "2026-10-20", "instructions": "Unauthorized follow-up"},
        headers={"Authorization": TOKEN_DOC_SHARMA},
    )
    assert res_unassigned_comp.status_code == 403


# ==============================================================================
# 4. Concurrency Collision Guard
# ==============================================================================

def test_atomic_case_claim_collision_returns_409():
    """When Clinician A accepts a case, Clinician B receives 409 Conflict."""
    case_id = _create_patient_case(token=TOKEN_PATIENT_1, suffix="collision_test")

    client.post(f"/api/v1/cases/{case_id}/brief/generate", json={"confirmRegenerate": False}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/brief/approve", json={"notes": "Approved"}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/submit", json={}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})

    # Clinician Patil claims first
    res1 = client.post(f"/api/v1/cases/{case_id}/accept", json={}, headers={"Authorization": TOKEN_DOC_PATIL})
    assert res1.status_code == 200
    assert res1.json()["assignedClinicianId"] == "demo_doc_patil"

    # Clinician Sharma claims simultaneously
    res2 = client.post(f"/api/v1/cases/{case_id}/accept", json={}, headers={"Authorization": TOKEN_DOC_SHARMA})
    assert res2.status_code == 409
    assert "cannot be accepted" in res2.json()["detail"].lower()


# ==============================================================================
# 5. State Machine Invariants
# ==============================================================================

def test_invalid_state_transition_skips_rejected():
    """Direct match attempt on DRAFT case without SUBMITTED transition is blocked."""
    case_id = _create_patient_case(token=TOKEN_PATIENT_1, suffix="state_invariants")

    # Attempt to directly call match on DRAFT case
    res_direct_match = client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})
    assert res_direct_match.status_code == 400
    assert "invalid" in res_direct_match.json()["detail"].lower()

    # Move to COMPLETED through valid lifecycle
    client.post(f"/api/v1/cases/{case_id}/brief/generate", json={"confirmRegenerate": False}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/brief/approve", json={"notes": "Approved"}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/submit", json={}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/match", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/accept", json={}, headers={"Authorization": TOKEN_DOC_PATIL})
    client.post(
        f"/api/v1/cases/{case_id}/consultation",
        json={"clinicianNotes": "Valid consultation observations", "provisionalCareAdvice": "Valid care guidance", "isSimulated": True},
        headers={"Authorization": TOKEN_DOC_PATIL},
    )
    client.post(
        f"/api/v1/cases/{case_id}/complete",
        json={"required": False, "recommendedDate": "2026-10-25", "instructions": "Standard discharge"},
        headers={"Authorization": TOKEN_DOC_PATIL},
    )

    # Attempt to resubmit or claim already completed case
    res_resubmit = client.post(f"/api/v1/cases/{case_id}/submit", json={}, headers={"Authorization": TOKEN_PATIENT_1})
    assert res_resubmit.status_code == 400

    res_reclaim = client.post(f"/api/v1/cases/{case_id}/accept", json={}, headers={"Authorization": TOKEN_DOC_SHARMA})
    assert res_reclaim.status_code == 409


# ==============================================================================
# 6. Submission Idempotency Guarantees
# ==============================================================================

def test_submission_idempotency_returns_consistent_state():
    """Repeated submit with identical idempotencyKey returns 200 without duplicate creation."""
    case_id = _create_patient_case(token=TOKEN_PATIENT_1, suffix="idempotency_test")
    client.post(f"/api/v1/cases/{case_id}/brief/generate", json={"confirmRegenerate": False}, headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/brief/approve", json={"notes": "Approved"}, headers={"Authorization": TOKEN_PATIENT_1})

    idem_key = f"idem_submit_test_{time.time()}"
    res1 = client.post(f"/api/v1/cases/{case_id}/submit", json={"idempotencyKey": idem_key}, headers={"Authorization": TOKEN_PATIENT_1})
    assert res1.status_code == 200
    submitted_at = res1.json()["submittedAt"]

    # Repeat submit with identical key
    res2 = client.post(f"/api/v1/cases/{case_id}/submit", json={"idempotencyKey": idem_key}, headers={"Authorization": TOKEN_PATIENT_1})
    assert res2.status_code == 200
    assert res2.json()["submittedAt"] == submitted_at
    assert res2.json()["status"] == "SUBMITTED"


# ==============================================================================
# 7. Clean Handling of Nonexistent & Stale Case IDs
# ==============================================================================

def test_nonexistent_case_ids_return_404_cleanly():
    """Invalid or nonexistent case IDs return 404 without internal crashes."""
    fake_id = "case_nonexistent_9999"

    assert client.get(f"/api/v1/cases/{fake_id}", headers={"Authorization": TOKEN_PATIENT_1}).status_code == 404
    assert client.get(f"/api/v1/cases/{fake_id}/brief", headers={"Authorization": TOKEN_PATIENT_1}).status_code == 404
    assert client.post(f"/api/v1/cases/{fake_id}/submit", json={}, headers={"Authorization": TOKEN_PATIENT_1}).status_code == 404
    assert client.post(f"/api/v1/cases/{fake_id}/match", headers={"Authorization": TOKEN_PATIENT_1}).status_code == 404
    assert client.post(f"/api/v1/cases/{fake_id}/accept", json={}, headers={"Authorization": TOKEN_DOC_PATIL}).status_code == 404
    assert client.get(f"/api/v1/cases/{fake_id}/consultation", headers={"Authorization": TOKEN_PATIENT_1}).status_code == 404


# ==============================================================================
# 8. Accurate Labeling of Simulated Demo Data
# ==============================================================================

def test_demo_clinicians_and_routes_clearly_labeled_as_simulated():
    """All seeded demo clinicians and matching outputs are explicitly tagged [DEMO / SIMULATED]."""
    res_list = client.get("/api/v1/clinicians", headers={"Authorization": TOKEN_PATIENT_1})
    assert res_list.status_code == 200
    clinicians = res_list.json()
    assert len(clinicians) > 0

    for c in clinicians:
        assert c["isDemo"] is True
        assert "[DEMO / SIMULATED]" in c["fullName"]

    # Verify root endpoint disclaimer
    root_res = client.get("/")
    assert root_res.status_code == 200
    assert "DEMO / SIMULATED" in root_res.json()["notice"]
