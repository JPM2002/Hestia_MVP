"""
Simple test for CASO 6: Low confidence -> Area clarification
"""
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from gateway_app.core.conversation.orchestrator import handle_incoming_text
from gateway_app.services import db


def test_caso6():
    wa_id = "56998765458"
    session = {
        "wa_id": wa_id,
        "org_id": 2,
        "hotel_id": 1,
        "state": "NEW",
    }

    print("\n=== CASO 6: Low Confidence Clarification ===\n")

    # STEP 1: Ambiguous message
    print("STEP 1: User sends ambiguous message")
    actions, session = handle_incoming_text(
        wa_id=wa_id,
        guest_phone=wa_id,
        guest_name=None,
        text="Tengo un problema en mi habitacion",
        session=session,
        timestamp=datetime.now(),
        raw_payload={}
    )

    # Check response
    response_text = " ".join(action.get("text", "") for action in actions).lower()

    assert "mantenimiento" in response_text, f"Should show clarification menu, got: {response_text[:200]}"
    assert "housekeeping" in response_text, "Should show housekeeping option"
    assert "1" in response_text and "2" in response_text, "Should show numbered options"
    assert session["state"] == "GH_AREA_CLARIFICATION", f"State should be GH_AREA_CLARIFICATION, got {session['state']}"

    print(f"[PASS] Clarification menu shown, state = {session['state']}")

    # STEP 2: User chooses option 2 (Housekeeping)
    print("\nSTEP 2: User chooses Housekeeping")
    actions, session = handle_incoming_text(
        wa_id=wa_id,
        guest_phone=wa_id,
        guest_name=None,
        text="2",
        session=session,
        timestamp=datetime.now(),
        raw_payload={}
    )

    response_text = " ".join(action.get("text", "") for action in actions).lower()

    print(f"Response: {response_text[:300].encode('ascii', 'ignore').decode('ascii')}")

    assert "nombre" in response_text, f"Should ask for name, got: {response_text[:200]}"
    assert "habitacion" in response_text, f"Should ask for room, got: {response_text[:200]}"
    assert session["state"] == "GH_IDENTIFY", f"State should be GH_IDENTIFY, got {session['state']}"
    assert session["ticket_draft"]["area"] == "HOUSEKEEPING", f"Area should be HOUSEKEEPING, got {session['ticket_draft']['area']}"
    assert session["ticket_draft"]["routing_source"] == "clarification", "routing_source should be clarification"
    assert session["ticket_draft"]["routing_confidence"] == 1.0, "routing_confidence should be 1.0"

    print(f"[PASS] Identity requested, area = {session['ticket_draft']['area']}, routing_source = {session['ticket_draft']['routing_source']}")

    # STEP 3: User provides identity
    print("\nSTEP 3: User provides identity")
    actions, session = handle_incoming_text(
        wa_id=wa_id,
        guest_phone=wa_id,
        guest_name=None,
        text="Juan Perez, habitacion 205",
        session=session,
        timestamp=datetime.now(),
        raw_payload={}
    )

    response_text = " ".join(action.get("text", "") for action in actions).lower()

    assert "juan perez" in response_text or "juan" in response_text, f"Should greet user, got: {response_text[:200]}"
    assert "205" in response_text, "Should mention room 205"
    assert "confirmas" in response_text, "Should ask for confirmation"
    assert session["state"] == "GH_TICKET_CONFIRM", f"State should be GH_TICKET_CONFIRM, got {session['state']}"

    print(f"[PASS] Confirmation shown, state = {session['state']}")

    # STEP 4: User confirms
    print("\nSTEP 4: User confirms")
    actions, session = handle_incoming_text(
        wa_id=wa_id,
        guest_phone=wa_id,
        guest_name=None,
        text="Si",
        session=session,
        timestamp=datetime.now(),
        raw_payload={}
    )

    response_text = " ".join(action.get("text", "") for action in actions).lower()

    assert "listo" in response_text or "notifique" in response_text, f"Should show success message, got: {response_text[:200]}"

    # Check ticket in DB
    ticket = db.fetchone("""
        SELECT * FROM tickets
        WHERE huesped_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (wa_id,))

    assert ticket is not None, "Ticket should be created"
    assert ticket["area"] == "HOUSEKEEPING", f"Area should be HOUSEKEEPING, got {ticket['area']}"
    assert ticket["routing_source"] == "clarification", f"routing_source should be clarification, got {ticket['routing_source']}"
    assert ticket["routing_confidence"] == 1.0, f"routing_confidence should be 1.0, got {ticket['routing_confidence']}"
    assert "User chose option 2" in ticket["routing_reason"], f"routing_reason should mention user choice, got {ticket['routing_reason']}"
    assert ticket["ubicacion"] == "205", f"Room should be 205, got {ticket['ubicacion']}"

    print(f"[PASS] Ticket created: id={ticket['id']}, area={ticket['area']}, routing_source={ticket['routing_source']}, confidence={ticket['routing_confidence']}")

    print("\n=== ALL TESTS PASSED ===\n")


if __name__ == "__main__":
    try:
        test_caso6()
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
