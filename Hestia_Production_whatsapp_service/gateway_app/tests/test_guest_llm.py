# gateway_app/tests/test_guest_llm.py

from gateway_app.services.guest_llm import render_confirm_draft


def test_render_confirm_draft_uses_guest_name_and_summary():
    session = {"guest_name": "Javier"}
    summary = "Se cambiarán las toallas de la habitación 101."
    text = render_confirm_draft(summary, session)

    assert "Javier" in text
    assert summary in text
    assert "SI" in text.upper()  # debería invitar a responder SI
