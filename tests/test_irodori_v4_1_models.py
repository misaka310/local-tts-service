from __future__ import annotations

from pathlib import Path

from local_tts_service.config import DEFAULT_CONFIG


def test_irodori_v4_1_base_and_anime_models_are_registered() -> None:
    models = DEFAULT_CONFIG["models"]

    base = models["irodori_v4_small"]
    anime = models["irodori_v4_1_anime"]

    assert base["label"] == "Irodori v4.1 Small"
    assert base["modelId"] == "Aratako/Irodori-TTS-v4.1-Small"
    assert base["checkpoint"] == "./runtime/models/irodori/Irodori-TTS-v4.1-Small/model.safetensors"

    assert anime["label"] == "Irodori v4.1 Anime"
    assert anime["modelId"] == "phasefield-audio/Irodori-TTS-v4.1-Anime"
    assert anime["checkpoint"] == "./runtime/models/irodori/Irodori-TTS-v4.1-Anime/model.safetensors"
    assert anime["runtime"] == "irodori_voicedesign_direct"
    assert anime["supportsReferenceVoice"] is True
    assert anime["supportsCaption"] is True
    assert anime["supportsInstruction"] is True
    assert anime["supportsStyleStrength"] is True
    assert anime["supportsVoiceDesign"] is True
    assert anime["supportsSpeedControl"] is True


def test_irodori_setup_downloads_v4_1_base_and_anime_models() -> None:
    setup_script = Path("scripts/setup-irodori.ps1").read_text(encoding="utf-8-sig")

    assert "Aratako/Irodori-TTS-v4.1-Small" in setup_script
    assert "phasefield-audio/Irodori-TTS-v4.1-Anime" in setup_script
    assert "Irodori-TTS-v4-Small" not in setup_script
