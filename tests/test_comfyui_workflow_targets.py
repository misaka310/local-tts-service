from __future__ import annotations

import json

import pytest

from local_tts_service.errors import ProviderError
from local_tts_service.models import ModelConfig, WorkflowTargetConfig, WorkflowTargetsConfig
from local_tts_service.runtimes.base import SynthesizeRequest
from local_tts_service.runtimes.comfyui import ComfyUIRuntime


def _build_runtime(tmp_path, models: dict[str, ModelConfig]) -> ComfyUIRuntime:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    runtime_dir = tmp_path / "runtime"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime = ComfyUIRuntime(
        output_dir=runtime_dir,
        models=models,
        base_url="http://127.0.0.1:8188",
        input_dir=input_dir,
        comfy_output_dir=output_dir,
        auto_launch=False,
    )
    runtime._is_server_healthy = lambda: True  # type: ignore[method-assign]
    return runtime


def test_workflow_targets_invalid_node_raises(tmp_path) -> None:
    runtime = _build_runtime(tmp_path, {})
    prompt = {"1": {"class_type": "Text", "inputs": {"text": ""}}}
    with pytest.raises(ProviderError) as exc:
        runtime._resolve_target(  # noqa: SLF001
            prompt=prompt,
            target_name="text",
            explicit_target=WorkflowTargetConfig(node_id="999", input_key="text"),
            class_hints=("Text",),
            keys=("text",),
            required=True,
            missing_message="text patch target was not found in workflow",
        )
    assert "workflowTargets.text is invalid" in str(exc.value)
    assert "nodeId '999'" in str(exc.value)


def test_workflow_targets_invalid_input_key_raises(tmp_path) -> None:
    runtime = _build_runtime(tmp_path, {})
    prompt = {"10": {"class_type": "Text", "inputs": {"text": ""}}}
    with pytest.raises(ProviderError) as exc:
        runtime._resolve_target(  # noqa: SLF001
            prompt=prompt,
            target_name="text",
            explicit_target=WorkflowTargetConfig(node_id="10", input_key="prompt"),
            class_hints=("Text",),
            keys=("text",),
            required=True,
            missing_message="text patch target was not found in workflow",
        )
    assert "workflowTargets.text is invalid" in str(exc.value)
    assert "inputKey 'prompt'" in str(exc.value)


def test_workflow_targets_apply_to_expected_node(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "workflow.json"
    reference_audio_path = tmp_path / "ref.wav"
    comfy_output_audio = tmp_path / "output" / "generated.wav"

    workflow = {
        "10": {"class_type": "Qwen3VoiceClone", "inputs": {"text": "", "audio": ""}},
        "25": {"class_type": "SaveAudio", "inputs": {"filename_prefix": "old"}},
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    reference_audio_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    comfy_output_audio.parent.mkdir(parents=True, exist_ok=True)
    comfy_output_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")

    models = {
        "irodori_v3": ModelConfig(
            runtime="comfyui",
            workflow_path=workflow_path,
            requires_reference_audio=True,
            workflow_targets=WorkflowTargetsConfig(
                text=WorkflowTargetConfig(node_id="10", input_key="text"),
                save_audio=WorkflowTargetConfig(node_id="25", input_key="filename_prefix"),
                reference_audio=WorkflowTargetConfig(node_id="10", input_key="audio"),
            ),
        )
    }
    runtime = _build_runtime(tmp_path, models)

    captured_prompt: dict[str, object] = {}

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            assert payload is not None
            captured_prompt.update(payload["prompt"])  # type: ignore[index]
            return {"prompt_id": "p-1"}
        if method == "GET" and "/history/" in url:
            return {"p-1": {"status": {"status_str": "success"}, "outputs": {"node": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}}}}
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_http_json", fake_http_json)

    result = runtime.synthesize(
        SynthesizeRequest(
            text="test input",
            request_id="req-1",
            model_name="irodori_v3",
            output_basename="tts-req-1-abc",
            reference_audio_path=reference_audio_path,
        )
    )

    node10 = captured_prompt["10"]  # type: ignore[index]
    node25 = captured_prompt["25"]  # type: ignore[index]
    assert node10["inputs"]["text"] == "test input"  # type: ignore[index]
    assert node10["inputs"]["audio"]  # type: ignore[index]
    assert node25["inputs"]["filename_prefix"] == "tts-req-1-abc"  # type: ignore[index]
    assert result.audio_path.exists()


def test_requires_reference_audio_missing_path_raises(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.json"
    workflow = {
        "10": {"class_type": "Text", "inputs": {"text": ""}},
        "25": {"class_type": "SaveAudio", "inputs": {"filename_prefix": "old"}},
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

    models = {
        "irodori_v3": ModelConfig(
            runtime="comfyui",
            workflow_path=workflow_path,
            requires_reference_audio=True,
            reference_audio_path=None,
            reference_text_path=None,
            workflow_targets=WorkflowTargetsConfig(
                text=WorkflowTargetConfig(node_id="10", input_key="text"),
                save_audio=WorkflowTargetConfig(node_id="25", input_key="filename_prefix"),
            ),
        )
    }
    runtime = _build_runtime(tmp_path, models)
    with pytest.raises(ProviderError) as exc:
        runtime.synthesize(
            SynthesizeRequest(
                text="test",
                request_id="req",
                model_name="irodori_v3",
                output_basename="tts-req",
            )
        )
    assert "referenceAudioPath is required" in str(exc.value)


def test_caption_is_merged_into_text_when_same_target(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "workflow.json"
    comfy_output_audio = tmp_path / "output" / "generated.wav"
    workflow = {
        "3": {"class_type": "IrodoriTTSSampler", "inputs": {"text": ""}},
        "4": {"class_type": "SaveAudio", "inputs": {"filename_prefix": "old"}},
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    comfy_output_audio.parent.mkdir(parents=True, exist_ok=True)
    comfy_output_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")

    models = {
        "irodori_v2": ModelConfig(
            runtime="comfyui",
            workflow_path=workflow_path,
            requires_reference_audio=False,
            supports_caption=True,
            default_caption="落ち着いた女性の声",
            workflow_targets=WorkflowTargetsConfig(
                text=WorkflowTargetConfig(node_id="3", input_key="text"),
                caption=WorkflowTargetConfig(node_id="3", input_key="text"),
                save_audio=WorkflowTargetConfig(node_id="4", input_key="filename_prefix"),
            ),
        )
    }
    runtime = _build_runtime(tmp_path, models)
    captured_prompt: dict[str, object] = {}

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            assert payload is not None
            captured_prompt.update(payload["prompt"])  # type: ignore[index]
            return {"prompt_id": "p-2"}
        if method == "GET" and "/history/" in url:
            return {"p-2": {"status": {"status_str": "success"}, "outputs": {"node": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}}}}
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_http_json", fake_http_json)
    runtime.synthesize(
        SynthesizeRequest(
            text="本文です",
            caption=None,
            request_id="req-2",
            model_name="irodori_v2",
            output_basename="tts-req-2",
        )
    )
    assert captured_prompt["3"]["inputs"]["text"] == "落ち着いた女性の声\n\n本文です"  # type: ignore[index]


def test_caption_is_ignored_when_model_does_not_support_it(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "workflow.json"
    comfy_output_audio = tmp_path / "output" / "generated.wav"
    workflow = {
        "10": {"class_type": "Text", "inputs": {"text": ""}},
        "20": {"class_type": "SaveAudio", "inputs": {"filename_prefix": "old"}},
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    comfy_output_audio.parent.mkdir(parents=True, exist_ok=True)
    comfy_output_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")

    models = {
        "mock_like": ModelConfig(
            runtime="comfyui",
            workflow_path=workflow_path,
            requires_reference_audio=False,
            supports_caption=False,
            workflow_targets=WorkflowTargetsConfig(
                text=WorkflowTargetConfig(node_id="10", input_key="text"),
                save_audio=WorkflowTargetConfig(node_id="20", input_key="filename_prefix"),
            ),
        )
    }
    runtime = _build_runtime(tmp_path, models)
    captured_prompt: dict[str, object] = {}

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            assert payload is not None
            captured_prompt.update(payload["prompt"])  # type: ignore[index]
            return {"prompt_id": "p-3"}
        if method == "GET" and "/history/" in url:
            return {"p-3": {"status": {"status_str": "success"}, "outputs": {"node": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}}}}
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_http_json", fake_http_json)
    runtime.synthesize(
        SynthesizeRequest(
            text="通常テキスト",
            caption="ASMR風",
            request_id="req-3",
            model_name="mock_like",
            output_basename="tts-req-3",
        )
    )
    assert captured_prompt["10"]["inputs"]["text"] == "通常テキスト"  # type: ignore[index]


def test_seed_target_is_applied_when_seed_is_provided(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "workflow.json"
    comfy_output_audio = tmp_path / "output" / "generated.wav"
    workflow = {
        "3": {"class_type": "IrodoriTTSSampler", "inputs": {"text": "", "seed": 10}},
        "4": {"class_type": "SaveAudio", "inputs": {"filename_prefix": "old"}},
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    comfy_output_audio.parent.mkdir(parents=True, exist_ok=True)
    comfy_output_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")

    models = {
        "irodori_v2": ModelConfig(
            runtime="comfyui",
            workflow_path=workflow_path,
            requires_reference_audio=False,
            workflow_targets=WorkflowTargetsConfig(
                text=WorkflowTargetConfig(node_id="3", input_key="text"),
                seed=WorkflowTargetConfig(node_id="3", input_key="seed"),
                save_audio=WorkflowTargetConfig(node_id="4", input_key="filename_prefix"),
            ),
        )
    }
    runtime = _build_runtime(tmp_path, models)
    captured_prompt: dict[str, object] = {}

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            assert payload is not None
            captured_prompt.update(payload["prompt"])  # type: ignore[index]
            return {"prompt_id": "p-seed"}
        if method == "GET" and "/history/" in url:
            return {"p-seed": {"status": {"status_str": "success"}, "outputs": {"node": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}}}}
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_http_json", fake_http_json)
    runtime.synthesize(
        SynthesizeRequest(
            text="seed test",
            seed=123456,
            request_id="req-seed",
            model_name="irodori_v2",
            output_basename="tts-seed",
        )
    )

    assert captured_prompt["3"]["inputs"]["seed"] == 123456  # type: ignore[index]


def test_seed_target_keeps_workflow_default_when_seed_is_missing(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "workflow.json"
    comfy_output_audio = tmp_path / "output" / "generated.wav"
    workflow = {
        "3": {"class_type": "IrodoriTTSSampler", "inputs": {"text": "", "seed": 77}},
        "4": {"class_type": "SaveAudio", "inputs": {"filename_prefix": "old"}},
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    comfy_output_audio.parent.mkdir(parents=True, exist_ok=True)
    comfy_output_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")

    models = {
        "irodori_v3": ModelConfig(
            runtime="comfyui",
            workflow_path=workflow_path,
            requires_reference_audio=False,
            workflow_targets=WorkflowTargetsConfig(
                text=WorkflowTargetConfig(node_id="3", input_key="text"),
                seed=WorkflowTargetConfig(node_id="3", input_key="seed"),
                save_audio=WorkflowTargetConfig(node_id="4", input_key="filename_prefix"),
            ),
        )
    }
    runtime = _build_runtime(tmp_path, models)
    captured_prompt: dict[str, object] = {}

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            assert payload is not None
            captured_prompt.update(payload["prompt"])  # type: ignore[index]
            return {"prompt_id": "p-seed-default"}
        if method == "GET" and "/history/" in url:
            return {"p-seed-default": {"status": {"status_str": "success"}, "outputs": {"node": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}}}}
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_http_json", fake_http_json)
    runtime.synthesize(
        SynthesizeRequest(
            text="seed default",
            request_id="req-seed-default",
            model_name="irodori_v3",
            output_basename="tts-seed-default",
        )
    )

    assert captured_prompt["3"]["inputs"]["seed"] == 77  # type: ignore[index]


def test_synthesize_auto_launches_comfyui_when_health_recovers(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "workflow.json"
    reference_audio_path = tmp_path / "ref.wav"
    comfy_output_audio = tmp_path / "output" / "generated.wav"
    launch_bat = tmp_path / "start-comfyui.bat"

    workflow = {
        "10": {"class_type": "Qwen3VoiceClone", "inputs": {"text": "", "audio": ""}},
        "25": {"class_type": "SaveAudio", "inputs": {"filename_prefix": "old"}},
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    reference_audio_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    (tmp_path / "input").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime").mkdir(parents=True, exist_ok=True)
    comfy_output_audio.parent.mkdir(parents=True, exist_ok=True)
    comfy_output_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")
    launch_bat.write_text("@echo off\r\n", encoding="utf-8")

    runtime = ComfyUIRuntime(
        output_dir=tmp_path / "runtime",
        models={
            "irodori_v3": ModelConfig(
                runtime="comfyui",
                workflow_path=workflow_path,
                requires_reference_audio=True,
                workflow_targets=WorkflowTargetsConfig(
                    text=WorkflowTargetConfig(node_id="10", input_key="text"),
                    save_audio=WorkflowTargetConfig(node_id="25", input_key="filename_prefix"),
                    reference_audio=WorkflowTargetConfig(node_id="10", input_key="audio"),
                ),
            )
        },
        base_url="http://127.0.0.1:8188",
        input_dir=tmp_path / "input",
        comfy_output_dir=tmp_path / "output",
        auto_launch=True,
        launch_bat_path=launch_bat,
        launch_working_dir=tmp_path,
        startup_timeout_sec=3,
        startup_poll_interval_sec=0.01,
        health_path="/system_stats",
    )

    calls: list[str] = []
    health_results = iter([False, False, True])

    def fake_health() -> bool:
        calls.append("health")
        return next(health_results)

    def fake_launch() -> None:
        calls.append("launch")

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            return {"prompt_id": "p-launch"}
        if method == "GET" and "/history/" in url:
            return {"p-launch": {"status": {"status_str": "success"}, "outputs": {"node": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}}}}
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_is_server_healthy", fake_health)
    monkeypatch.setattr(runtime, "_launch_comfyui", fake_launch)
    monkeypatch.setattr(runtime, "_http_json", fake_http_json)

    runtime.synthesize(
        SynthesizeRequest(
            text="起動確認です",
            request_id="req-launch",
            model_name="irodori_v3",
            output_basename="tts-req-launch",
            reference_audio_path=reference_audio_path,
        )
    )

    assert calls.count("launch") == 1
    assert calls[:3] == ["health", "launch", "health"]


def test_synthesize_does_not_launch_when_already_healthy(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "workflow.json"
    comfy_output_audio = tmp_path / "output" / "generated.wav"
    workflow = {
        "10": {"class_type": "Text", "inputs": {"text": ""}},
        "20": {"class_type": "SaveAudio", "inputs": {"filename_prefix": "old"}},
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    (tmp_path / "input").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime").mkdir(parents=True, exist_ok=True)
    comfy_output_audio.parent.mkdir(parents=True, exist_ok=True)
    comfy_output_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")

    runtime = ComfyUIRuntime(
        output_dir=tmp_path / "runtime",
        models={
            "irodori_v3": ModelConfig(
                runtime="comfyui",
                workflow_path=workflow_path,
                requires_reference_audio=False,
                workflow_targets=WorkflowTargetsConfig(
                    text=WorkflowTargetConfig(node_id="10", input_key="text"),
                    save_audio=WorkflowTargetConfig(node_id="20", input_key="filename_prefix"),
                ),
            )
        },
        base_url="http://127.0.0.1:8188",
        input_dir=tmp_path / "input",
        comfy_output_dir=tmp_path / "output",
        auto_launch=True,
        launch_bat_path=tmp_path / "start-comfyui.bat",
        launch_working_dir=tmp_path,
    )

    launched: list[bool] = []

    def fake_http_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30):
        if method == "POST" and url.endswith("/prompt"):
            return {"prompt_id": "p-ok"}
        if method == "GET" and "/history/" in url:
            return {"p-ok": {"status": {"status_str": "success"}, "outputs": {"node": {"audio": [{"filename": "generated.wav", "subfolder": ""}]}}}}
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(runtime, "_is_server_healthy", lambda: True)
    monkeypatch.setattr(runtime, "_launch_comfyui", lambda: launched.append(True))
    monkeypatch.setattr(runtime, "_http_json", fake_http_json)

    runtime.synthesize(
        SynthesizeRequest(
            text="already running",
            request_id="req-ok",
            model_name="irodori_v3",
            output_basename="tts-req-ok",
        )
    )

    assert launched == []


def test_synthesize_returns_clear_error_when_server_unavailable_and_auto_launch_disabled(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "workflow.json"
    workflow = {
        "10": {"class_type": "Text", "inputs": {"text": ""}},
        "20": {"class_type": "SaveAudio", "inputs": {"filename_prefix": "old"}},
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    (tmp_path / "input").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime").mkdir(parents=True, exist_ok=True)

    runtime = ComfyUIRuntime(
        output_dir=tmp_path / "runtime",
        models={
            "irodori_v3": ModelConfig(
                runtime="comfyui",
                workflow_path=workflow_path,
                requires_reference_audio=False,
                workflow_targets=WorkflowTargetsConfig(
                    text=WorkflowTargetConfig(node_id="10", input_key="text"),
                    save_audio=WorkflowTargetConfig(node_id="20", input_key="filename_prefix"),
                ),
            )
        },
        base_url="http://127.0.0.1:8188",
        input_dir=tmp_path / "input",
        comfy_output_dir=tmp_path / "output",
        auto_launch=False,
    )

    monkeypatch.setattr(runtime, "_is_server_healthy", lambda: False)

    with pytest.raises(ProviderError) as exc:
        runtime.synthesize(
            SynthesizeRequest(
                text="offline",
                request_id="req-offline",
                model_name="irodori_v3",
                output_basename="tts-req-offline",
            )
        )

    assert "ComfyUI is not reachable" in str(exc.value)
    assert "autoLaunch" in str(exc.value)
