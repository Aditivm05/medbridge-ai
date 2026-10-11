"""
MedBridge AI — Standalone Live Socket E2E Validation Script
Executes the full patient and clinician journey against the active FastAPI backend (8000)
and Vite dev server (5173) over real HTTP sockets.
"""

import sys
import time
import httpx

BACKEND_BASE = "http://127.0.0.1:8000"
FRONTEND_BASE = "http://127.0.0.1:5173"
API_V1 = f"{BACKEND_BASE}/api/v1"


def print_step(step_num: int, title: str):
    print(f"\n[{step_num:02d}] === {title} ===")


def assert_status(resp: httpx.Response, expected_code, step_desc: str):
    expected = [expected_code] if isinstance(expected_code, int) else expected_code
    if resp.status_code not in expected:
        print(f"FAILED: {step_desc} - Expected HTTP {expected}, got {resp.status_code}")
        print(f"Response: {resp.text}")
        sys.exit(1)
    print(f"PASSED: {step_desc} (HTTP {resp.status_code})")


def run_suite():
    results = []

    with httpx.Client(timeout=15.0) as client:
        # Step 1: Frontend Server Check
        print_step(1, "Verify Vite Frontend is Serving")
        resp = client.get(FRONTEND_BASE)
        assert_status(resp, 200, "Frontend index.html reachable")
        assert "MedBridge AI" in resp.text or "root" in resp.text, "Vite HTML structure missing"
        results.append("01. Frontend server health check")

        # Step 2: Backend Health
        print_step(2, "Verify FastAPI Backend Health")
        resp = client.get(f"{BACKEND_BASE}/health")
        assert_status(resp, 200, "Backend /health reachable")
        data = resp.json()
        assert data.get("service") == "MedBridge AI", f"Unexpected service: {data}"
        print(f"  Service: {data.get('service')} | Version: {data.get('version')} | Model: {data.get('aiModel')}")
        results.append("02. Backend /health probe")

        # Step 3: Auth & Identity Verification
        print_step(3, "Verify Authentication & Identity Endpoints")
        p1_headers = {"Authorization": "Bearer mock-token-patient-1"}
        resp = client.get(f"{API_V1}/auth/me", headers=p1_headers)
        assert_status(resp, 200, "Patient 1 identity verification")
        p1_data = resp.json()
        assert p1_data["uid"] == "patient_demo_1" and p1_data["role"] == "patient"
        print(f"  Patient Authenticated: uid={p1_data['uid']}, role={p1_data['role']}")

        doc_headers = {"Authorization": "Bearer mock-token-demo_doc_patil"}
        resp = client.get(f"{API_V1}/auth/me", headers=doc_headers)
        assert_status(resp, 200, "Verified Clinician identity verification")
        doc_data = resp.json()
        assert doc_data["role"] == "clinician" and doc_data["isVerifiedClinician"] is True
        print(f"  Clinician Authenticated: uid={doc_data['uid']}, verified={doc_data['isVerifiedClinician']}")

        unverified_headers = {"Authorization": "Bearer mock-token-clinician-unverified"}
        resp = client.get(f"{API_V1}/auth/me", headers=unverified_headers)
        assert_status(resp, 200, "Unverified Clinician identity verification")
        unv_data = resp.json()
        assert unv_data["role"] == "clinician" and unv_data["isVerifiedClinician"] is False

        resp = client.get(f"{API_V1}/auth/me", headers={"Authorization": "Bearer invalid-garbage-token"})
        assert_status(resp, 401, "Invalid token rejection")
        results.append("03. Auth & Identity verification")

        # Step 4: Patient Intake & Backend Case Creation
        print_step(4, "Patient Intake -> Real Backend Case Creation (DRAFT)")
        ts = int(time.time() * 1000)
        intake_payload = {
            "chiefComplaint": "Persistent pulsating migraine with aura and photo-sensitivity",
            "duration": "4 days",
            "requestedUrgency": "urgent",
            "patientLanguage": "en",
            "metadata": {
                "symptoms": ["headache", "photophobia", "nausea"],
                "allergies": "Penicillin",
                "knownConditions": "Occasional tension headaches",
            },
            "idempotencyKey": f"live_intake_{ts}",
        }
        resp = client.post(f"{API_V1}/cases", headers=p1_headers, json=intake_payload)
        assert_status(resp, [200, 201], "Backend case creation")
        case_data = resp.json()
        case_id = case_data["caseId"]
        assert case_id.startswith("case_"), f"Unexpected case ID format: {case_id}"
        assert case_data["status"] == "DRAFT"
        assert case_data["patientId"] == "patient_demo_1"
        print(f"  Case Created: {case_id} (Status: {case_data['status']})")
        results.append(f"04. Backend case creation with ID: {case_id}")

        # Step 5: Patient Dashboard Listing
        print_step(5, "Patient Dashboard: List Cases")
        resp = client.get(f"{API_V1}/cases", headers=p1_headers)
        assert_status(resp, 200, "Patient list cases")
        cases_list = resp.json()
        assert any(c["caseId"] == case_id for c in cases_list), "Created case not found in dashboard"
        results.append("05. Patient dashboard case listing")

        # Step 6: Doctor Brief AI Generation / Synthesis
        print_step(6, "Doctor Brief AI Generation / Synthesis")
        resp = client.post(f"{API_V1}/cases/{case_id}/brief/generate", headers=p1_headers, json={"confirmRegenerate": False})
        assert_status(resp, 200, "Doctor brief synthesis")
        brief_data = resp.json()
        assert brief_data["briefStatus"] == "DRAFT_AI"
        assert brief_data["caseId"] == case_id
        results.append("06. Doctor brief synthesis (DRAFT_AI)")

        # Step 7: Retrieve Doctor Brief
        print_step(7, "Retrieve Doctor Brief from Backend")
        resp = client.get(f"{API_V1}/cases/{case_id}/brief", headers=p1_headers)
        assert_status(resp, 200, "Doctor brief retrieval")
        results.append("07. Doctor brief retrieval")

        # Step 8: Edit Doctor Brief & Persistence Verification
        print_step(8, "Patient Edits Doctor Brief & Verifies Persistence")
        edit_text = "Symptoms began after prolonged screen work on Tuesday, worsening rapidly."
        edit_payload = {"timelineAndDetails": edit_text}
        resp = client.put(f"{API_V1}/cases/{case_id}/brief", headers=p1_headers, json=edit_payload)
        assert_status(resp, 200, "Doctor brief edit save")
        edited_brief = resp.json()
        assert edited_brief["briefStatus"] == "EDITED"

        # Re-fetch independently to ensure persistence
        resp = client.get(f"{API_V1}/cases/{case_id}/brief", headers=p1_headers)
        assert_status(resp, 200, "Re-fetch edited brief")
        persisted_brief = resp.json()
        assert persisted_brief["timelineAndDetails"] == edit_text
        assert persisted_brief["briefStatus"] == "EDITED"
        results.append("08. Doctor brief editing and persistence check")

        # Step 9: Patient Approval of Doctor Brief
        print_step(9, "Patient Approves Doctor Brief")
        approve_payload = {"notes": "Approved by patient after reviewing timeline and symptoms"}
        resp = client.post(f"{API_V1}/cases/{case_id}/brief/approve", headers=p1_headers, json=approve_payload)
        assert_status(resp, 200, "Doctor brief approval")
        approved_brief = resp.json()
        assert approved_brief["briefStatus"] == "PATIENT_APPROVED"
        results.append("09. Doctor brief patient approval (PATIENT_APPROVED)")

        # Step 10: Case Submission to Matching
        print_step(10, "Submit Case to Clinician Matching Pool")
        idem_submit = f"live_submit_{ts}"
        resp = client.post(f"{API_V1}/cases/{case_id}/submit", headers=p1_headers, json={"idempotencyKey": idem_submit})
        assert_status(resp, 200, "Case submission")
        submitted_case = resp.json()
        assert submitted_case["status"] == "SUBMITTED"

        # Verify idempotency
        resp_idem = client.post(f"{API_V1}/cases/{case_id}/submit", headers=p1_headers, json={"idempotencyKey": idem_submit})
        assert_status(resp_idem, 200, "Idempotent repeat submission")
        results.append("10. Case submission with idempotency protection")

        # Step 11: Execute Clinician Matching
        print_step(11, "Trigger Clinician Matching")
        resp = client.post(f"{API_V1}/cases/{case_id}/match", headers=p1_headers)
        assert_status(resp, 200, "Clinician matching trigger")
        match_result = resp.json()
        assert match_result["status"] == "MATCHING"
        candidates = match_result.get("matches", [])
        assert len(candidates) > 0, "Expected at least one demo clinician in matching candidates"
        top_clinician = candidates[0]
        print(f"  Top Candidate: {top_clinician['fullName']} ({top_clinician['specialty']}) - ID: {top_clinician['clinicianId']}")
        results.append("11. Clinician matching trigger & candidate evaluation")

        # Step 12: Verified Clinician Pool Inspection
        print_step(12, "Verified Clinician Views Matching Pool")
        resp = client.get(f"{API_V1}/clinicians/matching-pool", headers=doc_headers)
        assert_status(resp, 200, "Verified clinician matching pool")
        pool = resp.json()
        assert any(c["caseId"] == case_id for c in pool), "Case not visible in clinician matching pool"
        results.append("12. Verified clinician matching pool access")

        # Step 13: Concurrency & RBAC - Unverified Clinician Claim Block
        print_step(13, "RBAC Security: Unverified Clinician Claim Attempt (Must Fail with 403)")
        resp = client.post(f"{API_V1}/cases/{case_id}/accept", headers=unverified_headers, json={})
        assert_status(resp, 403, "Unverified clinician blocked from claiming case")
        results.append("13. Unverified clinician claim blocked (HTTP 403)")

        # Step 14: Cross-Patient Isolation Check
        print_step(14, "Tenant Isolation: Cross-Patient Access Block (Must Fail with 403)")
        p2_headers = {"Authorization": "Bearer mock-token-patient-2"}
        resp = client.get(f"{API_V1}/cases/{case_id}", headers=p2_headers)
        assert_status(resp, 403, "Cross-patient read access forbidden")
        resp = client.put(f"{API_V1}/cases/{case_id}/brief", headers=p2_headers, json={"timelineAndDetails": "Malicious override"})
        assert_status(resp, 403, "Cross-patient brief edit forbidden")
        results.append("14. Cross-patient isolation enforced (HTTP 403)")

        # Step 15: Verified Clinician Claims Case (Atomic Acceptance)
        print_step(15, "Verified Clinician 1 Claims Case (Atomic Acceptance)")
        resp = client.post(f"{API_V1}/cases/{case_id}/accept", headers=doc_headers, json={})
        assert_status(resp, 200, "Clinician 1 claim case")
        claimed_case = resp.json()
        assert claimed_case["status"] == "ACCEPTED"
        assert claimed_case["assignedClinicianId"] == doc_data["uid"]
        results.append("15. Atomic case claim by verified clinician")

        # Step 16: Concurrency Collision Guard (Clinician 2 Duplicate Claim)
        print_step(16, "Concurrency Collision Guard: Second Clinician Duplicate Claim (Must Fail with 409)")
        doc2_headers = {"Authorization": "Bearer mock-token-demo_doc_sharma"}
        resp = client.post(f"{API_V1}/cases/{case_id}/accept", headers=doc2_headers, json={})
        assert_status(resp, 409, "Duplicate claim collision rejected with 409 Conflict")
        results.append("16. Concurrency collision guard (HTTP 409 Conflict)")

        # Step 17: Clinician Consultation Recording
        print_step(17, "Clinician Records Clinical Assessment & Care Advice")
        consult_payload = {
            "clinicianNotes": "Patient assessed with acute migraine episode with visual aura. Recommend dark quiet rest and hydration.",
            "provisionalCareAdvice": "Hydration, avoid screen exposure, apply cold compress, seek emergency care if motor deficit occurs.",
            "isSimulated": True,
        }
        resp = client.post(f"{API_V1}/cases/{case_id}/consultation", headers=doc_headers, json=consult_payload)
        assert_status(resp, 200, "Consultation record saved")
        resp_case = client.get(f"{API_V1}/cases/{case_id}", headers=doc_headers)
        assert resp_case.json()["status"] == "IN_CONSULTATION"
        results.append("17. Clinician consultation recorded (IN_CONSULTATION)")

        # Step 18: Clinician Case Completion & Follow-up Scheduling
        print_step(18, "Clinician Finalizes Case & Follow-up Plan")
        followup_payload = {
            "required": True,
            "recommendedDate": "2026-10-18",
            "instructions": "Follow up with primary care physician or MedBridge if headache frequency increases or does not subside within 48h.",
        }
        resp = client.post(f"{API_V1}/cases/{case_id}/complete", headers=doc_headers, json=followup_payload)
        assert_status(resp, 200, "Case completed and follow-up scheduled")
        comp_data = resp.json()
        assert comp_data["case"]["status"] == "COMPLETED"
        assert comp_data["followUp"]["required"] is True
        results.append("18. Case completion and follow-up schedule (COMPLETED)")

        # Step 19: Patient Reads Completed Case & Consultation
        print_step(19, "Patient Views Final Case & Clinical Consultation Record")
        resp = client.get(f"{API_V1}/cases/{case_id}", headers=p1_headers)
        assert_status(resp, 200, "Patient reads completed case")
        assert resp.json()["status"] == "COMPLETED"

        resp = client.get(f"{API_V1}/cases/{case_id}/consultation", headers=p1_headers)
        assert_status(resp, 200, "Patient reads consultation notes")
        results.append("19. Patient reads consultation and completed record")

        # Step 20: Honest Empty Matching State Verification
        print_step(20, "Verify Honest Empty Matching State (No Fabricated Matches)")
        empty_case_payload = {
            "chiefComplaint": "Specialized coordination case where matching pool has no available clinician",
            "duration": "1 week",
            "requestedUrgency": "routine",
            "patientLanguage": "hi",
            "metadata": {
                "declinedClinicianIds": ["demo_doc_sharma", "demo_doc_patil", "demo_doc_deshmukh"],
            },
            "idempotencyKey": f"live_empty_{ts}",
        }
        resp = client.post(f"{API_V1}/cases", headers=p1_headers, json=empty_case_payload)
        assert_status(resp, [200, 201], "Create case for empty match test")
        empty_case_id = resp.json()["caseId"]

        client.post(f"{API_V1}/cases/{empty_case_id}/submit", headers=p1_headers, json={})
        resp = client.post(f"{API_V1}/cases/{empty_case_id}/match", headers=p1_headers)
        assert_status(resp, 200, "Trigger match for non-matching case")
        empty_match = resp.json()
        assert empty_match["status"] == "NO_CLINICIAN_AVAILABLE"
        assert len(empty_match.get("matches", [])) == 0
        print(f"  Honest Empty State Confirmed: Status={empty_match['status']}, candidate count=0")
        results.append("20. Honest empty matching state verified (NO_CLINICIAN_AVAILABLE, zero fake candidates)")

        # Step 21: Invalid State Transition Guard
        print_step(21, "Invalid State Transition Guard")
        resp = client.post(f"{API_V1}/cases/{case_id}/submit", headers=p1_headers, json={})
        assert_status(resp, 400, "Submitting COMPLETED case rejected with 400 Bad Request")
        results.append("21. Invalid state transition blocked (HTTP 400)")

    print("\n" + "=" * 60)
    print("ALL 21 LIVE END-TO-END VALIDATION STEPS PASSED SUCCESSFULLY!")
    print("=" * 60)
    for r in results:
        print(f" [PASS] {r}")


if __name__ == "__main__":
    run_suite()
