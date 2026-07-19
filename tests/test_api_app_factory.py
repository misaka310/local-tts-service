from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_tts_service.api import app as app_module


class FakeRuntime:
    def __init__(self) -> None:
        self.prepared: list[str] = []
        self.closed = False

    def prepare_model(self, model_id: str) -> None:
        self.prepared.append(model_id)

    def close(self) -> None:
        self.closed = True


class FakeLocalService:
    def __init__(self, config, runtimes) -> None:
        self.config = config
        self.runtimes = runtimes

    def pick_model(self, *_args):
        return "default"

    def resolve_reference_voice(self, *_args):
        return None

    def list_reference_voices(self):
        return []


class FakeCatalog:
    def __init__(self, config, runtimes) -> None:
        self.config = config
        self.runtimes = runtimes

    def availability(self, *_args):
        return {"available": True}


class FakeSynthesis:
    def __init__(self, *args) -> None:
        self.args = args


class FakeHealth:
    def __init__(self, *args) -> None:
        self.args = args


def test_create_app_wires_services_and_runtime_lifecycle(monkeypatch, tmp_path) -> None:
    runtime = FakeRuntime()
    config = SimpleNamespace(
        cors_allowed_origins=["http://127.0.0.1:5177"],
        default_model="default",
        models={"default": SimpleNamespace(runtime="fake")},
    )

    monkeypatch.setattr(app_module, "load_config", lambda root: config)
    monkeypatch.setattr(app_module, "build_runtime_registry", lambda _config: {"fake": runtime})
    monkeypatch.setattr(app_module, "LocalTTSService", FakeLocalService)
    monkeypatch.setattr(app_module, "ModelCatalogService", FakeCatalog)
    monkeypatch.setattr(app_module, "SynthesisService", FakeSynthesis)
    monkeypatch.setattr(app_module, "HealthService", FakeHealth)

    app = app_module.create_app(tmp_path)

    assert runtime.prepared == ["default"]
    assert isinstance(app.state.service, FakeLocalService)
    assert isinstance(app.state.model_catalog, FakeCatalog)
    assert isinstance(app.state.synthesis_service, FakeSynthesis)
    assert isinstance(app.state.health_service, FakeHealth)
    assert app.title == "local-tts-service"

    for shutdown_handler in app.router.on_shutdown:
        shutdown_handler()
    assert runtime.closed is True


def test_helpers_handle_optional_runtime_hooks_and_error_shape() -> None:
    runtime = FakeRuntime()
    app_module._prepare_default_model(
        SimpleNamespace(default_model="missing", models={}),
        {"fake": runtime},
    )
    assert runtime.prepared == []

    app_module._close_runtimes([object(), runtime])
    assert runtime.closed is True

    response = app_module._error_response(400, ValueError("invalid request"))
    assert response.status_code == 400
    assert json.loads(response.body) == {
        "ok": False,
        "error": "invalid request",
        "errorMessage": "invalid request",
    }
