"""
Test CASO 6: Low confidence → Area clarification flow

Expected behavior:
1. User: "Tengo un problema en mi habitación"
2. Bot: Shows clarification menu (1-4) WITHOUT asking for identity first
3. User: "2" (chooses Housekeeping)
4. Bot: Asks for identity (name + room)
5. User: "Juan Pérez, habitación 205"
6. Bot: Shows confirmation
7. User: "Sí"
8. Bot: Creates ticket with routing_source="clarification", confidence=1.0

CRITICAL: System must NOT create ticket before user clarifies area
CRITICAL: System must NOT ask for identity before area clarification
"""
import json
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from gateway_app.core.conversation.orchestrator import handle_incoming_text
from gateway_app.services import db

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)


def get_last_ticket(wa_id: str):
    """Retrieve the last ticket for a given wa_id"""
    result = db.fetchone("""
        SELECT * FROM tickets
        WHERE huesped_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (wa_id,))

    return result


def test_caso6_clarification_flow():
    """
    CASO 6: Low confidence → Area clarification
    """
    print("\n" + "="*80)
    print("TEST CASO 6: Low Confidence -> Area Clarification")
    print("="*80)

    wa_id = "56998765458"  # Same as in your test
    session = {
        "wa_id": wa_id,
        "org_id": 2,
        "hotel_id": 1,
        "state": "NEW",
    }

    # ============================================================
    # STEP 1: Send ambiguous message
    # ============================================================
    print("\n>> STEP 1: User sends ambiguous message")
    print("User: 'Tengo un problema en mi habitación'")

    from datetime import datetime
    actions, session = handle_incoming_text(
        wa_id=wa_id,
        guest_phone=wa_id,
        guest_name=None,
        text="Tengo un problema en mi habitación",
        session=session,
        timestamp=datetime.now(),
        raw_payload={}
    )

    print(f"\n<< Bot response:")
    for action in actions:
        print(action.get("text", ""))

    # Verify: Should ask for clarification (1-4 menu)
    response_text = " ".join(action.get("text", "") for action in actions)

    assert "1" in response_text and "Mantenimiento" in response_text, "[FAIL] Should show clarification menu"
    assert "Mantenimiento" in response_text, "[FAIL] Should show area options"
    assert "numero (1-4)" in response_text.lower(), "[FAIL] Should ask for number choice"

    # Verify: Should NOT ask for identity yet
    assert "nombre completo" not in response_text, "[FAIL] Should NOT ask for name yet"
    assert "habitacion" in response_text.lower() and "numero de habitacion" not in response_text.lower(), "[FAIL] Should NOT ask for room yet (but message contains 'habitacion')"

    # Verify: State should be GH_AREA_CLARIFICATION
    assert session["state"] == "GH_AREA_CLARIFICATION", f"[FAIL] State should be GH_AREA_CLARIFICATION, got {session['state']}"

    # Verify: Should have pending_detail
    assert "pending_detail" in session, "[FAIL] Should have pending_detail in session"

    # Verify: NO ticket created yet
    ticket = get_last_ticket(wa_id)
    # Could be None or old ticket - just check it's not for "problema en la habitación"
    if ticket:
        assert "problema en la habitacion" not in ticket.get("detalle", "").lower(), "[FAIL] Should NOT create ticket before clarification"

    print("[PASS] PASO 1: Clarification menu shown correctly")

    # ============================================================
    # STEP 2: User chooses area (2 = Housekeeping)
    # ============================================================
    print("\n>> STEP 2: User chooses area")
    print("User: '2'")

    actions, session = handle_incoming_text(
        wa_id=wa_id,
        guest_phone=wa_id,
        guest_name=None,
        text="2",
        session=session,
        timestamp=datetime.now(),
        raw_payload={}
    )

    print(f"\n<< Bot response:")
    for action in actions:
        print(action.get("text", ""))

    response_text = " ".join(action.get("text", "") for action in actions)

    # Verify: Should NOW ask for identity
    assert "nombre completo" in response_text, "[FAIL] Should ask for name after clarification"
    assert "número de habitación" in response_text, "[FAIL] Should ask for room after clarification"

    # Verify: State should be GH_IDENTIFY
    assert session["state"] == "GH_IDENTIFY", f"[FAIL] State should be GH_IDENTIFY, got {session['state']}"

    # Verify: ticket_draft should have area=HOUSEKEEPING
    assert "ticket_draft" in session, "[FAIL] Should have ticket_draft in session"
    assert session["ticket_draft"]["area"] == "HOUSEKEEPING", f"[FAIL] Area should be HOUSEKEEPING, got {session['ticket_draft']['area']}"
    assert session["ticket_draft"]["routing_source"] == "clarification", "[FAIL] routing_source should be clarification"
    assert session["ticket_draft"]["routing_confidence"] == 1.0, "[FAIL] routing_confidence should be 1.0"

    print("[PASS] PASO 2: Identity request sent after clarification")

    # ============================================================
    # STEP 3: User provides identity
    # ============================================================
    print("\n>> STEP 3: User provides identity")
    print("User: 'Juan Pérez, habitación 205'")

    actions, session = handle_incoming_text(
        wa_id=wa_id,
        guest_phone=wa_id,
        guest_name=None,
        text="Juan Pérez, habitación 205",
        session=session,
        timestamp=datetime.now(),
        raw_payload={}
    )

    print(f"\n<< Bot response:")
    for action in actions:
        print(action.get("text", ""))

    response_text = " ".join(action.get("text", "") for action in actions)

    # Verify: Should show confirmation
    assert "Perfecto, Juan Pérez" in response_text, "[FAIL] Should greet user by name"
    assert "Housekeeping" in response_text, "[FAIL] Should mention Housekeeping"
    assert "205" in response_text, "[FAIL] Should mention room 205"
    assert "¿Confirmas?" in response_text, "[FAIL] Should ask for confirmation"

    # Verify: State should be GH_TICKET_CONFIRM
    assert session["state"] == "GH_TICKET_CONFIRM", f"[FAIL] State should be GH_TICKET_CONFIRM, got {session['state']}"

    print("[PASS] PASO 3: Confirmation shown")

    # ============================================================
    # STEP 4: User confirms
    # ============================================================
    print("\n>> STEP 4: User confirms")
    print("User: 'Sí'")

    actions, session = handle_incoming_text(
        wa_id=wa_id,
        guest_phone=wa_id,
        guest_name=None,
        text="Sí",
        session=session,
        timestamp=datetime.now(),
        raw_payload={}
    )

    print(f"\n<< Bot response:")
    for action in actions:
        print(action.get("text", ""))

    response_text = " ".join(action.get("text", "") for action in actions)

    # Verify: Success message
    assert "Listo" in response_text or "notifiqué" in response_text, "[FAIL] Should show success message"

    # Verify: Ticket created in DB
    ticket = get_last_ticket(wa_id)
    assert ticket is not None, "[FAIL] Ticket should be created"

    print("\n** Ticket created in DB:")
    print(json.dumps({
        "id": ticket["id"],
        "area": ticket["area"],
        "detalle": ticket["detalle"],
        "ubicacion": ticket["ubicacion"],
        "huesped_nombre": ticket.get("huesped_nombre"),
        "routing_source": ticket["routing_source"],
        "routing_reason": ticket["routing_reason"],
        "routing_confidence": ticket["routing_confidence"],
    }, indent=2, ensure_ascii=False))

    # Verify metadata
    assert ticket["area"] == "HOUSEKEEPING", f"[FAIL] Area should be HOUSEKEEPING, got {ticket['area']}"
    assert ticket["routing_source"] == "clarification", f"[FAIL] routing_source should be 'clarification', got {ticket['routing_source']}"
    assert ticket["routing_confidence"] == 1.0, f"[FAIL] routing_confidence should be 1.0, got {ticket['routing_confidence']}"
    assert "User chose option 2" in ticket["routing_reason"], f"[FAIL] routing_reason should mention user choice"
    assert ticket["ubicacion"] == "205", f"[FAIL] Room should be 205, got {ticket['ubicacion']}"

    print("\n[PASS] PASO 4: Ticket created with correct metadata")

    print("\n" + "="*80)
    print("*** TEST CASO 6 PASSED!")
    print("="*80)


if __name__ == "__main__":
    try:
        test_caso6_clarification_flow()
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
