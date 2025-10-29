from app import create_app

def test_app_factory():
    app = create_app()
    assert app is not None
