# MedBridge AI — Project Status Tracker

## 1. Project Summary
MedBridge AI is an AI-powered urgent healthcare care-coordination hackathon MVP. It bridges patients with urgent concerns to verified clinicians by generating a structured, human-reviewed Doctor Brief and facilitating simulated consultations and follow-ups. It enforces strict safety boundaries: care coordination only, no autonomous diagnosis or prescription, immediate zero-network emergency guidance (112 India), and clear `[DEMO / SIMULATED]` labels.

## 2. Phase Progress (Canonical Numbering)
- [x] **Phase 1: Architecture, Data Modeling, Tooling & Safety Blueprint** *(Completed)*
- [x] **Phase 2: Full-Stack Scaffolding, README, Landing Page & GET /health** *(Completed & Verified)*
- [x] **Phase 3: All 7 Interactive Screens, Synthetic Data, Mock Services & Responsive Layouts** *(Completed & Verified)*
- [x] **Phase 4: Firebase Auth (Emulator-First), Role Custom Claims, Protected Routes & Ownership Gates** *(Completed & Verified)*
- [x] **Phase 5: Database and Case Management** *(Completed & Verified)*
- [ ] **Phase 6: Documents and Voice** *(In Progress: Phase 6a, 6b, 6c Completed; Phase 6c-fix Firestore persistence & Storage uploads Verified (manual, emulator, 2026-10-10); Firestore transactions UNVERIFIED until Phase 8)*
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
- **Automated Test Suite (45/45 Passing):**
  - `test_phase6c_pdf_text_extraction.py` (11 tests) -> ALL PASSED
    - `test_extract_single_page_pdf_text` -> PASSED (single page text with citation)
    - `test_extract_multipage_pdf_per_page_text` -> PASSED (per-page dictionary citations)
    - `test_extract_empty_or_scanned_pdf_marked_needs_ocr` -> PASSED (NEEDS_OCR without content guessing)
    - `test_corrupted_pdf_handled_gracefully` -> PASSED (FAILED status, no server crash)
    - `test_encrypted_pdf_handled_gracefully` -> PASSED (readable error, no server crash)
    - `test_oversized_page_count_handled_gracefully` -> PASSED (30-page limit enforced, no crash)
    - `test_unauthorized_access_to_extracted_text_rejected` -> PASSED (HTTP 403 ownership isolation)
    - `test_audit_events_for_extraction` -> PASSED (DOC_TEXT_EXTRACTED & DOC_EXTRACTION_FAILED audit logs)
    - `test_image_upload_marked_needs_ocr_without_gemini` -> PASSED (NEEDS_OCR, 0 Gemini calls)
    - `test_extraction_timeout_handled_gracefully` -> PASSED (simulated hang -> FAILED + readable error + audit event)
    - `test_backend_restart_persistence_check` -> PASSED (case, doc, text, and idempotency survive backend restart)
  - `test_phase6a_document_upload.py` (13 tests) -> ALL PASSED
    - `test_valid_pdf_upload_succeeds` -> PASSED
    - `test_valid_jpeg_and_png_uploads_succeed` -> PASSED
    - `test_invalid_extension_rejected` -> PASSED (HTTP 400)
    - `test_mismatched_extension_and_mime_rejected` -> PASSED (HTTP 400)
    - `test_unsupported_mime_type_rejected` -> PASSED (HTTP 400)
    - `test_magic_byte_spoofing_rejected` -> PASSED (HTTP 400 + audit rejection log)
    - `test_empty_file_rejected` -> PASSED (HTTP 400)
    - `test_10mb_limit_exceeded_rejected` -> PASSED (HTTP 400)
    - `test_max_5_documents_per_case_limit_enforced` -> PASSED (HTTP 400 on 6th file & intent)
    - `test_upload_intent_validations` -> PASSED (intent validation matrix)
    - `test_document_ownership_isolation` -> PASSED (HTTP 403 Forbidden)
    - `test_unauthenticated_upload_rejected` -> PASSED (HTTP 401 Unauthorized)
    - `test_nonexistent_case_upload_rejected` -> PASSED (HTTP 404 Not Found)
  - `test_phase5_state_machine_and_crud.py` (9 tests) -> ALL PASSED
  - `test_auth_and_access.py` (6 tests) -> ALL PASSED
  - `test_case_flow.py` (6 tests) -> ALL PASSED
- **Phase 6c-Fix: Firestore Persistence & Storage Uploads:**
  - **Real-emulator persistence**: **VERIFIED** *(manual, emulator, 2026-10-10: case creation and document retrieval verified)*.
  - **Storage uploads**: **VERIFIED** *(manual, emulator, 2026-10-10: file streamed to `cases/{caseId}/...` Storage bucket path)*.
  - **Firestore transaction acceptance**: **UNVERIFIED** *(kept UNVERIFIED until Phase 8 live multi-client testing; covered by `@firestore_transactional` in automated fake test suite)*.
  - Migrated `CaseService` and `DocumentService` to direct Firestore persistence (`cases`, `cases/{caseId}/documents`, `idempotency_keys`).
  - Idempotency keys now persist in Firestore, guaranteeing duplicate prevention survives backend restarts.
  - Converted case acceptance to real Firestore transactions (`@firestore_transactional`) with race condition detection and HTTP 409 conflict.
  - Uploaded files stream directly to the Storage emulator bucket (`medbridge-ai-documents`) with zero local disk copies. Added `data/` and `emulator-data/` to `.gitignore`.
  - Added fail-fast emulator connection checks in production mode (raises `FirestoreConnectionError` if emulator unreachable, no silent fallbacks).
  - Test suite operates against a dedicated `FakeFirestoreClient` and `FakeStorageClient` for fast, offline, serverless execution (45/45 tests passing).
- **Phase 6b Frontend Upload UI:**
  - `DocumentUploadScreen.tsx` updated with drag & drop file picker, client checks (PDF/JPG/PNG, max 10 MB, max 5 files), `XMLHttpRequest` real progress tracking, in-memory queue, status badges (`Selected`, `Uploading`, `Confirmed by server`, `Failed`), per-file retry mechanism, and error mapping.
  - `api.uploadDocument` implemented in `frontend/src/services/api.ts` with `xhr.upload.onprogress`.
- **TypeScript & Vite Build:** `tsc && vite build` succeeded with returncode 0 (`1500 modules transformed`, zero TS errors).

## 5. Next Steps
- Await user approval before starting **Phase 6d** (signed-URL access with owner / assigned clinician / admin checks, `DOC_VIEWED` and denial audit events, emulator fallback, and tests for allowed/denied cases).
- Do NOT start Phase 6d yet.
- Do NOT start Phase 6e.

## 6. Known Issues & Tech Debt
1. **`extractedAt` set on failure**: When document extraction fails (e.g. invalid PDF format or timeout), `extractedAt` timestamp is populated alongside `extractionStatus = FAILED` and `ocrStatus = failed`. It should ideally only represent successful extractions or distinguish terminal failure timestamp.
2. **Documents collection layout differs from ARCHITECTURE.md**: Current persistence writes to `/cases/{caseId}/documents/{docId}` as well as top-level `/documents/{docId}` index, whereas `ARCHITECTURE.md` specifies a single top-level `/documents` collection schema with a `caseId` field.
3. **Bucket creation must happen in app startup, not manually**: Storage bucket auto-creation / check must be handled programmatically during backend startup lifecycle instead of relying on manual creation or predefined emulator setup.

