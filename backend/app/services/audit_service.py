from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import logging
from app.schemas.audit import AuditEventType, AuditEventResponse, AuditEventCreate
from app.models.firestore_models import audit_event_to_firestore_dict, audit_event_from_firestore_dict
from app.core.firestore_client import get_firestore_client

logger = logging.getLogger("medbridge.audit_service")


class AuditService:
    def __init__(self, db=None):
        self._db = db
        # In-memory storage for fast local testing and lookup
        self._events: List[AuditEventResponse] = []

    @property
    def db(self):
        if self._db is None:
            self._db = get_firestore_client()
        return self._db

    def log_event(
        self,
        event_type: AuditEventType,
        actor_id: str,
        actor_role: str,
        case_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
    ) -> AuditEventResponse:
        e_id = event_id or str(uuid.uuid4())
        event = AuditEventResponse(
            eventId=e_id,
            caseId=case_id,
            actorId=actor_id,
            actorRole=actor_role,
            eventType=event_type,
            ipAddress=ip_address,
            userAgent=user_agent,
            details=details or {},
            timestamp=datetime.utcnow(),
        )
        self._events.append(event)
        try:
            self.db.collection("audit_events").document(e_id).set(audit_event_to_firestore_dict(event))
        except Exception as e:
            logger.warning(f"Could not persist audit event '{e_id}' to Firestore: {e}")
        return event

    def record_committed_event(self, event: AuditEventResponse) -> None:
        """Registers a transactionally committed audit event into local cache."""
        if not any(e.eventId == event.eventId for e in self._events):
            self._events.append(event)

    def get_events_for_case(self, case_id: str) -> List[AuditEventResponse]:
        """Retrieves all audit events for a case, merging in-memory records and Firestore documents."""
        events_by_id: Dict[str, AuditEventResponse] = {e.eventId: e for e in self._events if e.caseId == case_id}
        try:
            snaps = self.db.collection("audit_events").where("caseId", "==", case_id).stream()
            for snap in snaps:
                if snap.exists:
                    ev = audit_event_from_firestore_dict(snap.id, snap.to_dict())
                    events_by_id[ev.eventId] = ev
        except Exception as e:
            logger.warning(f"Could not query audit events from Firestore: {e}")
        return sorted(list(events_by_id.values()), key=lambda e: e.timestamp)

    get_case_events = get_events_for_case

    def list_recent_events(self, limit: int = 50) -> List[AuditEventResponse]:
        return sorted(self._events, key=lambda e: e.timestamp, reverse=True)[:limit]

    def list_events(self) -> List[AuditEventResponse]:
        return list(self._events)


audit_service = AuditService()
