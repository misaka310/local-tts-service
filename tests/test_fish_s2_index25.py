from __future__ import annotations

import json
from pathlib import Path

import pytest

from local_tts_service.config import load_config
from scripts.wsl_tts_bridge import environment_key_for_model
from scripts.wsl_tts_infer import load_request
from scripts.wsl_tts_runner import GENERATORS


@pytest.mark.parametrize("name,model_id,requires_text", [
    ("fish_s2_pro", "fishaudio/s2-pro", True),
    ("indextts_2_5", "IndexTeam/IndexTTS-2.5", False),
])
def test_models_have_real_external_routes(name: str, model_id: str, requires_text: bool) -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root)
    model = config.models[name]
    assert model.runtime == "external_cli"
    assert model.model_id == model_id
    assert model.requires_reference_audio is True
    assert model.requires_reference_text is requires_text
    assert model.external_command_key == name
    assert environment_key_for_model(name) == name
    assert name in GENERATORS
    external = config.runtimes["external_cli"]
    assert name in external["commands"]
    assert name in external["availabilityCommands"]


@pytest.mark.parametrize("name,transcript_required", [
    ("fish_s2_pro", True),
    ("indextts_2_5", False),
])
def test_reference_request_contract(tmp_path: Path, name: str, transcript_required: bool) -> None:
    wav = tmp_path / "voice.wav"
    wav.write_bytes(b"RIFF____WAVE")
    transcript = tmp_path / "voice.txt"
    transcript.write_text("参照の台詞。", encoding="utf-8")
    payload = {
        "model": name, "text": "今日は良い天気です。",
        "referenceAudioPath": str(wav), "outputPath": str(tmp_path / "result.wav"),
    }
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if transcript_required:
        with pytest.raises(ValueError, match="referenceAudioPath and referenceTextPath"):
            load_request(request_file)
        payload["referenceTextPath"] = str(transcript)
        request_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    request = load_request(request_file)
    assert request.model == name
    assert request.reference_audio_path == wav
    assert request.reference_text == ("参照の台詞。" if transcript_required else None)


def test_indextts_requires_audio_even_without_transcript(tmp_path: Path) -> None:
    file = tmp_path / "request.json"
    file.write_text(json.dumps({"model": "indextts_2_5", "text": "テスト",
                                 "outputPath": str(tmp_path / "out.wav")}), encoding="utf-8")
    with pytest.raises(ValueError, match="referenceAudioPath"):
        load_request(file)
