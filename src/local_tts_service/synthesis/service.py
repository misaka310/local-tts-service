from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from ..errors import RequestValidationError
from ..models import SpeakRequest, SpeakResponse
from ..reference_voices import gpt_sovits_duration_error
from ..runtime_registry import resolve_runtime_name
from ..storage import build_audio_url, safe_request_id
from .capability_validator import validate_instruction_requirements, validate_model_capabilities, validate_voice_design_instruction
from .chunked_synthesizer import synthesize_chunked
from .chunking import merge_chunking_override
from .request_normalizer import normalize_request

@dataclass(frozen=True)
class SynthesisOutcome:
    response: SpeakResponse | None = None
    error_payload: dict[str, Any] | None = None
    status_code: int = 200

@dataclass
class SynthesisService:
    config: Any
    runtimes: dict[str, Any]
    pick_model: Callable[[str | None, str | None], tuple[str, Any]]
    resolve_reference_voice: Callable[..., Any | None]
    model_availability: Callable[[str, Any], tuple[bool, str | None]]

    def synthesize(self, payload: SpeakRequest) -> SynthesisOutcome:
        request_id = safe_request_id(payload.requestId)
        model_name, model_cfg = self.pick_model(payload.model, payload.voice)
        validate_model_capabilities(payload, model_name, model_cfg)
        normalized = normalize_request(payload, model_cfg)
        validate_instruction_requirements(normalized.payload, model_name, model_cfg)
        requested_voice = payload.voiceId or payload.referenceVoice
        reference_voice = None
        if model_cfg.requires_reference_audio:
            if not str(requested_voice or "").strip(): raise RequestValidationError(f"voiceId is required for model: {model_name}")
            reference_voice = self.resolve_reference_voice(requested_voice, require_reference_text=bool(getattr(model_cfg, "requires_reference_text", False)))
        elif str(requested_voice or "").strip() and getattr(model_cfg, "supports_reference_voice", False):
            reference_voice = self.resolve_reference_voice(requested_voice, require_reference_text=bool(getattr(model_cfg, "requires_reference_text", False)))
        if reference_voice is not None and str(model_name).startswith("gpt_sovits_"):
            duration_error = gpt_sovits_duration_error(reference_voice.duration_sec)
            if duration_error: raise RequestValidationError(f"GPT-SoVITS縺ｧ縺ｯ縺薙・蜿ら・髻ｳ螢ｰ縺ｯ菴ｿ縺医∪縺帙ｓ: {reference_voice.voice_id} ({duration_error})")
        available, reason = self.model_availability(model_name, model_cfg)
        if not available:
            return SynthesisOutcome(status_code=400, error_payload={"ok": False, "requestId": request_id, "model": model_name, "runtime": model_cfg.runtime, "voiceId": reference_voice.voice_id if reference_voice is not None else requested_voice, "audioPath": "", "audioUrl": "", "seedUsed": normalized.payload.seed, "instructionUsed": normalized.instruction, "available": False, "unavailableReason": reason, "errorMessage": reason or f"model unavailable: {model_name}", "timings": None, "textLength": len(normalized.payload.text), "voiceDescription": normalized.payload.voiceDescription or normalized.instruction, "captionInjectionMode": None})
        validate_voice_design_instruction(normalized.payload, model_name, model_cfg)
        runtime_name = resolve_runtime_name(payload.engine, model_cfg.runtime)
        runtime = self.runtimes.get(runtime_name)
        if runtime is None: raise RequestValidationError(f"unknown runtime: {runtime_name}")
        chunking = merge_chunking_override(getattr(model_cfg, "chunking", None) or self.config.chunking, normalized.payload.chunking)
        result = synthesize_chunked(runtime=runtime, payload=normalized.payload, request_id=request_id, model_name=model_name, audio_output_dir=self.config.audio_output_dir, chunking=chunking, reference_voice=reference_voice)
        voice_desc = payload.voiceDescription or normalized.caption or getattr(model_cfg, "voice_description", None)
        return SynthesisOutcome(response=SpeakResponse(ok=True, requestId=request_id, model=model_name, runtime=result.runtime, voiceId=reference_voice.voice_id if reference_voice is not None else None, audioUrl=build_audio_url(self.config.public_base_url, result.audio_path.name), audioPath=str(result.audio_path), seedUsed=normalized.payload.seed, instructionUsed=normalized.instruction, available=True, unavailableReason=None, errorMessage=None, timings=getattr(result, "timings", None), textLength=len(normalized.payload.text), voiceDescription=voice_desc, captionInjectionMode=getattr(result, "caption_injection_mode", None)))
