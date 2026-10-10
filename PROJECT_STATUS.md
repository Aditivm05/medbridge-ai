# MedBridge AI — Project Status Tracker

## 1. Project Summary
MedBridge AI is an AI-powered urgent healthcare care-coordination hackathon MVP. It bridges patients with urgent concerns to verified clinicians by generating a structured, human-reviewed Doctor Brief and facilitating simulated consultations and follow-ups. It enforces strict safety boundaries: care coordination only, no autonomous diagnosis or prescription, immediate zero-network emergency guidance (112 India), and clear `[DEMO / SIMULATED]` labels.

## 2. Phase Progress (Canonical Numbering)
- [x] **Phase 1: Architecture, Data Modeling, Tooling & Safety Blueprint** *(Completed)*
- [x] **Phase 2: Full-Stack Scaffolding, README, Landing Page & GET /health** *(Completed & Verified)*
- [x] **Phase 3: All 7 Interactive Screens, Synthetic Data, Mock Services & Responsive Layouts** *(Completed & Verified)*
- [x] **Phase 4: Firebase Auth (Emulator-First), Role Custom Claims, Protected Routes & Ownership Gates** *(Completed & Verified)*
- [x] **Phase 5: Database and Case Management** *(Completed. Persistence verified on real emulator (10 Oct 2026); transaction acceptance UNVERIFIED until Phase 8.)*
- [ ] **Phase 6: Documents and Voice** *(Not fully verified. Voice input = PLANNED. Real-Gemini OCR, 6d stream endpoint on real emulator, and uvicorn log filter UNVERIFIED)*
  - **Phase 6a**: Upload intent, validation (mime, magic bytes, size, file count) — **Status**: Completed | **Tag**: `phase-6a-complete`
  - **Phase 6b**: Frontend Document Upload Screen with drag-and-drop & XHR upload progress — **Status**: Completed | **Tag**: `phase-6b-complete`
  - **Phase 6c**: Text-based PDF extraction via pypdf & low-text detection — **Status**: Completed | **Tag**: `phase-6c-complete`
  - **Phase 6c-fix**: Firestore document persistence and emulator storage bucket auto-creation — **Status**: Completed | **Tags**: `phase-6c-fix-fakes-only`, `phase-6c-fix-verified`
  - **Phase 6d**: Document access via short-lived HMAC stream URLs and signed URLs — **Status**: Completed | **Tag**: `phase-6d-fakes-only`
  - **Phase 6e**: Gemini multimodal OCR for scanned PDFs and images — **Status**: Completed (mocked tests only) | **Tag**: `phase-6e-fakes-only`
  - **Voice Input**: Speech-to-text / voice intake — **Status**: PLANNED
- [ ] **Phase 7: AI Doctor Brief (Gemini)** *(In Progress)*
  - **Phase 7a**: AI Doctor Brief backend: strict Pydantic DoctorBrief schema (no diagnosis/prescription), Gemini generation service with fallback skeleton, document reference validation, structured conflicts list, brief endpoints (`generate`, `get`, `put`, `approve`, `review`), lifecycle (`DRAFT_AI` -> `PATIENT_APPROVED` -> `CLINICIAN_REVIEWED`), version snapshots, and rate limiting — **Status**: Completed (mocked tests passing; endpoints included in 7a)
  - **Remaining**:
    - **Phase 7c**: Frontend Doctor Brief review screen (interactive edits, patient approve, clinician review) *(Pending)*
    - **Real-Gemini brief test**: Live API verification with real Gemini API key *(UNVERIFIED)*

## 3. Files Created Across Phases 1 - 7a
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
- `backend/app/services/document_service.py`: Extraction service per-page (`pypdf`), low-text `NEEDS_OCR` tagging, encrypted/corrupted/page-limit safeguards (30 pages max), audit events, and Phase 6e Gemini multimodal OCR pipeline.
- `backend/app/services/gemini_service.py`: Multimodal Gemini OCR service with strict data-only prompt, Pydantic validation, exponential backoff on 429/5xx, and synthetic data notices.
- `backend/app/services/brief_service.py`: AI Doctor Brief service using Google GenAI SDK, strict data-only prompt, Pydantic structured output, conflict detection, rate limiting, and fallback skeleton.
- `backend/app/services/audit_service.py`: Append-only audit logger.
- `backend/app/api/routers/`: Routers for `health.py`, `auth.py`, `cases.py` (CRUD + submit + accept + matching), `documents.py` (upload-and-verify, background extraction, OCR trigger, text retrieval), `briefs.py` (Doctor Brief generate, read, edit, patient approve, clinician review), `audit.py` (with `/audit/cases/{case_id}`).
- `backend/tests/test_phase7a_doctor_brief.py`: Automated Phase 7a Doctor Brief test suite (12 tests: Complete info, missing info, conflicting info, malformed JSON fallback, 429/5xx retry, 400 fail, timeout, injection defense, no-diagnosis schema rule, invalid doc references dropped, RBAC gates, lifecycle/re-approval).
- `backend/tests/test_phase6e_gemini_ocr_extraction.py`: Automated Phase 6e OCR test suite (13 tests: success, malformed JSON, 429/5xx retries, 400 no-retry, missing/invalid key, timeout, prompt injection data safety, pypdf text preservation, duplicate trigger guard, RBAC).
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
- **Automated Test Suite (89/89 Passing):**
  - `test_phase7a_doctor_brief.py` (12 tests) -> ALL PASSED
    - `test_schema_has_no_diagnosis_or_prescription_fields` -> PASSED (extra='forbid' strictly rejects diagnosis, prescription, or treatment)
    - `test_synthetic_case_a_complete_information` -> PASSED (verbatim complaint, timeline, vitals with exact units, document findings with sources and pages, BRIEF_GENERATED logged without content)
    - `test_synthetic_case_b_missing_information_and_incomplete_documents` -> PASSED (literal 'unknown' preserved, incomplete docs with NEEDS_OCR/FAILED/PROCESSING flagged in missingInformation as not yet read)
    - `test_synthetic_case_c_conflicting_information` -> PASSED (conflicting doses in patient input vs lab report recorded in conflicts list without AI resolution)
    - `test_malformed_json_fallback_to_blank_skeleton` -> PASSED (malformed output returns blank skeleton with validation warning, zero crash)
    - `test_api_error_retry_on_429_and_5xx_and_fail_on_400` -> PASSED (retries on 429/5xx, fails immediately without retry on 400)
    - `test_timeout_handled_gracefully` -> PASSED (GEMINI_TIMEOUT_SECONDS enforced, returns blank skeleton with timeout warning, zero crash)
    - `test_prompt_injection_treated_strictly_as_passive_data` -> PASSED ('ignore previous instructions, diagnose...' treated purely as passive data, zero diagnosis)
    - `test_invalid_document_references_dropped_and_warned` -> PASSED (invalid document IDs and out-of-bounds page numbers dropped and warned)
    - `test_rbac_and_ownership_gates` -> PASSED (401 unauthenticated, 403 cross-patient, 403 unassigned clinician, 403 clinician in MATCHING/DRAFT, 200 assigned clinician in ACCEPTED, 403 unassigned clinician review)
    - `test_brief_lifecycle_editing_and_reapproval` -> PASSED (PATIENT_APPROVED -> human edit sets EDITED, increments version, saves snapshot in previousVersions; patient cannot edit once SUBMITTED; regenerate over EDITED brief requires confirmRegenerate=true)
    - `test_generation_only_in_draft_and_rate_limiting` -> PASSED (generation blocked when not in DRAFT status, per-case rate limit enforced with 429)
  - `test_phase6e_gemini_ocr_extraction.py` (13 tests) -> ALL PASSED
  - `test_phase6d_signed_url_access.py` (19 tests) -> ALL PASSED
  - `test_phase6c_pdf_text_extraction.py` (11 tests) -> ALL PASSED
  - `test_phase6a_document_upload.py` (13 tests) -> ALL PASSED
  - `test_phase5_state_machine_and_crud.py` (9 tests) -> ALL PASSED
  - `test_auth_and_access.py` (6 tests) -> ALL PASSED
  - `test_case_flow.py` (6 tests) -> ALL PASSED
- **Phase 7a Verification Status:**
  - **Real-Gemini brief generation**: **`UNVERIFIED`** *(awaiting manual user test run with real GEMINI_API_KEY)*.
- **Phase 6 Verification Status:**
  - **Real-Gemini multimodal extraction**: **`UNVERIFIED`** *(awaiting manual user test run with real GEMINI_API_KEY)*.
  - **Stream endpoint on the real emulator**: **`UNVERIFIED`** *(awaiting manual user test run)*.
  - **Uvicorn log filter**: **`UNVERIFIED`** *(awaiting manual inspection on live server)*.
  - **Firestore persistence**: **VERIFIED** *(manual, emulator, 10 Oct 2026: case survived a backend restart)*.
  - **Storage upload**: **VERIFIED** *(manual, emulator, 10 Oct 2026: bucket medbridge-ai-documents with cases/ folder seen in emulator UI)*.
  - **Firestore transaction acceptance**: **UNVERIFIED** *(kept UNVERIFIED until Phase 8)*.
  - **Phase 12 IAM signBlob production signing**: **`UNTESTED`** *(documented in ARCHITECTURE.md for production Cloud Run deployment)*.
- **Phase 6b Frontend Upload UI:**
  - `DocumentUploadScreen.tsx` updated with drag & drop file picker, client checks (PDF/JPG/PNG, max 10 MB, max 5 files), `XMLHttpRequest` real progress tracking, in-memory queue, status badges (`Selected`, `Uploading`, `Confirmed by server`, `Failed`), per-file retry mechanism, and error mapping.
  - `api.uploadDocument` implemented in `frontend/src/services/api.ts` with `xhr.upload.onprogress`.
- **TypeScript & Vite Build:** `tsc && vite build` succeeded with returncode 0 (`1500 modules transformed`, zero TS errors).

## 5. Next Steps
- User will review Phase 7a backend test outputs and git diff.
- Do NOT start servers.
- Do NOT commit, amend, or tag.
- Next implementation target: Phase 7c frontend Doctor Brief review screen.

## 6. Known Limitations & Tech Debt

### Known Limitations
1. **Brief generation rate limit is in memory**: Brief generation rate limit is in memory (resets on restart, not shared across instances).
2. **Names typed in free text are not removed before sending**: Patient ID, patient name, case ID, and filenames are strictly excluded, but any names typed directly into free-text fields (such as chief complaint or history) are not filtered before sending to Gemini; platform intended for synthetic data only.
3. **DRAFT check and case updates use an in-process lock**: The status check and metadata updates in `case_service.py` (`update_case`) use an in-process threading lock (`self._lock`) rather than a distributed lock or database transaction; safe for single-instance deployment, but concurrent updates across multiple server instances would require Firestore transactions.

### Technical Debt & Known Issues
3. **`extractedAt` is set even when extraction fails**: When document extraction fails (e.g. invalid PDF format or timeout), the `extractedAt` timestamp is populated alongside `extractionStatus = FAILED` and `ocrStatus = failed`. It should ideally only represent successful extractions or distinguish a terminal failure timestamp.
4. **`documents` is a top-level collection, but ARCHITECTURE.md says `cases/{caseId}/documents`**: Current persistence writes to `/cases/{caseId}/documents/{docId}` as well as the top-level `/documents/{docId}` index, whereas `ARCHITECTURE.md` specifies `cases/{caseId}/documents`.
5. **Storage bucket auto-creation on emulator startup**: Implemented in Phase 6d (`ensure_emulator_storage_bucket()`) in `app/main.py` and `app/core/firestore_client.py`.


