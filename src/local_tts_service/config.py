from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .models import AppConfig, ModelConfig, WorkflowTargetConfig, WorkflowTargetsConfig

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8730,
    "publicBaseUrl": "",
    "defaultModel": "irodori_v3",
    "referenceVoicesDir": "./reference/voices",
    "audioOutputDir": "./runtime/audio",
    "chunking": {
        "softChunkChars": 120,
        "maxChunkChars": 200,
        "hardLimitChars": 260,
        "pauseBetweenChunksMs": 250,
        "keepChunkFiles": False,
    },
    "corsAllowedOrigins": [
        "http://127.0.0.1",
        "http://localhost",
        "http://127.0.0.1:5177",
        "http://localhost:5177",
    ],
    "stack": {
        "killPortsBeforeStart": False,
        "portsToKill": [8730, 5177],
        "startupTimeoutSec": 180,
        "pollIntervalSec": 1.0,
    },
    "externalServices": {
        "comfyui": {
            "enabled": False,
            "name": "ComfyUI",
            "startCommand": "",
            "baseUrl": "http://127.0.0.1:8288",
            "healthUrl": "http://127.0.0.1:8288/system_stats",
        },
        "gptSovits": {
            "enabled": False,
            "rootDir": "./runtime/vendor/GPT-SoVITS",
            "apiUrl": "http://127.0.0.1:9880/tts",
        },
    },
    "frontend": {
        "host": "127.0.0.1",
        "port": 5177,
        "ttsBaseUrl": "http://127.0.0.1:8730",
    },
    "models": {
        "mock": {
            "runtime": "mock_wav",
            "requiresReferenceAudio": False,
        },
        "irodori_v2": {
            "runtime": "irodori_voicedesign_direct",
            "label": "irodori v2",
            "modelId": "Aratako/Irodori-TTS-500M-v2",
            "checkpoint": "./runtime/models/irodori/Irodori-TTS-500M-v2/model.safetensors",
            "family": "irodori",
            "requiresReferenceAudio": False,
            "supportsReferenceVoice": True,
            "supportsCaption": False,
            "supportsInstruction": False,
            "supportsStyleStrength": False,
            "supportsVoiceDesign": False,
            "supportsSpeedControl": False,
            "supportsSeed": True,
            "chunking": {"softChunkChars": 100, "maxChunkChars": 160, "hardLimitChars": 200, "pauseBetweenChunksMs": 250},
        },
        "irodori_v3": {
            "runtime": "irodori_voicedesign_direct",
            "label": "irodori v3",
            "modelId": "Aratako/Irodori-TTS-500M-v3",
            "checkpoint": "./runtime/models/irodori/Irodori-TTS-500M-v3/model.safetensors",
            "family": "irodori",
            "requiresReferenceAudio": False,
            "supportsSeed": True,
            "supportsInstruction": False,
            "supportsStyleStrength": False,
            "supportsVoiceDesign": False,
            "supportsSpeedControl": True,
            "supportsReferenceVoice": True,
            "chunking": {"softChunkChars": 160, "maxChunkChars": 220, "hardLimitChars": 280, "pauseBetweenChunksMs": 250},
        },
        "irodori_v3_low_latency": {
            "runtime": "irodori_voicedesign_direct",
            "label": "Irodori v3 低遅延 (8-step)",
            "modelId": "Aratako/Irodori-TTS-500M-v3",
            "checkpoint": "./runtime/models/irodori/Irodori-TTS-500M-v3/model.safetensors",
            "family": "irodori",
            "requiresReferenceAudio": False,
            "supportsSeed": True,
            "supportsInstruction": False,
            "supportsStyleStrength": False,
            "supportsVoiceDesign": False,
            "supportsSpeedControl": True,
            "supportsReferenceVoice": True,
            "chunking": {"softChunkChars": 160, "maxChunkChars": 220, "hardLimitChars": 280, "pauseBetweenChunksMs": 250},
            "notes": "8-step / sway / reference latent cache の低遅延プロファイル。",
            "runtimeOptions": {
                "optimizationProfile": "low_latency_8",
                "codecPrecision": "bf16",
            },
        },
        "irodori_v3_voicedesign": {
            "runtime": "irodori_voicedesign_direct",
            "label": "Irodori v3 VoiceDesign",
            "family": "irodori",
            "modelId": "Aratako/Irodori-TTS-600M-v3-VoiceDesign",
            "checkpoint": "./runtime/models/irodori/Irodori-TTS-600M-v3-VoiceDesign/model.safetensors",
            "requiresReferenceAudio": False,
            "supportsCaption": True,
            "supportsInstruction": True,
            "supportsSeed": True,
            "supportsSpeedControl": True,
            "supportsStyleStrength": True,
            "supportsVoiceDesign": True,
            "supportsReferenceVoice": True,
            "chunking": {"softChunkChars": 160, "maxChunkChars": 220, "hardLimitChars": 280, "pauseBetweenChunksMs": 250},
        },
        "irodori_v4_small": {
            "runtime": "irodori_voicedesign_direct",
            "label": "Irodori v4 Small",
            "family": "irodori",
            "modelId": "Aratako/Irodori-TTS-v4-Small",
            "checkpoint": "./runtime/models/irodori/Irodori-TTS-v4-Small/model.safetensors",
            "requiresReferenceAudio": False,
            "supportsCaption": True,
            "supportsInstruction": True,
            "supportsSeed": True,
            "supportsSpeedControl": True,
            "supportsStyleStrength": True,
            "supportsVoiceDesign": True,
            "supportsReferenceVoice": True,
            "chunking": {"softChunkChars": 180, "maxChunkChars": 240, "hardLimitChars": 300, "pauseBetweenChunksMs": 250},
            "notes": "参照音声による声寄せと話し方メモを1モデルで利用できるIrodori v4 Smallです。",
        },
        "qwen3_tts_clone_0_6b": {
            "runtime": "qwen3_tts",
            "label": "Qwen3-TTS Voice Clone 0.6B",
            "family": "qwen3_tts",
            "modelId": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            "requiresReferenceAudio": True,
            "requiresReferenceText": True,
            "supportsSeed": True,
            "supportsLanguage": True,
            "supportsVoiceClone": True,
            "supportsReferenceVoice": True,
            "defaultLanguage": "Japanese",
            "notes": "voice.wav と voice.txt を使って短文の本人声寄せ比較を行うモデルです。",
        },
        "qwen3_tts_clone_1_7b": {
            "runtime": "qwen3_tts",
            "label": "Qwen3-TTS Voice Clone 1.7B",
            "family": "qwen3_tts",
            "modelId": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            "requiresReferenceAudio": True,
            "requiresReferenceText": True,
            "supportsSeed": True,
            "supportsLanguage": True,
            "supportsVoiceClone": True,
            "supportsReferenceVoice": True,
            "defaultLanguage": "Japanese",
            "notes": "0.6B と比較するための高品質 clone モデルです。",
        },
        "sarashina2_2_tts": {
            "runtime": "external_cli",
            "label": "Sarashina2.2-TTS",
            "family": "sarashina",
            "modelId": "sbintuitions/sarashina2.2-tts",
            "requiresReferenceAudio": True,
            "requiresReferenceText": True,
            "supportsReferenceVoice": True,
            "supportsVoiceClone": True,
            "supportsLanguage": True,
            "supportsSeed": True,
            "defaultLanguage": "ja",
            "externalCommandKey": "sarashina",
            "chunking": {"softChunkChars": 120, "maxChunkChars": 180, "hardLimitChars": 240, "pauseBetweenChunksMs": 250},
            "notes": "日本語中心のゼロショット音声クローン。非商用ライセンスです。",
        },
        "fireredtts2": {
            "runtime": "external_cli",
            "label": "FireRedTTS-2",
            "family": "fireredtts2",
            "modelId": "FireRedTeam/FireRedTTS2",
            "requiresReferenceAudio": True,
            "requiresReferenceText": True,
            "supportsReferenceVoice": True,
            "supportsVoiceClone": True,
            "supportsLanguage": True,
            "supportsSeed": True,
            "defaultLanguage": "ja",
            "externalCommandKey": "fireredtts2",
            "chunking": {"softChunkChars": 160, "maxChunkChars": 240, "hardLimitChars": 320, "pauseBetweenChunksMs": 250},
            "notes": "多言語対応のゼロショット音声クローン。WSLの専用環境で実行します。",
        },
        "t5gemma_tts_2b_2b": {
            "runtime": "external_cli",
            "label": "T5Gemma-TTS 2B-2B",
            "family": "t5gemma_tts",
            "modelId": "Aratako/T5Gemma-TTS-2b-2b",
            "requiresReferenceAudio": True,
            "requiresReferenceText": True,
            "supportsReferenceVoice": True,
            "supportsVoiceClone": True,
            "supportsLanguage": True,
            "supportsSeed": True,
            "defaultLanguage": "ja",
            "externalCommandKey": "t5gemma",
            "chunking": {"softChunkChars": 100, "maxChunkChars": 160, "hardLimitChars": 220, "pauseBetweenChunksMs": 250},
            "notes": "日本語TTSのゼロショット音声クローン。非商用ライセンスです。",
        },
        "fish_s1_mini": {
            "runtime": "external_cli",
            "label": "FishAudio S1-mini",
            "family": "fish_speech",
            "modelId": "fishaudio/s1-mini",
            "requiresReferenceAudio": True,
            "requiresReferenceText": True,
            "supportsReferenceVoice": True,
            "supportsVoiceClone": True,
            "supportsLanguage": True,
            "supportsSeed": True,
            "defaultLanguage": "ja",
            "externalCommandKey": "fish_s1_mini",
            "chunking": {"softChunkChars": 120, "maxChunkChars": 180, "hardLimitChars": 240, "pauseBetweenChunksMs": 250},
            "notes": "ゲート付き重みを使うゼロショット音声クローン。非商用ライセンスです。",
        },
        "orpheus_3b_asmr": {
            "runtime": "external_cli",
            "label": "Orpheus 3B ASMR",
            "family": "orpheus",
            "modelId": "nyuuzyou/Orpheus-3B-ASMR",
            "requiresReferenceAudio": False,
            "requiresReferenceText": False,
            "supportsReferenceVoice": False,
            "supportsVoiceClone": False,
            "supportsLanguage": True,
            "defaultLanguage": "en",
            "externalCommandKey": "orpheus_asmr",
            "chunking": {"softChunkChars": 160, "maxChunkChars": 240, "hardLimitChars": 320, "pauseBetweenChunksMs": 250},
            "notes": "ASMR音声で追加学習された英語向けOrpheus 3B。30では安定した既存voice（tara）で使います。",
        },
        "ming_omni_tts_0_5b": {
            "runtime": "external_cli",
            "label": "Ming Omni TTS 0.5B",
            "family": "ming_omni_tts",
            "modelId": "inclusionAI/Ming-omni-tts-0.5B",
            "requiresReferenceAudio": False,
            "requiresReferenceText": False,
            "supportsReferenceVoice": True,
            "supportsVoiceClone": True,
            "supportsInstruction": True,
            "supportsLanguage": True,
            "defaultLanguage": "zh",
            "externalCommandKey": "ming_omni_tts",
            "chunking": {"softChunkChars": 120, "maxChunkChars": 180, "hardLimitChars": 240, "pauseBetweenChunksMs": 250},
            "notes": "参照音声は任意。話し方メモをstyle指示として渡し、参照なしのvoice designと参照ありのvoice cloneの両方を使えます。",
        },
        "chatterbox_multilingual_v3": {
            "runtime": "external_cli",
            "label": "Chatterbox Multilingual V3",
            "family": "chatterbox",
            "modelId": "ResembleAI/chatterbox",
            "requiresReferenceAudio": True,
            "requiresReferenceText": False,
            "supportsReferenceVoice": True,
            "supportsVoiceClone": True,
            "supportsLanguage": True,
            "supportsSeed": True,
            "supportsStyleStrength": True,
            "defaultLanguage": "ja",
            "externalCommandKey": "chatterbox",
            "chunking": {"softChunkChars": 100, "maxChunkChars": 160, "hardLimitChars": 220, "pauseBetweenChunksMs": 250},
            "notes": "日本語を含む23言語に対応するChatterbox Multilingual V3。参照音声と表現強度を使って感情豊かな音声を生成します。",
        },
        "fun_cosyvoice3_0_5b": {
            "runtime": "external_cli",
            "label": "Fun-CosyVoice 3.0 0.5B",
            "family": "cosyvoice",
            "modelId": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
            "requiresReferenceAudio": True,
            "requiresReferenceText": False,
            "supportsReferenceVoice": True,
            "supportsVoiceClone": True,
            "supportsLanguage": True,
            "supportsSeed": True,
            "supportsInstruction": True,
            "supportsSpeedControl": True,
            "defaultLanguage": "ja",
            "externalCommandKey": "cosyvoice",
            "chunking": {"softChunkChars": 100, "maxChunkChars": 160, "hardLimitChars": 220, "pauseBetweenChunksMs": 250},
            "notes": "日本語入力を内部でカタカナへ正規化し、参照音声と感情・話速指示で生成するFun-CosyVoice 3.0です。",
        },
        "f5_tts_zero_shot": {
            "runtime": "external_cli",
            "label": "F5-TTS Zero-shot",
            "family": "f5_tts",
            "modelId": "F5TTS_v1_Base",
            "requiresReferenceAudio": True,
            "requiresReferenceText": True,
            "supportsReferenceVoice": True,
            "supportsVoiceClone": True,
            "supportsLanguage": True,
            "supportsSeed": True,
            "defaultLanguage": "ja",
            "externalCommandKey": "f5_tts",
            "chunking": {"softChunkChars": 140, "maxChunkChars": 200, "hardLimitChars": 240, "pauseBetweenChunksMs": 250},
            "notes": "reference/voices/<voiceId>/voice.wav と voice.txt を使うゼロショット比較用モデルです。",
        },
        "gpt_sovits_zero_shot": {
            "runtime": "external_cli",
            "label": "GPT-SoVITS Zero-shot",
            "family": "gpt_sovits",
            "modelId": "api_v2",
            "requiresReferenceAudio": True,
            "requiresReferenceText": True,
            "supportsReferenceVoice": True,
            "supportsVoiceClone": True,
            "supportsLanguage": True,
            "supportsSeed": True,
            "defaultLanguage": "ja",
            "externalCommandKey": "gpt_sovits_api",
            "chunking": {"softChunkChars": 80, "maxChunkChars": 120, "hardLimitChars": 160, "pauseBetweenChunksMs": 250},
            "textSplitMethod": "cut0",
            "notes": "起動済み GPT-SoVITS api_v2.py に参照音声付きで投げるゼロショットモデルです。",
        },
        "gpt_sovits_finetuned": {
            "runtime": "external_cli",
            "label": "GPT-SoVITS Fine-tuned",
            "family": "gpt_sovits",
            "modelId": "api_v2",
            "requiresReferenceAudio": False,
            "requiresReferenceText": False,
            "supportsReferenceVoice": True,
            "supportsVoiceClone": True,
            "supportsLanguage": True,
            "supportsSeed": True,
            "defaultLanguage": "ja",
            "externalCommandKey": "gpt_sovits_api",
            "checkpointDir": "./runtime/gpt-sovits/weights/default",
            "requiresTrainedCheckpoint": True,
            "chunking": {"softChunkChars": 80, "maxChunkChars": 120, "hardLimitChars": 160, "pauseBetweenChunksMs": 250},
            "textSplitMethod": "cut0",
            "notes": "scripts/train-gpt-sovits-voice.bat で作った重みを GPT-SoVITS 側に読み込ませて使う枠です。参照音声は任意です。",
        },
    },
    "runtimes": {
        "mock_wav": {"durationSec": 1.2, "sampleRate": 24000},
        "comfyui": {
            "baseUrl": "http://127.0.0.1:8288",
            "inputDir": "./runtime/comfy-input",
            "outputDir": "./runtime/comfy-output",
            "timeoutSec": 300,
            "pollIntervalSec": 1.0,
            "defaultAudioExt": ".wav",
            "autoLaunch": False,
            "launchBatPath": "./scripts/start-comfyui.bat",
            "startupTimeoutSec": 180,
            "startupPollIntervalSec": 1.0,
            "healthPath": "/system_stats",
        },
        "comfyui_voxcpm2": {
            "baseUrl": "http://127.0.0.1:8288",
            "inputDir": "./runtime/comfy-input",
            "outputDir": "./runtime/comfy-output",
            "timeoutSec": 300,
            "pollIntervalSec": 1.0,
            "defaultAudioExt": ".wav",
        },
        "irodori_voicedesign_direct": {
            "pythonExecutable": "./runtime/venv-irodori/Scripts/python.exe",
            "wrapperDir": "./runtime/vendor/Irodori-TTS-upstream",
            "checkpoint": "",
            "timeoutSec": 1800,
            "startupTimeoutSec": 1800,
            "idleTimeoutSec": 600,
            "modelDevice": "auto",
            "modelPrecision": "auto",
            "codecDevice": "auto",
            "codecPrecision": "fp32",
            "codecRepo": "./runtime/models/irodori/Semantic-DACVAE-Japanese-32dim",
            "textProcessorRepo": "llm-jp/llm-jp-3-150m",
            "textProcessorDir": "./runtime/models/irodori/tokenizers/llm-jp-3-150m",
        },
        "qwen3_tts": {
            "device": "auto",
            "dtype": "auto",
            "attnImplementation": "",
            "hfCacheDir": "",
            "vendorDir": "./runtime/vendor/qwen3-tts",
            "allowDownload": False,
        },
        "external_cli": {
            "requestDir": "./runtime/external-requests",
            "timeoutSec": 1800,
            "dryRun": False,
            "commands": {
                "f5_tts": ["powershell", "-NoProfile", "-File", "./scripts/run-f5-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
                "gpt_sovits_api": ["powershell", "-NoProfile", "-File", "./scripts/run-gpt-sovits-api.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
                "sarashina": ["powershell", "-NoProfile", "-File", "./scripts/run-wsl-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
                "fireredtts2": ["powershell", "-NoProfile", "-File", "./scripts/run-wsl-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
                "t5gemma": ["powershell", "-NoProfile", "-File", "./scripts/run-wsl-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
                "fish_s1_mini": ["powershell", "-NoProfile", "-File", "./scripts/run-wsl-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
                "orpheus_asmr": ["powershell", "-NoProfile", "-File", "./scripts/run-wsl-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
                "ming_omni_tts": ["powershell", "-NoProfile", "-File", "./scripts/run-wsl-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
                "chatterbox": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "./scripts/run-local-expressive-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
                "cosyvoice": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "./scripts/run-local-expressive-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"]
            },
            "availabilityCommands": {
                "sarashina": ["powershell", "-NoProfile", "-File", "./scripts/check-wsl-tts.ps1", "-Model", "sarashina2_2_tts"],
                "fireredtts2": ["powershell", "-NoProfile", "-File", "./scripts/check-wsl-tts.ps1", "-Model", "fireredtts2"],
                "t5gemma": ["powershell", "-NoProfile", "-File", "./scripts/check-wsl-tts.ps1", "-Model", "t5gemma_tts_2b_2b"],
                "fish_s1_mini": ["powershell", "-NoProfile", "-File", "./scripts/check-wsl-tts.ps1", "-Model", "fish_s1_mini"],
                "orpheus_asmr": ["powershell", "-NoProfile", "-File", "./scripts/check-wsl-tts.ps1", "-Model", "orpheus_3b_asmr"],
                "ming_omni_tts": ["powershell", "-NoProfile", "-File", "./scripts/check-wsl-tts.ps1", "-Model", "ming_omni_tts_0_5b"],
                "chatterbox": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "./scripts/check-local-expressive-tts.ps1", "-Model", "chatterbox"],
                "cosyvoice": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "./scripts/check-local-expressive-tts.ps1", "-Model", "cosyvoice"]
            }
        },
    },
}


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as fp:
            payload = json.load(fp)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config parse error: {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ConfigError(f"config must be object: {path}")
    return payload


def _as_path(root_dir: Path, value: Any) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ConfigError("path value is empty")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (root_dir / path).resolve()
    return path


def _parse_chunking_config(raw: Any, defaults: dict[str, Any]) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    merged = {**defaults, **source}
    return {
        "softChunkChars": int(merged.get("softChunkChars", defaults.get("softChunkChars", 120))),
        "maxChunkChars": int(merged.get("maxChunkChars", defaults.get("maxChunkChars", 200))),
        "hardLimitChars": int(merged.get("hardLimitChars", defaults.get("hardLimitChars", 260))),
        "pauseBetweenChunksMs": int(merged.get("pauseBetweenChunksMs", defaults.get("pauseBetweenChunksMs", 250))),
        "keepChunkFiles": bool(merged.get("keepChunkFiles", defaults.get("keepChunkFiles", False))),
    }


def _normalize_legacy(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(raw)

    if "defaultEngine" in normalized and "defaultModel" not in normalized:
        mapped_engine = str(normalized.get("defaultEngine") or "").strip()
        if mapped_engine == "mock_wav":
            normalized["defaultModel"] = "mock"

    if "defaultVoice" in normalized and "defaultModel" not in normalized:
        normalized["defaultModel"] = normalized.get("defaultVoice")

    if "providers" in normalized and "runtimes" not in normalized:
        runtimes = copy.deepcopy(normalized.get("providers") or {})
        if "comfyui_qwen3" in runtimes:
            runtimes["comfyui"] = runtimes.pop("comfyui_qwen3")
        runtimes.pop("windows_sapi", None)
        normalized["runtimes"] = runtimes

    if "voices" in normalized and "models" not in normalized:
        raw_voices = normalized.get("voices")
        models: dict[str, Any] = {}
        if isinstance(raw_voices, dict):
            for voice_name, payload in raw_voices.items():
                if not isinstance(payload, dict):
                    continue
                provider = str(payload.get("provider", "")).strip()
                runtime = "comfyui" if provider == "comfyui_qwen3" else provider
                models[str(voice_name)] = {
                    "runtime": runtime,
                    "workflowPath": payload.get("workflowPath"),
                    "referenceAudioPath": payload.get("referenceAudioPath"),
                    "referenceTextPath": payload.get("referenceTextPath"),
                    "requiresReferenceAudio": bool(payload.get("referenceAudioPath") and payload.get("referenceTextPath")),
                    "supportsCaption": payload.get("supportsCaption"),
                    "defaultCaption": payload.get("defaultCaption"),
                    "voiceDescription": payload.get("voiceDescription"),
                    "workflowTargets": payload.get("workflowTargets"),
                }
        if models:
            normalized["models"] = models

    return normalized


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(raw)

    mapping: dict[str, tuple[str, type]] = {
        "LOCAL_TTS_HOST": ("host", str),
        "LOCAL_TTS_PORT": ("port", int),
        "LOCAL_TTS_PUBLIC_BASE_URL": ("publicBaseUrl", str),
        "LOCAL_TTS_DEFAULT_MODEL": ("defaultModel", str),
        "LOCAL_TTS_DEFAULT_REFERENCE_VOICE": ("defaultReferenceVoice", str),
        "LOCAL_TTS_REFERENCE_VOICES_DIR": ("referenceVoicesDir", str),
        "LOCAL_TTS_AUDIO_OUTPUT_DIR": ("audioOutputDir", str),
        # legacy names
        "LOCAL_TTS_DEFAULT_ENGINE": ("defaultModel", str),
        "LOCAL_TTS_DEFAULT_VOICE": ("defaultModel", str),
    }
    for env_name, (field, caster) in mapping.items():
        value = os.getenv(env_name)
        if value is not None and str(value).strip() != "":
            data[field] = caster(value)

    comfy = data.setdefault("runtimes", {}).setdefault("comfyui", {})
    comfy_map: dict[str, tuple[str, type]] = {
        "LOCAL_TTS_COMFYUI_BASE_URL": ("baseUrl", str),
        "LOCAL_TTS_COMFYUI_INPUT_DIR": ("inputDir", str),
        "LOCAL_TTS_COMFYUI_OUTPUT_DIR": ("outputDir", str),
        "LOCAL_TTS_COMFYUI_TIMEOUT_SEC": ("timeoutSec", int),
        "LOCAL_TTS_COMFYUI_POLL_INTERVAL_SEC": ("pollIntervalSec", float),
        "LOCAL_TTS_COMFYUI_DEFAULT_AUDIO_EXT": ("defaultAudioExt", str),
        "LOCAL_TTS_COMFYUI_AUTO_LAUNCH": ("autoLaunch", lambda value: str(value).strip().lower() in {"1", "true", "yes", "on"}),
        "LOCAL_TTS_COMFYUI_LAUNCH_BAT_PATH": ("launchBatPath", str),
        "LOCAL_TTS_COMFYUI_LAUNCH_WORKING_DIR": ("launchWorkingDir", str),
        "LOCAL_TTS_COMFYUI_STARTUP_TIMEOUT_SEC": ("startupTimeoutSec", int),
        "LOCAL_TTS_COMFYUI_STARTUP_POLL_INTERVAL_SEC": ("startupPollIntervalSec", float),
        "LOCAL_TTS_COMFYUI_HEALTH_PATH": ("healthPath", str),
    }
    for env_name, (field, caster) in comfy_map.items():
        value = os.getenv(env_name)
        if value is not None and str(value).strip() != "":
            comfy[field] = caster(value)

    voxcpm2 = data.setdefault("runtimes", {}).setdefault("comfyui_voxcpm2", {})
    voxcpm2_map: dict[str, tuple[str, type]] = {
        "LOCAL_TTS_VOXCPM2_BASE_URL": ("baseUrl", str),
        "LOCAL_TTS_VOXCPM2_INPUT_DIR": ("inputDir", str),
        "LOCAL_TTS_VOXCPM2_OUTPUT_DIR": ("outputDir", str),
        "LOCAL_TTS_VOXCPM2_TIMEOUT_SEC": ("timeoutSec", int),
        "LOCAL_TTS_VOXCPM2_POLL_INTERVAL_SEC": ("pollIntervalSec", float),
        "LOCAL_TTS_VOXCPM2_DEFAULT_AUDIO_EXT": ("defaultAudioExt", str),
    }
    for env_name, (field, caster) in voxcpm2_map.items():
        value = os.getenv(env_name)
        if value is not None and str(value).strip() != "":
            voxcpm2[field] = caster(value)

    irodori = data.setdefault("runtimes", {}).setdefault("irodori_voicedesign_direct", {})
    irodori_map: dict[str, tuple[str, type]] = {
        "LOCAL_TTS_IRODORI_IDLE_TIMEOUT_SEC": ("idleTimeoutSec", float),
    }
    for env_name, (field, caster) in irodori_map.items():
        value = os.getenv(env_name)
        if value is not None and str(value).strip() != "":
            irodori[field] = caster(value)

    qwen3_tts = data.setdefault("runtimes", {}).setdefault("qwen3_tts", {})
    qwen3_tts_map: dict[str, tuple[str, type]] = {
        "LOCAL_TTS_QWEN3_TTS_DEVICE": ("device", str),
        "LOCAL_TTS_QWEN3_TTS_DTYPE": ("dtype", str),
        "LOCAL_TTS_QWEN3_TTS_ATTN_IMPLEMENTATION": ("attnImplementation", str),
        "LOCAL_TTS_QWEN3_TTS_HF_CACHE_DIR": ("hfCacheDir", str),
        "LOCAL_TTS_QWEN3_TTS_VENDOR_DIR": ("vendorDir", str),
        "LOCAL_TTS_QWEN3_TTS_ALLOW_DOWNLOAD": (
            "allowDownload",
            lambda value: str(value).strip().lower() in {"1", "true", "yes", "on"},
        ),
    }
    for env_name, (field, caster) in qwen3_tts_map.items():
        value = os.getenv(env_name)
        if value is not None and str(value).strip() != "":
            qwen3_tts[field] = caster(value)

    return data


def _parse_workflow_target(raw: Any, field_name: str, model_name: str) -> WorkflowTargetConfig:
    if not isinstance(raw, dict):
        raise ConfigError(f"models.{model_name}.workflowTargets.{field_name} must be object")
    node_id = str(raw.get("nodeId", "")).strip()
    input_key = str(raw.get("inputKey", "")).strip()
    if not node_id:
        raise ConfigError(f"models.{model_name}.workflowTargets.{field_name}.nodeId is required")
    if not input_key:
        raise ConfigError(f"models.{model_name}.workflowTargets.{field_name}.inputKey is required")
    return WorkflowTargetConfig(node_id=node_id, input_key=input_key)


def _parse_workflow_targets(raw: Any, model_name: str) -> WorkflowTargetsConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigError(f"models.{model_name}.workflowTargets must be object")

    return WorkflowTargetsConfig(
        text=_parse_workflow_target(raw["text"], "text", model_name) if "text" in raw else None,
        caption=_parse_workflow_target(raw["caption"], "caption", model_name) if "caption" in raw else None,
        seed=_parse_workflow_target(raw["seed"], "seed", model_name) if "seed" in raw else None,
        save_audio=_parse_workflow_target(raw["saveAudio"], "saveAudio", model_name) if "saveAudio" in raw else None,
        reference_audio=_parse_workflow_target(raw["referenceAudio"], "referenceAudio", model_name) if "referenceAudio" in raw else None,
        reference_text=_parse_workflow_target(raw["referenceText"], "referenceText", model_name) if "referenceText" in raw else None,
    )


def load_config(root_dir: Path | None = None) -> AppConfig:
    resolved_root = (root_dir or Path.cwd()).resolve()
    merged = copy.deepcopy(DEFAULT_CONFIG)

    config_paths = (
        resolved_root / "config" / "config.example.json",
        resolved_root / "config.example.json",
        resolved_root / "config.local.json",
        resolved_root / "config" / "config.local.json",
    )
    explicit_config_env = os.getenv("LOCAL_TTS_CONFIG_PATH")

    for path in config_paths:
        if path.exists():
            merged = _deep_merge(merged, _normalize_legacy(_load_json(path)))

    if explicit_config_env:
        merged = _deep_merge(merged, _normalize_legacy(_load_json(_as_path(resolved_root, explicit_config_env))))

    merged = _apply_env_overrides(merged)

    raw_model_map = merged.get("models")
    if isinstance(raw_model_map, dict):
        raw_model_map.pop("qwen3_tts_design_1_7b", None)
    if str(merged.get("defaultModel", "")).strip() == "qwen3_tts_design_1_7b":
        merged["defaultModel"] = "irodori_v3"

    host = str(merged.get("host", "127.0.0.1")).strip() or "127.0.0.1"
    port = int(merged.get("port", 8730))

    public_base_url = str(merged.get("publicBaseUrl", "")).strip()
    if not public_base_url:
        public_base_url = f"http://{host}:{port}"

    audio_output_dir = _as_path(resolved_root, merged.get("audioOutputDir", "./runtime/audio"))
    audio_output_dir.mkdir(parents=True, exist_ok=True)

    default_chunking = _parse_chunking_config(merged.get("chunking"), DEFAULT_CONFIG["chunking"])

    raw_models = merged.get("models")
    if not isinstance(raw_models, dict) or not raw_models:
        raise ConfigError("models must be non-empty object")

    models: dict[str, ModelConfig] = {}
    for model_name, payload in raw_models.items():
        name = str(model_name or "").strip()
        if not name:
            continue
        if not isinstance(payload, dict):
            raise ConfigError(f"model config must be object: {name}")

        runtime = str(payload.get("runtime", "")).strip()
        if not runtime:
            raise ConfigError(f"models.{name}.runtime is required")

        requires_reference_audio = bool(payload.get("requiresReferenceAudio", False))
        supports_caption = bool(payload.get("supportsCaption", False))
        supports_instruction = bool(payload.get("supportsInstruction", False))
        supports_language = bool(payload.get("supportsLanguage", False))
        supports_seed = bool(payload.get("supportsSeed", False))
        default_speed_control = name == "t5gemma_tts_2b_2b"
        supports_speed_control = bool(payload.get("supportsSpeedControl", default_speed_control))
        supports_style_strength = bool(payload.get("supportsStyleStrength", False))
        supports_voice_clone = bool(payload.get("supportsVoiceClone", False))
        supports_voice_design = bool(payload.get("supportsVoiceDesign", False))
        supports_reference_voice = bool(payload.get("supportsReferenceVoice", requires_reference_audio))
        requires_reference_text = bool(payload.get("requiresReferenceText", False))
        workflow_path = payload.get("workflowPath")
        reference_audio_path = payload.get("referenceAudioPath")
        reference_text_path = payload.get("referenceTextPath")
        if runtime == "comfyui":
            reference_audio_path = None
            reference_text_path = None
        default_caption_raw = payload.get("defaultCaption")
        default_caption: str | None = None
        if default_caption_raw is not None:
            normalized_caption = str(default_caption_raw).strip()
            if normalized_caption:
                default_caption = normalized_caption
        voice_description_raw = payload.get("voiceDescription")
        voice_description: str | None = None
        if voice_description_raw is not None:
            normalized_voice_description = str(voice_description_raw).strip()
            if normalized_voice_description:
                voice_description = normalized_voice_description
        label_raw = payload.get("label")
        label = str(label_raw).strip() if label_raw is not None and str(label_raw).strip() else name
        family_raw = payload.get("family")
        family = str(family_raw).strip() if family_raw is not None and str(family_raw).strip() else runtime
        model_id_raw = payload.get("modelId")
        model_id = str(model_id_raw).strip() if model_id_raw is not None and str(model_id_raw).strip() else None
        default_language_raw = payload.get("defaultLanguage")
        default_language = (
            str(default_language_raw).strip() if default_language_raw is not None and str(default_language_raw).strip() else None
        )
        notes_raw = payload.get("notes")
        notes = str(notes_raw).strip() if notes_raw is not None and str(notes_raw).strip() else None
        external_command_key_raw = payload.get("externalCommandKey")
        external_command_key = str(external_command_key_raw).strip() if external_command_key_raw is not None and str(external_command_key_raw).strip() else None
        checkpoint_raw = payload.get("checkpoint")
        checkpoint_dir_raw = payload.get("checkpointDir")
        requires_trained_checkpoint = bool(payload.get("requiresTrainedCheckpoint", False))
        model_chunking = _parse_chunking_config(payload.get("chunking"), default_chunking) if "chunking" in payload else None
        text_split_method_raw = payload.get("textSplitMethod")
        text_split_method = str(text_split_method_raw).strip() if text_split_method_raw is not None and str(text_split_method_raw).strip() else None
        runtime_options_raw = payload.get("runtimeOptions")
        if runtime_options_raw is None:
            runtime_options = None
        elif not isinstance(runtime_options_raw, dict):
            raise ConfigError(f"models.{name}.runtimeOptions must be object")
        else:
            runtime_options = dict(runtime_options_raw)

        if runtime in {"comfyui", "comfyui_voxcpm2"} and not workflow_path:
            raise ConfigError(f"models.{name}.workflowPath is required for runtime={runtime}")

        models[name] = ModelConfig(
            runtime=runtime,
            workflow_path=_as_path(resolved_root, workflow_path) if workflow_path else None,
            label=label,
            family=family,
            model_id=model_id,
            requires_reference_audio=requires_reference_audio,
            requires_reference_text=requires_reference_text,
            reference_audio_path=_as_path(resolved_root, reference_audio_path) if reference_audio_path else None,
            reference_text_path=_as_path(resolved_root, reference_text_path) if reference_text_path else None,
            supports_caption=supports_caption,
            supports_instruction=supports_instruction,
            supports_language=supports_language,
            supports_seed=supports_seed,
            supports_speed_control=supports_speed_control,
            supports_style_strength=supports_style_strength,
            supports_voice_clone=supports_voice_clone,
            supports_voice_design=supports_voice_design,
            supports_reference_voice=supports_reference_voice,
            default_language=default_language,
            notes=notes,
            default_caption=default_caption,
            voice_description=voice_description,
            external_command_key=external_command_key,
            checkpoint=_as_path(resolved_root, checkpoint_raw) if checkpoint_raw else None,
            checkpoint_dir=_as_path(resolved_root, checkpoint_dir_raw) if checkpoint_dir_raw else None,
            requires_trained_checkpoint=requires_trained_checkpoint,
            chunking=model_chunking,
            text_split_method=text_split_method,
            runtime_options=runtime_options,
            workflow_targets=_parse_workflow_targets(payload.get("workflowTargets"), name),
        )

    default_model = str(merged.get("defaultModel", "")).strip() or next(iter(models.keys()))
    if default_model not in models:
        raise ConfigError(f"defaultModel is not defined in models: {default_model}")

    runtimes = merged.get("runtimes")
    if not isinstance(runtimes, dict):
        raise ConfigError("runtimes must be object")

    raw_stack = merged.get("stack")
    if not isinstance(raw_stack, dict):
        raw_stack = {}
    raw_ports = raw_stack.get("portsToKill", [])
    ports_to_kill: list[int] = []
    if isinstance(raw_ports, list):
        for value in raw_ports:
            try:
                kill_port = int(value)
            except (TypeError, ValueError):
                continue
            if 1 <= kill_port <= 65535:
                ports_to_kill.append(kill_port)
    stack = {
        "killPortsBeforeStart": bool(raw_stack.get("killPortsBeforeStart", True)),
        "portsToKill": ports_to_kill,
        "startupTimeoutSec": int(raw_stack.get("startupTimeoutSec", 180)),
        "pollIntervalSec": float(raw_stack.get("pollIntervalSec", 1.0)),
    }

    external_services = merged.get("externalServices")
    if not isinstance(external_services, dict):
        external_services = {}

    frontend = merged.get("frontend")
    if not isinstance(frontend, dict):
        frontend = {}

    reference_voices_dir = _as_path(resolved_root, merged.get("referenceVoicesDir", "./reference/voices"))
    default_reference_voice_raw = str(merged.get("defaultReferenceVoice", "")).strip()
    default_reference_voice = default_reference_voice_raw or None

    chunking_config = default_chunking

    cors_allowed_origins = merged.get("corsAllowedOrigins")
    if not isinstance(cors_allowed_origins, list):
        cors_allowed_origins = ["http://127.0.0.1", "http://localhost"]

    return AppConfig(
        root_dir=resolved_root,
        host=host,
        port=port,
        public_base_url=public_base_url.rstrip("/"),
        default_model=default_model,
        audio_output_dir=audio_output_dir,
        cors_allowed_origins=[str(origin) for origin in cors_allowed_origins],
        models=models,
        runtimes=runtimes,
        stack=stack,
        external_services=external_services,
        frontend=frontend,
        reference_voices_dir=reference_voices_dir,
        default_reference_voice=default_reference_voice,
        chunking=chunking_config,
    )
