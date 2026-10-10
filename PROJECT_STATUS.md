# MedBridge AI — Project Status Tracker

## 1. Project Summary
MedBridge AI is an AI-powered urgent healthcare care-coordination hackathon MVP. It bridges patients with urgent concerns to verified clinicians by generating a structured, human-reviewed Doctor Brief and facilitating simulated consultations and follow-ups. It enforces strict safety boundaries: care coordination only, no autonomous diagnosis or prescription, immediate zero-network emergency guidance (112 India), and clear `[DEMO / SIMULATED]` labels.

## 2. Phase Progress (Canonical Numbering)
- [x] **Phase 1: Architecture, Data Modeling, Tooling & Safety Blueprint** *(Completed)*
- [x] **Phase 2: Full-Stack Scaffolding, README, Landing Page & GET /health** *(Completed & Verified)*
- [x] **Phase 3: All 7 Interactive Screens, Synthetic Data, Mock Services & Responsive Layouts** *(Completed & Verified)*
- [x] **Phase 4: Firebase Auth (Emulator-First), Role Custom Claims, Protected Routes & Ownership Gates** *(Completed & Verified)*
- [x] **Phase 5: Database and Case Management** *(Completed & Verified)*
- [ ] **Phase 6: Documents and Voice** *(In Progress: Phase 6a, 6b, 6c Completed; Phase 6c-fix Firestore persistence & Storage uploads Verified (manual, emulator, 10 Oct 2026); Phase 6d Signed-URL & Stream Access Implemented (18/18 pytest passing); Stream endpoint on real emulator marked UNVERIFIED until manual run; Firestore transactions UNVERIFIED until Phase 8)*
- [ ] **Phase 7: AI Doctor Brief (Gemini)** *(Pending)*

## 3. Files Created Across Phases 1 - 5
### Architecture, Docs & Infrastructure
- `docs/ARCHITECTURE.md`: Complete system architecture, data models for 10 collections, state machine table, concurrency transaction rules, and REST API blueprint.
- `README.md`: Comprehensive beginner-friendly setup guide with click-by-click commands, architecture diagram, and expected outputs.
- `PROJECT_STATUS.md`: Project status, environment variables, phase tracking, and milestones.
- `firebase.json`: Firebase emulator configuration (Auth: 9099, Firestore: 8080, Storage: 9199, UI: 4000).
- `firebase/firestore.rules`: Deny-by-default Firestore security rules.
- `firebase/firestore.indexes.json`: Firestore index configuration.
- `firebase/storage.rules`: Deny-by-default Storage security rules.
- `firebase/seed_data.json`: Seed demo clinicians with `[DEMO / SIMULATED]` markers.

### Backend (`backend/`)
- `backend/requirements.txt`: Backend dependencies (FastAPI, Pydantic, google-genai, firebase-admin, pytest, etc.).
- `backend/app/main.py`: FastAPI application entrypoint with root `GET /health`, CORS, latency tracking, and API v1 router mounting.
- `backend/app/core/config.py`: Application settings using Pydantic Settings.
- `backend/app/core/auth.py`: Firebase Auth token verification, `AuthenticatedUser` model, custom claims manager, role guards (`require_role`, `require_verified_clinician`), and case ownership enforcement (`check_case_ownership`).
- `backend/app/core/state_machine.py`: Centralized Case State Machine with transition validators across 10 states and 18 allowed transitions.
- `backend/app/core/firestore_client.py`: Centralized Firestore and Storage client factory, emulator connection verification (fail-fast), and in-memory `FakeFirestoreClient` / `FakeStorageClient` for offline pytest suite.
- `backend/app/models/firestore_models.py`: Firestore snapshot serializers, Timestamp converters, and enum parsers.
- `backend/app/schemas/`: Pydantic schemas for `case.py` (with `CaseUpdate` and `CaseSubmitRequest`), `audit.py` (full lifecycle events), `user.py`, `patient.py`, `clinician.py`, `document.py`, `doctor_brief.py`, `consultation.py`.
- `backend/app/services/case_service.py`: Service layer with complete Case CRUD, draft-only update guard, idempotent submit, and atomic concurrency locking.
- `backend/app/services/document_service.py`: Extraction service per-page (`pypdf`), low-text `NEEDS_OCR` tagging, encrypted/corrupted/page-limit safeguards (30 pages max), audit events.
- `backend/app/services/audit_service.py`: Append-only audit logger.
- `backend/app/api/routers/`: Routers for `health.py`, `auth.py`, `cases.py` (CRUD + submit + accept + matching), `documents.py` (upload-and-verify, background extraction, text retrieval), `audit.py` (with `/audit/cases/{case_id}`).
- `backend/tests/test_phase6d_signed_url_access.py`: Automated signed URL & streaming access test suite (RBAC owner/clinician/admin, 403 status gates, token swap & expiry rejection, header security, zero-token audit logging).
- `backend/tests/test_phase6c_pdf_text_extraction.py`: Automated PDF text extraction test suite (single-page, multi-page, empty/scanned, corrupted, encrypted, oversized, security isolation, audit events).
- `backend/tests/test_phase6a_document_upload.py`: Automated upload validation test suite (extension, MIME, magic bytes, 10 MB limit, 5 files per case, ownership isolation).
- `backend/tests/test_phase5_state_machine_and_crud.py`: Exhaustive 100-pair state transition matrix test (18 valid, 82 invalid), CRUD lifecycle, idempotency, and Firestore models.
- `backend/tests/test_auth_and_access.py`: Pytest automated suite proving 401 unauth, patient ownership isolation (403), unverified clinician claim block (403), verified clinician acceptance (200), and custom claims inspection.
- `backend/tests/test_case_flow.py`: Pytest automated test suite (health, state transitions, idempotency, magic bytes, race condition 409 conflict).
- `backend/pytest.ini`: Pytest configuration.
- `backend/conftest.py`, `backend/app/__init__.py`, `backend/.venv/.../sitecustomize.py`: Python 3.10.0 ForwardRef compatibility shims.

### Frontend Components & Security UI (`frontend/`)
- `frontend/src/types/index.ts`: TypeScript domain definitions across all 7 screens.
- `frontend/src/vite-env.d.ts`: Standard Vite client type definitions.
- `frontend/src/services/authService.ts`: Active authentication context, Firebase emulator token provider, and persona switcher.
- `frontend/src/services/api.ts`: Authenticated fetch wrapper injecting `Authorization: Bearer <token>` and API helpers.
- `frontend/src/services/mockData.ts`: Realistic synthetic data (initial cases, demo clinicians, CBC lab report, ultrasound notes, Doctor Brief).
- `frontend/src/services/caseStore.ts`: Reactive state management store using Observer pattern with atomic claim and 409 conflict simulator.
- `frontend/src/i18n/translations.ts`: Multilingual dictionary (English, Hindi, Marathi) with complete labels for all 7 screens.
- `frontend/src/components/common/EmergencyBanner.tsx`: Static zero-network 112 emergency guidance.
- `frontend/src/components/common/SimulationBadge.tsx`: Visual `[DEMO / SIMULATED]` badge.
- `frontend/src/components/common/StatusBadge.tsx`: Accessible status badges across 10 case states.
- `frontend/src/components/common/ConnectionIndicator.tsx`: Network & emulator telemetry badge.
- `frontend/src/components/common/Header.tsx`: Multilingual, role-switching responsive header with active auth claims badge.
- `frontend/src/components/screens/PatientDashboard.tsx`: Screen 1 — Patient requests list, filter tabs, empty states, and new request action.
- `frontend/src/components/screens/IntakeScreen.tsx`: Screen 2 — Rapid clinical intake, urgency selector, common symptom tags, emergency triggers.
- `frontend/src/components/screens/DocumentUploadScreen.tsx`: Screen 3 — File dropzone, 1-click synthetic reports (CBC, Ultrasound), validation rules.
- `frontend/src/components/screens/DoctorBriefReviewScreen.tsx`: Screen 4 — AI Doctor Brief review gate, objective facts table with preserved units, unknowns, edit modal.
- `frontend/src/components/screens/ClinicianDashboard.tsx`: Screen 5 — Clinician matching pool, active doctor profile switcher, simulate 409 race collision button, atomic claim action.
- `frontend/src/components/screens/ConsultationWorkspace.tsx`: Screen 6 — Side-by-side workspace: brief & lab report inspector + assessment notes & care advice form.
- `frontend/src/components/screens/FollowUpScreen.tsx`: Screen 7 — Follow-up date scheduling, emergency warning sign directives, case finalization summary.
- `frontend/src/App.tsx`: Main application router with Golden Workflow stepper, health widget, and dev-only Phase 4 Security Tester widget.
- `frontend/scripts/capture_screenshots.cjs`: Automated screenshot generation script capturing all 7 screens at 1280px desktop and 360px mobile viewports.
- `frontend/scripts/capture_phase4_screenshot.cjs`: Automated security verification script capturing browser rejection toasts for cross-patient access and unverified clinician claim.

## 4. Verified Milestones & Test Outputs
- **Automated Test Suite (64/64 Passing):**
  - `test_phase6d_signed_url_access.py` (19 tests) -> ALL PASSED
    - `test_owner_allowed_download_url` -> PASSED (HTTP 200, short-lived 300s, DOC_VIEWED logged, no token in audit logs)
    - `test_other_patient_denied_download_url` -> PASSED (HTTP 403 Forbidden, DOC_VIEW_DENIED logged)
    - `test_assigned_clinician_allowed_in_accepted_in_consultation_completed` -> PASSED (HTTP 200 in ACCEPTED, IN_CONSULTATION, COMPLETED)
    - `test_assigned_clinician_denied_on_cancelled_case` -> PASSED (HTTP 403 Forbidden, DOC_VIEW_DENIED logged)
    - `test_clinician_on_reassigned_case_denied` -> PASSED (HTTP 403 Forbidden when case reassigned)
    - `test_unassigned_clinician_denied_download_url` -> PASSED (HTTP 403 Forbidden)
    - `test_unverified_clinician_denied_download_url` -> PASSED (HTTP 403 Forbidden)
    - `test_admin_allowed_download_url` -> PASSED (HTTP 200)
    - `test_unauthenticated_request_denied` -> PASSED (HTTP 401 Unauthorized)
    - `test_invalid_case_or_document_id_returns_404` -> PASSED (HTTP 404 Not Found)
    - `test_stream_endpoint_pdf_headers` -> PASSED (X-Content-Type-Options: nosniff, Cache-Control: no-store, Content-Disposition: inline, Content-Type: application/pdf)
    - `test_stream_endpoint_image_headers` -> PASSED (Content-Disposition: attachment for images, Content-Type: image/jpeg)
    - `test_stream_token_swapped_to_different_document_rejected` -> PASSED (HTTP 403 Forbidden on swapped documentId)
    - `test_stream_token_expired_rejected` -> PASSED (HTTP 403 Forbidden on past timestamp)
    - `test_stream_token_never_logged` -> PASSED (tokens verified absent from both audit logs and application logs)
    - `test_assigned_clinician_stream_access_denied_if_case_cancelled` -> PASSED (HTTP 403 Forbidden)
    - `test_startup_bucket_creation_error_handling` -> PASSED (re-raises RuntimeError, logs clear error, never swallows)
    - `test_startup_validates_stream_secret_outside_testing` -> PASSED (raises RuntimeError if DOC_STREAM_SECRET missing outside testing)
    - `test_stream_access_log_filter_redacts_tokens` -> PASSED (uvicorn.access filter strips query parameters and HMAC tokens from log records)
  - `test_phase6c_pdf_text_extraction.py` (11 tests) -> ALL PASSED
  - `test_phase6a_document_upload.py` (13 tests) -> ALL PASSED
  - `test_phase5_state_machine_and_crud.py` (9 tests) -> ALL PASSED
  - `test_auth_and_access.py` (6 tests) -> ALL PASSED
  - `test_case_flow.py` (6 tests) -> ALL PASSED
- **Phase 6d Verification Status:**
  - **Stream endpoint on the real emulator**: **`UNVERIFIED`** *(awaiting manual user test run)*.
  - **Firestore persistence**: **VERIFIED** *(manual, emulator, 10 Oct 2026: case survived a backend restart)*.
  - **Storage upload**: **VERIFIED** *(manual, emulator, 10 Oct 2026: bucket medbridge-ai-documents with cases/ folder seen in emulator UI)*.
  - **Firestore transaction acceptance**: **UNVERIFIED** *(kept UNVERIFIED until Phase 8)*.
  - **Phase 12 IAM signBlob production signing**: **`UNTESTED`** *(documented in ARCHITECTURE.md for production Cloud Run deployment)*.
- **Phase 6b Frontend Upload UI:**
  - `DocumentUploadScreen.tsx` updated with drag & drop file picker, client checks (PDF/JPG/PNG, max 10 MB, max 5 files), `XMLHttpRequest` real progress tracking, in-memory queue, status badges (`Selected`, `Uploading`, `Confirmed by server`, `Failed`), per-file retry mechanism, and error mapping.
  - `api.uploadDocument` implemented in `frontend/src/services/api.ts` with `xhr.upload.onprogress`.
- **TypeScript & Vite Build:** `tsc && vite build` succeeded with returncode 0 (`1500 modules transformed`, zero TS errors).

## 5. Next Steps
- User will manually run verification of the stream endpoint on the real emulator.
- Do NOT start servers.
- Do NOT start Phase 6e.

## 6. Known Issues & Tech Debt
1. **`extractedAt` is set even when extraction fails**: When document extraction fails (e.g. invalid PDF format or timeout), the `extractedAt` timestamp is populated alongside `extractionStatus = FAILED` and `ocrStatus = failed`. It should ideally only represent successful extractions or distinguish a terminal failure timestamp.
2. **`documents` is a top-level collection, but ARCHITECTURE.md says `cases/{caseId}/documents`**: Current persistence writes to `/cases/{caseId}/documents/{docId}` as well as the top-level `/documents/{docId}` index, whereas `ARCHITECTURE.md` specifies `cases/{caseId}/documents`.
3. **Storage bucket auto-creation on emulator startup**: Implemented in Phase 6d (`ensure_emulator_storage_bucket()`) in `app/main.py` and `app/core/firestore_client.py`.


