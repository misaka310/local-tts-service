from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from ...storage import resolve_audio_path
router=APIRouter()
_CONTENT_TYPES={".wav":"audio/wav",".mp3":"audio/mpeg",".flac":"audio/flac",".ogg":"audio/ogg",".m4a":"audio/mp4",".aac":"audio/aac"}
@router.get("/audio/{filename}")
async def get_audio(filename: str, request: Request) -> FileResponse:
    path=resolve_audio_path(request.app.state.service.config.audio_output_dir, filename)
    return FileResponse(path=path, media_type=_CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream"), filename=path.name)
