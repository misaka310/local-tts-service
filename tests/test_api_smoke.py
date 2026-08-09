from __future__ import annotations

import json

import wave

from fastapi.testclient import TestClient

import local_tts_service.server as server_module
from local_tts_service.runtimes.base import SynthesizeResult
from local_tts_service.server import create_app
from local_tts_service.storage import write_silence_wav


def _write_config(tmp_path) -> None:
    config = {
        "host": "127.0.0.1",
        "port": 8730,
        "defaultModel": "mock",
        "defaultReferenceVoice": "default",
        "referenceVoicesDir": "./reference/voices",
        "audioOutputDir": "./runtime/audio",
        "chunking": {
            "softChunkChars": 120,
            "maxChunkChars": 200,
            "hardLimitChars": 260,
            "pauseBetweenChunksMs": 250,
        },
        "externalServices": {"comfyui": {"enabled": True}},
        "models": {
            "mock": {
                "runtime": "mock_wav",
                "requiresReferenceAudio": False,
            },
            "irodori_v2": {
                "runtime": "comfyui",
                "workflowPath": "./reference/workflows/irodori_v2_api.json",
                "requiresReferenceAudio": False,
                "supportsCaption": True,
                "defaultCaption": "落ち着いた女性の声",
                "workflowTargets": {
                    "text": {"nodeId": "3", "inputKey": "text"},
                    "caption": {"nodeId": "3", "inputKey": "text"},
                    "saveAudio": {"nodeId": "4", "inputKey": "filename_prefix"},
                    "seed": {"nodeId": "3", "inputKey": "seed"},
                },
            },
            "irodori_v3": {
                "runtime": "comfyui",
                "label": "irodori v3",
                "family": "irodori",
                "workflowPath": "./reference/workflows/irodori_v3_api.json",
                "requiresReferenceAudio": False,
                "supportsSeed": True,
                "supportsReferenceVoice": True,
                "workflowTargets": {
                    "text": {"nodeId": "3", "inputKey": "text"},
                    "seed": {"nodeId": "3", "inputKey": "seed"},
                    "saveAudio": {"nodeId": "4", "inputKey": "filename_prefix"},
                    "referenceAudio": {"nodeId": "2", "inputKey": "ref_audio"},
                },
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
            },
            "qwen3_tts_design_1_7b": {
                "runtime": "qwen3_tts",
                "label": "Qwen3-TTS Voice Design 1.7B",
                "family": "qwen3_tts",
                "modelId": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                "supportsInstruction": True,
                "supportsLanguage": True,
                "supportsSeed": True,
                "supportsVoiceDesign": True,
                "defaultLanguage": "Japanese",
            },
            "irodori_v3_voicedesign": {
                "runtime": "irodori_voicedesign_direct",
                "requiresReferenceAudio": False,
                "supportsCaption": True,
                "supportsInstruction": True,
                "supportsSeed": True,
                "supportsSpeedControl": True,
                "supportsStyleStrength": True,
                "supportsVoiceDesign": True,
                "supportsReferenceVoice": True,
            },
            "voxcpm2_tts": {
                "runtime": "comfyui_voxcpm2",
                "workflowPath": "./reference/workflows/voxcpm2_tts_api.json",
                "requiresReferenceAudio": False,
                "voiceDescription": "A calm Japanese female voice",
            },
        },
        "runtimes": {
            "mock_wav": {
                "durationSec": 0.1,
                "sampleRate": 16000,
            },
            "comfyui": {
                "baseUrl": "http://127.0.0.1:8188",
                "inputDir": "./runtime/comfy-input",
                "outputDir": "./runtime/comfy-output",
                "autoLaunch": True,
                "launchBatPath": "./scripts/start-comfyui.bat",
                "launchWorkingDir": "./runtime",
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
                "checkpoint": "Aratako/Irodori-TTS-600M-v3-VoiceDesign",
                "wrapperDir": "D:/ComfyUI_TTS_E2E_SANDBOX/ComfyUI/custom_nodes/ComfyUI_IrodoriTTS_Wrapper",
                "modelDevice": "cpu",
                "codecDevice": "cpu",
            },
            "qwen3_tts": {
                "device": "cpu",
                "dtype": "float32",
                "vendorDir": "./runtime/vendor/qwen3-tts",
                "allowDownload": False,
            },
        },
    }
    (tmp_path / "config.example.json").write_text(json.dumps(config), encoding="utf-8")
    workflow_dir = tmp_path / "reference" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    for workflow_name in ("irodori_v2_api.json", "irodori_v3_api.json", "voxcpm2_tts_api.json"):
        (workflow_dir / workflow_name).write_text("{}", encoding="utf-8")
    default_voice_dir = tmp_path / "reference" / "voices" / "default"
    default_voice_dir.mkdir(parents=True, exist_ok=True)
    (default_voice_dir / "voice.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    person_a_dir = tmp_path / "reference" / "voices" / "person_a"
    person_a_dir.mkdir(parents=True, exist_ok=True)
    (person_a_dir / "voice.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    disabled_dir = tmp_path / "reference" / "voices" / "broken"
    disabled_dir.mkdir(parents=True, exist_ok=True)
    (disabled_dir / "text.txt").write_text("missing wav", encoding="utf-8")


def test_server_main_runs_prebuilt_app_without_module_reimport(monkeypatch) -> None:
    config = type("Config", (), {"host": "127.0.0.1", "port": 8730})()
    calls: list[object] = []
    monkeypatch.setattr(server_module, "load_config", lambda _root: config)
    monkeypatch.setattr(
        "uvicorn.run",
        lambda application, **kwargs: calls.append((application, kwargs)),
    )

    server_module.main()

    assert calls == [(server_module.app, {"host": "127.0.0.1", "port": 8730, "reload": False})]


def test_api_smoke(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert "defaultModel" in health.json()
    assert "comfyui_voxcpm2" in health.json()["availableProviders"]
    assert "qwen3_tts" in health.json()["availableProviders"]
    assert any(
        item["model"] == "irodori_v2" and item["supportsCaption"] is True
        for item in health.json()["availableModelInfo"]
    )

    models = client.get("/v1/models")
    assert models.status_code == 200
    assert models.json()["ok"] is True
    assert any(item["model"] == "mock" for item in models.json()["models"])
    assert any(
        item["model"] == "irodori_v2"
        and item["supportsCaption"] is True
        and item["defaultCaption"] == "落ち着いた女性の声"
        for item in models.json()["models"]
    )
    assert any(
        item["id"] == "qwen3_tts_clone_0_6b"
        and isinstance(item["available"], bool)
        and item["requiresReferenceText"] is True
        and item["supportsVoiceClone"] is True
        for item in models.json()["models"]
    )
    assert any(
        item["id"] == "irodori_v3_voicedesign"
        and item["supportsSpeedControl"] is True
        and item["supportsStyleStrength"] is True
        for item in models.json()["models"]
    )

    direct_runtime = app.state.service.runtimes["irodori_voicedesign_direct"]
    released_models: list[str] = []
    direct_runtime.release_model = lambda model_name: released_models.append(model_name) or True
    unload = client.post("/v1/models/irodori_v3_voicedesign/unload")
    assert unload.status_code == 200
    assert unload.json() == {
        "ok": True,
        "model": "irodori_v3_voicedesign",
        "runtime": "irodori_voicedesign_direct",
        "released": True,
    }
    assert released_models == ["irodori_v3_voicedesign"]

    speak = client.post(
        "/v1/speak",
        json={
            "text": "hello",
            "model": "mock",
            "requestId": "smoke",
        },
    )
    assert speak.status_code == 200
    payload = speak.json()
    assert payload["ok"] is True
    assert payload["model"] == "mock"
    assert payload["runtime"] == "mock_wav"
    assert payload["audioUrl"].startswith("http")

    audio_name = payload["audioUrl"].split("/")[-1]
    audio = client.get(f"/audio/{audio_name}")
    assert audio.status_code == 200
    assert audio.content


def test_health_is_lightweight_but_model_list_runs_external_cli_environment_probes(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    runtime = app.state.service.runtimes["external_cli"]
    calls: list[str] = []

    def record_probe(model_name, model_cfg):
        calls.append(model_name)
        return runtime.get_static_model_availability(model_name, model_cfg)

    monkeypatch.setattr(runtime, "get_model_availability", record_probe)
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert calls == []
    assert client.get("/v1/models").status_code == 200
    assert "sarashina2_2_tts" in calls
    assert "t5gemma_tts_2b_2b" in calls


def test_model_list_can_skip_external_probes_without_losing_model_info(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    runtime = app.state.service.runtimes["external_cli"]
    calls: list[str] = []

    def record_probe(model_name, model_cfg):
        calls.append(model_name)
        return runtime.get_static_model_availability(model_name, model_cfg)

    monkeypatch.setattr(runtime, "get_model_availability", record_probe)
    client = TestClient(app)

    lightweight = client.get("/v1/models?probe=false")
    assert lightweight.status_code == 200
    assert lightweight.json()["ok"] is True
    assert calls == []
    sarashina = next(item for item in lightweight.json()["models"] if item["id"] == "sarashina2_2_tts")
    assert sarashina["runtime"] == "external_cli"
    assert isinstance(sarashina["available"], bool)
    assert "label" in sarashina

    probed = client.get("/v1/models?probe=true")
    assert probed.status_code == 200
    assert "sarashina2_2_tts" in calls
    assert "t5gemma_tts_2b_2b" in calls

    calls.clear()
    compatible_default = client.get("/v1/models")
    assert compatible_default.status_code == 200
    assert "sarashina2_2_tts" in calls
    assert "t5gemma_tts_2b_2b" in calls


def test_health_hides_runtimes_unused_by_configured_models(tmp_path) -> None:
    _write_config(tmp_path)
    config_path = tmp_path / "config.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["models"] = {
        name: model
        for name, model in config["models"].items()
        if model.get("runtime") not in {"comfyui", "comfyui_voxcpm2"}
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    health = TestClient(create_app(tmp_path)).get("/health")

    assert health.status_code == 200
    payload = health.json()
    assert "comfyui" not in payload["availableRuntimes"]
    assert "comfyui_voxcpm2" not in payload["availableProviders"]
    assert "irodori_voicedesign_direct" in payload["availableRuntimes"]
    assert "mock" in payload["availableModels"]
    assert "qwen3_tts_design_1_7b" not in payload["availableModels"]


def test_disabled_comfyui_marks_comfy_models_unavailable(tmp_path) -> None:
    _write_config(tmp_path)
    config_path = tmp_path / "config.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["externalServices"] = {
        "comfyui": {"enabled": False},
        "gptSovits": {"enabled": False},
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "run-gpt-sovits-api.ps1").write_text("exit 0\n", encoding="utf-8")

    client = TestClient(create_app(tmp_path))
    response = client.get("/v1/models")

    assert response.status_code == 200
    model = next(item for item in response.json()["models"] if item["id"] == "irodori_v3")
    assert model["available"] is False
    assert "disabled" in model["unavailableReason"].lower()
    gpt_model = next(item for item in response.json()["models"] if item["id"] == "gpt_sovits_zero_shot")
    assert gpt_model["available"] is False
    assert "disabled" in gpt_model["unavailableReason"].lower()


def test_api_accepts_legacy_voice_field(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)

    speak = client.post(
        "/v1/speak",
        json={
            "text": "legacy",
            "voice": "mock",
            "requestId": "legacy-voice",
        },
    )
    assert speak.status_code == 200
    assert speak.json()["model"] == "mock"


def test_legacy_voices_endpoint_returns_deprecated_flag(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)

    voices = client.get("/v1/voices")
    assert voices.status_code == 200
    payload = voices.json()
    assert payload["ok"] is True
    assert payload["deprecated"] is True
    assert payload["use"] == "/v1/reference-voices"
    assert any(item["voiceId"] == "default" for item in payload["voices"])


def test_reference_voices_endpoint_lists_available_voices(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)

    voices = client.get("/v1/reference-voices")
    assert voices.status_code == 200
    payload = voices.json()
    assert payload["ok"] is True
    assert payload["defaultReferenceVoice"] == "default"
    assert any(item["voiceId"] == "default" and item["enabled"] is True for item in payload["voices"])
    assert any(item["voiceId"] == "person_a" and item["enabled"] is True for item in payload["voices"])
    assert any(item["voiceId"] == "broken" and item["enabled"] is False for item in payload["voices"])


def test_speak_accepts_legacy_engine_override(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)

    class _FakeVoxRuntime:
        name = "comfyui_voxcpm2"

        def synthesize(self, request):  # noqa: ANN001
            out = tmp_path / "runtime" / "audio" / f"{request.output_basename}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")
            return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out)

    app.state.service.runtimes["comfyui_voxcpm2"] = _FakeVoxRuntime()
    client = TestClient(app)

    speak = client.post(
        "/v1/speak",
        json={
            "text": "engine override",
            "model": "voxcpm2_tts",
            "engine": "comfyui_voxcpm2",
            "requestId": "legacy-engine",
        },
    )
    assert speak.status_code == 200
    assert speak.json()["runtime"] == "comfyui_voxcpm2"


def test_speak_accepts_comfyui_qwen3_legacy_engine_alias(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)

    class _FakeComfyRuntime:
        name = "comfyui"

        def synthesize(self, request):  # noqa: ANN001
            out = tmp_path / "runtime" / "audio" / f"{request.output_basename}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")
            return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out)

    app.state.service.runtimes["comfyui"] = _FakeComfyRuntime()
    client = TestClient(app)

    speak = client.post(
        "/v1/speak",
        json={
            "text": "legacy comfyui_qwen3",
            "model": "irodori_v2",
            "engine": "comfyui_qwen3",
            "requestId": "legacy-comfyui-qwen3",
        },
    )
    assert speak.status_code == 200
    assert speak.json()["runtime"] == "comfyui"


def test_health_deep_reports_runtime_and_model_details(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    runtime = app.state.service.runtimes["comfyui"]
    runtime._is_server_healthy = lambda: True  # type: ignore[method-assign]
    client = TestClient(app)

    deep = client.get("/health/deep")
    assert deep.status_code == 200
    payload = deep.json()
    assert payload["ok"] is True
    assert payload["service"]["defaultModel"] == "mock"
    assert payload["runtimeChecks"]["comfyui"]["ok"] is True
    assert payload["runtimeChecks"]["comfyui"]["autoLaunch"] is True
    assert payload["runtimeChecks"]["comfyui"]["launchBatPath"].replace("/", "\\").endswith("scripts\\start-comfyui.bat")
    assert payload["modelChecks"]["irodori_v3"]["configured"] is True
    assert payload["service"]["defaultReferenceVoice"] == "default"
    assert payload["referenceVoicesDir"].replace("/", "\\").endswith("reference\\voices")
    assert any(item["voiceId"] == "default" and item["enabled"] is True for item in payload["referenceVoices"])
    assert payload["chunking"]["maxChunkChars"] == 200


def test_health_deep_skips_disabled_comfyui(tmp_path) -> None:
    _write_config(tmp_path)
    config_path = tmp_path / "config.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["externalServices"] = {"comfyui": {"enabled": False}}
    config_path.write_text(json.dumps(config), encoding="utf-8")

    client = TestClient(create_app(tmp_path))
    deep = client.get("/health/deep")

    assert deep.status_code == 200
    payload = deep.json()
    assert payload["ok"] is True
    assert payload["runtimeChecks"]["comfyui"]["enabled"] is False
    assert payload["runtimeChecks"]["comfyui"]["skipped"] is True


def test_health_deep_ignores_enabled_comfyui_when_no_model_uses_it(tmp_path) -> None:
    _write_config(tmp_path)
    config_path = tmp_path / "config.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["models"] = {
        name: model
        for name, model in config["models"].items()
        if model.get("runtime") not in {"comfyui", "comfyui_voxcpm2"}
    }
    config["externalServices"]["comfyui"]["enabled"] = True
    config_path.write_text(json.dumps(config), encoding="utf-8")

    app = create_app(tmp_path)
    runtime = app.state.service.runtimes["comfyui"]
    runtime._is_server_healthy = lambda: (_ for _ in ()).throw(AssertionError("unused ComfyUI was probed"))  # type: ignore[method-assign]
    deep = TestClient(app).get("/health/deep")

    assert deep.status_code == 200
    payload = deep.json()
    assert payload["ok"] is True
    assert "comfyui" not in payload["runtimeChecks"]
    assert "comfyui" not in payload["externalChecks"]


def test_speak_chunks_long_text_and_merges_wav(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)
    calls: list[str] = []

    class _ChunkRuntime:
        name = "comfyui"

        def synthesize(self, request):  # noqa: ANN001
            calls.append(request.text)
            out = tmp_path / "runtime" / "audio" / f"{request.output_basename}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            write_silence_wav(out, duration_sec=0.05, sample_rate=16000)
            return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out)

    app.state.service.runtimes["comfyui"] = _ChunkRuntime()
    long_text = ("これはチャンク結合のテストです。" * 220)[:5000]

    speak = client.post(
        "/v1/speak",
        json={
            "text": long_text,
            "model": "irodori_v3",
            "voiceId": "default",
            "requestId": "chunk-test",
            "format": "wav",
        },
    )
    assert speak.status_code == 200
    payload = speak.json()
    assert payload["ok"] is True
    assert len(calls) >= 2
    for chunk_text in calls:
        assert len(chunk_text) <= 260

    audio_path = payload["audioPath"]
    assert "\\runtime\\audio\\" in audio_path
    chunk_dir = tmp_path / "runtime" / "audio" / "chunks" / "chunk-test"
    assert not chunk_dir.exists()

    with wave.open(audio_path, "rb") as fp:
        assert fp.getframerate() == 16000
        assert fp.getnframes() > 0


def test_speak_passes_selected_reference_voice_to_runtime(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)
    captured = {}

    class _VoiceRuntime:
        name = "comfyui"

        def synthesize(self, request):  # noqa: ANN001
            captured["voice_id"] = request.voice_id
            captured["reference_audio_path"] = str(request.reference_audio_path)
            captured["reference_text_path"] = request.reference_text_path
            out = tmp_path / "runtime" / "audio" / f"{request.output_basename}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            write_silence_wav(out, duration_sec=0.05, sample_rate=16000)
            return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out)

    app.state.service.runtimes["comfyui"] = _VoiceRuntime()
    speak = client.post(
        "/v1/speak",
        json={
            "text": "voice select",
            "model": "irodori_v3",
            "voiceId": "person_a",
            "requestId": "voice-select",
            "format": "wav",
        },
    )
    assert speak.status_code == 200
    assert captured["voice_id"] == "person_a"
    assert captured["reference_audio_path"].replace("/", "\\").endswith("reference\\voices\\person_a\\voice.wav")
    assert captured["reference_text_path"] is None


def test_speak_preserves_emoji_text_for_irodori_v3(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)
    captured = {}

    class _EmojiRuntime:
        name = "comfyui"

        def synthesize(self, request):  # noqa: ANN001
            captured["text"] = request.text
            out = tmp_path / "runtime" / "audio" / f"{request.output_basename}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            write_silence_wav(out, duration_sec=0.05, sample_rate=16000)
            return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out)

    app.state.service.runtimes["comfyui"] = _EmojiRuntime()
    emoji_text = "え、ほんとに？😳 うぅ…😭 でもやる！🔥"
    speak = client.post(
        "/v1/speak",
        json={
            "text": emoji_text,
            "model": "irodori_v3",
            "voiceId": "person_a",
            "requestId": "irodori-v3-emoji",
            "format": "wav",
        },
    )

    assert speak.status_code == 200
    assert captured["text"] == emoji_text


def test_irodori_v3_allows_generation_without_reference_voice(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)
    captured = {}

    class _NoReferenceRuntime:
        name = "comfyui"

        def synthesize(self, request):  # noqa: ANN001
            captured["voice_id"] = request.voice_id
            captured["reference_audio_path"] = request.reference_audio_path
            out = tmp_path / "runtime" / "audio" / f"{request.output_basename}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            write_silence_wav(out, duration_sec=0.05, sample_rate=16000)
            return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out)

    app.state.service.runtimes["comfyui"] = _NoReferenceRuntime()
    speak = client.post(
        "/v1/speak",
        json={
            "text": "voice missing",
            "model": "irodori_v3",
            "requestId": "voice-missing",
            "format": "wav",
        },
    )
    assert speak.status_code == 200
    assert captured == {"voice_id": None, "reference_audio_path": None}


def test_speak_passes_seed_to_runtime(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)
    captured = {}

    class _SeedRuntime:
        name = "comfyui"

        def synthesize(self, request):  # noqa: ANN001
            captured["seed"] = request.seed
            out = tmp_path / "runtime" / "audio" / f"{request.output_basename}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            write_silence_wav(out, duration_sec=0.05, sample_rate=16000)
            return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out)

    app.state.service.runtimes["comfyui"] = _SeedRuntime()
    speak = client.post(
        "/v1/speak",
        json={
            "text": "seed pass through",
            "model": "irodori_v2",
            "seed": 2468,
            "requestId": "seed-pass",
            "format": "wav",
        },
    )
    assert speak.status_code == 200
    assert captured["seed"] == 2468


def test_speak_accepts_style_caption_alias(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)
    captured = {}

    class _VoiceDesignRuntime:
        name = "irodori_voicedesign_direct"

        def synthesize(self, request):  # noqa: ANN001
            captured["caption"] = request.caption
            out = tmp_path / "runtime" / "audio" / f"{request.output_basename}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            write_silence_wav(out, duration_sec=0.05, sample_rate=16000)
            return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out)

    app.state.service.runtimes["irodori_voicedesign_direct"] = _VoiceDesignRuntime()
    speak = client.post(
        "/v1/speak",
        json={
            "text": "caption alias",
            "model": "irodori_v3_voicedesign",
            "voiceId": "person_a",
            "styleCaption": "少し明るく自然なトーン",
            "requestId": "caption-alias",
            "format": "wav",
        },
    )

    assert speak.status_code == 200
    assert captured["caption"] == "少し明るく自然なトーン"


def test_voicedesign_maps_instruction_and_native_controls(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)
    captured = {}

    class _VoiceDesignRuntime:
        name = "irodori_voicedesign_direct"

        def synthesize(self, request):  # noqa: ANN001
            captured["caption"] = request.caption
            captured["speed_scale"] = request.speed_scale
            captured["style_strength"] = request.style_strength
            captured["reference_audio_path"] = request.reference_audio_path
            out = tmp_path / "runtime" / "audio" / f"{request.output_basename}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            write_silence_wav(out, duration_sec=0.05, sample_rate=16000)
            return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out)

    app.state.service.runtimes["irodori_voicedesign_direct"] = _VoiceDesignRuntime()
    speak = client.post(
        "/v1/speak",
        json={
            "text": "native controls",
            "model": "irodori_v3_voicedesign",
            "instruction": "明るく自然なトーン",
            "speedScale": 1.2,
            "styleStrength": 4.5,
            "requestId": "native-controls",
            "format": "wav",
        },
    )

    assert speak.status_code == 200
    assert captured == {
        "caption": "明るく自然なトーン",
        "speed_scale": 1.2,
        "style_strength": 4.5,
        "reference_audio_path": None,
    }


def test_voicedesign_allows_reference_voice_without_instruction(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)
    captured = {}

    class _VoiceDesignRuntime:
        name = "irodori_voicedesign_direct"

        def synthesize(self, request):  # noqa: ANN001
            captured["caption"] = request.caption
            captured["voice_id"] = request.voice_id
            captured["reference_audio_path"] = request.reference_audio_path
            out = tmp_path / "runtime" / "audio" / f"{request.output_basename}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            write_silence_wav(out, duration_sec=0.05, sample_rate=16000)
            return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out)

    app.state.service.runtimes["irodori_voicedesign_direct"] = _VoiceDesignRuntime()
    speak = client.post(
        "/v1/speak",
        json={
            "text": "reference only",
            "model": "irodori_v3_voicedesign",
            "voiceId": "person_a",
            "requestId": "reference-only",
            "format": "wav",
        },
    )

    assert speak.status_code == 200
    assert captured["caption"] is None
    assert captured["voice_id"] == "person_a"
    assert str(captured["reference_audio_path"]).replace("/", "\\").endswith(
        "reference\\voices\\person_a\\voice.wav"
    )


def test_voicedesign_rejects_style_strength_without_instruction(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)

    speak = client.post(
        "/v1/speak",
        json={
            "text": "style without caption",
            "model": "irodori_v3_voicedesign",
            "styleStrength": 4.5,
            "requestId": "style-without-caption",
            "format": "wav",
        },
    )

    assert speak.status_code == 400
    assert "styleStrength requires instruction or caption" in speak.json()["error"]


def test_qwen_clone_requires_voice_txt(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)

    speak = client.post(
        "/v1/speak",
        json={
            "text": "voice txt required",
            "model": "qwen3_tts_clone_0_6b",
            "voiceId": "default",
            "requestId": "qwen-clone-missing-text",
            "format": "wav",
        },
    )

    assert speak.status_code == 400
    assert "voice.txt is required for voiceId: default" in speak.json()["error"]


def test_qwen_voice_design_is_retired_from_standard_config(tmp_path) -> None:
    _write_config(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)

    speak = client.post(
        "/v1/speak",
        json={
            "text": "qwen design",
            "model": "qwen3_tts_design_1_7b",
            "styleCaption": "落ち着いた配信者風で短く自然に",
            "requestId": "qwen-design-caption",
            "format": "wav",
        },
    )

    assert speak.status_code == 400
    assert "unknown model" in speak.json()["error"]


def test_qwen_unavailable_returns_clear_payload(tmp_path) -> None:
    _write_config(tmp_path)
    (tmp_path / "reference" / "voices" / "person_a" / "voice.txt").write_text("こんにちは", encoding="utf-8")
    app = create_app(tmp_path)
    client = TestClient(app)

    speak = client.post(
        "/v1/speak",
        json={
            "text": "qwen unavailable",
            "model": "qwen3_tts_clone_1_7b",
            "voiceId": "person_a",
            "requestId": "qwen-unavailable",
            "format": "wav",
        },
    )

    assert speak.status_code == 400
    payload = speak.json()
    assert payload["available"] is False
    assert payload["model"] == "qwen3_tts_clone_1_7b"
    assert payload["unavailableReason"]
