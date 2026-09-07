from __future__ import annotations

from local_tts_service.config import load_config


def test_irodori_v4_1_models_are_builtin_defaults(tmp_path):
    config = load_config(tmp_path)

    assert config.models["irodori_v4_1_small"].label == "Irodori v4.1 Small"
    assert config.models["irodori_v4_1_small"].model_id == "Aratako/Irodori-TTS-v4.1-Small"
    assert config.models["irodori_v4_1_anime"].label == "Irodori v4.1 Anime"
    assert config.models["irodori_v4_1_anime"].model_id == "phasefield-audio/Irodori-TTS-v4.1-Anime"
