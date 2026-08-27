from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_local_tts_does_not_own_voice_buttons_product_contract() -> None:
    forbidden = (
        REPO / "config/voice-buttons-phrases.json",
        REPO / "docs/voice-buttons.md",
        REPO / "scripts/generate_voiceboard_audio.py",
        REPO / "tests/test_voiceboard_generation.py",
    )
    assert all(not path.exists() for path in forbidden)

    architecture = (REPO / "docs/architecture.md").read_text(encoding="utf-8")
    assert "Voice Buttons固有の40本" in architecture
    assert "Voice Buttons Site" in architecture
