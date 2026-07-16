from __future__ import annotations

MODEL_ENV_KEYS: dict[str, str] = {
    "sarashina2_2_tts": "sarashina",
    "fireredtts2": "fireredtts2",
    "t5gemma_tts_2b_2b": "t5gemma",
    "fish_s1_mini": "fish_s1_mini",
}


def environment_key_for_model(model_name: str) -> str:
    normalized = str(model_name or "").strip()
    try:
        return MODEL_ENV_KEYS[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported WSL TTS model: {normalized or '<empty>'}") from exc
