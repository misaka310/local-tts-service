from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
import wave

import pytest

from scripts import qwen3_isolated_runner as runner
from local_tts_service.models import ModelConfig
from local_tts_service.runtimes.base import SynthesizeRequest
from local_tts_service.runtimes.qwen3_tts import Qwen3TTSRuntime


def model() -> ModelConfig:
    return ModelConfig(
        runtime="qwen3_tts", model_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        requires_reference_audio=True, requires_reference_text=True, supports_voice_clone=True,
    )


def make_runtime(tmp_path: Path) -> Qwen3TTSRuntime:
    python = tmp_path / "rocm" / "python.exe"
    python.parent.mkdir()
    python.touch()
    model_dir = tmp_path / "Qwen__Qwen3-TTS-12Hz-1.7B-Base"
    model_dir.mkdir()
    return Qwen3TTSRuntime(
        output_dir=tmp_path / "audio", models={"qwen3_tts_clone_1_7b": model()},
        vendor_dir=tmp_path, isolated_python_executable=python,
    )


def test_rocm_probe_never_accepts_cuda_without_hip(monkeypatch) -> None:
    import sys
    fake = SimpleNamespace(
        version=SimpleNamespace(hip=None), __version__="test+cu128",
        cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1, get_device_name=lambda i: "NVIDIA"),
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    monkeypatch.setattr(runner.importlib.util, "find_spec", lambda package: object())
    status = runner.rocm_status()
    assert not status["ok"]
    assert status["backend"] == "other"
    assert not status["gpuAvailable"]


def test_rocm_probe_requires_actual_gpu_and_packages(monkeypatch) -> None:
    import sys
    fake = SimpleNamespace(
        version=SimpleNamespace(hip="7.2"), __version__="test+rocm",
        cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1, get_device_name=lambda i: "AMD Radeon"),
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    monkeypatch.setattr(runner.importlib.util, "find_spec", lambda package: object())
    status = runner.rocm_status()
    assert status["ok"]
    assert status["backend"] == "rocm"
    assert status["gpuName"] == "AMD Radeon"


def test_availability_uses_isolated_worker_not_service_dependencies(tmp_path, monkeypatch) -> None:
    runtime = make_runtime(tmp_path)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, stdout=json.dumps({"ok": True, "backend": "rocm", "gpuAvailable": True}), stderr="")

    monkeypatch.setattr("local_tts_service.runtimes.qwen3_tts.subprocess.run", fake_run)
    monkeypatch.setattr(runtime, "_has_dependency", lambda _: (_ for _ in ()).throw(AssertionError("must use isolated environment")))
    first = runtime.get_model_availability("qwen3_tts_clone_1_7b", model())
    second = runtime.get_model_availability("qwen3_tts_clone_1_7b", model())
    assert first.available and second.available
    assert len(calls) == 1
    assert runtime.get_runtime_metadata()["executionDevice"] == "AMD ROCm GPU"


def test_unavailable_rocm_does_not_silently_use_cpu(tmp_path, monkeypatch) -> None:
    runtime = make_runtime(tmp_path)
    monkeypatch.setattr(
        "local_tts_service.runtimes.qwen3_tts.subprocess.run",
        lambda cmd, **kwargs: CompletedProcess(cmd, 2, stdout=json.dumps({
            "ok": False, "backend": "other", "reason": "ROCm GPU is unavailable",
        }), stderr=""),
    )
    availability = runtime.get_model_availability("qwen3_tts_clone_1_7b", model())
    assert availability.available is False
    assert "ROCm" in availability.reason
    assert runtime.get_runtime_metadata()["cpuFallback"] is False


def test_isolated_inference_uses_registered_wav_txt_and_output(tmp_path, monkeypatch) -> None:
    runtime = make_runtime(tmp_path)
    monkeypatch.setattr(runtime, "_check_isolated_rocm", lambda: (True, None))
    wav = tmp_path / "voice.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\\0\\0" * 240)
    txt = tmp_path / "voice.txt"
    txt.write_text("こんにちは", encoding="utf-8")
    captured = {}

    def fake_run(command, **kwargs):
        payload = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        captured.update(payload)
        output = Path(payload["outputPath"])
        with wave.open(str(output), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\\0\\0" * 240)
        return CompletedProcess(command, 0, stdout='{"ok":true}', stderr="")

    monkeypatch.setattr("local_tts_service.runtimes.qwen3_tts.subprocess.run", fake_run)
    result = runtime.synthesize(
        SynthesizeRequest(
            text="こんにちは", request_id="rocm-check", model_name="qwen3_tts_clone_1_7b",
            output_basename="rocm-output", reference_audio_path=wav,
            reference_text_path=txt, voice_id="registered", language="Japanese",
        )
    )
    assert result.audio_path.is_file()
    assert captured["referenceAudioPath"] == str(wav)
    assert captured["referenceTextPath"] == str(txt)
    assert captured["language"] == "Japanese"
    assert result.audio_path.stat().st_size > 44


def test_registry_passes_optional_rocm_python_without_changing_default(tmp_path) -> None:
    from local_tts_service.runtime_registry import build_runtime_registry

    config = SimpleNamespace(
        root_dir=tmp_path, audio_output_dir=tmp_path / "audio",
        models={"qwen3_tts_clone_1_7b": model()}, stack={}, external_services={},
        runtimes={"qwen3_tts": {
            "isolatedPythonExecutable": str(tmp_path / "rocm-python.exe"),
            "isolatedTimeoutSec": 123,
        }},
    )
    runtime = build_runtime_registry(config)["qwen3_tts"]
    assert runtime.isolated_python_executable == tmp_path / "rocm-python.exe"
    assert runtime.isolated_timeout_sec == 123
    config.runtimes["qwen3_tts"] = {}
    direct = build_runtime_registry(config)["qwen3_tts"]
    assert direct.isolated_python_executable is None


def test_isolated_inference_rejects_missing_reference(tmp_path, monkeypatch) -> None:
    runtime = make_runtime(tmp_path)
    monkeypatch.setattr(runtime, "_check_isolated_rocm", lambda: (True, None))
    with pytest.raises(Exception, match="voice.wav"):
        runtime.synthesize(SynthesizeRequest(
            text="test", request_id="id", model_name="qwen3_tts_clone_1_7b", output_basename="audio"
        ))
