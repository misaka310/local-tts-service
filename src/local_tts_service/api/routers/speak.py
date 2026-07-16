from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from ...errors import ProviderError
from ...models import SpeakRequest, SpeakResponse
router=APIRouter()
@router.post("/v1/speak", response_model=SpeakResponse)
async def speak(payload: SpeakRequest, request: Request) -> SpeakResponse:
    outcome=request.app.state.synthesis_service.synthesize(payload)
    if outcome.error_payload is not None: return JSONResponse(status_code=outcome.status_code, content=outcome.error_payload)
    if outcome.response is None: raise ProviderError("synthesis completed without a response")
    return outcome.response
