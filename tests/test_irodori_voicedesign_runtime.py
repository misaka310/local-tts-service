from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from local_tts_service.errors import ProviderError
from local_tts_service.models import ModelConfig
from local_tts_service.runtimes.base import SynthesizeRequest
from local_tts_service.runtimes.irodori_voicedesign_direct import IrodoriVoiceDesignDirectRuntime


class _LiveWorker:
    def poll(self) -> None:
        return None


class _DeadWorker:
    returncode = 1

    def poll(self) -> int:
        return self.returncode


def _build_runtime(tmp_path: Path) -> IrodoriVoiceDesignDirectRuntime:
    python_exe = tmp_path / "python.exe"
    python_exe.write_bytes(b"")
    wrapper_dir = tmp_path / "wrapper"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    helper_script = tmp_path / "scripts" / "run_irodori_voicedesign.py"
    helper_script.parent.mkdir(parents=True, exist_ok=True)
    helper_script.write_text("print('stub')", encoding="utf-8")
    checkpoint = tmp_path / "runtime" / "models" / "irodori" / "voicedesign" / "model.safetensors"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"model")
    codec_dir = tmp_path / "runtime" / "models" / "irodori" / "codec"
    codec_dir.mkdir(parents=True, exist_ok=True)
    (codec_dir / "weights.pth").write_bytes(b"codec")
    processor_dir = tmp_path / "runtime" / "models" / "irodori" / "tokenizers" / "llm-jp-3-150m"
    processor_dir.mkdir(parents=True, exist_ok=True)
    (processor_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    (processor_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    runtime = IrodoriVoiceDesignDirectRuntime(
        output_dir=tmp_path / "runtime" / "audio",
        models={
            "irodori_v3_voicedesign": ModelConfig(
                runtime="irodori_voicedesign_direct",
                checkpoint=checkpoint,
                requires_reference_audio=False,
                supports_caption=True,
                supports_instruction=True,
                supports_reference_voice=True,
                supports_speed_control=True,
                supports_style_strength=True,
                supports_voice_design=True,
            )
        },
        root_dir=tmp_path,
        python_executable=str(python_exe),
        wrapper_dir=wrapper_dir,
        checkpoint="",
        codec_repo=str(codec_dir),
        text_processor_dir=str(processor_dir),
        model_device="cpu",
        model_precision="fp32",
        codec_device="cpu",
        codec_precision="fp32",
    )
    runtime._worker = _LiveWorker()  # type: ignore[assignment]
    runtime._prepared_models.add("irodori_v3_voicedesign")
    return runtime


def test_runtime_metadata_warns_when_cuda_falls_back_to_cpu(tmp_path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path)
    runtime.model_device = "cuda"
    calls = []

    def fake_run(cmd, cwd, capture_output, text, timeout, check, env):  # noqa: ANN001
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"cudaAvailable": False, "torchVersion": "2.10.0+cpu"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    metadata = runtime.get_runtime_metadata()

    assert metadata["executionDevice"] == "cpu"
    assert metadata["cpuFallback"] is True
    assert "CPU" in str(metadata["performanceWarning"])
    assert runtime.get_runtime_metadata() == metadata
    assert len(calls) == 1


def test_voicedesign_runtime_sends_only_generation_request_to_ready_worker(tmp_path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path)
    reference_audio = tmp_path / "ref.wav"
    reference_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    output_wav = tmp_path / "runtime" / "audio" / "clip.wav"
    captured = {}

    def fake_request(payload, timeout_sec):  # noqa: ANN001
        captured["request"] = dict(payload)
        captured["timeout"] = timeout_sec
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        output_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")
        return {
            "ok": True,
            "outputPath": str(output_wav),
            "captionInjectionMode": "separate_target",
            "externalNetworkAttempts": 0,
        }

    monkeypatch.setattr(runtime, "_request_worker", fake_request)
    result = runtime.synthesize(
        SynthesizeRequest(
            text="どうも、ドチタオです",
            caption="自然な配信者の名乗り。短く聞き取りやすい。",
            request_id="req-1",
            model_name="irodori_v3_voicedesign",
            output_basename="clip",
            seed=1001,
            speed_scale=1.25,
            style_strength=4.5,
            reference_audio_path=reference_audio,
        )
    )

    assert captured["request"]["action"] == "synthesize"
    assert captured["request"]["caption"] == "自然な配信者の名乗り。短く聞き取りやすい。"
    assert captured["request"]["referenceAudioPath"] == str(reference_audio)
    assert captured["request"]["durationScale"] == pytest.approx(0.8)
    assert captured["request"]["cfgScaleCaption"] == pytest.approx(4.5)
    assert captured["timeout"] == runtime.timeout_sec
    assert result.audio_path == output_wav.resolve()
    assert result.caption_injection_mode == "separate_target"


def test_voicedesign_runtime_allows_caption_without_reference(tmp_path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path)
    output_wav = tmp_path / "runtime" / "audio" / "caption-only.wav"
    captured = {}

    def fake_request(payload, timeout_sec):  # noqa: ANN001
        del timeout_sec
        captured["request"] = dict(payload)
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        output_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")
        return {
            "ok": True,
            "outputPath": str(output_wav),
            "captionInjectionMode": "separate_target",
            "externalNetworkAttempts": 0,
        }

    monkeypatch.setattr(runtime, "_request_worker", fake_request)
    result = runtime.synthesize(
        SynthesizeRequest(
            text="参照音声なしで生成します。",
            caption="落ち着いた低めの女性の声。",
            request_id="caption-only",
            model_name="irodori_v3_voicedesign",
            output_basename="caption-only",
            seed=1002,
            speed_scale=1.0,
            style_strength=4.0,
        )
    )

    assert captured["request"]["caption"] == "落ち着いた低めの女性の声。"
    assert captured["request"]["referenceAudioPath"] is None
    assert captured["request"]["cfgScaleCaption"] == pytest.approx(4.0)
    assert result.audio_path == output_wav.resolve()


def test_voicedesign_runtime_fails_when_worker_returns_error(tmp_path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path)
    reference_audio = tmp_path / "ref.wav"
    reference_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")

    def fake_request(payload, timeout_sec):  # noqa: ANN001
        del payload, timeout_sec
        raise ProviderError("caption target missing")

    monkeypatch.setattr(runtime, "_request_worker", fake_request)

    with pytest.raises(ProviderError) as exc:
        runtime.synthesize(
            SynthesizeRequest(
                text="AIドチタオです",
                caption="落ち着いた低めのトーン",
                request_id="req-2",
                model_name="irodori_v3_voicedesign",
                output_basename="clip2",
                reference_audio_path=reference_audio,
            )
        )

    assert "VoiceDesign runtime failed" in str(exc.value)
    assert "caption target missing" in str(exc.value)


def test_irodori_direct_runtime_uses_model_specific_repo_local_checkpoint(tmp_path, monkeypatch) -> None:
    python_exe = tmp_path / "runtime" / "venv-irodori" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True, exist_ok=True)
    python_exe.write_bytes(b"")
    wrapper_dir = tmp_path / "runtime" / "vendor" / "Irodori-TTS-upstream"
    (wrapper_dir / "irodori_tts").mkdir(parents=True, exist_ok=True)
    helper_script = tmp_path / "scripts" / "run_irodori_voicedesign.py"
    helper_script.parent.mkdir(parents=True, exist_ok=True)
    helper_script.write_text("print('stub')", encoding="utf-8")
    checkpoint = tmp_path / "runtime" / "models" / "irodori" / "Irodori-TTS-500M-v3" / "model.safetensors"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"model")
    codec_dir = tmp_path / "runtime" / "models" / "irodori" / "Semantic-DACVAE-Japanese-32dim"
    codec_dir.mkdir(parents=True, exist_ok=True)
    processor_dir = tmp_path / "runtime" / "models" / "irodori" / "tokenizers" / "llm-jp-3-150m"
    processor_dir.mkdir(parents=True, exist_ok=True)
    (processor_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    (processor_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

    runtime = IrodoriVoiceDesignDirectRuntime(
        output_dir=tmp_path / "runtime" / "audio",
        models={
            "irodori_v3": ModelConfig(
                runtime="irodori_voicedesign_direct",
                model_id="Aratako/Irodori-TTS-500M-v3",
                checkpoint=Path("./runtime/models/irodori/Irodori-TTS-500M-v3/model.safetensors"),
                requires_reference_audio=False,
                supports_seed=True,
                supports_speed_control=True,
                supports_reference_voice=True,
            )
        },
        root_dir=tmp_path,
        python_executable="./runtime/venv-irodori/Scripts/python.exe",
        wrapper_dir=Path("./runtime/vendor/Irodori-TTS-upstream"),
        checkpoint="",
        codec_repo="./runtime/models/irodori/Semantic-DACVAE-Japanese-32dim",
        text_processor_dir=str(processor_dir),
        model_device="cpu",
        model_precision="fp32",
        codec_device="cpu",
        codec_precision="fp32",
    )
    runtime._worker = _LiveWorker()  # type: ignore[assignment]
    runtime._prepared_models.add("irodori_v3")
    reference_audio = tmp_path / "ref.wav"
    reference_audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    output_wav = tmp_path / "runtime" / "audio" / "base.wav"
    captured = {}

    def fake_request(payload, timeout_sec):  # noqa: ANN001
        del timeout_sec
        captured["request"] = dict(payload)
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        output_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEdata")
        return {
            "ok": True,
            "outputPath": str(output_wav),
            "captionInjectionMode": "none",
            "externalNetworkAttempts": 0,
        }

    monkeypatch.setattr(runtime, "_request_worker", fake_request)
    result = runtime.synthesize(
        SynthesizeRequest(
            text="通常版Irodoriの直接実行を確認します。",
            request_id="base-direct",
            model_name="irodori_v3",
            output_basename="base",
            seed=1,
            speed_scale=0.9,
            reference_audio_path=reference_audio,
        )
    )

    assert captured["request"]["action"] == "synthesize"
    assert Path(captured["request"]["checkpoint"]) == checkpoint.resolve()
    assert Path(captured["request"]["wrapperDir"]) == wrapper_dir.resolve()
    assert Path(captured["request"]["codecRepo"]) == codec_dir.resolve()
    assert captured["request"]["durationScale"] == pytest.approx(1 / 0.9)
    assert result.audio_path == output_wav.resolve()


def test_generation_does_not_reload_after_worker_exit(tmp_path, monkeypatch) -> None:
    runtime = _build_runtime(tmp_path)
    runtime._worker = _DeadWorker()  # type: ignore[assignment]
    requests: list[dict[str, object]] = []

    def fake_request(payload, timeout_sec):  # noqa: ANN001
        del timeout_sec
        requests.append(dict(payload))
        return {"ok": True, "externalNetworkAttempts": 0}

    monkeypatch.setattr(runtime, "_request_worker", fake_request)

    with pytest.raises(ProviderError, match="サービスを再起動"):
        runtime.synthesize(
            SynthesizeRequest(
                text="worker停止後の生成です。",
                request_id="dead-worker",
                model_name="irodori_v3_voicedesign",
                output_basename="dead-worker",
            )
        )

    assert requests == []
    assert "irodori_v3_voicedesign" not in runtime._prepared_models


def test_irodori_direct_runtime_reports_missing_repo_local_install(tmp_path) -> None:
    model = ModelConfig(
        runtime="irodori_voicedesign_direct",
        model_id="Aratako/Irodori-TTS-500M-v3",
        checkpoint=Path("./runtime/models/irodori/Irodori-TTS-500M-v3/model.safetensors"),
    )
    runtime = IrodoriVoiceDesignDirectRuntime(
        output_dir=tmp_path / "runtime" / "audio",
        models={"irodori_v3": model},
        root_dir=tmp_path,
        python_executable="./runtime/venv-irodori/Scripts/python.exe",
        wrapper_dir=Path("./runtime/vendor/Irodori-TTS-upstream"),
        checkpoint="",
        codec_repo="./runtime/models/irodori/Semantic-DACVAE-Japanese-32dim",
    )

    availability = runtime.get_static_model_availability("irodori_v3", model)

    assert availability.available is False
    assert "Tokenizer" in str(availability.reason)
    assert "runtime/models/irodori/tokenizers/llm-jp-3-150m" in str(availability.reason)


def test_irodori_helper_falls_back_to_cpu_and_fp32_without_cuda(monkeypatch) -> None:
    helper = Path(__file__).parents[1] / "scripts" / "run_irodori_voicedesign.py"
    spec = importlib.util.spec_from_file_location("local_tts_irodori_helper", helper)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(module.torch.cuda, "is_available", lambda: False)

    assert module._resolve_runtime_device("cuda") == "cpu"
    assert module._resolve_runtime_device("auto") == "cpu"
    assert module._resolve_runtime_precision("bf16", "cpu") == "fp32"
    assert module._resolve_runtime_precision("auto", "cpu") == "fp32"


def test_irodori_helper_imports_dataclass_fields_used_by_config_patch() -> None:
    helper = Path(__file__).parents[1] / "scripts" / "run_irodori_voicedesign.py"
    source = helper.read_text(encoding="utf-8")

    assert "from dataclasses import fields" in source
    assert "fields(original_cls)" in source
    assert "_patch_model_constructor_precision" in source
    assert "torch.set_default_dtype(target_dtype)" in source
    assert "_patch_safetensors_load_device" in source
    assert "device=str(resolved_device)" in source
    assert "_resolve_runtime_device" in source
    assert "torch.cuda.is_available()" in source
    assert "_resolve_runtime_precision" in source
    assert 'return "fp32"' in source
    assert "hf_hub_download" not in source
    assert "local_files_only=True" in source
    assert "_install_external_network_guard" in source
    assert '"HF_HUB_OFFLINE"' in source
    assert 'action == "preload"' in source
    assert 'action == "synthesize"' in source
