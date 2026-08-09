from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import ConfigError
from .runtimes import (
    ComfyUIRuntime,
    ComfyUIVoxCPM2Runtime,
    ExternalCliRuntime,
    IrodoriVoiceDesignDirectRuntime,
    MockWavRuntime,
    Qwen3TTSRuntime,
)

RUNTIME_ALIASES = {
    "comfyui_qwen3": "comfyui",
}


def resolve_path(root: Path, value: Any, label: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ConfigError(f"{label} path setting is empty")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()
    return path


def resolve_runtime_name(engine: str | None, configured_runtime: str) -> str:
    selected = str(engine or configured_runtime).strip()
    return RUNTIME_ALIASES.get(selected, selected)


def build_runtime_registry(config: Any) -> dict[str, Any]:
    runtimes: dict[str, Any] = {}
    runtime_log_dir = (config.root_dir / "runtime" / "logs").resolve()

    mock_cfg = config.runtimes.get("mock_wav", {})
    runtimes["mock_wav"] = MockWavRuntime(
        output_dir=config.audio_output_dir,
        duration_sec=float(mock_cfg.get("durationSec", 1.2)),
        sample_rate=int(mock_cfg.get("sampleRate", 24000)),
    )

    comfy_cfg = config.runtimes.get("comfyui", {})
    runtimes["comfyui"] = ComfyUIRuntime(
        output_dir=config.audio_output_dir,
        models=config.models,
        base_url=str(comfy_cfg.get("baseUrl", "http://127.0.0.1:8288")),
        input_dir=resolve_path(
            config.root_dir,
            comfy_cfg.get("inputDir", "./runtime/comfy-input"),
            "comfyui.inputDir",
        ),
        comfy_output_dir=resolve_path(
            config.root_dir,
            comfy_cfg.get("outputDir", "./runtime/comfy-output"),
            "comfyui.outputDir",
        ),
        timeout_sec=int(comfy_cfg.get("timeoutSec", 300)),
        poll_interval_sec=float(comfy_cfg.get("pollIntervalSec", 1.0)),
        default_audio_ext=str(comfy_cfg.get("defaultAudioExt", ".wav")),
        auto_launch=bool(comfy_cfg.get("autoLaunch", False)),
        launch_bat_path=(
            resolve_path(config.root_dir, comfy_cfg.get("launchBatPath"), "comfyui.launchBatPath")
            if comfy_cfg.get("launchBatPath")
            else None
        ),
        launch_working_dir=(
            resolve_path(
                config.root_dir,
                comfy_cfg.get("launchWorkingDir"),
                "comfyui.launchWorkingDir",
            )
            if comfy_cfg.get("launchWorkingDir")
            else None
        ),
        startup_timeout_sec=int(
            comfy_cfg.get("startupTimeoutSec", config.stack.get("startupTimeoutSec", 180))
        ),
        startup_poll_interval_sec=float(
            comfy_cfg.get("startupPollIntervalSec", config.stack.get("pollIntervalSec", 1.0))
        ),
        health_path=str(comfy_cfg.get("healthPath", "/system_stats")),
        runtime_log_dir=runtime_log_dir,
    )

    voxcpm2_cfg = config.runtimes.get("comfyui_voxcpm2", {})
    runtimes["comfyui_voxcpm2"] = ComfyUIVoxCPM2Runtime(
        output_dir=config.audio_output_dir,
        models=config.models,
        base_url=str(voxcpm2_cfg.get("baseUrl", "http://127.0.0.1:8288")),
        input_dir=resolve_path(
            config.root_dir,
            voxcpm2_cfg.get("inputDir", comfy_cfg.get("inputDir", "./runtime/comfy-input")),
            "comfyui_voxcpm2.inputDir",
        ),
        comfy_output_dir=resolve_path(
            config.root_dir,
            voxcpm2_cfg.get("outputDir", comfy_cfg.get("outputDir", "./runtime/comfy-output")),
            "comfyui_voxcpm2.outputDir",
        ),
        timeout_sec=int(voxcpm2_cfg.get("timeoutSec", comfy_cfg.get("timeoutSec", 300))),
        poll_interval_sec=float(
            voxcpm2_cfg.get("pollIntervalSec", comfy_cfg.get("pollIntervalSec", 1.0))
        ),
        default_audio_ext=str(
            voxcpm2_cfg.get("defaultAudioExt", comfy_cfg.get("defaultAudioExt", ".wav"))
        ),
    )

    voicedesign_cfg = config.runtimes.get("irodori_voicedesign_direct", {})
    if isinstance(voicedesign_cfg, dict) and voicedesign_cfg:
        runtimes["irodori_voicedesign_direct"] = IrodoriVoiceDesignDirectRuntime(
            output_dir=config.audio_output_dir,
            models=config.models,
            root_dir=config.root_dir,
            python_executable=str(voicedesign_cfg.get("pythonExecutable", "")),
            wrapper_dir=resolve_path(
                config.root_dir,
                voicedesign_cfg.get("wrapperDir", ""),
                "irodori_voicedesign_direct.wrapperDir",
            ),
            checkpoint=str(voicedesign_cfg.get("checkpoint", "")),
            timeout_sec=int(voicedesign_cfg.get("timeoutSec", 1800)),
            startup_timeout_sec=int(voicedesign_cfg.get("startupTimeoutSec", 1800)),
            idle_timeout_sec=float(voicedesign_cfg.get("idleTimeoutSec", 600)),
            model_device=str(voicedesign_cfg.get("modelDevice", "auto")),
            model_precision=str(voicedesign_cfg.get("modelPrecision", "auto")),
            codec_device=str(
                voicedesign_cfg.get("codecDevice", voicedesign_cfg.get("modelDevice", "auto"))
            ),
            codec_precision=str(voicedesign_cfg.get("codecPrecision", "fp32")),
            codec_repo=str(
                voicedesign_cfg.get(
                    "codecRepo",
                    "./runtime/models/irodori/Semantic-DACVAE-Japanese-32dim",
                )
            ),
            text_processor_repo=str(
                voicedesign_cfg.get("textProcessorRepo", "llm-jp/llm-jp-3-150m")
            ),
            text_processor_dir=str(
                voicedesign_cfg.get(
                    "textProcessorDir",
                    "./runtime/models/irodori/tokenizers/llm-jp-3-150m",
                )
            ),
            reference_cache_dir=str(
                voicedesign_cfg.get(
                    "referenceCacheDir",
                    "./runtime/cache/irodori-reference-latents",
                )
            ),
        )

    qwen3_tts_cfg = config.runtimes.get("qwen3_tts", {})
    runtimes["qwen3_tts"] = Qwen3TTSRuntime(
        output_dir=config.audio_output_dir,
        models=config.models,
        device=str(qwen3_tts_cfg.get("device", "auto")),
        dtype=str(qwen3_tts_cfg.get("dtype", "auto")),
        attn_implementation=str(qwen3_tts_cfg.get("attnImplementation", "")),
        hf_cache_dir=(
            resolve_path(config.root_dir, qwen3_tts_cfg.get("hfCacheDir"), "qwen3_tts.hfCacheDir")
            if qwen3_tts_cfg.get("hfCacheDir")
            else None
        ),
        vendor_dir=(
            resolve_path(config.root_dir, qwen3_tts_cfg.get("vendorDir"), "qwen3_tts.vendorDir")
            if qwen3_tts_cfg.get("vendorDir")
            else None
        ),
        allow_download=bool(qwen3_tts_cfg.get("allowDownload", False)),
    )

    external_cli_cfg = config.runtimes.get("external_cli", {})
    external_commands = external_cli_cfg.get("commands", {})
    if not isinstance(external_commands, dict):
        external_commands = {}
    runtimes["external_cli"] = ExternalCliRuntime(
        output_dir=config.audio_output_dir,
        models=config.models,
        root_dir=config.root_dir,
        request_dir=resolve_path(
            config.root_dir,
            external_cli_cfg.get("requestDir", "./runtime/external-requests"),
            "external_cli.requestDir",
        ),
        commands=external_commands,
        availability_commands=external_cli_cfg.get("availabilityCommands", {}),
        timeout_sec=int(external_cli_cfg.get("timeoutSec", 1800)),
        dry_run=bool(external_cli_cfg.get("dryRun", False)),
    )

    return runtimes
