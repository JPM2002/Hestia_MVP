# gateway_app/core/models.py
"""
Domain models and typed helpers for the WhatsApp gateway.

These dataclasses are intentionally lightweight. They are used by:
- The webhook layer to represent parsed WhatsApp messages.
- The NLU layer (guest_llm / faq_llm) to structure results.
- The state machine to track guest sessions and ticket drafts.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional


# ---- NLU result -------------------------------------------------------------


@dataclass
class NLUResult:
    """
    Normalized output of the guest NLU.

    This mirrors the JSON schema enforced in services.guest_llm:
      {
        "intent": "...",
        "area": "...",
        "priority": "...",
        "room": "...",
        "detail": "...",
        "name": "...",
        "is_cancel": bool,
        "is_help": bool,
        "is_smalltalk": bool,
        "wants_handoff": bool
      }
    """

    intent: Optional[str] = None  # ticket_request | handoff_request | general_chat | cancel | help | not_understood
    area: Optional[str] = None    # MANTENCION | HOUSEKEEPING | ROOMSERVICE | None
    priority: Optional[str] = None  # URGENTE | ALTA | MEDIA | BAJA | None
    room: Optional[str] = None
    detail: Optional[str] = None
    name: Optional[str] = None     # Guest name (for identity validation)

    is_cancel: bool = False
    is_help: bool = False
    is_smalltalk: bool = False
    wants_handoff: bool = False

    # Multiple requests (when user has 2+ requests for different departments)
    # Each item: {"area": "...", "detail": "...", "priority": "..."}
    multiple_requests: Optional[List[Dict[str, Any]]] = None

    # Routing metadata (audit trail)
    routing_source: Optional[str] = None       # rules | llm | clarification | fallback
    routing_reason: Optional[str] = None       # Human-readable routing reason
    routing_confidence: Optional[float] = None  # 0.0-1.0
    routing_version: str = "v1"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NLUResult":
        """
        Build an NLUResult from a raw dict, applying safe defaults.
        Extra keys are ignored.
        """
        return cls(
            intent=data.get("intent"),
            area=data.get("area"),
            priority=data.get("priority"),
            room=data.get("room"),
            detail=data.get("detail"),
            name=data.get("name"),
            is_cancel=bool(data.get("is_cancel", False)),
            is_help=bool(data.get("is_help", False)),
            is_smalltalk=bool(data.get("is_smalltalk", False)),
            wants_handoff=bool(data.get("wants_handoff", False)),
            multiple_requests=data.get("multiple_requests"),
            # Routing metadata (with _ prefix in source dict)
            routing_source=data.get("_routing_source"),
            routing_reason=data.get("_routing_reason"),
            routing_confidence=data.get("_routing_confidence"),
            routing_version=data.get("_routing_version", "v1"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---- WhatsApp message representation ----------------------------------------


@dataclass
class IncomingMessage:
    """
    Parsed representation of a single WhatsApp message entry.

    We keep only the fields we actually care about and stash the
    full raw payload in `raw` for debugging or future use.
    """

    wa_id: str                     # WhatsApp message ID
    from_number: str               # Sender phone / wa_id
    timestamp: Optional[int]       # Unix timestamp (string in WA payload, normalized to int)
    msg_type: str                  # "text", "audio", "image", etc.
    text: Optional[str] = None     # For text messages
    audio_media_id: Optional[str] = None  # For voice notes
    raw: Dict[str, Any] = field(default_factory=dict)

    def is_text(self) -> bool:
        return self.msg_type == "text" and bool(self.text)

    def is_audio(self) -> bool:
        return self.msg_type == "audio" and bool(self.audio_media_id)


# ---- Guest session + ticket draft -------------------------------------------


@dataclass
class GuestSession:
    """
    Minimal in-memory representation of a guest conversation.

    Persistent storage (DB) is handled elsewhere; this model is for
    state machine + routing logic.
    """

    wa_id: str                     # WhatsApp contact id (wa_id)
    phone: str                     # Phone number
    state: str                     # DFA state, e.g., "GH_S0"
    guest_name: Optional[str] = None
    room: Optional[str] = None
    language: Optional[str] = None  # "es", "en", "de", etc.

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Arbitrary extra data (e.g., current ticket draft id, flags, etc.)
    data: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # datetime is not JSON-serializable by default; cast to ISO.
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        return d


@dataclass
class TicketDraft:
    """
    Draft ticket before it is confirmed and sent to the main Hestia system.
    """

    area: Optional[str] = None         # MANTENCION | HOUSEKEEPING | ROOMSERVICE
    priority: Optional[str] = None     # URGENTE | ALTA | MEDIA | BAJA
    room: Optional[str] = None
    detail: Optional[str] = None

    # Optional references / metadata
    guest_wa_id: Optional[str] = None
    guest_phone: Optional[str] = None
    guest_name: Optional[str] = None

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def apply_nlu(self, nlu: NLUResult) -> None:
        """
        Convenience helper to update fields from an NLUResult,
        only when the NLU provides non-empty values.
        """
        if nlu.area:
            self.area = nlu.area
        if nlu.priority:
            self.priority = nlu.priority
        if nlu.room:
            self.room = nlu.room
        if nlu.detail:
            self.detail = nlu.detail
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        return d
