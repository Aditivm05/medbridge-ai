# MedBridge AI — Project Status Tracker

## 1. Project Summary
MedBridge AI is an AI-powered urgent healthcare care-coordination hackathon MVP. It bridges patients with urgent concerns to verified clinicians by generating a structured, human-reviewed Doctor Brief and facilitating simulated consultations and follow-ups. It enforces strict safety boundaries: care coordination only, no autonomous diagnosis or prescription, immediate zero-network emergency guidance (112 India), and clear `[DEMO / SIMULATED]` labels.

## 2. Phase Progress (Canonical Numbering)
- [x] **Phase 1: Architecture, Data Modeling, Tooling & Safety Blueprint** *(Completed)*
- [x] **Phase 2: Full-Stack Scaffolding, README, Landing Page & GET /health** *(Completed & Verified)*
- [x] **Phase 3: All 7 Interactive Screens, Synthetic Data, Mock Services & Responsive Layouts** *(Completed & Verified)*
- [x] **Phase 4: Firebase Auth (Emulator-First), Role Custom Claims, Protected Routes & Ownership Gates** *(Completed & Verified)*
- [x] **Phase 5: Database and Case Management** *(Completed & Verified)*
- [ ] **Phase 6: Documents and Voice** *(In Progress: Phase 6a Backend Validation Completed)*
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
- `backend/app/models/firestore_models.py`: Firestore snapshot serializers, Timestamp converters, and enum parsers.
- `backend/app/schemas/`: Pydantic schemas for `case.py` (with `CaseUpdate` and `CaseSubmitRequest`), `audit.py` (full lifecycle events), `user.py`, `patient.py`, `clinician.py`, `document.py`, `doctor_brief.py`, `consultation.py`.
- `backend/app/services/case_service.py`: Service layer with complete Case CRUD, draft-only update guard, idempotent submit, and atomic concurrency locking.
- `backend/app/services/audit_service.py`: Append-only audit logger.
- `backend/app/api/routers/`: Routers for `health.py`, `auth.py`, `cases.py` (CRUD + submit + accept + matching), `documents.py`, `audit.py` (with `/audit/cases/{case_id}`).
- `backend/tests/test_phase5_state_machine_and_crud.py`: Exhaustive 100-pair state transition matrix test (18 valid, 82 invalid), CRUD lifecycle, idempotency, and Firestore models.
- `backend/tests/test_phase6a_document_upload.py`: Automated upload validation test suite (extension, MIME, magic bytes, 10 MB limit, 5 files per case, ownership isolation).
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
- **Automated Test Suite (34/34 Passing):**
  - `test_phase6a_document_validation.py` (13 tests) -> ALL PASSED
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
- **TypeScript & Vite Build:** `tsc && vite build` succeeded with returncode 0 (`1499 modules transformed in 3.59s`, zero TS errors).
- **Backend Health Check:** `GET http://127.0.0.1:8000/health` returned HTTP 200.
- **Frontend Server:** `GET http://127.0.0.1:5173` returned HTTP 200.

## 5. Next Steps
- Phase 6b: Audio/voice upload handling and transcription.
