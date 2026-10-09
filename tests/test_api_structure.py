from local_tts_service.api.app import create_app as api_create_app
from local_tts_service.server import create_app as legacy_create_app


def test_server_create_app_is_api_app_factory() -> None:
    assert legacy_create_app is api_create_app
