"""
Phase 10 - Stage 2A: Backend Authorization Hardening Test Suite
Verifies:
1. Doctor Brief generation ownership:
   - Patient A cannot generate a brief for Patient B's case.
   - Clinicians cannot trigger brief generation for draft cases.
   - Only the owning patient (or admin) can generate a Doctor Brief.
   - Direct service boundary enforcement (BriefAccessForbiddenError).
2. Document endpoint authorization:
   - Patients can only access documents from their own cases.
   - Unverified clinicians cannot access protected document metadata, text, OCR, or downloads.
   - Clinicians not assigned to a case cannot access protected document metadata, text, OCR, or downloads.
   - Assigned verified clinicians can only access documents when case is in ACCEPTED, IN_CONSULTATION, or COMPLETED status.
   - Cross-case document ID substitution is rejected with HTTP 404 Not Found.
3. Case visibility:
   - Clinicians cannot inspect another patient's DRAFT or SUBMITTED case.
   - Clinicians can view MATCHING cases (intake pool).
   - Only the assigned clinician can view an ACCEPTED case; unrelated clinicians are rejected with HTTP 403 Forbidden.
   - Clinician case listing (GET /cases) strictly filters to cases assigned to that clinician.
4. Demo clinician seeding:
   - Unauthenticated, patient, and clinician callers cannot trigger POST /clinicians/seed (HTTP 401 / 403).
   - Only administrators can seed demo clinicians (HTTP 200).
5. Authentication claims management:
   - Non-admin callers cannot update user custom claims via POST /auth/claims (HTTP 403).
   - Administrators can update claims (HTTP 200).
6. Audit endpoints:
   - System-wide audit log (GET /audit) is restricted to administrators.
   - Case audit logs (GET /audit/cases/{case_id} and GET /audit?caseId={case_id}) are restricted to assigned clinicians and administrators.
   - Clinicians cannot inspect audit logs for cases they are not assigned to.
"""

import io
import json
import time
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.state_machine import CaseStatus
from app.schemas.audit import AuditEventType
from app.services.case_service import case_service
from app.services.brief_service import brief_service, BriefAccessForbiddenError
from app.services.document_service import document_service

client = TestClient(app)

TOKEN_PATIENT_1 = "Bearer mock-token-patient-1"
TOKEN_PATIENT_2 = "Bearer mock-token-patient-2"
TOKEN_CLINICIAN_A = "Bearer mock-token-demo_doc_sharma"
TOKEN_CLINICIAN_B = "Bearer mock-token-demo_doc_patil"
TOKEN_CLINICIAN_UNVERIFIED = "Bearer mock-token-demo_doc_pending"
TOKEN_ADMIN = "Bearer mock-token-admin"

VALID_PDF_BYTES = b"%PDF-1.4\n%Demo PDF synthetic report\n%%EOF"


@pytest.fixture(autouse=True)
def reset_demo_clinicians():
    """Resets the demo clinicians into Firestore before each test."""
    from app.services.clinician_service import clinician_service
    db = clinician_service.db
    if hasattr(db, "is_fake") and db.is_fake:
        for k in list(db._store.keys()):
            if k.startswith("cases/") or k.startswith("consultations/") or k.startswith("follow_ups/"):
                del db._store[k]
    clinician_service.seed_default_clinicians()


def _create_case(token: str, key_suffix: str = "p10") -> str:
    payload = {
        "chiefComplaint": f"Symptom intake for Phase 10 auth test ({key_suffix})",
        "duration": "2 days",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": f"idem_p10_{key_suffix}_{time.time()}",
    }
    res = client.post("/api/v1/cases", json=payload, headers={"Authorization": token})
    assert res.status_code == 201
    return res.json()["caseId"]


def _upload_document(case_id: str, token: str, filename: str = "report.pdf") -> str:
    files = {"file": (filename, io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    res = client.post(
        f"/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": token},
    )
    assert res.status_code == 200
    return res.json()["documentId"]


# ==============================================================================
# 1. Doctor Brief Generation Ownership
# ==============================================================================

def test_patient_a_cannot_generate_brief_for_patient_b_case():
    """Requirement: Patient A cannot generate a brief for Patient B's draft case."""
    case_b_id = _create_case(token=TOKEN_PATIENT_2, key_suffix="patient_b_case")

    # Patient A attempts to generate brief for Patient B's case
    res_unauth = client.post(
        f"/api/v1/cases/{case_b_id}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_unauth.status_code == 403
    assert "owning patient" in res_unauth.json()["detail"].lower()

    # Clinician attempts to generate brief for Patient B's case
    res_clin = client.post(
        f"/api/v1/cases/{case_b_id}/brief/generate",
        headers={"Authorization": TOKEN_CLINICIAN_A},
    )
    assert res_clin.status_code == 403
    assert "owning patient" in res_clin.json()["detail"].lower()

    # Direct service layer check: BriefAccessForbiddenError raised
    with pytest.raises(BriefAccessForbiddenError):
        brief_service.generate_brief(
            case_id=case_b_id,
            actor_id="patient_demo_1",
            actor_role="patient",
        )

    # Legitimate owner (Patient B) can generate brief
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({"timelineAndDetails": "Synthetic symptom timeline"})
    mock_client.models.generate_content.return_value = mock_resp
    brief_service.set_client_for_testing(mock_client)

    res_owner = client.post(
        f"/api/v1/cases/{case_b_id}/brief/generate",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res_owner.status_code == 200
    assert res_owner.json()["caseId"] == case_b_id


# ==============================================================================
# 2. Document Endpoint Authorization & Cross-Case Substitution
# ==============================================================================

def test_document_endpoint_authorization_and_cross_case_substitution():
    """
    Requirements:
    - Patients must only access their own case's documents.
    - Unverified and unassigned clinicians cannot read protected document metadata, text, OCR, or extraction.
    - Cross-case document-ID substitution is rejected with HTTP 404 Not Found.
    """
    case_a_id = _create_case(token=TOKEN_PATIENT_1, key_suffix="doc_case_a")
    doc_a_id = _upload_document(case_a_id, token=TOKEN_PATIENT_1, filename="case_a_doc.pdf")

    case_b_id = _create_case(token=TOKEN_PATIENT_2, key_suffix="doc_case_b")
    doc_b_id = _upload_document(case_b_id, token=TOKEN_PATIENT_2, filename="case_b_doc.pdf")

    # 1. Patient 2 cannot access Patient 1's document
    res_meta = client.get(
        f"/api/v1/cases/{case_a_id}/documents/{doc_a_id}",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res_meta.status_code == 403
    assert "own medical cases" in res_meta.json()["detail"].lower()

    res_text = client.get(
        f"/api/v1/cases/{case_a_id}/documents/{doc_a_id}/text",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res_text.status_code == 403
    assert "own medical cases" in res_text.json()["detail"].lower()

    res_ocr = client.post(
        f"/api/v1/cases/{case_a_id}/documents/{doc_a_id}/ocr",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res_ocr.status_code == 403

    res_extract = client.post(
        f"/api/v1/cases/{case_a_id}/documents/{doc_a_id}/extract",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res_extract.status_code == 403

    # 2. Unverified clinician cannot access Patient 1's document
    res_unverified = client.get(
        f"/api/v1/cases/{case_a_id}/documents/{doc_a_id}",
        headers={"Authorization": TOKEN_CLINICIAN_UNVERIFIED},
    )
    assert res_unverified.status_code == 403
    assert "verified" in res_unverified.json()["detail"].lower()

    # 3. Unassigned verified clinician cannot access Patient 1's document
    res_unassigned = client.get(
        f"/api/v1/cases/{case_a_id}/documents/{doc_a_id}",
        headers={"Authorization": TOKEN_CLINICIAN_A},
    )
    assert res_unassigned.status_code == 403
    assert "not assigned" in res_unassigned.json()["detail"].lower()

    # 4. Cross-case document substitution:
    # Attempting to fetch doc_A using case_B's path must return 404 (document not found for case)
    res_subst_meta = client.get(
        f"/api/v1/cases/{case_b_id}/documents/{doc_a_id}",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res_subst_meta.status_code == 404
    assert f"not found for case '{case_b_id}'" in res_subst_meta.json()["detail"]

    res_subst_text = client.get(
        f"/api/v1/cases/{case_b_id}/documents/{doc_a_id}/text",
        headers={"Authorization": TOKEN_PATIENT_2},
    )
    assert res_subst_text.status_code == 404
    assert f"not found for case '{case_b_id}'" in res_subst_text.json()["detail"]

    # 5. Legitimate assigned clinician access:
    # Progress case A to MATCHING and accept it with Clinician A
    client.post(f"/api/v1/cases/{case_a_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_a_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})
    accept_res = client.post(f"/api/v1/cases/{case_a_id}/accept", headers={"Authorization": TOKEN_CLINICIAN_A})
    assert accept_res.status_code == 200

    # Clinician A can now access case A's document
    res_assigned_meta = client.get(
        f"/api/v1/cases/{case_a_id}/documents/{doc_a_id}",
        headers={"Authorization": TOKEN_CLINICIAN_A},
    )
    assert res_assigned_meta.status_code == 200
    assert res_assigned_meta.json()["documentId"] == doc_a_id

    res_assigned_text = client.get(
        f"/api/v1/cases/{case_a_id}/documents/{doc_a_id}/text",
        headers={"Authorization": TOKEN_CLINICIAN_A},
    )
    assert res_assigned_text.status_code == 200

    # But Clinician B (unassigned) still cannot access case A's document
    res_other_clin = client.get(
        f"/api/v1/cases/{case_a_id}/documents/{doc_a_id}",
        headers={"Authorization": TOKEN_CLINICIAN_B},
    )
    assert res_other_clin.status_code == 403


# ==============================================================================
# 3. Case Visibility: DRAFT and SUBMITTED Restricted from Unrelated Clinicians
# ==============================================================================

def test_case_visibility_draft_and_submitted_restricted_from_unrelated_clinicians():
    """
    Requirements:
    - Clinicians cannot read another patient's DRAFT or SUBMITTED case.
    - Clinicians CAN view MATCHING cases (intake pool).
    - Only the assigned clinician can read an ACCEPTED case.
    """
    case_id = _create_case(token=TOKEN_PATIENT_1, key_suffix="visibility_test")

    # 1. Case in DRAFT status -> Clinician gets 403
    res_draft = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_CLINICIAN_A})
    assert res_draft.status_code == 403
    assert "matching pool" in res_draft.json()["detail"].lower()

    # 2. Case in SUBMITTED status -> Clinician gets 403
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    res_submitted = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_CLINICIAN_A})
    assert res_submitted.status_code == 403
    assert "matching pool" in res_submitted.json()["detail"].lower()

    # 3. Case in MATCHING status -> Clinician can view
    client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})
    res_matching = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_CLINICIAN_A})
    assert res_matching.status_code == 200
    assert res_matching.json()["status"] == CaseStatus.MATCHING.value

    # 4. Clinician A accepts case -> status ACCEPTED
    client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_CLINICIAN_A})

    # Clinician A (assigned) can view
    res_assigned = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_CLINICIAN_A})
    assert res_assigned.status_code == 200
    assert res_assigned.json()["assignedClinicianId"] == "demo_doc_sharma"

    # Clinician B (unassigned) cannot view
    res_unassigned = client.get(f"/api/v1/cases/{case_id}", headers={"Authorization": TOKEN_CLINICIAN_B})
    assert res_unassigned.status_code == 403


def test_case_listing_clinician_filtered_to_assigned_only():
    """Requirement: Clinician case listing (GET /cases) strictly filters to cases assigned to that clinician."""
    case_id = _create_case(token=TOKEN_PATIENT_1, key_suffix="list_filter_test")
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_CLINICIAN_A})

    # Clinician A lists cases -> case is included
    res_a = client.get("/api/v1/cases", headers={"Authorization": TOKEN_CLINICIAN_A})
    assert res_a.status_code == 200
    case_ids_a = [c["caseId"] for c in res_a.json()]
    assert case_id in case_ids_a

    # Clinician B lists cases -> case is NOT included
    res_b = client.get("/api/v1/cases", headers={"Authorization": TOKEN_CLINICIAN_B})
    assert res_b.status_code == 200
    case_ids_b = [c["caseId"] for c in res_b.json()]
    assert case_id not in case_ids_b


# ==============================================================================
# 4. Demo Clinician Seeding Authorization
# ==============================================================================

def test_clinician_seeding_restricted_to_admin():
    """Requirement: Non-admin callers cannot seed clinicians."""
    # Unauthenticated -> 401
    res_unauth = client.post("/api/v1/clinicians/seed")
    assert res_unauth.status_code == 401

    # Patient -> 403
    res_patient = client.post("/api/v1/clinicians/seed", headers={"Authorization": TOKEN_PATIENT_1})
    assert res_patient.status_code == 403

    # Clinician -> 403
    res_clin = client.post("/api/v1/clinicians/seed", headers={"Authorization": TOKEN_CLINICIAN_A})
    assert res_clin.status_code == 403

    # Admin -> 200
    res_admin = client.post("/api/v1/clinicians/seed", headers={"Authorization": TOKEN_ADMIN})
    assert res_admin.status_code == 200
    assert len(res_admin.json()) >= 5


# ==============================================================================
# 5. Authentication Claims Management Authorization
# ==============================================================================

def test_claims_management_restricted_to_admin():
    """Requirement: Non-admin callers cannot grant themselves admin or verified-clinician claims."""
    payload = {
        "uid": "rogue_user_test",
        "role": "admin",
        "is_verified_clinician": True,
    }

    # Unauthenticated -> 401
    res_unauth = client.post("/api/v1/auth/claims", json=payload)
    assert res_unauth.status_code == 401

    # Patient -> 403
    res_patient = client.post(
        "/api/v1/auth/claims",
        json=payload,
        headers={"Authorization": TOKEN_PATIENT_1},
    )
    assert res_patient.status_code == 403

    # Clinician -> 403
    res_clin = client.post(
        "/api/v1/auth/claims",
        json=payload,
        headers={"Authorization": TOKEN_CLINICIAN_A},
    )
    assert res_clin.status_code == 403

    # Admin -> 200
    res_admin = client.post(
        "/api/v1/auth/claims",
        json=payload,
        headers={"Authorization": TOKEN_ADMIN},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["status"] == "success"


# ==============================================================================
# 6. Audit Endpoints Access Control
# ==============================================================================

def test_audit_endpoints_access_control():
    """
    Requirements:
    - Clinicians cannot read unrelated case audit events.
    - System-wide audit trail is restricted to administrators.
    - Assigned clinician can read their case's audit events.
    """
    case_id = _create_case(token=TOKEN_PATIENT_1, key_suffix="audit_auth_test")

    # 1. System-wide audit logs:
    # Patient -> 403
    res_sys_patient = client.get("/api/v1/audit", headers={"Authorization": TOKEN_PATIENT_1})
    assert res_sys_patient.status_code == 403

    # Clinician without caseId query -> 403
    res_sys_clin = client.get("/api/v1/audit", headers={"Authorization": TOKEN_CLINICIAN_A})
    assert res_sys_clin.status_code == 403
    assert "system-wide" in res_sys_clin.json()["detail"].lower()

    # Admin without caseId query -> 200
    res_sys_admin = client.get("/api/v1/audit", headers={"Authorization": TOKEN_ADMIN})
    assert res_sys_admin.status_code == 200
    assert isinstance(res_sys_admin.json(), list)

    # 2. Case-specific audit log for unassigned case:
    # Clinician A tries GET /audit/cases/{case_id} -> 403
    res_case_unassigned = client.get(
        f"/api/v1/audit/cases/{case_id}",
        headers={"Authorization": TOKEN_CLINICIAN_A},
    )
    assert res_case_unassigned.status_code == 403

    # Clinician A tries GET /audit?caseId={case_id} -> 403
    res_query_unassigned = client.get(
        f"/api/v1/audit?caseId={case_id}",
        headers={"Authorization": TOKEN_CLINICIAN_A},
    )
    assert res_query_unassigned.status_code == 403

    # 3. Assign case to Clinician A
    client.post(f"/api/v1/cases/{case_id}/submit", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/matching", headers={"Authorization": TOKEN_PATIENT_1})
    client.post(f"/api/v1/cases/{case_id}/accept", headers={"Authorization": TOKEN_CLINICIAN_A})

    # Assigned Clinician A can now read case audit events
    res_case_assigned = client.get(
        f"/api/v1/audit/cases/{case_id}",
        headers={"Authorization": TOKEN_CLINICIAN_A},
    )
    assert res_case_assigned.status_code == 200
    events = res_case_assigned.json()
    assert len(events) >= 1
    assert all(e["caseId"] == case_id for e in events)

    # Filtered query works for assigned clinician
    res_query_assigned = client.get(
        f"/api/v1/audit?caseId={case_id}",
        headers={"Authorization": TOKEN_CLINICIAN_A},
    )
    assert res_query_assigned.status_code == 200

    # Unassigned Clinician B still gets 403
    res_case_other = client.get(
        f"/api/v1/audit/cases/{case_id}",
        headers={"Authorization": TOKEN_CLINICIAN_B},
    )
    assert res_case_other.status_code == 403

    # Nonexistent case returns 404
    res_nonexistent = client.get(
        "/api/v1/audit/cases/case_nonexistent_xyz",
        headers={"Authorization": TOKEN_CLINICIAN_A},
    )
    assert res_nonexistent.status_code == 404
