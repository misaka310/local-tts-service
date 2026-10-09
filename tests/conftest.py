from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def clear_local_tts_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "LOCAL_TTS_CONFIG_PATH",
        "LOCAL_TTS_HOST",
        "LOCAL_TTS_PORT",
        "LOCAL_TTS_PUBLIC_BASE_URL",
        "LOCAL_TTS_DEFAULT_MODEL",
        "LOCAL_TTS_DEFAULT_REFERENCE_VOICE",
        "LOCAL_TTS_REFERENCE_VOICES_DIR",
        "LOCAL_TTS_AUDIO_OUTPUT_DIR",
        "LOCAL_TTS_COMFYUI_BASE_URL",
        "LOCAL_TTS_COMFYUI_INPUT_DIR",
        "LOCAL_TTS_COMFYUI_OUTPUT_DIR",
        "LOCAL_TTS_COMFYUI_TIMEOUT_SEC",
        "LOCAL_TTS_COMFYUI_POLL_INTERVAL_SEC",
        "LOCAL_TTS_COMFYUI_DEFAULT_AUDIO_EXT",
        "LOCAL_TTS_COMFYUI_AUTO_LAUNCH",
        "LOCAL_TTS_COMFYUI_LAUNCH_BAT_PATH",
        "LOCAL_TTS_COMFYUI_LAUNCH_WORKING_DIR",
        "LOCAL_TTS_COMFYUI_STARTUP_TIMEOUT_SEC",
        "LOCAL_TTS_COMFYUI_STARTUP_POLL_INTERVAL_SEC",
        "LOCAL_TTS_COMFYUI_HEALTH_PATH",
        "LOCAL_TTS_VOXCPM2_BASE_URL",
        "LOCAL_TTS_VOXCPM2_INPUT_DIR",
        "LOCAL_TTS_VOXCPM2_OUTPUT_DIR",
        "LOCAL_TTS_VOXCPM2_TIMEOUT_SEC",
        "LOCAL_TTS_VOXCPM2_POLL_INTERVAL_SEC",
        "LOCAL_TTS_VOXCPM2_DEFAULT_AUDIO_EXT",
    ]:
        monkeypatch.delenv(key, raising=False)
