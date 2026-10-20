from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from ..reference_voices import find_reference_voice
from ..api.dependencies import serialize_voice

def health_check_url(base_url: str, health_path: str) -> str:
    path = str(health_path or "/system_stats").strip() or "/system_stats"
    if path.startswith(("http://", "https://")): return path
    return f"{base_url.rstrip('/')}{path if path.startswith('/') else '/' + path}"

def check_http_health(url: str) -> tuple[bool, str | None]:
    try:
        with urlopen(Request(url, method="GET"), timeout=2) as response:
            return 200 <= int(getattr(response, "status", 200)) < 500, None
    except HTTPError as exc: return False, f"HTTP {exc.code}"
    except URLError as exc: return False, str(exc.reason)
    except OSError as exc: return False, str(exc)

@dataclass
class HealthService:
    config: Any
    runtimes: dict[str, Any]
    model_availability: Callable[[str, Any], tuple[bool, str | None]]
    list_reference_voices: Callable[[], list[Any]]

    def build_deep_payload(self) -> dict[str, Any]:
        config, runtimes = self.config, self.runtimes
        runtime_checks: dict[str, Any] = {}
        external_checks: dict[str, Any] = {}

        comfy_model_names = sorted(
            name
            for name, model in config.models.items()
            if model.runtime in {"comfyui", "comfyui_voxcpm2"}
        )
        if comfy_model_names:
            comfy_cfg = config.runtimes.get("comfyui", {})
            runtime = runtimes.get("comfyui")
            base_url = str(comfy_cfg.get("baseUrl", "http://127.0.0.1:8288"))
            url = health_check_url(base_url, str(comfy_cfg.get("healthPath", "/system_stats")))
            external = config.external_services.get("comfyui", {})
            enabled = bool(external.get("enabled", False))
            if not enabled:
                ok, error = True, None
            elif callable(getattr(runtime, "check_health", None)):
                try:
                    ok = bool(runtime.check_health())
                    error = None if ok else "runtime health check returned false"
                except Exception as exc:
                    ok, error = False, str(exc)
            else:
                ok, error = check_http_health(url)

            runtime_checks["comfyui"] = {
                "ok": ok,
                "enabled": enabled,
                "skipped": not enabled,
                "requiredByModels": comfy_model_names,
                "baseUrl": base_url,
                "healthUrl": url,
                "autoLaunch": bool(comfy_cfg.get("autoLaunch", False)),
                "launchBatPath": str(comfy_cfg.get("launchBatPath", "")),
                "launchWorkingDir": str(comfy_cfg.get("launchWorkingDir", "")),
                "inputDir": str(comfy_cfg.get("inputDir", "")),
                "outputDir": str(comfy_cfg.get("outputDir", "")),
                "error": error,
                "runtimeClass": type(runtime).__name__ if runtime is not None else None,
            }
            if isinstance(external, dict) and external:
                health_url = str(external.get("healthUrl", url))
                ext_ok, ext_error = check_http_health(health_url) if enabled else (True, None)
                external_checks["comfyui"] = {
                    "ok": ext_ok,
                    "enabled": enabled,
                    "skipped": not enabled,
                    "requiredByModels": comfy_model_names,
                    "healthUrl": health_url,
                    "rootDir": str(external.get("rootDir", "")),
                    "startCommand": str(external.get("startCommand", "")),
                    "error": ext_error,
                }

        model_checks = {}
        for name, model in sorted(config.models.items()):
            available, reason = self.model_availability(name, model)
            default_voice = None
            usable = None
            if model.requires_reference_audio and config.default_reference_voice:
                resolved = find_reference_voice(config.reference_voices_dir, config.default_reference_voice)
                default_voice = config.default_reference_voice
                usable = bool(resolved and resolved.enabled)
            model_checks[name] = {
                "configured": True,
                "runtime": model.runtime,
                "workflowPath": str(model.workflow_path) if model.workflow_path else None,
                "workflowExists": bool(model.workflow_path and model.workflow_path.is_file()),
                "requiresReferenceAudio": model.requires_reference_audio,
                "requiresReferenceText": bool(getattr(model, "requires_reference_text", False)),
                "available": available,
                "unavailableReason": reason,
                "modelId": getattr(model, "model_id", None),
                "referenceAudioPath": str(model.reference_audio_path) if model.reference_audio_path else None,
                "referenceAudioExists": bool(model.reference_audio_path and model.reference_audio_path.is_file()),
                "referenceTextPath": str(model.reference_text_path) if model.reference_text_path else None,
                "referenceTextExists": bool(model.reference_text_path and model.reference_text_path.is_file()),
                "defaultReferenceVoice": default_voice,
                "defaultReferenceVoiceUsable": usable,
                "chunking": getattr(model, "chunking", None) or config.chunking,
                "textSplitMethod": getattr(model, "text_split_method", None),
            }

        return {
            "ok": all(item.get("ok", False) for item in runtime_checks.values()),
            "service": {
                "name": "local-tts-service",
                "host": config.host,
                "port": config.port,
                "defaultModel": config.default_model,
                "defaultReferenceVoice": config.default_reference_voice,
                "publicBaseUrl": config.public_base_url,
                "audioOutputDir": str(config.audio_output_dir),
            },
            "referenceVoicesDir": str(config.reference_voices_dir),
            "chunking": config.chunking,
            "runtimeChecks": runtime_checks,
            "externalChecks": external_checks,
            "modelChecks": model_checks,
            "referenceVoices": [serialize_voice(v) for v in self.list_reference_voices()],
        }
