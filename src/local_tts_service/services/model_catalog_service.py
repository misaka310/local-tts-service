from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from ..models import ModelInfo
from ..runtimes import ExternalCliRuntime

@dataclass
class ModelCatalogService:
    config: Any
    runtimes: dict[str, Any]

    def availability(self, name: str, cfg: Any, *, run_external_probe: bool = True) -> tuple[bool, str | None]:
        runtime = self.runtimes.get(cfg.runtime)
        if runtime is None: return False, f"runtime is not configured: {cfg.runtime}"
        if cfg.runtime in {"comfyui", "comfyui_voxcpm2"}:
            external = self.config.external_services.get("comfyui", {})
            if not bool(external.get("enabled", False)): return False, "ComfyUI is disabled in config/config.local.json"
            if cfg.workflow_path is not None and not cfg.workflow_path.is_file(): return False, f"workflow file not found: {cfg.workflow_path}"
        if isinstance(runtime, ExternalCliRuntime) and getattr(cfg, "external_command_key", None) == "gpt_sovits_api":
            external = self.config.external_services.get("gptSovits")
            if isinstance(external, dict) and "enabled" in external and not bool(external.get("enabled")): return False, "GPT-SoVITS is disabled in config/config.local.json"
        inspector_name = "get_model_availability"
        if not run_external_probe and callable(getattr(runtime, "get_static_model_availability", None)): inspector_name = "get_static_model_availability"
        inspector = getattr(runtime, inspector_name, None)
        if callable(inspector):
            status = inspector(name, cfg); return bool(getattr(status, "available", False)), getattr(status, "reason", None)
        return True, None

    def serialize(self, name: str, cfg: Any, *, run_external_probe: bool = True) -> ModelInfo:
        available, reason = self.availability(name, cfg, run_external_probe=run_external_probe)
        runtime = self.runtimes.get(cfg.runtime)
        runtime_metadata: dict[str, Any] = {}
        metadata_provider = getattr(runtime, "get_runtime_metadata", None)
        if available and callable(metadata_provider):
            runtime_metadata = dict(metadata_provider() or {})
        return ModelInfo(
            id=name,
            label=str(getattr(cfg, "label", None) or name),
            family=str(getattr(cfg, "family", None) or cfg.runtime),
            model=name,
            runtime=cfg.runtime,
            available=available,
            enabled=available,
            unavailableReason=reason,
            modelId=getattr(cfg, "model_id", None),
            supportsReferenceVoice=bool(getattr(cfg, "supports_reference_voice", cfg.requires_reference_audio)),
            requiresReferenceText=bool(getattr(cfg, "requires_reference_text", False)),
            supportsVoiceClone=bool(getattr(cfg, "supports_voice_clone", False)),
            supportsVoiceDesign=bool(getattr(cfg, "supports_voice_design", False)),
            supportsInstruction=bool(getattr(cfg, "supports_instruction", False)),
            supportsLanguage=bool(getattr(cfg, "supports_language", False)),
            supportsSeed=bool(getattr(cfg, "supports_seed", False)),
            supportsSpeedControl=bool(getattr(cfg, "supports_speed_control", False)),
            supportsStyleStrength=bool(getattr(cfg, "supports_style_strength", False)),
            defaultLanguage=getattr(cfg, "default_language", None),
            notes=getattr(cfg, "notes", None),
            executionDevice=runtime_metadata.get("executionDevice"),
            cpuFallback=bool(runtime_metadata.get("cpuFallback", False)),
            performanceWarning=runtime_metadata.get("performanceWarning"),
            requiresReferenceAudio=cfg.requires_reference_audio,
            supportsCaption=cfg.supports_caption,
            defaultCaption=cfg.default_caption,
            chunking=getattr(cfg, "chunking", None) or self.config.chunking,
            textSplitMethod=getattr(cfg, "text_split_method", None),
        )

    def list(self, *, run_external_probe: bool) -> list[ModelInfo]:
        return [self.serialize(name, cfg, run_external_probe=run_external_probe) for name, cfg in sorted(self.config.models.items())]
