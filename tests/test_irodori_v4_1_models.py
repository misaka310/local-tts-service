from __future__ import annotations

from pathlib import Path

from local_tts_service.config import load_config


def test_irodori_v4_1_base_and_anime_models_are_registered() -> None:
    models = load_config(Path.cwd()).models

    base = models["irodori_v4_1_small"]
    anime = models["irodori_v4_1_anime"]

    assert base.label == "Irodori v4.1 Small"
    assert base.model_id == "Aratako/Irodori-TTS-v4.1-Small"
    assert base.checkpoint is not None
    assert base.checkpoint.as_posix().endswith(
        "runtime/models/irodori/Irodori-TTS-v4.1-Small/model.safetensors"
    )

    assert anime.label == "Irodori v4.1 Anime"
    assert anime.model_id == "phasefield-audio/Irodori-TTS-v4.1-Anime"
    assert anime.checkpoint is not None
    assert anime.checkpoint.as_posix().endswith(
        "runtime/models/irodori/Irodori-TTS-v4.1-Anime/model.safetensors"
    )
    assert anime.runtime == "irodori_voicedesign_direct"
    assert anime.supports_reference_voice is True
    assert anime.supports_caption is True
    assert anime.supports_instruction is True
    assert anime.supports_style_strength is True
    assert anime.supports_voice_design is True
    assert anime.supports_speed_control is True


def test_irodori_setup_downloads_v4_1_base_and_anime_models() -> None:
    setup_script = Path("scripts/setup-irodori.ps1").read_text(encoding="utf-8-sig")

    assert "Aratako/Irodori-TTS-v4.1-Small" in setup_script
    assert "phasefield-audio/Irodori-TTS-v4.1-Anime" in setup_script
