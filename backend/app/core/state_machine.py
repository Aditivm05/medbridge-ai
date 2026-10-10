from enum import Enum
from typing import Dict, Set


class CaseStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    MATCHING = "MATCHING"
    ACCEPTED = "ACCEPTED"
    IN_CONSULTATION = "IN_CONSULTATION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_CLINICIAN_AVAILABLE = "NO_CLINICIAN_AVAILABLE"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


# Single source of truth for allowed state transitions
ALLOWED_TRANSITIONS: Dict[CaseStatus, Set[CaseStatus]] = {
    CaseStatus.DRAFT: {
        CaseStatus.SUBMITTED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.SUBMITTED: {
        CaseStatus.MATCHING,
        CaseStatus.CANCELLED,
        CaseStatus.FAILED,
    },
    CaseStatus.MATCHING: {
        CaseStatus.ACCEPTED,
        CaseStatus.NO_CLINICIAN_AVAILABLE,
        CaseStatus.CANCELLED,
    },
    CaseStatus.ACCEPTED: {
        CaseStatus.IN_CONSULTATION,
        CaseStatus.ESCALATED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.IN_CONSULTATION: {
        CaseStatus.COMPLETED,
        CaseStatus.ESCALATED,
    },
    CaseStatus.COMPLETED: set(),  # Terminal state
    CaseStatus.CANCELLED: set(),  # Terminal state
    CaseStatus.NO_CLINICIAN_AVAILABLE: {
        CaseStatus.MATCHING,  # Retry matching
        CaseStatus.CANCELLED,
    },
    CaseStatus.FAILED: {
        CaseStatus.MATCHING,  # Retry matching
        CaseStatus.CANCELLED,
    },
    CaseStatus.ESCALATED: {
        CaseStatus.COMPLETED,  # Clinician completes emergency coordination record
    },
}


class InvalidStateTransitionError(Exception):
    """Raised when an illegal case state transition is attempted."""
    def __init__(self, current_status: CaseStatus, target_status: CaseStatus, reason: str = ""):
        self.current_status = current_status
        self.target_status = target_status
        self.reason = reason
        allowed = [s.value for s in ALLOWED_TRANSITIONS.get(current_status, set())]
        msg = (
            f"Invalid state transition from '{current_status.value}' to '{target_status.value}'. "
            f"Allowed next states: {allowed}."
        )
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(msg)


def validate_transition(current_status: CaseStatus, target_status: CaseStatus) -> None:
    """
    Validates if transitioning from current_status to target_status is permitted.
    Raises InvalidStateTransitionError if illegal.
    """
    allowed_targets = ALLOWED_TRANSITIONS.get(current_status, set())
    if target_status not in allowed_targets:
        raise InvalidStateTransitionError(current_status, target_status)


def is_terminal_status(status: CaseStatus) -> bool:
    """Returns True if the given status is a terminal state."""
    return len(ALLOWED_TRANSITIONS.get(status, set())) == 0
