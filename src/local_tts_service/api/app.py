from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..config import load_config
from ..errors import NotFoundError, ProviderError, RequestValidationError
from ..runtime_registry import build_runtime_registry
from ..services import HealthService, ModelCatalogService
from ..synthesis import SynthesisService
from .dependencies import LocalTTSService
from .routers import audio, health, models, speak, voices


def _prepare_default_model(config: Any, runtimes: Mapping[str, Any]) -> None:
    """Prepare only the configured default model when its runtime supports preloading."""
    default_config = config.models.get(config.default_model)
    if default_config is None:
        return

    default_runtime = runtimes.get(default_config.runtime)
    prepare_model = getattr(default_runtime, "prepare_model", None)
    if callable(prepare_model):
        prepare_model(config.default_model)


def _close_runtimes(runtimes: Iterable[Any]) -> None:
    """Close every runtime that exposes a close hook without coupling FastAPI to providers."""
    for runtime in runtimes:
        close = getattr(runtime, "close", None)
        if callable(close):
            close()


def _error_response(status_code: int, exc: Exception) -> JSONResponse:
    """Return the backward-compatible error shape used by existing clients."""
    message = str(exc)
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "error": message, "errorMessage": message},
    )


def create_app(root_dir: Path | None = None) -> FastAPI:
    """Build the FastAPI application and wire provider-independent service boundaries."""
    config = load_config(root_dir)
    runtimes = build_runtime_registry(config)

    app = FastAPI(title="local-tts-service", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    service = LocalTTSService(config, runtimes)
    catalog = ModelCatalogService(config, runtimes)
    _prepare_default_model(config, runtimes)

    synthesis = SynthesisService(
        config,
        runtimes,
        service.pick_model,
        service.resolve_reference_voice,
        catalog.availability,
    )
    health_service = HealthService(
        config,
        runtimes,
        catalog.availability,
        service.list_reference_voices,
    )

    app.state.service = service
    app.state.model_catalog = catalog
    app.state.synthesis_service = synthesis
    app.state.health_service = health_service

    def close_runtimes() -> None:
        _close_runtimes(runtimes.values())

    app.router.add_event_handler("shutdown", close_runtimes)

    @app.exception_handler(RequestValidationError)
    async def request_error(_request: Any, exc: RequestValidationError) -> JSONResponse:
        return _error_response(400, exc)

    @app.exception_handler(ProviderError)
    async def provider_error(_request: Any, exc: ProviderError) -> JSONResponse:
        return _error_response(502, exc)

    @app.exception_handler(NotFoundError)
    async def not_found_error(_request: Any, exc: NotFoundError) -> JSONResponse:
        return _error_response(404, exc)

    for router in (health.router, models.router, voices.router, speak.router, audio.router):
        app.include_router(router)

    return app
