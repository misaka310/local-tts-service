from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import wave


def get_iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_wav_duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        frame_rate = wav_file.getframerate()
        if frame_rate <= 0:
            raise ValueError(f"invalid WAV frame rate: {frame_rate}")
        return round(wav_file.getnframes() / frame_rate, 6)
