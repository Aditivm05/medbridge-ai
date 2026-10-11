"""
SYNTHETIC DATA ONLY.

Phase 9 Live Server Smoke Test: Full Golden Workflow
Executes against the running server on http://127.0.0.1:8000 with Firebase Emulators:
1. Patient submits intake request (DRAFT)
2. Document uploaded and verified (NOTE: The uploaded document is a stub PDF used for attachment and verification flow only; this script does not test OCR or check brief content)
3. AI Doctor Brief generated with Gemini
4. Patient approves Doctor Brief (SUBMITTED -> MATCHING)
5. Seeded DEMO clinician (Dr. Rajesh Patil) accepts case (ACCEPTED)
6. Clinician reviews Doctor Brief and records consultation notes (IN_CONSULTATION)
7. Clinician schedules follow-up and completes case (COMPLETED, clinician released)
8. Patient retrieves completed case history, consultation record, and follow-up directives
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

HEADERS_PATIENT = {
    "Authorization": "Bearer mock-token-patient-1",
    "Content-Type": "application/json"
}
HEADERS_CLINICIAN = {
    "Authorization": "Bearer mock-token-demo_doc_patil",
    "Content-Type": "application/json"
}


def run_phase9_golden_workflow():
    print("=== STARTING PHASE 9 LIVE GOLDEN WORKFLOW ===")

    # 0. Health check
    h = requests.get(f"{BASE_URL}/health")
    assert h.status_code == 200, f"Health check failed: {h.text}"
    print(f"[OK] Health check passed: {h.json()['status']}, AI Model: {h.json().get('aiModel')}")

    # 1. Patient Intake (DRAFT)
    case_payload = {
        "chiefComplaint": "Severe right lower quadrant abdominal pain with low-grade fever",
        "duration": "36 hours",
        "requestedUrgency": "urgent",
        "patientLanguage": "en",
        "idempotencyKey": f"golden_demo_p9_{int(time.time())}"
    }
    res1 = requests.post(f"{BASE_URL}/api/v1/cases", json=case_payload, headers=HEADERS_PATIENT)
    assert res1.status_code == 201, f"Create case failed: {res1.text}"
    case = res1.json()
    case_id = case["caseId"]
    print(f"[OK] Step 1: Created Case {case_id} in status {case['status']}")

    # 2. Attach Sample Medical Document (Valid minimal PDF with extractable text)
    sample_txt = (
        b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        b"1 0 obj\n<<\n/Producer (pypdf)\n>>\nendobj\n"
        b"2 0 obj\n<<\n/Type /Pages\n/Count 1\n/Kids [ 4 0 R ]\n>>\nendobj\n"
        b"3 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n/Outlines 7 0 R\n>>\nendobj\n"
        b"4 0 obj\n<<\n/Type /Page\n/MediaBox [ 0 0 612 792 ]\n/Contents 5 0 R\n/Resources <<\n/Font <<\n/F1 6 0 R\n>>\n>>\n/Parent 2 0 R\n>>\nendobj\n"
        b"5 0 obj\n<<\n/Length 56\n>>\nstream\nBT\n/F1 12 Tf\n72 712 Td\n(Ultrasound Pelvis Normal) Tj\nET\n\nendstream\nendobj\n"
        b"6 0 obj\n<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>\nendobj\n"
        b"7 0 obj\n<<\n>>\nendobj\n"
        b"xref\n0 8\n0000000000 65535 f \n0000000015 00000 n \n0000000054 00000 n \n0000000113 00000 n \n0000000178 00000 n \n0000000306 00000 n \n0000000412 00000 n \n0000000482 00000 n \n"
        b"trailer\n<<\n/Size 8\n/Root 3 0 R\n/Info 1 0 R\n>>\nstartxref\n503\n%%EOF\n"
    )
    files = {"file": ("ultrasound_appendix.pdf", sample_txt, "application/pdf")}
    res2 = requests.post(
        f"{BASE_URL}/api/v1/cases/{case_id}/documents/upload-and-verify",
        files=files,
        headers={"Authorization": "Bearer mock-token-patient-1"}
    )
    assert res2.status_code in (200, 201), f"Upload document failed: {res2.text}"
    doc = res2.json()
    print(f"[OK] Step 2: Uploaded & magic-byte verified document {doc['documentId']} ({doc['fileName']})")

    # 3. Generate AI Doctor Brief
    res3 = requests.post(
        f"{BASE_URL}/api/v1/cases/{case_id}/brief/generate",
        json={"confirmRegenerate": False},
        headers=HEADERS_PATIENT
    )
    assert res3.status_code == 200, f"Generate brief failed: {res3.text}"
    brief = res3.json()
    print(f"[OK] Step 3: Generated Doctor Brief {brief['briefId']} (status: {brief['briefStatus']})")

    # 4. Patient Approves Brief & Enqueues for Matching
    res4 = requests.post(
        f"{BASE_URL}/api/v1/cases/{case_id}/brief/approve",
        json={"notes": "Reviewed and approved by patient"},
        headers=HEADERS_PATIENT
    )
    assert res4.status_code == 200, f"Approve brief failed: {res4.text}"
    print(f"[OK] Step 4a: Patient approved brief (status: {res4.json()['briefStatus']})")

    # Enqueue case
    res4b = requests.post(f"{BASE_URL}/api/v1/cases/{case_id}/submit", headers=HEADERS_PATIENT)
    assert res4b.status_code == 200
    res4c = requests.post(f"{BASE_URL}/api/v1/cases/{case_id}/matching", headers=HEADERS_PATIENT)
    assert res4c.status_code == 200, f"Matching queue failed: {res4c.text}"
    print(f"[OK] Step 4b: Case transitioned to {res4c.json()['status']}")

    # 5. Clinician Matching Pool & Case Acceptance
    res5_pool = requests.get(f"{BASE_URL}/api/v1/clinicians/matching-pool", headers=HEADERS_CLINICIAN)
    assert res5_pool.status_code == 200
    pool = res5_pool.json()
    assert any(c["caseId"] == case_id for c in pool), f"Case {case_id} not found in pool: {pool}"
    print(f"[OK] Step 5a: Located case {case_id} in matching pool ({len(pool)} available cases)")

    # Clinician accepts case
    res5_accept = requests.post(f"{BASE_URL}/api/v1/cases/{case_id}/accept", headers=HEADERS_CLINICIAN)
    assert res5_accept.status_code == 200, f"Accept case failed: {res5_accept.text}"
    accepted_case = res5_accept.json()
    assert accepted_case["status"] == "ACCEPTED"
    assert accepted_case["assignedClinicianId"] == "demo_doc_patil"
    print(f"[OK] Step 5b: Clinician 'demo_doc_patil' accepted case {case_id} (status: ACCEPTED)")

    # 6. Clinician Reviews Doctor Brief & Records Consultation Notes
    res6_rev = requests.post(
        f"{BASE_URL}/api/v1/cases/{case_id}/brief/review",
        json={"clinicianNotes": "Verified clinical timeline and attached imaging report."},
        headers=HEADERS_CLINICIAN
    )
    assert res6_rev.status_code == 200
    print(f"[OK] Step 6a: Clinician verified Doctor Brief (status: {res6_rev.json()['briefStatus']})")

    # Clinician records consultation assessment
    consultation_payload = {
        "clinicianNotes": "Clinical assessment confirms localized tenderness in RLQ with positive McBurney point tenderness. No generalized guarding or rebound rigidity noted.",
        "provisionalCareAdvice": "Strict bed rest with oral clear hydration only. Avoid solid fatty foods or abdominal heating compresses. Monitor oral temperature every 4 hours.",
        "isSimulated": True
    }
    res6_consult = requests.post(
        f"{BASE_URL}/api/v1/cases/{case_id}/consultation",
        json=consultation_payload,
        headers=HEADERS_CLINICIAN
    )
    assert res6_consult.status_code == 200, f"Record consultation failed: {res6_consult.text}"
    consultation = res6_consult.json()
    assert consultation["isSimulated"] is True
    assert consultation["consultationType"] == "text_based_consultation_simulated"
    print(f"[OK] Step 6b: Recorded text-based consultation {consultation['consultationId']} (isSimulated: {consultation['isSimulated']})")

    # Verify status transitioned to IN_CONSULTATION
    c_check = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}", headers=HEADERS_PATIENT).json()
    assert c_check["status"] == "IN_CONSULTATION"
    print(f"[OK] Step 6c: Case status updated to {c_check['status']}")

    # 7. Follow-Up Scheduling & Case Completion
    followup_payload = {
        "required": True,
        "recommendedDate": "2026-10-18",
        "instructions": "If high fever > 101.5 F or continuous vomiting occurs, report immediately to nearest ER. Otherwise return for follow-up abdominal ultrasound review in 5 days."
    }
    res7 = requests.post(
        f"{BASE_URL}/api/v1/cases/{case_id}/complete",
        json=followup_payload,
        headers=HEADERS_CLINICIAN
    )
    assert res7.status_code == 200, f"Complete case failed: {res7.text}"
    comp = res7.json()
    completed_case = comp["case"]
    follow_up = comp["followUp"]
    assert completed_case["status"] == "COMPLETED"
    assert completed_case["completedAt"] is not None
    assert follow_up["required"] is True
    assert follow_up["recommendedDate"] == "2026-10-18"
    assert follow_up["status"] == "scheduled"
    print(f"[OK] Step 7a: Case completed (status: {completed_case['status']}, completedAt: {completed_case['completedAt']})")
    print(f"[OK] Step 7b: Follow-up scheduled (status: {follow_up['status']}, target: {follow_up['recommendedDate']})")

    # Verify clinician availability released back to available
    clin_check = requests.get(f"{BASE_URL}/api/v1/clinicians", headers=HEADERS_CLINICIAN).json()
    patil = next(c for c in clin_check if c["clinicianId"] == "demo_doc_patil")
    assert patil["availability"] == "available"
    assert patil["currentCaseId"] is None
    print(f"[OK] Step 7c: Clinician 'demo_doc_patil' availability released to '{patil['availability']}' (currentCaseId: {patil['currentCaseId']})")

    # 8. Patient Case History & Follow-Up View Verification
    # Patient fetches their case
    p_case = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}", headers=HEADERS_PATIENT).json()
    assert p_case["status"] == "COMPLETED"
    assert p_case["completedAt"] is not None
    print(f"[OK] Step 8a: Patient sees completed case in history (completedAt: {p_case['completedAt']})")

    # Patient fetches consultation
    p_consult = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}/consultation", headers=HEADERS_PATIENT).json()
    assert p_consult["clinicianNotes"] == consultation_payload["clinicianNotes"]
    assert p_consult["provisionalCareAdvice"] == consultation_payload["provisionalCareAdvice"]
    assert p_consult["isSimulated"] is True
    print(f"[OK] Step 8b: Patient retrieved consultation record (Assessment notes & Supportive care advice verified)")

    # Patient fetches follow-up
    p_followup = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}/follow-up", headers=HEADERS_PATIENT).json()
    assert p_followup["required"] is True
    assert p_followup["recommendedDate"] == "2026-10-18"
    assert p_followup["status"] == "scheduled"
    assert "report immediately to nearest ER" in p_followup["instructions"]
    print(f"[OK] Step 8c: Patient retrieved follow-up directives (target: {p_followup['recommendedDate']}, instructions verified)")

    # Cross-patient forbidden check
    cross_res = requests.get(f"{BASE_URL}/api/v1/cases/{case_id}/consultation", headers={"Authorization": "Bearer mock-token-patient-2"})
    assert cross_res.status_code == 403
    print(f"[OK] Step 8d: Cross-patient access securely rejected with HTTP 403 Forbidden")

    print("\n=== ALL 8 PHASES OF THE GOLDEN WORKFLOW SUCCEEDED WITH ZERO ERRORS ===")


if __name__ == "__main__":
    run_phase9_golden_workflow()
