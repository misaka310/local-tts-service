from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from ...models import ReferenceVoicesResponse
from ..dependencies import serialize_voice
router=APIRouter()
@router.get("/v1/voices")
async def list_voices_legacy(request: Request) -> JSONResponse:
    items=[serialize_voice(v) for v in request.app.state.service.list_reference_voices()]
    return JSONResponse(content={"ok": True, "deprecated": True, "use": "/v1/reference-voices", "voices": items})
@router.get("/v1/reference-voices", response_model=ReferenceVoicesResponse)
async def list_reference_voices(request: Request) -> ReferenceVoicesResponse:
    service=request.app.state.service; c=service.config
    return ReferenceVoicesResponse(defaultReferenceVoice=c.default_reference_voice, referenceVoicesDir=str(c.reference_voices_dir), voices=[serialize_voice(v) for v in service.list_reference_voices()])
