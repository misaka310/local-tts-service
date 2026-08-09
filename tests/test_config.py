from __future__ import annotations

import json

import pytest

from local_tts_service.config import DEFAULT_CONFIG, load_config
from local_tts_service.errors import ConfigError


def test_default_irodori_capabilities_match_official_models() -> None:
    models = DEFAULT_CONFIG["models"]
    v2 = models["irodori_v2"]
    v3 = models["irodori_v3"]
    low_latency = models["irodori_v3_low_latency"]
    voice_design = models["irodori_v3_voicedesign"]
    v4 = models["irodori_v4_small"]

    assert v2["supportsReferenceVoice"] is True
    assert v2["requiresReferenceAudio"] is False
    assert v2["supportsInstruction"] is False
    assert v2["supportsSpeedControl"] is False

    assert v3["supportsReferenceVoice"] is True
    assert v3["requiresReferenceAudio"] is False
    assert v3["supportsInstruction"] is False
    assert v3["supportsSpeedControl"] is True

    assert low_latency["modelId"] == v3["modelId"]
    assert low_latency["runtimeOptions"] == {
        "optimizationProfile": "low_latency_8",
        "codecPrecision": "bf16",
    }

    assert voice_design["supportsReferenceVoice"] is True
    assert voice_design["requiresReferenceAudio"] is False
    assert voice_design["supportsInstruction"] is True
    assert voice_design["supportsCaption"] is True
    assert voice_design["supportsSpeedControl"] is True
    assert voice_design["supportsStyleStrength"] is True

    assert v4["modelId"] == "Aratako/Irodori-TTS-v4-Small"
    assert v4["supportsReferenceVoice"] is True
    assert v4["requiresReferenceAudio"] is False
    assert v4["supportsInstruction"] is True
    assert v4["supportsCaption"] is True
    assert v4["supportsSpeedControl"] is True
    assert v4["supportsStyleStrength"] is True
    assert v4["supportsVoiceDesign"] is True


def test_load_config_reads_default_and_local(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "port": 8730,
                "defaultModel": "mock",
                "models": {
                    "mock": {"runtime": "mock_wav", "requiresReferenceAudio": False},
                    "irodori_v2": {
                        "runtime": "comfyui",
                        "workflowPath": "./reference/workflows/irodori_v2_api.json",
                        "requiresReferenceAudio": False,
                    },
                },
                "runtimes": {
                    "mock_wav": {"durationSec": 1.0, "sampleRate": 16000},
                    "comfyui": {"baseUrl": "http://127.0.0.1:8188", "inputDir": "./in", "outputDir": "./out"},
                },
                "stack": {
                    "killPortsBeforeStart": True,
                    "portsToKill": [8730, 8288, 5177],
                    "startupTimeoutSec": 200,
                    "pollIntervalSec": 1.5,
                },
                "externalServices": {
                    "comfyui": {
                        "enabled": True,
                        "name": "ComfyUI",
                        "rootDir": "D:/ComfyUI",
                        "startCommand": "python main.py --port 8288",
                        "healthUrl": "http://127.0.0.1:8288/system_stats",
                    }
                },
                "frontend": {
                    "host": "127.0.0.1",
                    "port": 5177,
                    "ttsBaseUrl": "http://127.0.0.1:8730",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config.local.json").write_text(
        json.dumps({"port": 8740, "defaultModel": "mock"}),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.port == 8740
    assert cfg.default_model == "mock"
    assert cfg.stack["killPortsBeforeStart"] is True
    assert 8730 in cfg.stack["portsToKill"]
    assert cfg.stack["startupTimeoutSec"] == 200
    assert cfg.external_services["comfyui"]["name"] == "ComfyUI"
    assert cfg.frontend["port"] == 5177


def test_load_config_reads_relocated_config_directory_and_keeps_legacy_compatibility(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.example.json").write_text(
        json.dumps(
            {
                "port": 8730,
                "defaultModel": "mock",
                "models": {"mock": {"runtime": "mock_wav", "requiresReferenceAudio": False}},
                "runtimes": {"mock_wav": {"durationSec": 1.0, "sampleRate": 16000}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config.local.json").write_text(json.dumps({"port": 8740}), encoding="utf-8")
    (config_dir / "config.local.json").write_text(json.dumps({"port": 8750}), encoding="utf-8")

    cfg = load_config(tmp_path)

    assert cfg.port == 8750
    assert cfg.default_model == "mock"


def test_load_config_env_override(tmp_path, monkeypatch) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "mock",
                "models": {"mock": {"runtime": "mock_wav", "requiresReferenceAudio": False}},
                "runtimes": {"mock_wav": {"durationSec": 1.0, "sampleRate": 16000}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("LOCAL_TTS_PORT", "8750")
    cfg = load_config(tmp_path)
    assert cfg.port == 8750


def test_load_config_retires_qwen_voice_design_from_existing_local_config(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "irodori_v3",
                "models": {
                    "irodori_v3": {
                        "runtime": "irodori_voicedesign_direct",
                        "requiresReferenceAudio": False,
                    },
                    "qwen3_tts_clone_1_7b": {
                        "runtime": "qwen3_tts",
                        "modelId": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                        "requiresReferenceAudio": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config.local.json").write_text(
        json.dumps(
            {
                "defaultModel": "qwen3_tts_design_1_7b",
                "models": {
                    "qwen3_tts_design_1_7b": {
                        "runtime": "qwen3_tts",
                        "modelId": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                        "supportsVoiceDesign": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)

    assert cfg.default_model == "irodori_v3"
    assert "qwen3_tts_design_1_7b" not in cfg.models
    assert "qwen3_tts_clone_1_7b" in cfg.models


def test_load_config_voxcpm2_env_override(tmp_path, monkeypatch) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "voxcpm2_tts",
                "models": {
                    "voxcpm2_tts": {
                        "runtime": "comfyui_voxcpm2",
                        "workflowPath": "./reference/workflows/voxcpm2_tts_api.json",
                        "requiresReferenceAudio": False,
                    }
                },
                "runtimes": {
                    "comfyui_voxcpm2": {"baseUrl": "http://127.0.0.1:8288", "inputDir": "./in", "outputDir": "./out"}
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("LOCAL_TTS_VOXCPM2_BASE_URL", "http://127.0.0.1:9388")
    monkeypatch.setenv("LOCAL_TTS_VOXCPM2_TIMEOUT_SEC", "123")
    cfg = load_config(tmp_path)
    assert cfg.runtimes["comfyui_voxcpm2"]["baseUrl"] == "http://127.0.0.1:9388"
    assert cfg.runtimes["comfyui_voxcpm2"]["timeoutSec"] == 123


def test_load_config_irodori_idle_timeout_env_override(tmp_path, monkeypatch) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "irodori_v3",
                "models": {
                    "irodori_v3": {
                        "runtime": "irodori_voicedesign_direct",
                        "requiresReferenceAudio": False,
                    }
                },
                "runtimes": {
                    "irodori_voicedesign_direct": {"idleTimeoutSec": 600}
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("LOCAL_TTS_IRODORI_IDLE_TIMEOUT_SEC", "0")
    cfg = load_config(tmp_path)

    assert cfg.runtimes["irodori_voicedesign_direct"]["idleTimeoutSec"] == 0.0


def test_load_config_comfyui_auto_launch_settings(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "irodori_v3",
                "models": {
                    "irodori_v3": {
                        "runtime": "comfyui",
                        "workflowPath": "./reference/workflows/irodori_v3_api.json",
                        "requiresReferenceAudio": True,
                    }
                },
                "runtimes": {
                    "comfyui": {
                        "baseUrl": "http://127.0.0.1:8288",
                        "inputDir": "./in",
                        "outputDir": "./out",
                        "autoLaunch": True,
                        "launchBatPath": "./scripts/start-comfyui.bat",
                        "launchWorkingDir": "./runtime",
                        "startupTimeoutSec": 90,
                        "startupPollIntervalSec": 0.5,
                        "healthPath": "/system_stats",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    comfy = cfg.runtimes["comfyui"]
    assert comfy["autoLaunch"] is True
    assert comfy["launchBatPath"] == "./scripts/start-comfyui.bat"
    assert comfy["launchWorkingDir"] == "./runtime"
    assert comfy["startupTimeoutSec"] == 90
    assert comfy["startupPollIntervalSec"] == 0.5
    assert comfy["healthPath"] == "/system_stats"


def test_load_config_reference_voice_settings(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "irodori_v3",
                "defaultReferenceVoice": "default",
                "referenceVoicesDir": "./reference/voices",
                "models": {
                    "irodori_v3": {
                        "runtime": "comfyui",
                        "workflowPath": "./reference/workflows/irodori_v3_api.json",
                        "requiresReferenceAudio": True,
                    }
                },
                "runtimes": {
                    "comfyui": {"baseUrl": "http://127.0.0.1:8288", "inputDir": "./in", "outputDir": "./out"}
                },
                "chunking": {
                    "softChunkChars": 120,
                    "maxChunkChars": 200,
                    "hardLimitChars": 260,
                    "pauseBetweenChunksMs": 250,
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.default_reference_voice == "default"
    assert cfg.reference_voices_dir.name == "voices"
    assert cfg.chunking["maxChunkChars"] == 200
    assert cfg.models["irodori_v3"].chunking is not None
    assert cfg.models["irodori_v3"].chunking["maxChunkChars"] == 220


def test_load_config_workflow_targets(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "irodori_v2",
                "models": {
                    "irodori_v2": {
                        "runtime": "comfyui",
                        "workflowPath": "./reference/workflow.json",
                        "requiresReferenceAudio": False,
                        "supportsCaption": True,
                        "defaultCaption": "落ち着いた女性の声",
                        "voiceDescription": "calm and clear",
                        "workflowTargets": {
                            "text": {"nodeId": "10", "inputKey": "text"},
                            "caption": {"nodeId": "10", "inputKey": "text"},
                            "saveAudio": {"nodeId": "20", "inputKey": "filename_prefix"},
                            "seed": {"nodeId": "10", "inputKey": "seed"},
                        },
                    }
                },
                "runtimes": {
                    "comfyui": {"baseUrl": "http://127.0.0.1:8188", "inputDir": "./in", "outputDir": "./out"}
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    targets = cfg.models["irodori_v2"].workflow_targets
    assert targets is not None
    assert targets.text is not None
    assert targets.text.node_id == "10"
    assert targets.text.input_key == "text"
    assert targets.caption is not None
    assert targets.caption.input_key == "text"
    assert targets.save_audio is not None
    assert targets.save_audio.node_id == "20"
    assert targets.seed is not None
    assert targets.seed.input_key == "seed"
    assert cfg.models["irodori_v2"].supports_caption is True
    assert cfg.models["irodori_v2"].default_caption == "落ち着いた女性の声"
    assert cfg.models["irodori_v2"].voice_description == "calm and clear"


def test_irodori_v2_without_reference_audio_is_allowed(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "irodori_v2",
                "models": {
                    "irodori_v2": {
                        "runtime": "comfyui",
                        "workflowPath": "./reference/workflow.json",
                        "requiresReferenceAudio": False,
                    }
                },
                "runtimes": {
                    "comfyui": {"baseUrl": "http://127.0.0.1:8188", "inputDir": "./in", "outputDir": "./out"}
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    model = cfg.models["irodori_v2"]
    assert model.requires_reference_audio is False
    assert model.reference_audio_path is None
    assert model.reference_text_path is None


def test_irodori_v3_does_not_require_fixed_reference_paths(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "irodori_v3",
                "models": {
                    "irodori_v3": {
                        "runtime": "comfyui",
                        "workflowPath": "./reference/workflow.json",
                        "requiresReferenceAudio": True,
                        "referenceAudioPath": "",
                        "referenceTextPath": "",
                    }
                },
                "runtimes": {
                    "comfyui": {"baseUrl": "http://127.0.0.1:8188", "inputDir": "./in", "outputDir": "./out"}
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    model = cfg.models["irodori_v3"]
    assert model.requires_reference_audio is True
    assert model.reference_audio_path is None
    assert model.reference_text_path is None


def test_legacy_voice_provider_config_is_mapped_to_models(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultVoice": "irodori",
                "voices": {
                    "irodori": {
                        "provider": "comfyui_qwen3",
                        "workflowPath": "./reference/workflow.json",
                    }
                },
                "providers": {
                    "comfyui_qwen3": {"baseUrl": "http://127.0.0.1:8188", "inputDir": "./in", "outputDir": "./out"}
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert "irodori" in cfg.models
    assert cfg.models["irodori"].runtime == "comfyui"


def test_legacy_voice_provider_voxcpm2_is_mapped_to_models(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultVoice": "voxcpm2_clone",
                "voices": {
                    "voxcpm2_clone": {
                        "provider": "comfyui_voxcpm2",
                        "workflowPath": "./reference/workflows/voxcpm2_clone_api.json",
                        "referenceAudioPath": "./reference/voxcpm2/sample.wav",
                        "referenceTextPath": "./reference/voxcpm2/sample.txt",
                        "voiceDescription": "slightly cheerful",
                    }
                },
                "providers": {
                    "comfyui_voxcpm2": {
                        "baseUrl": "http://127.0.0.1:8288",
                        "inputDir": "./in",
                        "outputDir": "./out",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert "voxcpm2_clone" in cfg.models
    assert cfg.models["voxcpm2_clone"].runtime == "comfyui_voxcpm2"
    assert cfg.models["voxcpm2_clone"].voice_description == "slightly cheerful"


def test_windows_sapi_not_present_in_default_runtimes(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "mock",
                "models": {"mock": {"runtime": "mock_wav", "requiresReferenceAudio": False}},
                "runtimes": {"mock_wav": {"durationSec": 1.0, "sampleRate": 16000}},
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert "windows_sapi" not in cfg.runtimes


def test_stack_ports_are_sanitized_to_valid_integers(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "mock",
                "models": {"mock": {"runtime": "mock_wav", "requiresReferenceAudio": False}},
                "runtimes": {"mock_wav": {"durationSec": 1.0, "sampleRate": 16000}},
                "stack": {
                    "portsToKill": [8730, "8288", "bad", -1, 70000],
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.stack["portsToKill"] == [8730, 8288]


def test_load_config_preserves_model_runtime_options(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "irodori_v3_low_latency",
                "models": {
                    "irodori_v3_low_latency": {
                        "runtime": "irodori_voicedesign_direct",
                        "runtimeOptions": {
                            "optimizationProfile": "low_latency_8",
                            "codecPrecision": "bf16",
                        },
                    }
                },
                "runtimes": {"irodori_voicedesign_direct": {"pythonExecutable": "python.exe"}},
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)

    assert cfg.models["irodori_v3_low_latency"].runtime_options == {
        "optimizationProfile": "low_latency_8",
        "codecPrecision": "bf16",
    }


def test_load_config_rejects_non_object_model_runtime_options(tmp_path) -> None:
    (tmp_path / "config.example.json").write_text(
        json.dumps(
            {
                "defaultModel": "bad",
                "models": {
                    "bad": {
                        "runtime": "mock_wav",
                        "runtimeOptions": "low_latency_8",
                    }
                },
                "runtimes": {"mock_wav": {}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="models.bad.runtimeOptions must be object"):
        load_config(tmp_path)
