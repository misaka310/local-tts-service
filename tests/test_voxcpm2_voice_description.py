from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from local_tts_service.errors import ProviderError
from local_tts_service.models import ModelConfig, SpeakRequest
from local_tts_service.runtimes.base import SynthesizeRequest
from local_tts_service.runtimes.comfyui_voxcpm2 import ComfyUIVoxCPM2Runtime
from local_tts_service.server import create_app


def _build_runtime(tmp_path, models: dict[str, ModelConfig]) -> ComfyUIVoxCPM2Runtime:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    runtime_dir = tmp_path / "runtime"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return ComfyUIVoxCPM2Runtime(
        output_dir=runtime_dir,
        models=models,
        base_url="http://127.0.0.1:8288",
        input_dir=input_dir,
        comfy_output_dir=output_dir,
    )


def test_comfyui_voxcpm2_voice_description_priority(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "voxcpm2_tts_ui.json"
    comfy_output_audio = tmp_path / "output" / "generated.wav"
    workflow = {
        "nodes": [
            {
                "id": 11,
                "type": "VoxCPM2_TTS",
                "inputs": [
                    {"name": "text", "type": "STRING", "widget": {"name": "text"}},
                    {"name": "voice_description", "type": "STRING", "widget": {"name": "voice_description"}},
                ],
                "widgets_values": ["old text", "old desc"],
            },
            {
                "id": 22,
                "type": "SaveAudio",
                "inputs": [{"name": "filename_prefix", "type": "STRING", "widget": {"name": "filename_prefix"}}],
                "widgets_values": ["before"],
            },
        ],
        "links": [],
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    comfy_output_audio.parent.mkdir(parents=True, exist_ok=True)
    comfy_output_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")

    # 1. Custom voice_description specified in request (highest priority)
    models = {
        "voxcpm2_tts": ModelConfig(
            runtime="comfyui_voxcpm2",
            workflow_path=workflow_path,
            requires_reference_audio=False,
            voice_description="config level voice desc",
        )
    }
    runtime = _build_runtime(tmp_path, models)
    captured_prompt: dict[str, Any] = {}

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            assert payload is not None
            captured_prompt.clear()
            captured_prompt.update(payload["prompt"])
            return {"prompt_id": "vox-test-desc-1"}
        if method == "GET" and "/history/" in url:
            return {
                "vox-test-desc-1": {
                    "status": {"status_str": "success"},
                    "outputs": {"save": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}},
                }
            }
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_http_json", fake_http_json)

    # Call with request voice_description
    runtime.synthesize(
        SynthesizeRequest(
            text="Hello world",
            request_id="req-desc-1",
            model_name="voxcpm2_tts",
            output_basename="tts-desc-1",
            voice_description="request level custom voice desc",
            caption="caption level voice desc",
        )
    )
    assert captured_prompt["11"]["inputs"]["voice_description"] == "request level custom voice desc"

    # 2. Call with only request caption (fallback priority 2)
    runtime.synthesize(
        SynthesizeRequest(
            text="Hello world",
            request_id="req-desc-2",
            model_name="voxcpm2_tts",
            output_basename="tts-desc-2",
            voice_description=None,
            caption="caption level voice desc",
        )
    )
    assert captured_prompt["11"]["inputs"]["voice_description"] == "caption level voice desc"

    # 3. Call with no request parameters (fallback priority 3: model config)
    runtime.synthesize(
        SynthesizeRequest(
            text="Hello world",
            request_id="req-desc-3",
            model_name="voxcpm2_tts",
            output_basename="tts-desc-3",
            voice_description=None,
            caption=None,
        )
    )
    assert captured_prompt["11"]["inputs"]["voice_description"] == "config level voice desc"


def test_speak_request_validation() -> None:
    # Validate Pydantic schema correctly maps new optional voiceDescription property
    req = SpeakRequest(
        text="Validation test",
        model="voxcpm2_tts",
        voiceDescription="A cheerful voice",
    )
    assert req.voiceDescription == "A cheerful voice"

    # Empty voiceDescription gets resolved to None
    req_empty = SpeakRequest(
        text="Validation test",
        model="voxcpm2_tts",
        voiceDescription="   ",
    )
    assert req_empty.voiceDescription is None

    # Too long voiceDescription (>4000) raises validation error
    with pytest.raises(ValueError, match="voiceDescription is too long"):
        SpeakRequest(
            text="Validation test",
            model="voxcpm2_tts",
            voiceDescription="a" * 4001,
        )
