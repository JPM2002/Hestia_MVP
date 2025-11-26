# gateway_app/tests/test_state_machine.py

def test_state_module_importable():
    """
    Smoke test muy simple: el módulo de estado se debe poder importar.
    No toca la BD ni el LLM.
    """
    import gateway_app.core.state as state_module  # noqa: F401

    # Si llegamos aquí sin excepción, el test pasa
    assert True
