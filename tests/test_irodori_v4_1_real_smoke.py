from __future__ import annotations

from pathlib import Path


def test_real_smoke_covers_both_irodori_v4_1_models_and_audio_quality() -> None:
    smoke_path = Path("scripts/smoke-irodori-v4-1.ps1")
    assert smoke_path.is_file(), "Irodori v4.1 real-generation smoke script is missing"

    smoke = smoke_path.read_text(encoding="utf-8-sig")
    assert "irodori_v4_1_small" in smoke
    assert "irodori_v4_1_anime" in smoke
    assert "sampleRate -ne 48000" in smoke
    assert "durationSec -lt 0.5" in smoke
    assert "rms -lt 0.0001" in smoke
    assert "RIFF" in smoke
    assert "WAVE" in smoke


def test_clean_install_runs_irodori_v4_1_real_smoke_before_shutdown() -> None:
    workflow = Path(".github/workflows/windows-clean-install.yml").read_text(encoding="utf-8-sig")

    smoke_step = "Run Irodori v4.1 real-generation smoke"
    stop_step = "Stop clean-install services"
    assert smoke_step in workflow
    assert "smoke-irodori-v4-1.ps1" in workflow
    assert workflow.index(smoke_step) < workflow.index(stop_step)
