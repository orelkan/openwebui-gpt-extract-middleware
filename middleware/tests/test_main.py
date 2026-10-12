from app.config import Settings
from app.main import create_app


def test_create_app_stores_given_settings(settings: Settings) -> None:
    app = create_app(settings)

    assert app.state.settings is settings
