from mystmon.api import create_app


def test_create_app_imports_collectors() -> None:
    app = create_app()

    assert app.title == "MystMon API"

