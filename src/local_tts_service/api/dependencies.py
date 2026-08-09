from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from ..errors import RequestValidationError
from ..reference_voices import find_reference_voice, scan_reference_voices

@dataclass
class LocalTTSService:
    config: Any
    runtimes: dict[str, Any]
    def pick_model(self, model_name: str | None, legacy_voice_name: str | None = None) -> tuple[str, Any]:
        chosen = str(model_name or "").strip() or str(legacy_voice_name or "").strip() or self.config.default_model
        cfg = self.config.models.get(chosen)
        if cfg is None: raise RequestValidationError(f"unknown model: {chosen}")
        return chosen, cfg
    def list_reference_voices(self) -> list[Any]:
        return scan_reference_voices(self.config.reference_voices_dir, require_reference_text=False)
    def resolve_reference_voice(self, requested_voice_id: str | None, *, require_reference_text: bool = False) -> Any | None:
        chosen = str(requested_voice_id or "").strip()
        if not chosen: return None
        voice = find_reference_voice(self.config.reference_voices_dir, chosen, require_reference_text=require_reference_text)
        if voice is None: raise RequestValidationError(f"unknown reference voice: {chosen}")
        if not voice.enabled:
            if require_reference_text and voice.has_reference_audio and not voice.has_reference_text: raise RequestValidationError(f"voice.txt is required for voiceId: {chosen}")
            raise RequestValidationError(f"reference voice is not usable: {chosen} ({voice.error_reason})")
        return voice

    def unload_model(self, model_name: str) -> dict[str, Any]:
        chosen, cfg = self.pick_model(model_name)
        runtime = self.runtimes.get(cfg.runtime)
        release_model = getattr(runtime, "release_model", None)
        if not callable(release_model):
            raise RequestValidationError(f"model runtime does not support unload: {chosen}")
        released = bool(release_model(chosen))
        return {"model": chosen, "runtime": cfg.runtime, "released": released}

def serialize_voice(voice: Any) -> dict[str, Any]:
    return {"voiceId": voice.voice_id, "displayName": voice.display_name, "hasReferenceAudio": voice.has_reference_audio, "hasReferenceText": voice.has_reference_text, "enabled": voice.enabled, "audioDurationSec": voice.duration_sec, "minReferenceDurationSec": voice.min_duration_sec, "maxReferenceDurationSec": voice.max_duration_sec, "errorReason": voice.error_reason}
