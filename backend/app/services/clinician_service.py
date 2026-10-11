"""
Clinician Service
Handles clinician profiles, demo seeding, matching algorithm, availability management,
and case decline workflows.
"""

import json
import logging
import threading
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
from fastapi import HTTPException, status

from app.core.firestore_client import get_firestore_client, firestore_transactional
from app.core.state_machine import CaseStatus
from app.schemas.audit import AuditEventType
from app.schemas.case import CaseResponse, RequestedUrgency
from app.schemas.clinician import (
    ClinicianProfile,
    ClinicianSpecialty,
    ClinicianAvailability,
    ClinicianVerificationStatus,
    ClinicianMatchItem,
    ClinicianMatchResponse,
)
from app.models.firestore_models import (
    clinician_to_firestore_dict,
    clinician_from_firestore_dict,
)
from app.services.audit_service import audit_service
from app.services.case_service import case_service

logger = logging.getLogger(__name__)


class ClinicianNotFoundError(Exception):
    pass


class ClinicianNotAvailableError(Exception):
    pass


DEFAULT_DEMO_CLINICIANS = [
    {
        "clinicianId": "demo_doc_sharma",
        "userId": "user_demo_doc_sharma",
        "fullName": "Dr. Ananya Sharma [DEMO / SIMULATED]",
        "licenseNumber": "MCI-SIM-48201",
        "specialty": "general_medicine",
        "languages": ["en", "hi"],
        "verificationStatus": "verified",
        "availability": "available",
        "isDemo": True,
        "currentCaseId": None,
    },
    {
        "clinicianId": "demo_doc_patil",
        "userId": "user_demo_doc_patil",
        "fullName": "Dr. Rajesh Patil [DEMO / SIMULATED]",
        "licenseNumber": "MMC-SIM-91823",
        "specialty": "emergency_medicine",
        "languages": ["en", "mr", "hi"],
        "verificationStatus": "verified",
        "availability": "available",
        "isDemo": True,
        "currentCaseId": None,
    },
    {
        "clinicianId": "demo_doc_deshmukh",
        "userId": "user_demo_doc_deshmukh",
        "fullName": "Dr. Priya Deshmukh [DEMO / SIMULATED]",
        "licenseNumber": "MMC-SIM-10492",
        "specialty": "pediatrics",
        "languages": ["en", "mr"],
        "verificationStatus": "verified",
        "availability": "available",
        "isDemo": True,
        "currentCaseId": None,
    },
    {
        "clinicianId": "demo_doc_pending",
        "userId": "user_demo_doc_pending",
        "fullName": "Dr. Vikram Malhotra [DEMO / SIMULATED]",
        "licenseNumber": "DMC-SIM-PENDING-771",
        "specialty": "general_medicine",
        "languages": ["en", "hi"],
        "verificationStatus": "pending",
        "availability": "available",
        "isDemo": True,
        "currentCaseId": None,
    },
    {
        "clinicianId": "demo_doc_offline",
        "userId": "user_demo_doc_offline",
        "fullName": "Dr. Sneha Kulkarni [DEMO / SIMULATED]",
        "licenseNumber": "MMC-SIM-99214",
        "specialty": "cardiology",
        "languages": ["en", "mr"],
        "verificationStatus": "verified",
        "availability": "offline",
        "isDemo": True,
        "currentCaseId": None,
    },
]


class ClinicianService:
    def __init__(self, db=None):
        self._db = db
        self._lock = threading.RLock()
        self._auto_seeded = False

    @property
    def db(self):
        if self._db is None:
            self._db = get_firestore_client()
        return self._db

    def seed_default_clinicians(self) -> List[ClinicianProfile]:
        """
        Seeds labelled [DEMO / SIMULATED] clinicians into Firestore.
        Reads from firebase/seed_data.json if present, falling back to embedded defaults.
        Idempotent: updates existing demo profiles without destroying system state.
        """
        with self._lock:
            data_to_seed = DEFAULT_DEMO_CLINICIANS
            seed_file = Path(__file__).resolve().parent.parent.parent.parent / "firebase" / "seed_data.json"
            if seed_file.is_file():
                try:
                    with open(seed_file, "r", encoding="utf-8") as f:
                        parsed = json.load(f)
                        if "clinicians" in parsed and isinstance(parsed["clinicians"], list):
                            data_to_seed = parsed["clinicians"]
                except Exception as e:
                    logger.warning(f"Could not load seed_data.json ({e}), using embedded demo clinicians.")

            seeded: List[ClinicianProfile] = []
            for item in data_to_seed:
                clinician_id = item["clinicianId"]
                # Enforce DEMO marking
                full_name = item.get("fullName", "")
                if "[DEMO / SIMULATED]" not in full_name:
                    full_name = f"{full_name} [DEMO / SIMULATED]"
                item["fullName"] = full_name
                item["isDemo"] = True

                profile = ClinicianProfile.model_validate(item)
                doc_ref = self.db.collection("clinicians").document(clinician_id)
                # If clinician already exists with an active assignment, preserve it
                existing_snap = doc_ref.get()
                if existing_snap.exists:
                    existing_data = existing_snap.to_dict() or {}
                    existing_case = existing_data.get("currentCaseId")
                    if existing_case:
                        c_snap = self.db.collection("cases").document(existing_case).get()
                        if c_snap.exists and (c_snap.to_dict() or {}).get("status") in (
                            CaseStatus.ACCEPTED.value,
                            CaseStatus.IN_CONSULTATION.value,
                        ):
                            profile = profile.model_copy(
                                update={
                                    "currentCaseId": existing_case,
                                    "availability": ClinicianAvailability.BUSY,
                                }
                            )
                doc_ref.set(clinician_to_firestore_dict(profile))
                seeded.append(profile)

            logger.info(f"Successfully seeded {len(seeded)} demo clinicians.")
            return seeded

    def get_clinician(self, clinician_id: str) -> ClinicianProfile:
        """Retrieves a clinician profile by ID from Firestore."""
        doc_ref = self.db.collection("clinicians").document(clinician_id)
        snap = doc_ref.get()
        if not snap.exists:
            raise ClinicianNotFoundError(f"Clinician '{clinician_id}' not found.")
        return clinician_from_firestore_dict(clinician_id, snap.to_dict())

    def list_clinicians(
        self,
        specialty: Optional[ClinicianSpecialty] = None,
        availability: Optional[ClinicianAvailability] = None,
        language: Optional[str] = None,
        verification_status: Optional[ClinicianVerificationStatus] = None,
    ) -> List[ClinicianProfile]:
        """Lists clinicians from Firestore with optional filtering."""
        snaps = list(self.db.collection("clinicians").stream())
        if not snaps and not self._auto_seeded:
            self._auto_seeded = True
            self.seed_default_clinicians()
            snaps = list(self.db.collection("clinicians").stream())

        profiles: List[ClinicianProfile] = []

        for snap in snaps:
            data = snap.to_dict()
            if not data:
                continue
            profile = clinician_from_firestore_dict(snap.id, data)

            if specialty and profile.specialty != specialty:
                continue
            if availability and profile.availability != availability:
                continue
            if verification_status and profile.verificationStatus != verification_status:
                continue
            if language:
                clean_lang = language.strip().lower()
                if not any(l.lower() == clean_lang for l in profile.languages):
                    continue

            profiles.append(profile)

        # Deterministic sorting: by clinicianId
        profiles.sort(key=lambda p: p.clinicianId)
        return profiles

    def _clinician_has_active_assignment(self, clinician_id: str, current_case_id: Optional[str] = None) -> bool:
        """Checks whether a clinician currently has an active case assignment (ACCEPTED or IN_CONSULTATION)."""
        if current_case_id:
            snap = self.db.collection("cases").document(current_case_id).get()
            if snap.exists:
                st = (snap.to_dict() or {}).get("status")
                if st in (CaseStatus.ACCEPTED.value, CaseStatus.IN_CONSULTATION.value):
                    return True
        try:
            query = self.db.collection("cases").where("assignedClinicianId", "==", clinician_id)
            for snap in query.stream():
                st = (snap.to_dict() or {}).get("status")
                if st in (CaseStatus.ACCEPTED.value, CaseStatus.IN_CONSULTATION.value):
                    return True
        except Exception as e:
            logger.warning(f"Error checking active assignments for clinician '{clinician_id}': {e}")
        return False

    def update_availability(
        self,
        clinician_id: str,
        availability: ClinicianAvailability,
        current_case_id: Optional[str] = None,
    ) -> ClinicianProfile:
        """
        Updates availability and assigned currentCaseId for a clinician.
        Protected by Firestore transaction to ensure atomic coordination with case acceptance and completion.
        Invariants:
        1. Cannot set availability to AVAILABLE while an active case assignment exists.
        2. Cannot clear or overwrite currentCaseId while the clinician has an active case assignment.
        """
        @firestore_transactional(self.db)
        def _tx_update_avail(tx):
            clin_ref = self.db.collection("clinicians").document(clinician_id)
            snap = clin_ref.get(transaction=tx)
            if not snap.exists:
                raise ClinicianNotFoundError(f"Clinician '{clinician_id}' not found.")
            data = snap.to_dict() or {}
            existing_case_id = data.get("currentCaseId")

            has_active = self._clinician_has_active_assignment(clinician_id, existing_case_id)

            avail_val = availability.value if hasattr(availability, "value") else str(availability)
            if avail_val == ClinicianAvailability.AVAILABLE.value and has_active:
                active_case_str = existing_case_id or "an active case"
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot set clinician '{clinician_id}' to AVAILABLE while assigned to active case '{active_case_str}'. The active case must be completed first.",
                )

            # Prevent ordinary availability updates from wiping out an active assignment
            target_case_id = current_case_id
            if has_active and target_case_id is None and existing_case_id:
                target_case_id = existing_case_id

            now = datetime.utcnow()
            update_data = {
                "availability": avail_val,
                "currentCaseId": target_case_id,
                "updatedAt": now.isoformat(),
            }
            tx.update(clin_ref, update_data)
            merged = dict(data, **update_data)
            return clinician_from_firestore_dict(clinician_id, merged)

        return _tx_update_avail()

    def find_matching_clinicians(
        self,
        case: CaseResponse,
        exclude_clinician_ids: Optional[List[str]] = None,
    ) -> List[Tuple[ClinicianProfile, int, bool]]:
        """
        Executes the Phase 8 Clinician Matching Algorithm.
        Criteria:
        1. Verification: verificationStatus == VERIFIED only.
        2. Availability: availability == AVAILABLE and currentCaseId is None.
        3. Exclusions: clinicianId not in exclude_clinician_ids (e.g. declined).
        4. Language: case.patientLanguage in clinician.languages.
        5. Specialty Matching:
           - Exact preferred specialty match: score = 100 (is_exact = True)
           - Telemedicine general/emergency fallback: score = 50 (is_exact = False)
        6. Queue Ordering / Deterministic Tie-breaking:
           - match_score descending, then clinicianId ascending.
        Returns: List of tuples (ClinicianProfile, match_score, is_exact_specialty_match).
        """
        exclude_set = set(exclude_clinician_ids or [])
        all_clinicians = self.list_clinicians()

        # Determine target preferred specialty
        meta = case.metadata or {}
        explicit_specialty = meta.get("preferredSpecialty") or meta.get("requestedSpecialty")
        if explicit_specialty:
            preferred_specialty = explicit_specialty
            is_explicit = True
        else:
            is_explicit = False
            if case.requestedUrgency == RequestedUrgency.EMERGENCY:
                preferred_specialty = ClinicianSpecialty.EMERGENCY_MEDICINE.value
            else:
                preferred_specialty = ClinicianSpecialty.GENERAL_MEDICINE.value

        patient_lang = (case.patientLanguage or "en").strip().lower()

        candidates: List[Tuple[ClinicianProfile, int, bool]] = []

        for clin in all_clinicians:
            # 1. Verification filter
            if clin.verificationStatus != ClinicianVerificationStatus.VERIFIED:
                continue

            # 2. Availability filter
            if clin.availability != ClinicianAvailability.AVAILABLE or clin.currentCaseId is not None:
                continue

            # 3. Exclusions
            if clin.clinicianId in exclude_set:
                continue

            # 4. Language filter
            clin_langs = [l.strip().lower() for l in clin.languages]
            if patient_lang not in clin_langs:
                continue

            # 5. Specialty matching
            clin_spec_val = clin.specialty.value if hasattr(clin.specialty, "value") else str(clin.specialty)
            if clin_spec_val == preferred_specialty:
                score = 100
                is_exact = True
            elif clin_spec_val in [ClinicianSpecialty.GENERAL_MEDICINE.value, ClinicianSpecialty.EMERGENCY_MEDICINE.value]:
                # Fallback general/emergency provider
                score = 50
                is_exact = False
            elif not is_explicit:
                # No specific specialty requested: any qualified provider who speaks the language can assist
                score = 30
                is_exact = False
            else:
                # Explicit specialty requested, and clinician is an unrelated specialist
                score = 0
                is_exact = False

            if score > 0:
                candidates.append((clin, score, is_exact))

        # 6. Deterministic ordering: highest score first, then clinicianId
        candidates.sort(key=lambda item: (-item[1], item[0].clinicianId))
        return candidates

    def trigger_matching(
        self,
        case_id: str,
        actor_id: str,
        actor_role: str,
    ) -> ClinicianMatchResponse:
        """
        Triggers matching for a case.
        If matches are found, updates metadata and returns ranked matches.
        If NO matching clinician is available, automatically transitions case
        to NO_CLINICIAN_AVAILABLE and logs CASE_NO_CLINICIAN.
        """
        with self._lock:
            case = case_service.get_case(case_id)

            # If case was previously NO_CLINICIAN_AVAILABLE, re-entering matching transitions to MATCHING
            if case.status == CaseStatus.NO_CLINICIAN_AVAILABLE:
                case = case_service.transition_status(
                    case_id=case_id,
                    target_status=CaseStatus.MATCHING,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    reason="Retrying clinician matching",
                )
            elif case.status != CaseStatus.MATCHING:
                # If case is already in another status (e.g. SUBMITTED), transition to MATCHING
                case = case_service.transition_status(
                    case_id=case_id,
                    target_status=CaseStatus.MATCHING,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    reason="Enqueued for clinician matching",
                )

            declined = list(case.metadata.get("declinedClinicianIds", [])) if case.metadata else []
            matches = self.find_matching_clinicians(case, exclude_clinician_ids=declined)

            if matches:
                matched_items = [
                    ClinicianMatchItem(
                        clinicianId=clin.clinicianId,
                        fullName=clin.fullName,
                        licenseNumber=clin.licenseNumber,
                        specialty=clin.specialty,
                        languages=clin.languages,
                        matchScore=score,
                        isExactSpecialtyMatch=is_exact,
                        availability=clin.availability,
                        isDemo=clin.isDemo,
                    )
                    for clin, score, is_exact in matches
                ]

                # Update case metadata with matched candidates
                current_meta = dict(case.metadata or {})
                current_meta["matchedClinicianIds"] = [m.clinicianId for m in matched_items]
                current_meta["matchingAttemptedAt"] = datetime.utcnow().isoformat()
                case_service.update_case_metadata(case_id, current_meta)

                audit_service.log_event(
                    event_type=AuditEventType.CASE_MATCHING_ENQUEUED,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    case_id=case_id,
                    details={
                        "matchedCount": len(matched_items),
                        "topClinicianId": matched_items[0].clinicianId,
                        "preferredSpecialty": current_meta.get("preferredSpecialty"),
                    },
                )

                return ClinicianMatchResponse(
                    caseId=case_id,
                    status=CaseStatus.MATCHING.value,
                    matches=matched_items,
                    matchedCount=len(matched_items),
                )
            else:
                # No clinician available! Transition to NO_CLINICIAN_AVAILABLE
                updated_case = case_service.transition_status(
                    case_id=case_id,
                    target_status=CaseStatus.NO_CLINICIAN_AVAILABLE,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    reason="No verified clinician available matching language and specialty requirements.",
                    extra_details={
                        "patientLanguage": case.patientLanguage,
                        "requestedUrgency": case.requestedUrgency.value,
                        "declinedCount": len(declined),
                    },
                )

                return ClinicianMatchResponse(
                    caseId=case_id,
                    status=CaseStatus.NO_CLINICIAN_AVAILABLE.value,
                    matches=[],
                    matchedCount=0,
                )

    def decline_case(
        self,
        case_id: str,
        clinician_id: str,
        reason: Optional[str],
        actor_id: str,
        actor_role: str,
    ) -> CaseResponse:
        """
        Clinician declines a case.
        - Records decline in audit trail (CASE_DECLINED).
        - Records clinician_id in case.metadata.declinedClinicianIds.
        - Re-runs matching against remaining clinicians.
        - If no candidates remain, transitions to NO_CLINICIAN_AVAILABLE.
        """
        with self._lock:
            case = case_service.get_case(case_id)
            if case.status != CaseStatus.MATCHING:
                raise ValueError(
                    f"Cannot decline case '{case_id}' in status '{case.status.value}'. "
                    "Only cases in MATCHING status can be declined."
                )

            # Record decline in metadata
            current_meta = dict(case.metadata or {})
            declined_list = list(current_meta.get("declinedClinicianIds", []))
            if clinician_id not in declined_list:
                declined_list.append(clinician_id)
            current_meta["declinedClinicianIds"] = declined_list
            current_meta["lastDeclinedBy"] = clinician_id
            current_meta["lastDeclineReason"] = reason or "Clinician unavailable or out of scope"

            case_service.update_case_metadata(case_id, current_meta)

            audit_service.log_event(
                event_type=AuditEventType.CASE_DECLINED,
                actor_id=actor_id,
                actor_role=actor_role,
                case_id=case_id,
                details={
                    "decliningClinicianId": clinician_id,
                    "reason": reason or "Clinician unavailable or out of scope",
                    "totalDeclined": len(declined_list),
                },
            )

            # Re-evaluate matching pool
            refetched_case = case_service.get_case(case_id)
            remaining_matches = self.find_matching_clinicians(
                refetched_case,
                exclude_clinician_ids=declined_list,
            )

            if not remaining_matches:
                # Pool exhausted! Transition to NO_CLINICIAN_AVAILABLE
                return case_service.transition_status(
                    case_id=case_id,
                    target_status=CaseStatus.NO_CLINICIAN_AVAILABLE,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    reason=f"Pool exhausted after decline by clinician '{clinician_id}'.",
                    extra_details={
                        "patientLanguage": refetched_case.patientLanguage,
                        "declinedClinicianId": clinician_id,
                        "declinedCount": len(declined_list),
                    },
                )

            return refetched_case


clinician_service = ClinicianService()
