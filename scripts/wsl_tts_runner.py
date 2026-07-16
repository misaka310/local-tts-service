from __future__ import annotations

from pathlib import Path
from typing import Callable
import wave

from scripts.wsl_fish_s1_adapter import generate_fish_s1
from scripts.wsl_tts_adapters import generate_firered, generate_sarashina, generate_t5gemma
from scripts.wsl_tts_infer import WslTtsRequest

GENERATORS: dict[str, Callable[[WslTtsRequest], None]] = {
    "sarashina2_2_tts": generate_sarashina,
    "fireredtts2": generate_firered,
    "t5gemma_tts_2b_2b": generate_t5gemma,
    "fish_s1_mini": generate_fish_s1,
}


def validate_output(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 44:
        raise RuntimeError(f"generated WAV is missing or empty: {path}")
    with path.open("rb") as fp:
        header = fp.read(12)
    if len(header) != 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise RuntimeError(f"generated file is not RIFF/WAVE: {path}")
    with wave.open(str(path), "rb") as wav:
        if wav.getnframes() <= 0 or wav.getframerate() <= 0:
            raise RuntimeError(f"generated WAV has no audio frames: {path}")
