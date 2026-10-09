from __future__ import annotations
from pathlib import Path
import shutil
from typing import Any, Protocol
from ..models import SpeakRequest
from ..runtimes import SynthesizeRequest
from ..runtimes.base import SynthesizeResult
from ..storage import build_output_basename, concat_wav_files
from .chunking import should_keep_chunk_files, split_text_for_chunks

class SynthesisRuntime(Protocol):
    def synthesize(self, request: SynthesizeRequest) -> SynthesizeResult: ...

def synthesize_chunked(*, runtime: SynthesisRuntime, payload: SpeakRequest, request_id: str, model_name: str, audio_output_dir: Path, chunking: dict[str, Any], reference_voice: Any | None) -> SynthesizeResult:
    chunks = split_text_for_chunks(payload.text, soft_chunk_chars=int(chunking.get("softChunkChars", 120)), max_chunk_chars=int(chunking.get("maxChunkChars", 200)), hard_limit_chars=int(chunking.get("hardLimitChars", 260)))
    def build_request(text: str, chunk_request_id: str, output_basename: str) -> SynthesizeRequest:
        return SynthesizeRequest(text=text, request_id=chunk_request_id, model_name=model_name, output_basename=output_basename, seed=payload.seed, speed_scale=payload.speedScale, style_strength=payload.styleStrength, caption=payload.caption or payload.styleCaption, instruction=payload.instruction, language=payload.language, voice_description=payload.voiceDescription, voice_id=reference_voice.voice_id if reference_voice is not None else None, reference_audio_path=reference_voice.audio_path if reference_voice is not None and reference_voice.has_reference_audio else None, reference_text_path=reference_voice.text_path if reference_voice is not None and reference_voice.has_reference_text else None, output_format=payload.format)
    if len(chunks) <= 1:
        basename = build_output_basename(payload.text, request_id); return runtime.synthesize(build_request(payload.text, request_id, basename))
    chunk_dir = audio_output_dir / "chunks" / request_id; chunk_dir.mkdir(parents=True, exist_ok=True)
    merged_basename = build_output_basename(payload.text, request_id); chunk_paths: list[Path] = []; runtime_name = getattr(runtime, "name", type(runtime).__name__)
    for index, chunk_text in enumerate(chunks, start=1):
        result = runtime.synthesize(build_request(chunk_text, f"{request_id}-chunk-{index:03d}", f"{merged_basename}-chunk-{index:03d}"))
        destination = chunk_dir / f"{index:03d}.wav"; result.audio_path.replace(destination); chunk_paths.append(destination); runtime_name = result.runtime
    merged_path = audio_output_dir / f"{merged_basename}.wav"; concat_wav_files(chunk_paths, merged_path, pause_between_chunks_ms=int(chunking.get("pauseBetweenChunksMs", 0)))
    if not should_keep_chunk_files(chunking):
        shutil.rmtree(chunk_dir)
    return SynthesizeResult(runtime=runtime_name, model=model_name, audio_path=merged_path)
