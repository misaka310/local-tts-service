from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from ...models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    config = request.app.state.service.config
    runtimes = request.app.state.service.runtimes
    configured_runtimes = sorted(
        {
            model.runtime
            for model in config.models.values()
            if model.runtime in runtimes
        }
    )
    model_info = request.app.state.model_catalog.list(run_external_probe=False)
    available_models = sorted(
        item.model for item in model_info if item.available
    )
    return HealthResponse(
        host=config.host,
        port=config.port,
        publicBaseUrl=config.public_base_url,
        defaultModel=config.default_model,
        audioOutputDir=str(config.audio_output_dir),
        availableRuntimes=configured_runtimes,
        availableProviders=configured_runtimes,
        availableModels=available_models,
        availableModelInfo=model_info,
    )


@router.get("/health/deep")
async def health_deep(request: Request) -> JSONResponse:
    return JSONResponse(
        content=await run_in_threadpool(
            request.app.state.health_service.build_deep_payload
        )
    )
