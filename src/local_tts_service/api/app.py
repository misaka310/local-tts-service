from __future__ import annotations
from pathlib import Path
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

def create_app(root_dir: Path | None = None) -> FastAPI:
    config=load_config(root_dir); runtimes=build_runtime_registry(config)
    app=FastAPI(title="local-tts-service", version="0.2.0")
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_allowed_origins, allow_credentials=False, allow_methods=["GET","POST","OPTIONS"], allow_headers=["*"])
    service=LocalTTSService(config, runtimes); catalog=ModelCatalogService(config, runtimes)
    synthesis=SynthesisService(config, runtimes, service.pick_model, service.resolve_reference_voice, catalog.availability)
    app.state.service=service; app.state.model_catalog=catalog; app.state.synthesis_service=synthesis
    app.state.health_service=HealthService(config, runtimes, catalog.availability, service.list_reference_voices)
    def error(status: int, exc: Exception) -> JSONResponse:
        message=str(exc); return JSONResponse(status_code=status, content={"ok":False,"error":message,"errorMessage":message})
    @app.exception_handler(RequestValidationError)
    async def request_error(_, exc: RequestValidationError): return error(400, exc)
    @app.exception_handler(ProviderError)
    async def provider_error(_, exc: ProviderError): return error(502, exc)
    @app.exception_handler(NotFoundError)
    async def not_found_error(_, exc: NotFoundError): return error(404, exc)
    for router in (health.router, models.router, voices.router, speak.router, audio.router): app.include_router(router)
    return app
