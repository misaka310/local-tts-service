from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import wave

import pytest

from local_tts_service.config import load_config
from local_tts_service.models import ModelConfig
from local_tts_service.runtimes import external_cli
from local_tts_service.runtimes.external_cli import ExternalCliRuntime


ROOT = Path(__file__).resolve().parent.parent

EXPECTED_MODELS = {
    "sarashina2_2_tts": ("sbintuitions/sarashina2.2-tts", "sarashina"),
    "fireredtts2": ("FireRedTeam/FireRedTTS2", "fireredtts2"),
    "t5gemma_tts_2b_2b": ("Aratako/T5Gemma-TTS-2b-2b", "t5gemma"),
    "fish_s1_mini": ("fishaudio/s1-mini", "fish_s1_mini"),
}


def test_wsl_zero_shot_models_are_registered_with_reference_contract() -> None:
    config = load_config(ROOT)

    for model_name, (model_id, command_key) in EXPECTED_MODELS.items():
        model = config.models[model_name]
        assert model.runtime == "external_cli"
        assert model.model_id == model_id
        assert model.external_command_key == command_key
        assert model.requires_reference_audio is True
        assert model.requires_reference_text is True
        assert model.supports_reference_voice is True
        assert model.supports_voice_clone is True
        assert model.supports_language is True
        assert model.default_language in {"ja", "Japanese"}

    commands = config.runtimes["external_cli"]["commands"]
    for _, command_key in EXPECTED_MODELS.values():
        command = commands[command_key]
        assert command[:3] == ["powershell", "-NoProfile", "-File"]
        assert "./scripts/run-wsl-tts.ps1" in command
        assert "{request_json}" in command
        assert "{output_path}" in command


def test_wsl_bridge_maps_only_supported_models() -> None:
    from scripts.wsl_tts_bridge import environment_key_for_model

    assert environment_key_for_model("sarashina2_2_tts") == "sarashina"
    assert environment_key_for_model("fireredtts2") == "fireredtts2"
    assert environment_key_for_model("t5gemma_tts_2b_2b") == "t5gemma"
    assert environment_key_for_model("fish_s1_mini") == "fish_s1_mini"

    with pytest.raises(ValueError, match="unsupported WSL TTS model"):
        environment_key_for_model("unknown")


def test_wsl_infer_validates_request_before_loading_heavy_dependencies(tmp_path: Path) -> None:
    from scripts.wsl_tts_infer import load_request

    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "model": "sarashina2_2_tts",
                "text": "これはテストです。",
                "referenceAudioPath": str(tmp_path / "missing.wav"),
                "referenceTextPath": str(tmp_path / "missing.txt"),
                "outputPath": str(tmp_path / "out.wav"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="reference audio"):
        load_request(request_path)


def test_wsl_infer_accepts_complete_request(tmp_path: Path) -> None:
    from scripts.wsl_tts_infer import load_request

    audio_path = tmp_path / "voice.wav"
    text_path = tmp_path / "voice.txt"
    audio_path.write_bytes(b"RIFF0000WAVE")
    text_path.write_text("参照音声です。", encoding="utf-8")
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "model": "fish_s1_mini",
                "modelId": "fishaudio/s1-mini",
                "text": "これはテストです。",
                "referenceAudioPath": str(audio_path),
                "referenceTextPath": str(text_path),
                "outputPath": str(tmp_path / "out.wav"),
                "seed": 123,
                "language": "ja",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    request = load_request(request_path)
    assert request.model == "fish_s1_mini"
    assert request.text == "これはテストです。"
    assert request.reference_text == "参照音声です。"
    assert request.seed == 123
    assert request.output_path == tmp_path / "out.wav"


def _write_pcm16_wav(path: Path, *, duration_sec: float, sample_rate: int = 16000) -> None:
    frame_count = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frame_count)


def test_wsl_infer_uses_short_companion_for_long_reference(tmp_path: Path) -> None:
    from scripts.wsl_tts_infer import WslTtsRequest, resolve_reference_prompt

    voice_dir = tmp_path / "voice"
    voice_dir.mkdir()
    long_audio = voice_dir / "voice.wav"
    long_text = voice_dir / "voice.txt"
    short_audio = voice_dir / "voice_short.wav"
    short_text = voice_dir / "voice_short.txt"
    _write_pcm16_wav(long_audio, duration_sec=60.0)
    _write_pcm16_wav(short_audio, duration_sec=8.0)
    long_text.write_text("長い参照文です。", encoding="utf-8")
    short_text.write_text("短い参照文です。", encoding="utf-8")
    request = WslTtsRequest(
        model="sarashina2_2_tts",
        model_id="sbintuitions/sarashina2.2-tts",
        text="生成対象です。",
        reference_audio_path=long_audio,
        reference_text_path=long_text,
        reference_text="長い参照文です。",
        output_path=tmp_path / "out.wav",
        seed=1,
        language="ja",
    )

    resolved = resolve_reference_prompt(request)

    assert resolved.reference_audio_path == short_audio
    assert resolved.reference_text_path == short_text
    assert resolved.reference_text == "短い参照文です。"


def test_wsl_infer_keeps_supported_short_reference(tmp_path: Path) -> None:
    from scripts.wsl_tts_infer import WslTtsRequest, resolve_reference_prompt

    audio = tmp_path / "voice.wav"
    text = tmp_path / "voice.txt"
    _write_pcm16_wav(audio, duration_sec=8.0)
    text.write_text("参照文です。", encoding="utf-8")
    request = WslTtsRequest(
        model="fireredtts2",
        model_id="FireRedTeam/FireRedTTS2",
        text="生成対象です。",
        reference_audio_path=audio,
        reference_text_path=text,
        reference_text="参照文です。",
        output_path=tmp_path / "out.wav",
        seed=1,
        language="ja",
    )

    assert resolve_reference_prompt(request) == request


def test_wsl_infer_rejects_long_reference_without_short_companion(tmp_path: Path) -> None:
    from scripts.wsl_tts_infer import WslTtsRequest, resolve_reference_prompt

    audio = tmp_path / "voice.wav"
    text = tmp_path / "voice.txt"
    _write_pcm16_wav(audio, duration_sec=60.0)
    text.write_text("長い参照文です。", encoding="utf-8")
    request = WslTtsRequest(
        model="fish_s1_mini",
        model_id="fishaudio/s1-mini",
        text="生成対象です。",
        reference_audio_path=audio,
        reference_text_path=text,
        reference_text="長い参照文です。",
        output_path=tmp_path / "out.wav",
        seed=1,
        language="ja",
    )

    with pytest.raises(ValueError, match="voice_short.wav"):
        resolve_reference_prompt(request)


def test_wsl_models_register_real_environment_availability_commands() -> None:
    config = load_config(ROOT)
    availability_commands = config.runtimes["external_cli"]["availabilityCommands"]

    for model_name, (_, command_key) in EXPECTED_MODELS.items():
        command = availability_commands[command_key]
        assert command[:3] == ["powershell", "-NoProfile", "-File"]
        assert "./scripts/check-wsl-tts.ps1" in command
        assert model_name in command


def test_external_cli_availability_probe_surfaces_environment_failure(tmp_path: Path) -> None:
    runtime = ExternalCliRuntime(
        output_dir=tmp_path / "audio",
        models={},
        root_dir=tmp_path,
        request_dir=tmp_path / "requests",
        commands={"wsl_model": [sys.executable, "-c", "print('run')"]},
        availability_commands={
            "wsl_model": [
                sys.executable,
                "-c",
                "import sys; print('WSLモデル環境が未導入です', file=sys.stderr); raise SystemExit(7)",
            ]
        },
    )
    model = ModelConfig(runtime="external_cli", external_command_key="wsl_model")

    availability = runtime.get_model_availability("wsl_model", model)

    assert availability.available is False
    assert availability.reason is not None
    assert "WSLモデル環境が未導入です" in availability.reason


def test_external_cli_timeout_terminates_the_started_process_tree(monkeypatch) -> None:
    terminated: list[object] = []

    class FakeProcess:
        pid = 4321
        returncode = -1

        def communicate(self, timeout=None):  # noqa: ANN001
            if timeout is not None:
                raise subprocess.TimeoutExpired(["fake"], timeout)
            return "", ""

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        external_cli,
        "_terminate_process_tree",
        lambda process: terminated.append(process),
    )

    with pytest.raises(subprocess.TimeoutExpired):
        external_cli._run_external_command(
            ["fake"],
            cwd=Path.cwd(),
            timeout=0.01,
        )

    assert len(terminated) == 1


def test_wsl_t5gemma_setup_and_availability_include_dependency_cache_checks() -> None:
    setup_source = (ROOT / "scripts" / "setup_wsl_tts_models.sh").read_text(encoding="utf-8")
    check_source = (ROOT / "scripts" / "check_wsl_tts.sh").read_text(encoding="utf-8")

    assert "cache_t5gemma_dependencies" in setup_source
    assert "--check-cache" in check_source
    assert "t5gemma_offline_infer.py" in check_source
