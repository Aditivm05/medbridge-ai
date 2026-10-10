from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
from app.schemas.audit import AuditEventType, AuditEventResponse, AuditEventCreate


class AuditService:
    def __init__(self):
        # In-memory storage for local baseline testing, easily swapped or mirrored with Firestore
        self._events: List[AuditEventResponse] = []

    def log_event(
        self,
        event_type: AuditEventType,
        actor_id: str,
        actor_role: str,
        case_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEventResponse:
        event = AuditEventResponse(
            eventId=str(uuid.uuid4()),
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
        return event

    def get_events_for_case(self, case_id: str) -> List[AuditEventResponse]:
        return [e for e in self._events if e.caseId == case_id]

    def list_recent_events(self, limit: int = 50) -> List[AuditEventResponse]:
        return sorted(self._events, key=lambda e: e.timestamp, reverse=True)[:limit]


audit_service = AuditService()
