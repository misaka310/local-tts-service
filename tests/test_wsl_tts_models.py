from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from local_tts_service.config import load_config
from local_tts_service.models import ModelConfig
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
