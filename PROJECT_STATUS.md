# MedBridge AI — Project Status Tracker

**Last Updated:** 11 October 2026
**Repository:** `C:\Medflow`
**Current Baseline:** Phase 10 Commit `edcc5ee`
**Working Tree Status:** Clean (0 uncommitted, 0 untracked files; 2 commits ahead of `origin/main`)

---

## 1. Project Overview

MedBridge AI (Medflow) is an AI-powered urgent healthcare care-coordination platform designed for rapid healthcare navigation in India. It bridges patients experiencing acute or worsening symptoms to licensed medical clinicians by synthesizing structured, human-reviewed Doctor Briefs and facilitating simulated consultations and follow-ups.

### Core Architectural Principles & Safety Boundaries
- **Care Coordination Only:** The platform explicitly forbids autonomous clinical diagnosis, treatment prescriptions, or automated triage escalation. All clinical assessments and management plans remain the 100% legal and professional responsibility of verified, licensed clinicians.
- **Zero-Network Emergency Guidance:** Static emergency instructions for national services (112 India) trigger immediately upon selection of urgent or emergency complaints without requiring network connectivity.
- **Explicit Simulation Signposting:** Every synthetic doctor persona, consultation note, and test record is visibly marked with `[DEMO / SIMULATED]` and `isDemo: true`.
- **Zero Fake Notifications:** No fake push alerts, mock SMS banners, or artificial notifications are sent or displayed.

### Technology Stack & Major Components
- **Frontend (`frontend/`):** React 18 SPA built with Vite, TypeScript, and Tailwind CSS. Features 7 core screens, an active persona/role switcher (Patient, Clinician, Auditor), multilingual i18n support (English, Hindi, Marathi), and a responsive desktop/mobile design.
- **Backend (`backend/`):** FastAPI application (Python 3.10) with Pydantic v2 schemas, strict type safety, centralized finite state machine (10 states, 18 valid transitions), and async service layers.
- **Firebase Emulators (`firebase.json`):** Emulator-first architecture targeting project `demo-medbridge-ai`:
  - **Firebase Authentication:** Port `9099` (custom claims for roles: `patient`, `clinician`, `admin`).
  - **Cloud Firestore:** Port `8080` (atomic document transactions, snapshot versioning, and append-only audit trail).
  - **Cloud Storage:** Port `9199` (bucket `medbridge-ai-documents` for clinical records and medical imagery).
  - **Emulator UI:** Port `4000` (live inspection of collections, auth users, and storage buckets).
- **Gemini Integration:** Official Google GenAI SDK (`google-genai`). Configured model: `gemini-3.8-flash` (configurable via `GEMINI_MODEL`, fallback `gemini-2.0-flash`). Used for structured Doctor Brief synthesis (with Pydantic output schemas) and optional remote OCR extraction.

---

## 2. Phase-by-Phase Progress

### Phases 1–7: Core Application, Safety Blueprint & Doctor Brief
- **Phase 1: Architecture, Data Modeling, Tooling & Safety Blueprint** *(Completed & Verified)*:
  System architecture, 10 collection schemas, state machine transition matrix, and strict safety guidelines documented in `docs/ARCHITECTURE.md`.
- **Phase 2: Full-Stack Scaffolding, README & Health Check** *(Completed & Verified)*:
  Vite React frontend, FastAPI backend with `/health` and `/api/v1/health` endpoints, CORS middleware, and developer setup documentation.
- **Phase 3: All 7 Interactive Screens, Synthetic Data & Layouts** *(Completed & Verified)*:
  Interactive components for Patient Dashboard, Intake, Document Upload, Doctor Brief Review, Clinician Dashboard, Consultation Workspace, and Follow-Up.
- **Phase 4: Firebase Auth, Custom Claims & Ownership Gates** *(Completed & Verified)*:
  Role-based access control (`patient`, `clinician`, `admin`), verified clinician flags (`isVerifiedClinician`), ownership validation (`check_case_ownership`), and development security tester.
- **Phase 5: Database & Case Management Lifecycle** *(Completed & Verified)*:
  Firestore persistence, case CRUD operations, 10-state lifecycle, and exhaustive 100-pair state transition matrix tests (18 valid, 82 invalid).
- **Phase 6: Medical Documents, Verification & OCR** *(Partially Verified)*:
  - **6a (Upload Validation):** Strict MIME validation, binary magic-byte inspection (PDF `%PDF-`, JPEG `\xff\xd8\xff`, PNG `\x89PNG`), 10 MB limit, max 5 documents per case (`13 tests passed`).
  - **6b (Frontend Upload Screen):** Drag-and-drop dropzone, upload queue, and real-time XHR progress tracking (`verified`).
  - **6c (PDF Text Extraction):** Page-by-page extraction via `pypdf`, 30-page ceiling, and low-text threshold flagging (`NEEDS_OCR`) (`11 tests passed`).
  - **6d (Document Streaming & URLs):** Ephemeral HMAC signed streaming URLs and GCS signed URL generation (`19 tests passed with fakes; live emulator streaming pending manual check`).
  - **6e (Gemini Multimodal OCR):** Background OCR pipeline for scanned reports and images (`13 tests passed with mocks; live Gemini OCR call pending user API key test`).
  - **Voice Intake:** Planned for future iteration.
- **Phase 7: AI Doctor Brief (Gemini)** *(Completed & Verified)*:
  - **7a (Doctor Brief Backend):** Structured Gemini generation, Pydantic `DoctorBrief` schema (forbids diagnosis/prescription fields), source reference citations, clinical conflict detection, fallback skeleton on AI failure, rate limiting, and version snapshots (`16 tests passed`).
  - **7b (Clinician Review Gate):** Verification and authorization checks on `POST /cases/{case_id}/brief/review`, blocking unverified or unassigned clinicians (`7 tests passed`).
  - **7c (Frontend Brief Review Screen):** Interactive human-in-the-loop review interface, side-by-side unresolved conflicts, fact source badges, patient approval gate, and edit modal that invalidates approval upon modification (`verified`).
  - **Live Smoke Test (11 Oct 2026):** End-to-end test against live emulators and live Gemini API (`gemini-3.8-flash`) verified.

### Phase 8: Clinician Matching, Concurrency & Lifecycle *(Completed & Verified)*
- **8a (Seeded Clinicians):** 5 demo clinicians seeded in Firestore with `[DEMO / SIMULATED]` labels, `isDemo: true`, language tags, and verification statuses (`demo_doc_patil`, `demo_doc_sharma`, `demo_doc_deshmukh`, `demo_doc_pending`, `demo_doc_offline`).
- **8b (Matching Engine):** Multi-factor deterministic matching algorithm evaluating verification status, availability (`available`), patient language match, and specialty scoring. Automatic transition to `NO_CLINICIAN_AVAILABLE` with audit logging on exhaustion.
- **8c (Atomic Case Acceptance):** Concurrency-safe atomic claim via Firestore transaction (`@firestore_transactional`). Enforces dual-document consistency across `cases/{case_id}` and `clinicians/{clinician_id}`. Race collisions raise `CaseConflictError` (HTTP 409 Conflict) and emit `CONFLICT_DETECTED` audit events.
- **8d (Decline & Availability Management):** Decline endpoint (`POST /cases/{case_id}/decline`) with candidate pool re-evaluation, availability toggle (`PATCH /clinicians/{id}/availability`), and matching pool retrieval (`GET /clinicians/matching-pool`).
- **8e (Clinician Dashboard UI):** Real-time matching queue, live accept/decline actions, availability toggle, and simulated race condition testing button (`verified`).
- **Test Coverage:** 17 automated Phase 8 tests passed; live 2-clinician concurrent race test on Firestore emulator verified (1 winner HTTP 200, 1 collision HTTP 409).

### Phase 9: Consultation Workspace, Case Completion & Follow-Up *(Completed & Verified)*
- **9a (Consultation Workspace):** Text-based consultation interface labelled `[DEMO / SIMULATED]` with side-by-side tabs for Doctor Brief and source documents with OCR previews.
- **9b (Clinical Observations & Supportive Care Advice):** Pydantic schemas enforcing length boundaries and non-prescription supportive guidance disclaimers.
- **9c (Case State Transitions):** Transitions `ACCEPTED` -> `IN_CONSULTATION` on consultation recording, and `IN_CONSULTATION` -> terminal `COMPLETED` on case finalization. Zero transitions permitted out of `COMPLETED`.
- **9d (Follow-Up Scheduling & Clinician Release):** Follow-up record creation (`required`, `recommendedDate`, emergency warning instructions) and automatic release of assigned clinician back to `available` with `currentCaseId: None`.
- **9e (Patient History View):** `PatientDashboard.tsx` and `FollowUpScreen.tsx` display completed case history, conclusion timestamps, assessment notes, and scheduled follow-up directives with read-only controls.
- **9f (Zero Fake Notifications):** Confirmed zero mock push notifications or simulated SMS alerts.
- **Test Coverage:** 9 automated Phase 9 tests passed; live integration smoke test (`smoke_test_phase9.py`) verified full 8-step Golden Workflow against live backend, emulators, and Gemini.

### Phase 10: Authorization Hardening, Privacy Controls & Transactional Consistency *(Completed & Verified)*
- **Stage 2A (Authorization Hardening):** Strict RBAC enforcement across all endpoints. Ownership checks ensure patients access only their own cases (HTTP 403 Forbidden). Verified clinician gates (`require_verified_clinician`) restrict matching pool, case claims, brief reviews, consultations, and follow-ups. Document and consultation endpoints restricted to patient owner or assigned verified clinician. Audit endpoints locked strictly to `admin`.
- **Stage 2B / 2B.2 (Clinical Privacy & Data Sanitization):** Sanitization engine (`app/core/sanitization.py`) redacts Indian phone numbers (`+91-9876543210`, `+91 98765 43210`, `09876543210`, and 10-digit mobile formats), emails, Aadhaar numbers (UIDAI), and PAN cards before text transmission to Gemini. Preserves clinical dates (`YYYY-MM-DD`), medication dosages (e.g. `10-20 mg`), and vital measurements. Safe exception-type logging in Gemini client initialization prevents credential leakage. Remote OCR gated behind `ALLOW_REMOTE_OCR=true`.
- **Stage 2C / 2C.2 (Transactional Completion & Concurrency Consistency):** Refactored `complete_case_and_followup` to execute inside a Firestore transaction (`@firestore_transactional`). Active-case check (`_clinician_has_other_active_cases`) is evaluated internally with fresh reads inside the transaction retry loop, preventing availability races during concurrent assignments. Clinician is released to `available` only if no other active cases exist. Terminal state validation prevents duplicate completions. Audit event (`CASE_COMPLETED`) is written atomically within the same transaction.
- **Commit Baseline:** `edcc5ee` (`feat(security): harden authorization, clinical data privacy, and transaction consistency`). 172 backend tests passing.

### Phase 11: Integration Testing & Release Readiness *(In Progress)*
- **Phase 11A (Environment & Integration Readiness Audit):** Completed on 11 Oct 2026. Verified clean Git working tree, backend health (172/172 tests passed), emulator reachability, and frontend production build. Identified integration gaps between frontend in-memory store and backend Firestore.
- **Phase 11B (End-to-End Live Integration Wiring):** Planned. Wires `IntakeScreen`/`caseStore.createCase` to `api.createCase`, reads `VITE_API_BASE_URL` in `api.ts`, connects `PatientDashboard` to `api.listCases()`, and conducts live multi-persona browser verification.

---

## 3. Latest Verified Test Results

| Test Category | Command / Suite | Result | Date Verified | Notes |
| :--- | :--- | :---: | :---: | :--- |
| **Backend Full Test Suite** | `.venv\Scripts\pytest.exe -v` | **172 passed, 1 warning** | 2026-10-11 | 0 failures. Harmless `StarletteDeprecationWarning` regarding httpx testclient. |
| **Frontend Production Build** | `npm run build` (`vite build`) | **Passed (0 errors)** | 2026-10-11 | 1500 modules transformed; built in 2.71s (`dist/assets/*.js` 478.22 kB). |
| **Phase 10 Security & Authorization** | `pytest tests/test_auth_and_access.py` | **9 passed** | 2026-10-11 | Cross-patient read blocked (403), unverified clinician claim blocked (403). |
| **Phase 10 Privacy Sanitization** | `pytest tests/test_phase10_sanitization.py` | **Passed** | 2026-10-11 | Indian phone numbers, Aadhaar, PAN redacted; dates and clinical ranges preserved. |
| **Phase 10 Transaction Concurrency** | `pytest tests/test_phase10_concurrency.py` | **Passed** | 2026-10-11 | Transaction retries, 2-phase availability validation, atomic completion audit. |
| **Phase 9 Consultation & Follow-Up** | `pytest tests/test_phase9_consultation_and_followup.py` | **9 passed** | 2026-10-11 | Consultation recording, terminal completed transition, clinician availability release. |
| **Phase 8 Clinician Matching & Race** | `pytest tests/test_phase8_clinician_matching.py` | **17 passed** | 2026-10-11 | Deterministic matching, decline fallback, 2-clinician concurrent claim collision (409). |
| **Phase 7 Doctor Brief Generation** | `pytest tests/test_phase7a_doctor_brief.py` + `7b` | **23 passed** | 2026-10-11 | Pydantic DoctorBrief schema, rate limiting, human edits, clinician review signoff. |
| **Phase 6 Document Processing** | `pytest tests/test_phase6*.py` | **56 passed** | 2026-10-11 | Upload validation, PDF extraction, HMAC signed URLs, multimodal OCR pipeline. |
| **Phase 5 State Machine & CRUD** | `pytest tests/test_phase5_state_machine_and_crud.py` | **9 passed** | 2026-10-11 | 100-pair state transition matrix (18 allowed, 82 rejected), idempotent creation. |
| **Live Smoke Test (Phase 9)** | `python scratch/smoke_test_phase9.py` | **Verified** | 2026-10-11 *(previous)* | Full 8-step workflow against live FastAPI, emulators, and Gemini API. |

*Note on verification status:* The test results above were rerun and confirmed in the local environment during the Phase 11A audit on 11 Oct 2026. The live smoke test was executed and verified during Phase 9 baseline certification.

---

## 4. Git and Repository Status

- **Repository Root:** `C:\Medflow`
- **Current Branch:** `main`
- **Latest Commit Hash:** `edcc5ee4a03e147b22ef05280b2a752fe638a1fe` (`edcc5ee`)
- **Latest Commit Message:** `feat(security): harden authorization, clinical data privacy, and transaction consistency`
- **Ancestry Verification:** Confirmed `edcc5ee` is `HEAD` (`git merge-base --is-ancestor edcc5ee HEAD` returned 0).
- **Working Tree State:** **Clean** (`git status --porcelain` reports 0 untracked or modified files prior to documentation update).
- **Remote Tracking:** Local `main` is **2 commits ahead of `origin/main`** (`## main...origin/main [ahead 2]`).
- **Safety Directive:** Commit history preserved; zero commits, pushes, or resets performed.

---

## 5. Current Application State

### Real Backend APIs Called by Frontend
- **Clinician Dashboard (`ClinicianDashboard.tsx`):**
  - `GET /api/v1/clinicians` (`api.listClinicians`) — fetches real clinician records.
  - `PATCH /api/v1/clinicians/{id}/availability` — updates availability status.
  - `POST /api/v1/cases/{id}/accept` — performs atomic case claim.
  - `POST /api/v1/cases/{id}/decline` — declines case and triggers rematching.
  - `GET /api/v1/clinicians/matching-pool` — fetches waiting cases.
- **Doctor Brief Review Screen (`DoctorBriefReviewScreen.tsx`):**
  - `GET /api/v1/cases/{id}/brief` — fetches generated Doctor Brief.
  - `POST /api/v1/cases/{id}/brief/generate` — triggers Gemini brief synthesis.
  - `PUT /api/v1/cases/{id}/brief` — saves human edits and increments brief version.
  - `POST /api/v1/cases/{id}/brief/approve` — records patient confirmation.
- **Document Upload Screen (`DocumentUploadScreen.tsx`):**
  - `POST /api/v1/cases/{id}/documents/upload-and-verify` — uploads files with progress tracking.
- **Consultation Workspace (`ConsultationWorkspace.tsx`):**
  - `GET /api/v1/cases/{id}/brief` — fetches brief for clinician review.
  - `GET /api/v1/cases/{id}/consultation` — retrieves existing notes.
  - `POST /api/v1/cases/{id}/brief/review` — clinician signoff with audit trail.
  - `POST /api/v1/cases/{id}/consultation` — records assessment observations and care advice.
- **Follow-Up Screen (`FollowUpScreen.tsx`):**
  - `GET /api/v1/cases/{id}/consultation` — displays consultation assessment.
  - `GET /api/v1/cases/{id}/follow-up` — fetches scheduled follow-up.
  - `POST /api/v1/cases/{id}/complete` — schedules follow-up, completes case, and releases clinician.
- **Health & Security Inspector (`App.tsx`):**
  - `GET /health` — live backend telemetry ping.
  - Live RBAC inspection probes (`/api/v1/cases`, `/auth/me`).

### Mock, Simulated & In-Memory Frontend Flows
- **Intake Screen (`IntakeScreen.tsx`):** Submits intake data to `useCaseStore().createCase()`. This generates an in-memory ID (`case_${Date.now()}_...`) and adds it to the local React store **without calling `api.createCase()`**. Consequently, the case is not persisted to backend Firestore.
- **Downstream Fallbacks:** Because cases created in the UI are not recorded on the backend, subsequent calls to `/documents/upload-and-verify`, `/brief/generate`, and `/accept` return `HTTP 404 Not Found`. Screens catch these errors and fall back to local mock state (`generateLocalFallbackBrief()`, local mock claim).
- **Patient Dashboard (`PatientDashboard.tsx`):** Renders cases from `caseStore.cases` (initialized with 3 hardcoded cases in `mockData.ts`). It does not currently call `api.listCases()`.
- **Admin Screen:** The UI header includes an `admin` persona, but no dedicated Admin/Audit screen component exists to view `/api/v1/audit/events`.

### Authentication & Telemetry State
- **Development Auth (`DEMO_AUTH_ENABLED`):** Active (`DEMO_AUTH_ENABLED=true` in `.env`). Deterministic mock tokens (`mock-token-patient-1`, `mock-token-demo_doc_patil`, `mock-token-admin`) are accepted outside production.
- **Production Guard:** `lifespan` in `app/main.py` explicitly refuses to start if `DEMO_AUTH_ENABLED` is true while `ENVIRONMENT=production`.
- **Live Endpoint Reachability (Verified 2026-10-11):**
  - FastAPI Backend (`http://127.0.0.1:8000/api/v1/health`): **Reachable (HTTP 200 OK)**.
  - Firebase Auth Emulator (`127.0.0.1:9099`): **Reachable (HTTP 200 OK)**.
  - Cloud Firestore Emulator (`127.0.0.1:8080`): **Reachable (HTTP 200 OK)**.
  - Cloud Storage Emulator (`127.0.0.1:9199`): **Reachable (TCP Port Open)**.
  - Firebase Emulator UI (`http://127.0.0.1:4000`): **Reachable (HTTP 200 OK)**.

---

## 6. Security and Privacy

### Access Control & Ownership Enforcement
- **Case Ownership Isolation:** Patients can access only cases where `case.patientId == current_user.uid`. Cross-patient requests return `HTTP 403 Forbidden`.
- **Verified Clinician Gate:** Only clinicians with `is_verified_clinician=True` and valid licenses can view matching pools, claim cases, review briefs, record consultations, or schedule follow-ups.
- **Clinician Assignment Isolation:** Clinicians cannot view clinical documents, briefs, or consultations unless assigned to the case (or viewing case overview in the `MATCHING` queue).
- **Audit Log Isolation:** Audit event retrieval (`GET /api/v1/audit/events`) is strictly restricted to callers with the `admin` role.

### Clinical Data Sanitization & Gemini Privacy Boundary
- **Pre-Transmission Sanitization:** `app/core/sanitization.py` strips direct patient identifiers before sending text to Gemini:
  - Indian mobile numbers (`+91-9876543210`, `+91 98765 43210`, `09876543210`, and 10-digit mobile numbers) replaced with `[PHONE REDACTED]`.
  - Email addresses replaced with `[EMAIL REDACTED]`.
  - 12-digit Aadhaar numbers replaced with `[AADHAAR REDACTED]`.
  - 10-character PAN identifiers replaced with `[PAN REDACTED]`.
- **Clinical Range Preservation:** Regex patterns strictly preserve ISO dates (`2026-10-11`), medication ranges (`10-20 mg`), and vital measurements (`120/80 mmHg`).
- **Safe Initialization Logging:** `app/services/gemini_service.py` logs only exception types during client initialization, preventing accidental logging of API keys or request data.
- **Privacy Notice & Limitation:** *Regex-based sanitization does not guarantee complete de-identification of unstructured free text. The platform is strictly designed for synthetic data. Names, locations, or uncommon identifiers typed into free-text symptoms may still be transmitted to Gemini.*

### Remote OCR Privacy Controls
- **Configuration Gate (`ALLOW_REMOTE_OCR`):** Remote multimodal OCR via Gemini is disabled by default unless explicitly configured (`ALLOW_REMOTE_OCR=true` in settings or environment).
- **Data Transmission Notice:** *When `ALLOW_REMOTE_OCR` is enabled, scanned PDF and image bytes are transmitted to Gemini API for text extraction. When disabled, scanned files are marked `NEEDS_OCR` without external transmission.*

### Concurrency Consistency & Atomic Transactions
- **Dual-Document Atomic Claim:** Case acceptance atomically updates the case to `ACCEPTED` and the clinician to `busy` using `@firestore_transactional`. Concurrent claims on the same case result in `HTTP 409 Conflict`.
- **Two-Phase Availability Validation on Completion:** Case completion evaluates clinician active-case count internally with fresh reads inside the Firestore transaction retry loop. The clinician is released to `available` only if no other active cases exist, preventing race collisions with concurrent case assignments.
- **Atomic Audit Emission:** The `CASE_COMPLETED` audit event is written within the same Firestore transaction as the case status transition, guaranteeing audit reliability.

---

## 7. Known Limitations and Risks

### Confirmed Issues & Technical Gaps
1. **Intake-to-Backend Disconnect:** Resolved in Phase 11B. `IntakeScreen` and `caseStore.createCase()` asynchronously invoke `api.createCase()`, transmitting intake clinical fields under `metadata` and an idempotency key.
2. **Hardcoded API Base URL:** Resolved in Phase 11B. `frontend/src/services/api.ts` uses `import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1'`.
3. **Patient Dashboard Sync:** Resolved in Phase 11B. `PatientDashboard` fetches real cases from `api.listCases(patientId)` on mount.
4. **Doctor Brief Generation Integration & Silent Fallbacks:** Resolved in Phase 11C Task 1. Frontend calls `api.generateBrief(caseId)` and `api.getBrief(caseId)` using canonical case IDs. `generateLocalFallbackBrief` was completely removed; failure states display actionable error cards with retry controls without fabricating data.
5. **Doctor Brief Human Editing & Approval Integration:** Pending Phase 11C Task 2. Frontend brief review screen currently uses local state for brief editing and approval mutations before case submission.
6. **Clinician Matching Integration:** Pending Phase 11C Task 3. Post-approval transition to clinician matching queue needs end-to-end integration with the backend matching service.
7. **Missing Admin / Auditor Screen (Medium):** The frontend header allows selecting the `admin` persona, but no screen exists to inspect `/api/v1/audit/events`.
8. **In-Memory Rate Limiting (Low):** Doctor Brief generation per-case rate limiting (minimum 1.0s interval) is tracked in server memory and resets on backend restart.
9. **No Live Telephony / Communication Channels:** All consultations are text-based simulations; live WebRTC audio/video and SMS/WhatsApp/email alerts are intentionally out of scope for this hackathon MVP.

### Items Needing Verification
1. **Real-Gemini Multimodal OCR on Live Documents:** Verified via mock unit tests (`test_phase6e_gemini_ocr_extraction.py`), but awaiting a live end-to-end extraction test with user-provided `GEMINI_API_KEY`.
2. **Live Browser HMAC Streaming:** HMAC stream generation verified in unit tests (`test_phase6d_signed_url_access.py`), but live browser audio/document streaming on the storage emulator has not been verified interactively.
3. **Automated Browser E2E Suite:** Multi-persona workflows have been tested manually and via python smoke scripts, but there is no automated Playwright or Cypress suite running against the build.

---

## 8. Current Implementation & Next Steps

### Completed: Phase 11B — Live Patient Case Creation & Dashboard Integration
- **Backend Schema & Service:** Added `CaseListResponse` schema; updated `CaseService.list_cases` with optional `patient_id` filter and `CaseResponse` model mapping.
- **Backend Case Router:** Implemented `POST /api/v1/cases` and `GET /api/v1/cases` with strict RBAC: patients can create cases and list only their own cases; cross-patient listings are rejected with 403 Forbidden.
- **Frontend Wiring:** `api.createCase` and `api.listCases` wired to backend; `caseStore.createCase` creates real backend cases and updates store; `PatientDashboard` fetches cases via API with loading and empty states.
- **Test Coverage:** Added 7 focused tests in `backend/tests/test_phase11b_patient_intake_and_dashboard.py` (all passed).

### Completed: Phase 11C — Task 1: Doctor Brief Generation & Retrieval Integration
- **Backend Endpoints Verified:**
  - `POST /api/v1/cases/{caseId}/brief/generate`: Enforces case ownership (patient owner only in `DRAFT` status), rate limiting (1.0s interval), Gemini prompt generation, and returns canonical `DoctorBrief`.
  - `GET /api/v1/cases/{caseId}/brief`: Enforces strict RBAC (patient owner, admin, or assigned clinician in `ACCEPTED`/`IN_CONSULTATION`/`COMPLETED` status).
- **Frontend Wiring:**
  - `api.generateBrief(caseId, confirmRegenerate)` and `api.getBrief(caseId)` enhanced with HTTP status reporting and error payload extraction.
  - `caseStore.generateDoctorBrief` and `caseStore.getDoctorBrief` converted to async backend API calls using canonical case IDs.
  - `DoctorBriefReviewScreen.tsx`: Removed `generateLocalFallbackBrief` and `isUsingFallback` state completely. Implemented clear loading state and actionable categorized error state (403 Forbidden, 429 Rate Limit, 404 Not Found, Network Errors) with retry and navigation buttons. Never synthesizes fallback briefs on error.
  - `App.tsx`: Removed obsolete synchronous pre-generation call from document upload screen to let `DoctorBriefReviewScreen` manage loading and error lifecycles cleanly.
- **Test Coverage & Verification:**
  - Added 10 focused tests in `backend/tests/test_phase11c_doctor_brief_generation.py`:
    1. Canonical contract generation success
    2. Brief retrieval by owning patient
    3. 404 for ungenerated brief
    4. 403 cross-patient generation rejection
    5. 403 cross-patient retrieval rejection
    6. 403 unassigned clinician access rejection
    7. 401 unauthenticated request rejection
    8. 404 non-existent case rejection
    9. Graceful backend generation failure without 500 crash (recording `validationWarnings`)
    10. Per-case generation rate limit enforcement (HTTP 429)
  - Full backend test suite: **189 passed, 0 failed** in 18.55s.
  - Frontend build: `tsc && vite build` succeeded with 0 errors in 2.98s.

### Remaining Phase 11C Tasks

#### Task 2: Doctor Brief Human Editing & Patient Approval Integration
1. Connect `PUT /api/v1/cases/{caseId}/brief` in `caseStore` and `DoctorBriefReviewScreen`:
   - Patient edits brief fields during review (permitted only while in `DRAFT` status).
   - Updates version and records edit history on the backend.
2. Connect `POST /api/v1/cases/{caseId}/brief/approve`:
   - Patient approves the brief, transitioning brief status to `PATIENT_APPROVED`.
3. Add verification tests for editing permissions, approval state transitions, and audit trail.

#### Task 3: Clinician Matching Workflow Integration
1. Connect post-approval submission to backend case state transition:
   - Case transitions from `DRAFT` to `SUBMITTED` -> `MATCHING`.
2. Connect `POST /api/v1/cases/{caseId}/match` or clinician matching queue retrieval.
3. Verify matching pool updates and clinician claim workflow in the clinician dashboard.


---
## Status update 11 Oct 2026 17:04 (supersedes earlier wording)

### Where the project stands
- Backend: Phases 1 to 10 committed and pushed (HEAD 51f8faa, tag phase-10-fakes-only). 189 backend tests pass; most use a fake Gemini client and fake or in-memory Firestore/Storage.
- Frontend: production build passes (`tsc && vite build`).
- Checked manually against the real Firebase emulators by the project owner: Firestore persistence across a backend restart; Storage bucket `medbridge-ai-documents` receives uploads (tag phase-6c-fix-verified).
- Agent-run only (owner review pending): live Gemini OCR and Doctor Brief generation on one synthetic scan; the 2-clinician concurrent-accept test; API smoke test of the golden workflow (uses mock-token auth and a stub PDF, does not check brief content).

### Corrections to earlier wording
- Any earlier "Completed & Verified" line for Phases 7, 8 and 9 means: backend tests pass plus an agent-run API smoke test. It does NOT mean the UI was clicked through. The browser agent failed (Playwright download error).
- The UI uses a demo persona switcher with mock tokens (gated by DEMO_AUTH_ENABLED, off by default, refused when ENVIRONMENT=production). There is no Firebase sign-in in the UI. The backend does verify real Firebase ID tokens and role claims.

### UNVERIFIED
- Browser click-through of the golden workflow (desktop and 360px).
- 6d stream endpoint on the real emulator and the uvicorn access-log filter.
- Blurry-scan OCR and conflicting-document behaviour of the real model.
- Real-Gemini behaviour has been checked on ONE synthetic scan only.

### Known issues to fix or disclose
- Approve handler in App.tsx does not await the backend result, and the button is not guarded against double clicks. It switches screens regardless of success.
- caseStore.ts sets status MATCHING locally instead of from the server response.
- Phase 4 security tester widget in App.tsx must be hidden outside dev mode.
- Rate limit and DRAFT check use in-process locks (single instance only).
- Names typed in free text are not removed before text is sent to Gemini; synthetic data only.

### Implemented / Simulated / Planned
- IMPLEMENTED: validated uploads, OCR and Doctor Brief with human review, case state machine, clinician matching, atomic accept, consultation notes, completion and follow-up record, audit events.
- SIMULATED: demo clinicians, text-based consultation, persona switching.
- PLANNED: Firebase sign-in in the UI, voice input, notifications, video, low-connectivity sync, Cloud Run / Firebase Hosting deployment.
