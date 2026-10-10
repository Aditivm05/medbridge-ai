# MedBridge AI — Urgent Healthcare Care-Coordination Platform

> **Hackathon MVP:** AI-Powered Urgent Healthcare Coordination.  
> **Core Principle:** Care coordination platform only. It does **NOT** diagnose, prescribe, or replace clinicians. Clinicians make 100% of medical assessments.

---

## 1. System Overview & Safety Guardrails

MedBridge AI bridges patients experiencing acute or urgent health concerns to verified medical clinicians.
- **Zero-Network Static Emergency Guidance:** Whenever a patient selects "Urgent" or "Emergency", an immediate static red banner renders on the client with direct access to **112 (India Emergency)** and the nearest hospital. This guidance never relies on network latency or AI models.
- **Strictly Care Coordination:** Gemini generates a structured **Doctor Brief** from patient intake and synthetic lab reports; it explicitly marks unknowns, keeps measurement units, and separates patient claims from objective document findings.
- **Human-in-the-Loop Review:** Patients must review and approve their brief before matching; clinicians review before finalizing consultation notes.
- **Concurrency-Safe Atomic Matching:** Clinicians claim cases via atomic transactions (returning HTTP 409 Conflict upon race conditions).
- **Simulation Transparency:** All demo clinicians, mock availability, and text-based consultations are visibly stamped with `[DEMO / SIMULATED]`.
- **Multilingual Support:** Fully localized in English, Hindi (हिन्दी), and Marathi (मराठी).

> [!CAUTION]
> **Synthetic Documents Notice & Data Privacy Boundary:**
> MedBridge AI is designed and evaluated strictly using synthetic healthcare documents and simulated patient profiles. Real patient medical records, protected health information (PHI), or sensitive clinical documents must **NEVER** be submitted to external AI APIs without an institutional privacy review, explicit patient consent, and enterprise compliance safeguards (e.g. HIPAA BAA, GDPR). All AI-extracted data is tagged with `extractionSource: "AI_EXTRACTED"` and requires human clinician review.

---

## 2. High-Level Architecture

```mermaid
flowchart TD
    A[Patient: Sign In / Language Select (EN, HI, MR)] --> B[Select Requested Urgency]
    B -->|Urgent / Emergency| E[STATIC EMERGENCY GUIDANCE: Call 112 / Nearest Hospital]
    B --> C[Intake Form: Symptoms + Synthetic Document Upload]
    C --> D[Backend: Magic Byte & MIME Validation -> Cloud Storage]
    D --> F[Gemini 2.0 Flash: Structured Doctor Brief Synthesis]
    F --> G[Patient Reviews & Confirms Doctor Brief]
    G --> H[Case State: MATCHING (Enqueued)]
    H --> I[Clinician Portal: Matching DEMO Clinician Views Brief]
    I --> J{Firestore Atomic Transaction: Claim Case}
    J -->|Success| K[Case State: ACCEPTED -> IN_CONSULTATION]
    J -->|Conflict / Already Claimed| L[HTTP 409 Conflict Returned]
    K --> M[Clinician Records Notes & Follow-up Instructions]
    M --> N[Case State: COMPLETED]
    N --> O[Patient Views Completed Case & Follow-up in EN/HI/MR]
```

---

## 3. Technology Stack

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS (mobile-first, deployed to Firebase Hosting).
- **Backend:** Python 3.10+, FastAPI, Pydantic v2 (Cloud Run container).
- **Auth & Database:** Firebase Authentication (custom claims), Cloud Firestore (atomic transactions).
- **Storage:** Cloud Storage (private bucket, short-lived 15-minute signed URLs).
- **AI Synthesis:** Google Gemini 2.0 Flash via the official `google-genai` Python SDK.
- **Testing & Emulators:** Pytest, Firebase Emulator Suite (Auth: 9099, Firestore: 8080, Storage: 9199).

---

## 4. Quick Start / Local Setup Guide

### Step 1: Clone & Inspect Repository
```bash
git clone <repo-url>
cd Medflow
```

### Step 2: Backend Setup (Python FastAPI)
1. **Create and activate virtual environment:**
   ```powershell
   # Windows PowerShell
   python -m venv backend\.venv
   .\backend\.venv\Scripts\Activate.ps1
   ```
2. **Install dependencies:**
   ```powershell
   pip install -r backend\requirements.txt
   ```
3. **Configure Environment:**
   ```powershell
   Copy-Item backend\.env.example backend\.env
   ```
4. **Run Backend Tests:**
   ```powershell
   pytest -v backend\tests
   ```
5. **Start FastAPI Backend Server (Port 8000):**
   ```powershell
   uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
   ```
   - **Health Endpoint:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
   - **Interactive API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

### Step 3: Frontend Setup (Vite + React + Tailwind CSS)
1. **Open a new terminal and navigate to frontend:**
   ```powershell
   cd frontend
   ```
2. **Configure Environment:**
   ```powershell
   Copy-Item .env.example .env
   ```
3. **Install npm dependencies:**
   ```powershell
   npm install
   ```
4. **Start Vite Dev Server (Port 5173):**
   ```powershell
   npm run dev
   ```
   - **Web App URL:** [http://127.0.0.1:5173](http://127.0.0.1:5173)

---

### Step 4: Verify Both Servers Running

#### A. Backend Health Verification:
Run in PowerShell:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```
**Expected Output:**
```json
{
  "status": "healthy",
  "service": "MedBridge AI",
  "version": "1.0.0",
  "environment": "development",
  "aiModel": "gemini-2.0-flash",
  "emulators": {
    "firestore": "127.0.0.1:8080",
    "auth": "127.0.0.1:9099",
    "storage": "127.0.0.1:9199"
  }
}
```

#### B. Frontend Landing Page Verification:
Open [http://127.0.0.1:5173](http://127.0.0.1:5173) in your browser:
- Header loads with `MedBridge AI` and `[DEMO / SIMULATED]` tag.
- Language selector switches seamlessly between **English (EN)**, **Hindi (हिन्दी)**, and **Marathi (मराठी)**.
- Selecting **"Urgent"** or **"Emergency"** instantly pops up the red **Static Emergency Warning Banner** with direct click-to-call for **112**.
- Backend health widget displays green `healthy` indicator.

---

## 5. Firebase Emulator Suite (Optional for Local Zero-Cost Testing)
```powershell
# In project root
npx -y firebase-tools emulators:start
```
Emulator UI is accessible at [http://127.0.0.1:4000](http://127.0.0.1:4000).

---

## 6. Project Structure

```
Medflow/
├── docs/
│   └── ARCHITECTURE.md       # Comprehensive specification & data contracts
├── firebase/
│   ├── firestore.rules       # Deny-by-default database security rules
│   └── storage.rules         # Private bucket security rules
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI entrypoint with /health and CORS
│   │   ├── core/             # Configuration & state machine turnstile
│   │   ├── schemas/          # Pydantic v2 domain schemas
│   │   ├── services/         # Atomic case service & audit logger
│   │   └── api/routers/      # Modular REST endpoints
│   ├── tests/                # Automated pytest suite
│   ├── requirements.txt      # Python dependencies
│   └── .env.example          # Backend environment variables template
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Main landing page & urgency controller
│   │   ├── components/       # Header, EmergencyBanner, SimulationBadge
│   │   └── i18n/             # English, Hindi, and Marathi translations
│   ├── package.json          # React, Tailwind, Lucide dependencies
│   └── .env.example          # Frontend environment variables template
├── firebase.json             # Firebase emulators configuration
├── PROJECT_STATUS.md         # Phase tracking & completed milestones
└── README.md                 # This setup guide
```
