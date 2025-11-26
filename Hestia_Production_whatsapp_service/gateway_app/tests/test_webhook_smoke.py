# gateway_app/tests/test_webhook_smoke.py

from gateway_app import create_app


def test_webhook_blueprint_registered():
    """
    Comprueba que la app se crea y que el blueprint 'webhook'
    está registrado en el mapa de URLs.
    """
    app = create_app()
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}

    assert any(
        ep.startswith("webhook.") for ep in endpoints
    ), "No se encontró ningún endpoint del blueprint 'webhook'"
