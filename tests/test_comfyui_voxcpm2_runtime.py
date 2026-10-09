from __future__ import annotations

import json

import pytest

from local_tts_service.errors import ProviderError
from local_tts_service.models import ModelConfig
from local_tts_service.runtimes.base import SynthesizeRequest
from local_tts_service.runtimes.comfyui_voxcpm2 import ComfyUIVoxCPM2Runtime


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


def test_ui_workflow_tts_text_is_patched(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "voxcpm2_tts_ui.json"
    comfy_output_audio = tmp_path / "output" / "generated.wav"
    workflow = {
        "nodes": [
            {
                "id": 11,
                "type": "VoxCPM2_TTS",
                "inputs": [{"name": "text", "type": "STRING", "widget": {"name": "text"}}],
                "widgets_values": ["old text"],
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

    models = {
        "voxcpm2_tts": ModelConfig(
            runtime="comfyui_voxcpm2",
            workflow_path=workflow_path,
            requires_reference_audio=False,
            voice_description="calm voice",
        )
    }
    runtime = _build_runtime(tmp_path, models)
    captured_prompt: dict[str, object] = {}

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            assert payload is not None
            captured_prompt.update(payload["prompt"])  # type: ignore[index]
            return {"prompt_id": "vox-tts-1"}
        if method == "GET" and "/history/" in url:
            return {
                "vox-tts-1": {
                    "status": {"status_str": "success"},
                    "outputs": {"save": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}},
                }
            }
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_http_json", fake_http_json)
    result = runtime.synthesize(
        SynthesizeRequest(
            text="こんにちは、VoxCPM2です。",
            request_id="req-tts",
            model_name="voxcpm2_tts",
            output_basename="tts-vox-tts",
        )
    )

    assert captured_prompt["11"]["inputs"]["text"] == "こんにちは、VoxCPM2です。"  # type: ignore[index]
    assert captured_prompt["11"]["inputs"]["voice_description"] == "calm voice"  # type: ignore[index]
    assert captured_prompt["22"]["inputs"]["filename_prefix"] == "tts-vox-tts"  # type: ignore[index]
    assert result.audio_path.exists()


def test_ui_workflow_clone_text_prompt_and_reference_audio_are_patched(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "voxcpm2_clone_ui.json"
    reference_audio_path = tmp_path / "ref.wav"
    reference_text_path = tmp_path / "ref.txt"
    comfy_output_audio = tmp_path / "output" / "generated.wav"
    workflow = {
        "nodes": [
            {
                "id": 1,
                "type": "LoadAudio",
                "inputs": [],
                "widgets_values": [],
            },
            {
                "id": 2,
                "type": "VoxCPM2_Clone",
                "inputs": [
                    {"name": "text", "type": "STRING", "widget": {"name": "text"}},
                    {"name": "prompt_text", "type": "STRING", "widget": {"name": "prompt_text"}},
                ],
                "widgets_values": ["old text", "old prompt"],
            },
            {
                "id": 3,
                "type": "SaveAudio",
                "inputs": [{"name": "filename_prefix", "type": "STRING", "widget": {"name": "filename_prefix"}}],
                "widgets_values": ["old-file"],
            },
        ],
        "links": [],
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    reference_audio_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    reference_text_path.write_text("これは参照テキストです", encoding="utf-8")
    comfy_output_audio.parent.mkdir(parents=True, exist_ok=True)
    comfy_output_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")

    models = {
        "voxcpm2_clone": ModelConfig(
            runtime="comfyui_voxcpm2",
            workflow_path=workflow_path,
            requires_reference_audio=True,
            reference_audio_path=reference_audio_path,
            reference_text_path=reference_text_path,
            voice_description="slightly cheerful",
        )
    }
    runtime = _build_runtime(tmp_path, models)
    captured_prompt: dict[str, object] = {}

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            assert payload is not None
            captured_prompt.update(payload["prompt"])  # type: ignore[index]
            return {"prompt_id": "vox-clone-1"}
        if method == "GET" and "/history/" in url:
            return {
                "vox-clone-1": {
                    "status": {"status_str": "success"},
                    "outputs": {"save": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}},
                }
            }
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_http_json", fake_http_json)
    runtime.synthesize(
        SynthesizeRequest(
            text="クローン読み上げ本文",
            request_id="req-clone",
            model_name="voxcpm2_clone",
            output_basename="tts-vox-clone",
        )
    )

    assert captured_prompt["1"]["inputs"]["audio"].startswith("tts-ref-")  # type: ignore[index]
    assert captured_prompt["2"]["inputs"]["text"] == "クローン読み上げ本文"  # type: ignore[index]
    assert captured_prompt["2"]["inputs"]["prompt_text"] == "これは参照テキストです"  # type: ignore[index]
    assert captured_prompt["2"]["inputs"]["reference_audio"] == ["1", 0]  # type: ignore[index]
    assert captured_prompt["2"]["inputs"]["voice_description"] == "slightly cheerful"  # type: ignore[index]


def test_save_audio_compatible_node_is_required(tmp_path) -> None:
    workflow_path = tmp_path / "voxcpm2_preview_only.json"
    workflow = {
        "11": {"class_type": "VoxCPM2_TTS", "inputs": {"text": ""}},
        "12": {"class_type": "PreviewAudio", "inputs": {}},
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

    models = {
        "voxcpm2_tts": ModelConfig(
            runtime="comfyui_voxcpm2",
            workflow_path=workflow_path,
            requires_reference_audio=False,
        )
    }
    runtime = _build_runtime(tmp_path, models)

    with pytest.raises(ProviderError) as exc:
        runtime.synthesize(
            SynthesizeRequest(
                text="preview only",
                request_id="req-preview",
                model_name="voxcpm2_tts",
                output_basename="tts-preview",
            )
        )
    assert "SaveAudio-compatible node" in str(exc.value)


def test_ui_workflow_links_are_preserved_for_clone_reference_audio(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "voxcpm2_clone_links_ui.json"
    reference_audio_path = tmp_path / "ref.wav"
    reference_text_path = tmp_path / "ref.txt"
    comfy_output_audio = tmp_path / "output" / "generated.wav"
    workflow = {
        "nodes": [
            {
                "id": 1,
                "type": "LoadAudio",
                "inputs": [],
                "widgets_values": [],
            },
            {
                "id": 2,
                "type": "VoxCPM2_Clone",
                "inputs": [
                    {"name": "reference_audio", "type": "AUDIO", "link": 7001},
                    {"name": "text", "type": "STRING", "widget": {"name": "text"}},
                    {"name": "prompt_text", "type": "STRING", "widget": {"name": "prompt_text"}},
                ],
                "widgets_values": ["old text", "old prompt"],
            },
            {
                "id": 3,
                "type": "VHS_SaveAudio",
                "inputs": [{"name": "filename_prefix", "type": "STRING", "widget": {"name": "filename_prefix"}}],
                "widgets_values": ["old-file"],
            },
        ],
        "links": [[7001, 1, 0, 2, 0, "AUDIO"]],
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    reference_audio_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    reference_text_path.write_text("ref text", encoding="utf-8")
    comfy_output_audio.parent.mkdir(parents=True, exist_ok=True)
    comfy_output_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")

    models = {
        "voxcpm2_clone": ModelConfig(
            runtime="comfyui_voxcpm2",
            workflow_path=workflow_path,
            requires_reference_audio=True,
            reference_audio_path=reference_audio_path,
            reference_text_path=reference_text_path,
        )
    }
    runtime = _build_runtime(tmp_path, models)
    captured_prompt: dict[str, object] = {}

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            assert payload is not None
            captured_prompt.update(payload["prompt"])  # type: ignore[index]
            return {"prompt_id": "vox-link-1"}
        if method == "GET" and "/history/" in url:
            return {
                "vox-link-1": {
                    "status": {"status_str": "success"},
                    "outputs": {"save": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}},
                }
            }
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_http_json", fake_http_json)
    runtime.synthesize(
        SynthesizeRequest(
            text="本文",
            request_id="req-link",
            model_name="voxcpm2_clone",
            output_basename="tts-vox-link",
        )
    )

    assert captured_prompt["1"]["inputs"]["audio"].startswith("tts-ref-")  # type: ignore[index]
    assert captured_prompt["2"]["inputs"]["reference_audio"] == ["1", 0]  # type: ignore[index]
