from fastapi import APIRouter, Request

from ...models import ModelsResponse

router = APIRouter()


@router.get("/v1/models", response_model=ModelsResponse)
async def list_models(request: Request, probe: bool = True) -> ModelsResponse:
    return ModelsResponse(models=request.app.state.model_catalog.list(run_external_probe=probe))


@router.post("/v1/models/{model_name}/unload")
async def unload_model(request: Request, model_name: str) -> dict[str, object]:
    return {"ok": True, **request.app.state.service.unload_model(model_name)}
