# MedBridge AI — Hackathon Demonstration Runbook

## 1. Executive Summary & Architecture Overview

**MedBridge AI** is an intelligent healthcare navigation and care coordination platform tailored for semi-urban and multilingual settings (English, Hindi, Marathi). It addresses acute triage congestion by taking patient intake narratives and medical PDFs, synthesizing an objective, non-diagnostic **Doctor Brief** via Gemini, and connecting patients to licensed clinicians with verified credentials.

> [!IMPORTANT]
> **Clinical Safety & Regulatory Notice:**  
> MedBridge AI is **NOT** a diagnostic system. It does not output medical diagnoses, prescriptions, or unsupervised treatment plans. Clinicians make 100% of all medical evaluations and clinical decisions. All simulated demo clinicians are clearly designated as `[DEMO / SIMULATED]`.

---

## 2. Prerequisites & Environment

| Component | Verified Local Version | Path / Command |
|:---|:---|:---|
| **Python** | Python 3.12+ | `backend\.venv\Scripts\python.exe` |
| **Node.js** | Node.js v24.20.0 (LTS) | `node-v24.20.0-win-x64` |
| **Package Manager** | npm 10.9.0 | In Node path |
| **FastAPI Backend** | 1.0.0 (uvicorn 0.34.0) | `http://127.0.0.1:8000` |
| **Vite Frontend** | Vite 5.4.21 (React 18) | `http://127.0.0.1:5173` |

### Required Environment Variables (No Secrets Required for Demo)
- Backend (`backend/.env` or shell env):
  - `TESTING=1` (activates self-contained in-memory `FakeFirestoreClient` with seeded demo doctors)
  - `DEMO_AUTH_ENABLED=true` (allows deterministic mock authorization headers)
  - `ENVIRONMENT=development`
  - `PORT=8000`
  - `GEMINI_MODEL=gemini-3.8-flash`
  - `GEMINI_API_KEY=` (optional: if omitted, Gemini gracefully falls back to deterministic fallback skeleton without crash)
- Frontend:
  - `VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1`

---

## 3. Fast Demo Startup

### Option A: One-Click Launcher (PowerShell)
```powershell
cd C:\MedFlow\medbridge-ai
powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
```

### Option B: Manual Two-Terminal Startup

#### Terminal 1 — FastAPI Backend (Port 8000)
```powershell
cd C:\MedFlow\medbridge-ai\backend
$env:TESTING="1"
.\.venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
*Alternative (from repository root):*
```powershell
cd C:\MedFlow\medbridge-ai
$env:TESTING="1"
.\backend\.venv\Scripts\activate
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```
*Health verification:* Open `http://127.0.0.1:8000/health` (returns `status: healthy`, `service: MedBridge AI`).

#### Terminal 2 — Vite Frontend (Port 5173)
```powershell
cd C:\MedFlow\medbridge-ai\frontend
# Ensure Node.js is in PATH if not already accessible globally
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $wingetNode = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter "node.exe" -Recurse -Depth 3 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wingetNode) { $env:Path = "$($wingetNode.DirectoryName);$env:Path" }
}
npm run dev -- --host 127.0.0.1 --port 5173
```
*Web App:* Open `http://127.0.0.1:5173` in Google Chrome or Microsoft Edge.

> [!NOTE]
> **In-Memory Simulation Lifecycle:**  
> All patient cases, Doctor Briefs, and matching claims reside in memory (`FakeFirestoreClient`) for the lifetime of the backend process (`TESTING=1`). Data does **NOT** persist across server restarts. Maintain the active backend process throughout the presentation. To clear session data without restarting, click the **"Reset Demo Data"** button in the bottom telemetry bar.

---

## 4. Demo Accounts & Personas

MedBridge AI uses deterministic authorization tokens in development mode. Select personas directly from the top navigation bar dropdown:

| Persona | Token | Role | Verified | Description |
|:---|:---|:---|:---|:---|
| **Patient (Demo 1)** | `mock-token-patient-1` | `patient` | N/A | Primary demo patient owner (`patient_demo_1`) |
| **Dr. Rajesh Patil** | `mock-token-demo_doc_patil` | `clinician` | **Yes** | Emergency Medicine (MMC-SIM-91823, En/Mr/Hi) |
| **Dr. Ananya Sharma** | `mock-token-demo_doc_sharma` | `clinician` | **Yes** | General Medicine (MCI-SIM-48201, En/Hi) |
| **Dr. Vikram Malhotra** | `mock-token-clinician-unverified` | `clinician` | **No** (Pending) | Used to demonstrate strict RBAC rejection |
| **Patient 2** | `mock-token-patient-2` | `patient` | N/A | Used to demonstrate cross-patient boundary protection |

---

## 5. Five-Minute Presentation Script & Flow

### Minute 1: The Problem & Patient Intake (Screen 1 & 2)
1. **Show Dashboard:** Open `http://127.0.0.1:5173`. Point to the green **"Backend Connected"** pill and **"DEMO / SIMULATED"** compliance badge.
2. **Talk Track:** *"In emergency and acute outpatient settings, patient narratives are often fragmented across languages, and patients struggle to describe timelines. MedBridge AI bridges this gap."*
3. **Action:** Click **"2. Intake"** on the workflow bar.
   - Chief Complaint: `"Severe throbbing headache with visual aura and nausea"`
   - Duration: `"3 days"`
   - Urgency: `"Urgent"`
   - Language: `"English"` (or Hindi / Marathi)
   - Click **"Submit Intake"**. Point out that a real backend-issued ID is returned (`case_...`, status `DRAFT`).

### Minute 2: Objective AI Doctor Brief & Human Correction (Screen 4)
1. **Action:** Navigate to **"4. Doctor Brief"**.
2. **Talk Track:** *"Notice that the Doctor Brief immediately displays a prominent safety disclaimer: 'AI-generated summary. Not a diagnosis or medical advice.' It strictly organizes the timeline, allergies, and vitals, highlighting missing information and discrepancies."*
3. **Demonstrate Edit & Versioning:** Click **"Suggest Edit"**.
   - Edit the Timeline: `"Symptoms began on Tuesday after screen exposure and worsened with bright lights."`
   - Click **"Save Edits"**.
   - Show that the brief status transitions to `EDITED`, and the version increments.
4. **Approve Brief:** Check *"I have reviewed and confirmed this medical summary is accurate"*, then click **"Approve Brief"** (transitions to `PATIENT_APPROVED`).

### Minute 3: Clinician Matching Algorithm & Honest Empty State
1. **Action:** Click **"Submit to Clinician Matching Pool"**.
2. **Talk Track:** *"The frontend calls `POST /cases/{id}/submit` with idempotency protection, then triggers `POST /cases/{id}/match`. The matching algorithm prioritizes verified licensure, language fluency, and medical specialty."*
3. **Show Candidates:** Point out the matching cards showing **Dr. Rajesh Patil** and **Dr. Ananya Sharma** with verified badges, license numbers, and matching scores.
4. **Demonstrating Honest Empty State:**
   - Mention: *"What if no clinician is available? If a patient requests a language or specialty with exhausted coverage, MedBridge AI returns an honest empty state (`NO_CLINICIAN_AVAILABLE`) with emergency guidance (112), rather than fabricating fake providers."*

### Minute 4: Clinician Claim & Concurrency Collision Protection (Screen 5)
1. **Action:** Click **"Switch to Clinician Dashboard to Claim Case"** (or switch persona to Dr. Rajesh Patil).
2. **Talk Track:** *"Here is the clinician triage matching pool. Dr. Patil can review the structured brief."*
3. **Atomic Claim:** Click **"Accept Case"**. The case transitions to `ACCEPTED` and is locked to Dr. Patil.
4. **Demonstrate Collision Guard:**
   - Open an incognito window or run the live test probe: If Dr. Sharma attempts to claim the same case, the backend returns **HTTP 409 Conflict**, preventing double-booking in busy clinics.

### Minute 5: Clinical Consultation & Completion (Screen 6 & 7)
1. **Action:** Click **"6. Consultation"**.
2. **Talk Track:** *"Dr. Patil enters supportive care guidance and clinical assessment notes. All advice is tagged as simulated non-prescription guidance."*
3. **Finalize Case:** Click **"7. Follow-Up"**, enter recommended follow-up instructions, and finalize the case.
   - Status transitions to terminal `COMPLETED`.
   - Clinician is automatically released back to `available`.
4. **Patient View:** Switch back to Patient persona; the patient sees the consultation notes and follow-up guidance.

---

## 6. Live Automated Verification (Run Anytime)

Run the standalone socket verification script in a separate PowerShell window to validate all 21 steps in under 3 seconds:

```powershell
cd C:\MedFlow\medbridge-ai
& backend\.venv\Scripts\python.exe scripts\verify_live_demo.py
```

Expected output:
```
ALL 21 LIVE END-TO-END VALIDATION STEPS PASSED SUCCESSFULLY!
 [PASS] 01. Frontend server health check
 [PASS] 02. Backend /health probe
 [PASS] 03. Auth & Identity verification
 [PASS] 04. Backend case creation with ID: case_...
 ...
 [PASS] 20. Honest empty matching state verified (NO_CLINICIAN_AVAILABLE, zero fake candidates)
 [PASS] 21. Invalid state transition blocked (HTTP 400)
```

---

## 7. Common Issues & Quick Recovery

| Symptom | Root Cause | Immediate Recovery |
|:---|:---|:---|
| Header shows "Backend Disconnected" | FastAPI is not running on port 8000 | Run: `$env:TESTING="1"; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| "Failed to load cases from server" | Port 8000 blocked or wrong URL | Verify `GET http://127.0.0.1:8000/health`. Check CORS or proxy. |
| In-memory data reset needed | Previous demo run populated test cases | Click **"Reset Demo Data"** in the bottom telemetry bar, or restart backend. |
| Port 8000 already in use | Stale background python process | Identify PID with `Get-NetTCPConnection -LocalPort 8000` and restart server. |

---

## 8. Presenter Pre-Flight Checklist & Demo Shutdown

### Pre-Flight Checklist (Run 2 Minutes Before Presentation)
- [ ] **Backend Health:** Open `http://127.0.0.1:8000/health` in browser; verify JSON status is `"healthy"`.
- [ ] **Frontend Application:** Open `http://127.0.0.1:5173`; verify top header displays green **"Backend Connected"** pill.
- [ ] **Default Persona:** Ensure top-right persona selector is set to **"Patient (Demo)"** (`mock-token-patient-1`).
- [ ] **Session State Clean:** Click **"Reset Demo Data"** in bottom telemetry bar if previous testing left draft cases.
- [ ] **Live Smoke Check:** Run `& backend\.venv\Scripts\python.exe scripts\verify_live_demo.py` to confirm all 21 endpoints respond.

### Clean Demo Shutdown
To cleanly terminate only the backend and frontend processes when the demonstration concludes:
```powershell
cd C:\MedFlow\medbridge-ai
powershell -ExecutionPolicy Bypass -File scripts\stop_demo.ps1
```
