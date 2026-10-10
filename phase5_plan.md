# Phase 5 Implementation Plan: Database and Case Management

> [!IMPORTANT]
> **Canonical Phase Numbering:**
> - **Phase 5:** Database and case management (current phase)
> - **Phase 6:** Documents and voice
> - **Phase 7:** AI Doctor Brief (Gemini)
> *(Gemini work is strictly deferred to Phase 7).*

---

## 1. Phase 5 Objectives & Scope

Phase 5 focuses exclusively on bulletproof **Database and Case Management**:
1. **Firestore Models & Serializers:** Clean mapping between Cloud Firestore document snapshots (timestamps, references) and typed Pydantic models.
2. **Case CRUD Operations:**
   - **Create:** Idempotent case creation via client-supplied `idempotencyKey`.
   - **Read:** Ownership-isolated reading of cases and queues.
   - **Update:** `PATCH /cases/{id}` permitting modifications strictly while in `DRAFT` status; rejects modifications in active clinical states.
   - **Delete/Cancel:** Graceful cancellation transitioning cases to `CANCELLED`.
3. **Central State-Transition Function:** Single source of truth for the 10-state lifecycle (`DRAFT`, `SUBMITTED`, `MATCHING`, `ACCEPTED`, `IN_CONSULTATION`, `COMPLETED`, `CANCELLED`, `NO_CLINICIAN_AVAILABLE`, `FAILED`, `ESCALATED`).
4. **Idempotent Submission:** Double-clicking "Submit" or network retries returns the existing `SUBMITTED` case with HTTP 200 without raising invalid transition exceptions.
5. **Immutable Audit Events:** Every state transition and modification logs an append-only audit event in the audit trail.
6. **Firestore Security Rules:** Verify deny-by-default rules with role custom claims, clinician license verification, and append-only audit protections.
7. **Exhaustive State Transition Testing:** Systematically test every single valid transition (18 edges) and every illegal transition (82 invalid pairs out of 100 total combinations), proving the state engine cannot be corrupted.

---

## 2. Exhaustive State Transition Matrix (10x10 = 100 Combinations)

The 10 case states:
- `DRAFT`
- `SUBMITTED`
- `MATCHING`
- `ACCEPTED`
- `IN_CONSULTATION`
- `COMPLETED` *(Terminal)*
- `CANCELLED` *(Terminal)*
- `NO_CLINICIAN_AVAILABLE`
- `FAILED`
- `ESCALATED`

### Allowed Transitions (18 Valid Edges)
| From State | Allowed Next States | Trigger / Scenario |
|---|---|---|
| `DRAFT` | `SUBMITTED`, `CANCELLED` | Patient submits intake or cancels draft |
| `SUBMITTED` | `MATCHING`, `CANCELLED`, `FAILED` | Brief generated/reviewed; or patient cancels; or system error |
| `MATCHING` | `ACCEPTED`, `NO_CLINICIAN_AVAILABLE`, `CANCELLED` | Clinician claims case; or timeout; or patient cancels |
| `ACCEPTED` | `IN_CONSULTATION`, `ESCALATED`, `CANCELLED` | Doctor begins consult; or emergency hospital referral; or cancel |
| `IN_CONSULTATION` | `COMPLETED`, `ESCALATED` | Doctor completes notes; or escalates to physical ER |
| `COMPLETED` | *(None - Terminal)* | Finalized case record |
| `CANCELLED` | *(None - Terminal)* | Closed case record |
| `NO_CLINICIAN_AVAILABLE` | `MATCHING`, `CANCELLED` | Patient retries matching pool; or closes request |
| `FAILED` | `MATCHING`, `CANCELLED` | System retries matching; or cancels |
| `ESCALATED` | `COMPLETED` | Emergency hospital coordination record finalized |

### Disallowed Transitions (82 Invalid Combinations)
All remaining 82 combinations (e.g., `DRAFT -> COMPLETED`, `COMPLETED -> MATCHING`, `ACCEPTED -> DRAFT`, `IN_CONSULTATION -> MATCHING`, `CANCELLED -> SUBMITTED`, self-transitions without status change) must strictly raise `InvalidStateTransitionError` and return `HTTP 400 Bad Request`.

---

## 3. Phase 5 Task List

- [ ] **Task 5.1: Verify Firestore Models & Converters**
  - Verify `app/models/firestore_models.py` handles Firestore timestamps, serialization of enums, and dict conversions.
- [ ] **Task 5.2: Complete Case CRUD in Router & Service**
  - Verify `POST /api/v1/cases` (Create with idempotency)
  - Verify `GET /api/v1/cases/{id}` (Read with ownership guard)
  - Verify `PATCH /api/v1/cases/{id}` (Update draft only)
  - Verify `DELETE /api/v1/cases/{id}` (Cancel/archive)
- [ ] **Task 5.3: Verify Idempotent Submission**
  - Test `POST /api/v1/cases/{id}/submit` when case is `DRAFT` (transitions to `SUBMITTED`)
  - Test `POST /api/v1/cases/{id}/submit` when case is already `SUBMITTED` (idempotent 200 OK without state corruption)
- [ ] **Task 5.4: Verify Audit Event Logging & Immutability**
  - Ensure every status transition maps to a specific `AuditEventType` (`CASE_CREATED`, `CASE_UPDATED`, `CASE_SUBMITTED`, `CASE_MATCHING_ENQUEUED`, `CASE_ACCEPTED`, `CASE_IN_CONSULTATION`, `CASE_COMPLETED`, `CASE_CANCELLED`, `CASE_ESCALATED`, `CASE_FAILED`, `CASE_NO_CLINICIAN`)
  - Audit logs are append-only with zero mutation or deletion APIs.
- [ ] **Task 5.5: Build Comprehensive Test Suite (`test_phase5_state_machine_and_crud.py`)**
  - **Test Suite A:** 100% matrix test covering all 18 valid state transitions.
  - **Test Suite B:** 100% matrix test asserting rejection for all 82 invalid transitions.
  - **Test Suite C:** Case CRUD lifecycle (create, read, patch while draft, reject patch while submitted, delete).
  - **Test Suite D:** Idempotent submission double-submit test.
  - **Test Suite E:** Audit trail verification across transitions.
- [ ] **Task 5.6: Verify Firestore Security Rules Alignment**
  - Inspect `firebase/firestore.rules` against all collection operations.
- [ ] **Task 5.7: Deliver Phase 5 Walkthrough & Beginner-Friendly Explanation**
  - Update `PROJECT_STATUS.md` and present verification report to user.
