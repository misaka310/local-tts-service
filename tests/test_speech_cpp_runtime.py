from __future__ import annotations

from pathlib import Path

from local_tts_service.models import ModelConfig
from local_tts_service.runtimes.base import SynthesizeRequest
from local_tts_service.runtimes.speech_cpp import SpeechCppRuntime


def _runtime(tmp_path: Path) -> SpeechCppRuntime:
    executable = tmp_path / "audiocpp_cli.exe"
    executable.write_bytes(b"stub")
    model = tmp_path / "irodori-v3-q8.gguf"
    model.write_bytes(b"gguf")
    models = {
        "irodori_v3_low_latency": ModelConfig(
            runtime="speech_cpp",
            supports_reference_voice=True,
            supports_seed=True,
            supports_speed_control=True,
            default_language="ja",
            runtime_options={"numInferenceSteps": 8},
        )
    }
    return SpeechCppRuntime(
        output_dir=tmp_path / "out",
        models=models,
        root_dir=tmp_path,
        executable=executable,
        model_path=model,
        backend="cuda",
        device=1,
    )


def test_build_command_uses_clone_task_for_reference_voice(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    reference = tmp_path / "voice.wav"
    reference.write_bytes(b"wav")
    request = SynthesizeRequest(
        text="こんにちは",
        request_id="r1",
        model_name="irodori_v3_low_latency",
        output_basename="out-r1",
        seed=1234,
        speed_scale=1.25,
        language="ja",
        reference_audio_path=reference,
    )

    command, output_path = runtime.build_command(request)

    assert command[0].endswith("audiocpp_cli.exe")
    assert command[command.index("--task") + 1] == "clon"
    assert command[command.index("--family") + 1] == "irodori_tts"
    assert command[command.index("--backend") + 1] == "cuda"
    assert command[command.index("--device") + 1] == "1"
    assert command[command.index("--voice-ref") + 1] == str(reference.resolve())
    assert "num_inference_steps=8" in command
    assert "no_ref=false" in command
    assert "duration_scale=0.8" in command
    assert output_path == (tmp_path / "out" / "out-r1.wav").resolve()


def test_build_command_uses_tts_task_without_reference_voice(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    request = SynthesizeRequest(
        text="こんにちは",
        request_id="r2",
        model_name="irodori_v3_low_latency",
        output_basename="out-r2",
        seed=9,
        language="ja",
    )

    command, _ = runtime.build_command(request)

    assert command[command.index("--task") + 1] == "tts"
    assert "--voice-ref" not in command
    assert "no_ref=true" in command


def test_static_availability_reports_missing_binary_or_model(tmp_path: Path) -> None:
    runtime = SpeechCppRuntime(
        output_dir=tmp_path / "out",
        models={"m": ModelConfig(runtime="speech_cpp")},
        root_dir=tmp_path,
        executable=tmp_path / "missing.exe",
        model_path=tmp_path / "missing.gguf",
    )

    availability = runtime.get_model_availability("m", runtime.models["m"])

    assert availability.available is False
    assert "audiocpp_cli" in (availability.reason or "")
    assert "GGUF" in (availability.reason or "")
