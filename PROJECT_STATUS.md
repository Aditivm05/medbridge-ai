# MedBridge AI — Project Status Tracker

## 1. Project Summary
MedBridge AI is an AI-powered urgent healthcare care-coordination hackathon MVP. It bridges patients with urgent concerns to verified clinicians by generating a structured, human-reviewed Doctor Brief and facilitating simulated consultations and follow-ups. It enforces strict safety boundaries: care coordination only, no autonomous diagnosis or prescription, immediate zero-network emergency guidance (112 India), and clear `[DEMO / SIMULATED]` labels.

## 2. Phase Progress (Canonical Numbering)
- [x] **Phase 1: Architecture, Data Modeling, Tooling & Safety Blueprint** *(Completed)*
- [x] **Phase 2: Full-Stack Scaffolding, README, Landing Page & GET /health** *(Completed & Verified)*
- [x] **Phase 3: All 7 Interactive Screens, Synthetic Data, Mock Services & Responsive Layouts** *(Completed & Verified)*
- [x] **Phase 4: Firebase Auth (Emulator-First), Role Custom Claims, Protected Routes & Ownership Gates** *(Completed & Verified)*
- [x] **Phase 5: Database and Case Management** *(Completed. Persistence verified on real emulator (10 Oct 2026); transaction acceptance VERIFIED in Phase 8.)*
- [ ] **Phase 6: Documents and Voice** *(Not fully verified. Voice input = PLANNED. Real-Gemini OCR, 6d stream endpoint on real emulator, and uvicorn log filter UNVERIFIED)*
  - **Phase 6a**: Upload intent, validation (mime, magic bytes, size, file count) — **Status**: Completed | **Tag**: `phase-6a-complete`
  - **Phase 6b**: Frontend Document Upload Screen with drag-and-drop & XHR upload progress — **Status**: Completed | **Tag**: `phase-6b-complete`
  - **Phase 6c**: Text-based PDF extraction via pypdf & low-text detection — **Status**: Completed | **Tag**: `phase-6c-complete`
  - **Phase 6c-fix**: Firestore document persistence and emulator storage bucket auto-creation — **Status**: Completed | **Tags**: `phase-6c-fix-fakes-only`, `phase-6c-fix-verified`
  - **Phase 6d**: Document access via short-lived HMAC stream URLs and signed URLs — **Status**: Completed | **Tag**: `phase-6d-fakes-only`
  - **Phase 6e**: Gemini multimodal OCR for scanned PDFs and images — **Status**: Completed (mocked tests only) | **Tag**: `phase-6e-fakes-only`
  - **Voice Input**: Speech-to-text / voice intake — **Status**: PLANNED
- [x] **Phase 7: AI Doctor Brief (Gemini)** *(Completed & Verified)*
  - **Phase 7a**: AI Doctor Brief backend: strict Pydantic DoctorBrief schema (no diagnosis/prescription), Gemini generation service with fallback skeleton, document reference validation, structured conflicts list, brief endpoints (`generate`, `get`, `put`, `approve`, `review`), lifecycle (`DRAFT_AI` -> `PATIENT_APPROVED` -> `CLINICIAN_REVIEWED`), version snapshots, and rate limiting — **Status**: Completed | **Verified**: Backend test suite (16 tests) & live smoke test.
  - **Phase 7b**: Clinician Review Integration: backend verification and authorization gates on `POST /cases/{case_id}/brief/review`, verified clinician role and assignment checks, duplicate review blocking, immutable audit trail logging — **Status**: Completed | **Verified**: Backend test suite (7 tests) & live smoke test.
  - **Phase 7c**: Frontend Doctor Brief review screen & Consultation Workspace: real endpoint wiring (`generate`, `get`, `put`, `approve`, `review`), separation of patient-reported and document-extracted facts, source labels (`PATIENT_REPORTED`, `PDF_TEXT`, `AI_EXTRACTED`), prominent missing info & clarification questions, side-by-side unresolved conflicts, permanent safety banner, interactive edit modal invalidating approval, submit button enabled only on approval — **Status**: Completed | **Verified**: Frontend production build (`tsc && vite build`) & ConsultationWorkspace integration.
  - **Live Integration Smoke Test**: End-to-end verified with running backend, Firebase emulators, and live Gemini API (`gemini-3.8-flash`) on 11 Oct 2026.
- [x] **Phase 8: Clinician Matching, Concurrency & Lifecycle** *(Completed & Verified)*
  - **Phase 8a**: Clinician seeding & personas: Seeded 5 demo clinicians in Firestore with explicit `[DEMO / SIMULATED]` labels, `isDemo: true`, specialty, language tags, and verification status (`verified`, `pending`).
  - **Phase 8b**: Deterministic Matching Engine: Verification gate, availability filter (`available`), patient language match, and specialty preference scoring with deterministic tie-breaking. Automatic fallback to `NO_CLINICIAN_AVAILABLE` with `CASE_NO_CLINICIAN` audit trail logging when no matching clinician is available or when pool is exhausted.
  - **Phase 8c**: Atomic Case Acceptance & Concurrency Locking: Firestore transaction (`@firestore_transactional`) enforcing dual-document atomic update on both `cases/{case_id}` and `clinicians/{clinician_id}`. Race collision detection raises `CaseConflictError` (HTTP 409) and logs `CONFLICT_DETECTED` audit event. Caller identity strictly enforced from authenticated token (`current_user.uid`), blocking unverified clinicians (HTTP 403) and arbitrary client-supplied IDs.
  - **Phase 8d**: Clinician Decline & Availability: Decline endpoint (`POST /cases/{case_id}/decline`) updating case history and falling back to remaining eligible clinicians. Availability endpoint (`PATCH /clinicians/{id}/availability`) and matching pool retrieval (`GET /clinicians/matching-pool`).
  - **Phase 8e**: Frontend Integration: `ClinicianDashboard.tsx` connected to real backend endpoints for matching pool queue, live accept/decline actions, real-time availability toggle, race collision simulation, and authenticated persona switching via `authService.switchUser`.
  - **Verification**: Complete backend test suite (17 Phase 8 tests, 121/121 total passing) & live Firestore emulator smoke test verifying 2-clinician simultaneous race collision (1 winner HTTP 200, 1 loser HTTP 409).
- [x] **Phase 9: Consultation Workspace, Case Completion & Follow-Up** *(Completed & Verified)*
  - **Phase 9a**: Consultation Workspace: Text-based consultation interface explicitly labelled `[DEMO / SIMULATED]`. Side-by-side / tabs layout for reviewing AI Doctor Brief and attached source documents with OCR extracted previews.
  - **Phase 9b**: Clinician Notes & Supportive Care Advice: Pydantic schemas (`ConsultationCreate`, `ConsultationResponse`) enforcing min length (10 chars), max length (5000 / 2000 chars), and strict non-prescription supportive guidance disclaimer.
  - **Phase 9c**: Case State Transitions & Lifecycle: Status transitions `ACCEPTED` -> `IN_CONSULTATION` on consultation recording, and `IN_CONSULTATION` -> terminal `COMPLETED` on case completion. Terminal state protection: zero outgoing transitions permitted from `COMPLETED`.
  - **Phase 9d**: Follow-Up Scheduling & Clinician Release: Follow-up schema (`FollowUpCreate`, `FollowUpResponse`) with `required` boolean, `recommendedDate` (YYYY-MM-DD), `instructions` with emergency red-flag safety directives, and `status: "scheduled"`. Case completion atomically sets `completedAt` and releases assigned clinician availability back to `available` with `currentCaseId: None`.
  - **Phase 9e**: Patient Case History & Follow-Up View: `PatientDashboard.tsx` and `FollowUpScreen.tsx` display completed cases with green completion badges, conclusion timestamps, recorded clinician consultation notes, and scheduled follow-up directives with read-only form controls. Cross-patient reads securely blocked (HTTP 403 Forbidden).
  - **Phase 9f**: Zero Fake Notifications: Confirmed zero fake notifications, mock toasts, or simulated SMS alerts across the entire workflow.
  - **Phase 9g**: Verification & Tests:
    - 9 automated Phase 9 backend tests in `tests/test_phase9_consultation_and_followup.py` and production auth tests in `tests/test_auth_and_access.py` passing.
    - Frontend production build (`tsc && vite build`) passing with zero errors.
    - Live end-to-end integration smoke test (`smoke_test_phase9.py`) executed against running FastAPI backend, Firebase emulators, and live Gemini AI (`gemini-3.8-flash`), verifying all 8 steps of the Golden Workflow. Note: The Phase 9 smoke test uses mock-token auth, a stub PDF, and does not check brief content.

## 3. Files Created Across Phases 1 - 9
### Architecture, Docs & Infrastructure
- `docs/ARCHITECTURE.md`: Complete system architecture, data models for 10 collections, state machine table, concurrency transaction rules, and REST API blueprint.
- `README.md`: Comprehensive beginner-friendly setup guide with click-by-click commands, architecture diagram, and expected outputs.
- `PROJECT_STATUS.md`: Project status, environment variables, phase tracking, and milestones.
- `firebase.json`: Firebase emulator configuration (Auth: 9099, Firestore: 8080, Storage: 9199, UI: 4000).
- `firebase/firestore.rules`: Deny-by-default Firestore security rules.
- `firebase/firestore.indexes.json`: Firestore index configuration.
- `firebase/storage.rules`: Deny-by-default Storage security rules.
- `firebase/seed_data.json`: Seed demo clinicians with `[DEMO / SIMULATED]` markers and `isDemo: true`.

### Backend (`backend/`)
- `backend/requirements.txt`: Backend dependencies (FastAPI, Pydantic, google-genai, firebase-admin, pytest, etc.).
- `backend/app/main.py`: FastAPI application entrypoint with root `GET /health`, CORS, latency tracking, and API v1 router mounting.
- `backend/app/core/config.py`: Application settings using Pydantic Settings.
- `backend/app/core/auth.py`: Firebase Auth token verification, `AuthenticatedUser` model, custom claims manager, role guards (`require_role`, `require_verified_clinician`), and case ownership enforcement (`check_case_ownership`).
- `backend/app/core/state_machine.py`: Centralized Case State Machine with transition validators across 10 states and 18 allowed transitions.
- `backend/app/core/firestore_client.py`: Centralized Firestore and Storage client factory, emulator connection verification (fail-fast), and in-memory `FakeFirestoreClient` / `FakeStorageClient` for offline pytest suite.
- `backend/app/models/firestore_models.py`: Firestore snapshot serializers, Timestamp converters, and enum parsers.
- `backend/app/schemas/`: Pydantic schemas for `case.py` (with `CaseUpdate` and `CaseSubmitRequest`), `clinician.py` (matching, availability, accept/decline), `audit.py` (full lifecycle events), `user.py`, `patient.py`, `document.py`, `doctor_brief.py`, `consultation.py`.
- `backend/app/services/case_service.py`: Service layer with complete Case CRUD, draft-only update guard, idempotent submit, and atomic concurrency locking via Firestore transactions (`accept_case_atomic`).
- `backend/app/services/clinician_service.py`: Clinician seed service, multi-attribute matching algorithm (verification, availability, language, specialty scoring, queue ordering), decline handler with exhaustion fallback, and availability manager.
- `backend/app/services/document_service.py`: Extraction service per-page (`pypdf`), low-text `NEEDS_OCR` tagging, encrypted/corrupted/page-limit safeguards (30 pages max), audit events, and Phase 6e Gemini multimodal OCR pipeline.
- `backend/app/services/gemini_service.py`: Multimodal Gemini OCR service with strict data-only prompt, Pydantic validation, exponential backoff on 429/5xx, and synthetic data notices.
- `backend/app/services/brief_service.py`: AI Doctor Brief service using Google GenAI SDK, strict data-only prompt, Pydantic structured output, conflict detection, rate limiting, and fallback skeleton.
- `backend/app/services/audit_service.py`: Append-only audit logger.
- `backend/app/api/routers/`: Routers for `health.py`, `auth.py`, `cases.py` (CRUD, submit, match, accept, decline, status), `clinicians.py` (seed, list, matching pool, availability), `documents.py` (upload-and-verify, background extraction, OCR trigger, text retrieval), `briefs.py` (Doctor Brief generate, read, edit, patient approve, clinician review), `audit.py` (with `/audit/cases/{case_id}`).
- `backend/app/services/consultation_service.py`: Consultation and Follow-up service layer handling notes recording, `IN_CONSULTATION` transition, case completion (`COMPLETED`), follow-up scheduling, and clinician availability release.
- `backend/app/api/routers/consultations.py`: Consultation endpoints (`POST /cases/{id}/consultation`, `GET /cases/{id}/consultation`, `POST /cases/{id}/complete`, `GET /cases/{id}/follow-up`).
- `backend/app/schemas/consultation.py`: Pydantic schemas for `ConsultationCreate`, `ConsultationResponse`, `FollowUpCreate`, `FollowUpResponse`.
- `backend/tests/test_phase9_consultation_and_followup.py`: Automated Phase 9 test suite (9 tests: consultation recording, unassigned clinician 403, patient role 403, unverified clinician 403, validation constraints, case completion & follow-up, terminal state protection, patient reading consultation/follow-up, cross-patient 403).
- `scratch/smoke_test_phase9.py`: Live integration smoke test verifying full 8-step Golden Workflow against live FastAPI backend, Firebase emulators, and live Gemini AI.
- `backend/tests/test_phase8_clinician_matching.py`: Automated Phase 8 clinician matching and concurrency test suite (17 tests).
- `backend/tests/test_phase7b_clinician_review.py`: Automated Phase 7b Clinician Review test suite (7 tests).
- `backend/tests/test_phase7a_doctor_brief.py`: Automated Phase 7a Doctor Brief test suite (16 tests).
- `backend/tests/test_phase6e_gemini_ocr_extraction.py`: Automated Phase 6e OCR test suite (13 tests).
- `backend/tests/test_phase6d_signed_url_access.py`: Automated signed URL & streaming access test suite (19 tests).
- `backend/tests/test_phase6c_pdf_text_extraction.py`: Automated PDF text extraction test suite (11 tests).
- `backend/tests/test_phase6a_document_upload.py`: Automated upload validation test suite (13 tests).
- `backend/tests/test_phase5_state_machine_and_crud.py`: Exhaustive 100-pair state transition matrix test (18 valid, 82 invalid), CRUD lifecycle, idempotency, and Firestore models.
- `backend/tests/test_auth_and_access.py`: Pytest automated suite proving 401 unauth, patient ownership isolation (403), unverified clinician claim block (403), verified clinician acceptance (200), and custom claims inspection.
- `backend/tests/test_case_flow.py`: Pytest automated test suite (health, state transitions, idempotency, magic bytes, race condition 409 conflict).
- `backend/pytest.ini`: Pytest configuration.
- `backend/conftest.py`, `backend/app/__init__.py`, `backend/.venv/.../sitecustomize.py`: Python 3.10.0 ForwardRef compatibility shims.

### Frontend Components & Security UI (`frontend/`)
- `frontend/src/types/index.ts`: TypeScript domain definitions across all 7 screens including `ConsultationData`, `FollowUpData`, `ClinicianData`.
- `frontend/src/vite-env.d.ts`: Standard Vite client type definitions.
- `frontend/src/services/authService.ts`: Active authentication context, Firebase emulator token provider, and persona switcher with all demo clinicians (`demo_doc_patil`, `demo_doc_sharma`, `demo_doc_deshmukh`, `demo_doc_pending`, `demo_doc_offline`).
- `frontend/src/services/api.ts`: Authenticated fetch wrapper injecting `Authorization: Bearer <token>` and API helpers (`saveConsultation`, `getConsultation`, `completeCaseWithFollowUp`, `getFollowUp`, `getMatchingPool`, `acceptCase`, `declineCase`, `matchCase`, `listClinicians`, `updateClinicianAvailability`).
- `frontend/src/services/mockData.ts`: Realistic synthetic data with all 5 demo clinicians labelled `[DEMO / SIMULATED]`.
- `frontend/src/services/caseStore.ts`: Reactive state management store with `recordConsultationNotes`, `completeCaseAndFollowUp`, `claimCaseAtomic`, `declineCase`, and `syncMatchingPool`.
- `frontend/src/components/screens/ConsultationWorkspace.tsx`: Text-based Consultation Workspace labelled `[DEMO / SIMULATED]`, Doctor Brief and Documents tabs, clinician observations, provisional care advice (non-prescription), async save loading state.
- `frontend/src/components/screens/FollowUpScreen.tsx`: Follow-up scheduling screen, emergency red-flag directives, async case completion, read-only completed summary view with consultation assessment record.
- `frontend/src/components/screens/PatientDashboard.tsx`: Patient dashboard with active/completed filters, case history list, completed case view with consultation and follow-up directives, zero fake notifications.
- `frontend/src/i18n/translations.ts`: Multilingual dictionary (English, Hindi, Marathi) with complete labels for all 7 screens including claim, decline, and conflict keys.
- `frontend/src/components/common/EmergencyBanner.tsx`: Static zero-network 112 emergency guidance.
- `frontend/src/components/common/SimulationBadge.tsx`: Visual `[DEMO / SIMULATED]` badge.
- `frontend/src/components/common/StatusBadge.tsx`: Accessible status badges across 10 case states.
- `frontend/src/components/common/ConnectionIndicator.tsx`: Network & emulator telemetry badge.
- `frontend/src/components/common/Header.tsx`: Multilingual, role-switching responsive header with active auth claims badge.
- `frontend/src/components/screens/PatientDashboard.tsx`: Screen 1 — Patient requests list, filter tabs, empty states, and new request action.
- `frontend/src/components/screens/IntakeScreen.tsx`: Screen 2 — Rapid clinical intake, urgency selector, common symptom tags, emergency triggers.
- `frontend/src/components/screens/DocumentUploadScreen.tsx`: Screen 3 — File dropzone, 1-click synthetic reports (CBC, Ultrasound), validation rules.
- `frontend/src/components/screens/DoctorBriefReviewScreen.tsx`: Screen 4 — AI Doctor Brief review gate, objective facts table with preserved units, unknowns, edit modal.
- `frontend/src/components/screens/ClinicianDashboard.tsx`: Screen 5 — Clinician matching pool connected to real backend API, active doctor profile switcher with auth token sync, clinician availability switcher (`available`/`busy`/`offline`), decline action, race collision simulation, and atomic claim action.
- `frontend/src/components/screens/ConsultationWorkspace.tsx`: Screen 6 — Side-by-side workspace: brief & lab report inspector + assessment notes & care advice form.
- `frontend/src/components/screens/FollowUpScreen.tsx`: Screen 7 — Follow-up date scheduling, emergency warning sign directives, case finalization summary.
- `frontend/src/App.tsx`: Main application router with Golden Workflow stepper, health widget, dev-only Phase 4 Security Tester widget, and wired Phase 8 matching pool actions.
- `frontend/scripts/capture_screenshots.cjs`: Automated screenshot generation script capturing all 7 screens at 1280px desktop and 360px mobile viewports.
- `frontend/scripts/capture_phase4_screenshot.cjs`: Automated security verification script capturing browser rejection toasts for cross-patient access and unverified clinician claim.

## 4. Verified Milestones & Test Outputs
- **Automated Test Suite (133/133 Passing):**
  - `test_phase9_consultation_and_followup.py` (9 tests) -> ALL PASSED
  - `test_phase8_clinician_matching.py` (17 tests) -> ALL PASSED
    - `test_seeded_demo_clinicians_have_explicit_demo_labels` -> PASSED (explicit `[DEMO / SIMULATED]` labels, `isDemo: true`)
    - `test_seed_endpoint_is_idempotent` -> PASSED (re-running seed returns 200 without duplication)
    - `test_matching_excludes_unverified_clinicians` -> PASSED (pending status excluded from matching pool)
    - `test_matching_excludes_offline_and_busy_clinicians` -> PASSED (only available status eligible)
    - `test_matching_filters_by_patient_language` -> PASSED (clinicians lacking patient language excluded)
    - `test_matching_specialty_preference_and_fallback_scoring` -> PASSED (specialty preference prioritized, general fallback scored lower)
    - `test_deterministic_queue_ordering_on_score_ties` -> PASSED (deterministic tie-breaking by ID)
    - `test_no_clinician_available_transitions_status_and_logs_audit` -> PASSED (unmatched case transitions to `NO_CLINICIAN_AVAILABLE` with `CASE_NO_CLINICIAN` audit event)
    - `test_retry_matching_from_no_clinician_available` -> PASSED (re-queuing allowed from `NO_CLINICIAN_AVAILABLE`)
    - `test_case_cancellation_from_no_clinician_available` -> PASSED (cancellation allowed from `NO_CLINICIAN_AVAILABLE`)
    - `test_atomic_accept_updates_case_and_clinician_documents` -> PASSED (atomic dual-document transaction: case assigned and clinician marked busy)
    - `test_decline_case_excludes_clinician_and_falls_back` -> PASSED (declining clinician excluded from next candidate pool)
    - `test_decline_exhaustion_transitions_to_no_clinician_available` -> PASSED (exhausted pool automatically transitions case to `NO_CLINICIAN_AVAILABLE`)
    - `test_concurrency_race_condition_two_simultaneous_accepts` -> PASSED (two simultaneous accepts: 1 succeeds 200, 1 collides 409 Conflict with `CONFLICT_DETECTED` audit event)
    - `test_unverified_clinician_cannot_accept_case` -> PASSED (unverified clinician claim raises 403 Forbidden)
    - `test_patient_cannot_accept_case` -> PASSED (patient role raises 403 Forbidden)
    - `test_unverified_clinician_cannot_decline_case` -> PASSED (unverified clinician decline raises 403 Forbidden)
  - `test_phase7b_clinician_review.py` (7 tests) -> ALL PASSED
  - `test_phase7a_doctor_brief.py` (16 tests) -> ALL PASSED
  - `test_phase6e_gemini_ocr_extraction.py` (13 tests) -> ALL PASSED
  - `test_phase6d_signed_url_access.py` (19 tests) -> ALL PASSED
  - `test_phase6c_pdf_text_extraction.py` (11 tests) -> ALL PASSED
  - `test_phase6a_document_upload.py` (13 tests) -> ALL PASSED
  - `test_phase5_state_machine_and_crud.py` (9 tests) -> ALL PASSED
  - `test_auth_and_access.py` (9 tests) -> ALL PASSED
  - `test_case_flow.py` (6 tests) -> ALL PASSED

- **Phase 9 Live Integration Smoke Test (11 Oct 2026 — VERIFIED):**
  - **Environment**: FastAPI backend running on port 8000; Firebase Auth (9099), Firestore (8080), Storage (9199) emulators active; live Gemini API (`gemini-3.8-flash`).
  - **Scope & Limitations**: The Phase 9 smoke test uses mock-token auth, a stub PDF, and does not check brief content.
  - **Full Golden Workflow Executed (`backend/scripts/smoke_test_phase9.py`)**:
    1. Patient submits intake request (DRAFT).
    2. Document uploaded and verified (stub PDF with valid minimal structure).
    3. AI Doctor Brief generated with Gemini.
    4. Patient approves Doctor Brief (SUBMITTED -> MATCHING).
    5. Seeded DEMO clinician (Dr. Rajesh Patil) accepts case (ACCEPTED).
    6. Clinician reviews Doctor Brief and records consultation notes (IN_CONSULTATION).
    7. Clinician schedules follow-up and completes case (COMPLETED, clinician released back to available).
    8. Patient retrieves completed case history, consultation record, and follow-up directives.

- **Phase 8 Live Integration Smoke Test (11 Oct 2026 — VERIFIED):**
  - **Environment**: FastAPI backend running on port 8000; Firebase Auth (9099), Firestore (8080), Storage (9199) emulators active.
  - **Seeding Verification**: Invoked `POST /api/v1/clinicians/seed`; verified 5 demo clinicians created with `[DEMO / SIMULATED]` labels and `isDemo: true`.
  - **Simultaneous Concurrency Race Collision**: Dispatched 2 simultaneous requests from different verified clinicians to `POST /cases/{case_id}/accept` on the same case in the Firestore emulator:
    - Clinician A succeeded with HTTP 200 (case status `ACCEPTED`, `assignedClinicianId: demo_doc_patil`, clinician availability `busy`).
    - Clinician B received HTTP 409 Conflict with message indicating case was already assigned.
    - Verified audit trail recorded `CONFLICT_DETECTED` with collision details.
  - **Unsupported Language & Pool Exhaustion**: Case created with unsupported language (`de`) transitioned to `NO_CLINICIAN_AVAILABLE` with `CASE_NO_CLINICIAN` audit event.
  - **Decline & Fallback**: Clinician declined case via `POST /cases/{case_id}/decline`; remaining pool re-evaluated and subsequently transitioned to `NO_CLINICIAN_AVAILABLE` upon exhaustion.

- **Phase 7 Live Integration Smoke Test (11 Oct 2026 — VERIFIED):**
  - **Environment**: FastAPI backend on port 8000 healthy; Firebase Auth (9099), Firestore (8080), Storage (9199) reachable; Gemini API key configured with model `gemini-3.8-flash`.
  - **Live Gemini Brief Generation**: Created synthetic case in DRAFT; invoked live `POST /cases/{id}/brief/generate`; verified strict schema conformance, verbatim chief complaint preservation, zero diagnosis/prescription fields, and structured vitals/gaps/questions.
  - **Patient Review & Invalidation**: Updated brief via `PUT /cases/{id}/brief`; verified previous approval invalidated (`briefStatus: EDITED`, version incremented); approved via `POST /cases/{id}/brief/approve` (`briefStatus: PATIENT_APPROVED`); verified persisted state retained across reload (`GET /cases/{id}/brief`).
  - **Clinician Review Integration**: Case transitioned to `SUBMITTED` -> `MATCHING` -> `ACCEPTED` by assigned verified clinician; verified unverified clinician blocked (403), unassigned clinician blocked (403), patient review blocked (403); assigned clinician review signed off with notes (`POST /cases/{id}/brief/review`, `briefStatus: CLINICIAN_REVIEWED`); duplicate review blocked (400).
  - **Audit Trail**: Full lifecycle audit trail verified in Firestore: `['CASE_CREATED', 'CASE_UPDATED', 'BRIEF_GENERATED', 'BRIEF_EDITED', 'BRIEF_APPROVED', 'CASE_SUBMITTED', 'CASE_MATCHING_ENQUEUED', 'CASE_ACCEPTED', 'BRIEF_CLINICIAN_REVIEWED']`.
  - **Scope Distinction**: Live integration verified against live running backend server, Firebase emulators, and Google Gemini API. Controlled failure handling (timeout, 429/5xx backoff, 400 fail-fast, malformed JSON fallback) verified via unit tests with mocks. Note: Browser-level end-to-end automation was not executed in this headless smoke test; API and component integration were verified via production build and live API execution.

- **Phase 6 Verification Status:**
  - **Real-Gemini multimodal extraction**: **`UNVERIFIED`** *(awaiting manual user test run with real GEMINI_API_KEY)*.
  - **Stream endpoint on the real emulator**: **`UNVERIFIED`** *(awaiting manual user test run)*.
  - **Uvicorn log filter**: **`UNVERIFIED`** *(awaiting manual inspection on live server)*.
  - **Firestore persistence**: **VERIFIED** *(manual, emulator, 10 Oct 2026: case survived a backend restart)*.
  - **Storage upload**: **VERIFIED** *(manual, emulator, 10 Oct 2026: bucket medbridge-ai-documents with cases/ folder seen in emulator UI)*.
  - **Firestore transaction acceptance**: **VERIFIED** *(11 Oct 2026: verified in Phase 8 via `test_atomic_accept_updates_case_and_clinician_documents` and live concurrency race test on Firestore emulator)*.
  - **Phase 12 IAM signBlob production signing**: **`UNTESTED`** *(documented in ARCHITECTURE.md for production Cloud Run deployment)*.

- **Frontend Production Build:** `tsc && vite build` succeeded with returncode 0 (`1500 modules transformed`, zero TS errors, built in 2.48s).

## 5. Next Steps
- Phase 8 (Clinician Matching, Concurrency & Lifecycle) is complete and verified.
- Next implementation target: Phase 9 (Consultation Workspace & Follow-Up lifecycle completion).
- Do NOT push to remote without user instruction.

## 6. Known Limitations & Tech Debt

### Known Limitations
1. **Demo Clinicians are Simulated**: All seeded clinicians (`Dr. Rajesh Patil`, `Dr. Ananya Sharma`, `Dr. Priya Deshmukh`, `Dr. Vikram Malhotra`, `Dr. Sneha Kulkarni`) are synthetic test personas explicitly tagged with `[DEMO / SIMULATED]` and `isDemo: true`.
2. **Matching Queue is In-Process / Query-Based**: The matching algorithm executes queries against Firestore rather than using a distributed message broker or Redis queue. This is appropriate for the hackathon MVP but would be backed by Cloud Tasks or Pub/Sub in high-volume production.
3. **Brief generation rate limit is in memory**: Brief generation rate limit is in memory (resets on restart, not shared across instances).
4. **Names typed in free text are not removed before sending**: Patient ID, patient name, case ID, and filenames are strictly excluded, but any names typed directly into free-text fields (such as chief complaint or history) are not filtered before sending to Gemini; platform intended for synthetic data only.
5. **DRAFT check and case updates use an in-process lock**: The status check and metadata updates in `case_service.py` (`update_case`) use an in-process threading lock (`self._lock`) rather than a distributed lock or database transaction; safe for single-instance deployment, but concurrent updates across multiple server instances would require Firestore transactions.

### Technical Debt & Known Issues
1. **Starlette Deprecation Warning**: Pytest reports `.venv\lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using 'httpx' with 'starlette.testclient' is deprecated; install 'httpx2' instead.` (harmless library notice from FastAPI's internal testclient import).
2. **`extractedAt` is set even when extraction fails**: When document extraction fails (e.g. invalid PDF format or timeout), the `extractedAt` timestamp is populated alongside `extractionStatus = FAILED` and `ocrStatus = failed`. It should ideally only represent successful extractions or distinguish a terminal failure timestamp.
3. **`documents` is a top-level collection, but ARCHITECTURE.md says `cases/{caseId}/documents`**: Current persistence writes to `/cases/{caseId}/documents/{docId}` as well as the top-level `/documents/{docId}` index, whereas `ARCHITECTURE.md` specifies `cases/{caseId}/documents`.
4. **Storage bucket auto-creation on emulator startup**: Implemented in Phase 6d (`ensure_emulator_storage_bucket()`) in `app/main.py` and `app/core/firestore_client.py`.
