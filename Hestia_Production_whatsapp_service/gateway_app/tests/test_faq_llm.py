# gateway_app/tests/test_faq_llm.py

def test_faq_items_structure():
    from gateway_app.services import faq_llm

    assert isinstance(faq_llm.FAQ_ITEMS, list)
    assert faq_llm.FAQ_ITEMS, "FAQ_ITEMS no debería estar vacío"

    for item in faq_llm.FAQ_ITEMS:
        assert isinstance(item, dict)
        assert "q" in item, "Cada FAQ debe tener clave 'q'"
        assert "a" in item, "Cada FAQ debe tener clave 'a'"
