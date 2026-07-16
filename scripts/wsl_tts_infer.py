from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Callable
import wave

SUPPORTED_MODELS = {
    "sarashina2_2_tts",
    "fireredtts2",
    "t5gemma_tts_2b_2b",
    "fish_s1_mini",
}


@dataclass(frozen=True)
class WslTtsRequest:
    model: str
    model_id: str
    text: str
    reference_audio_path: Path
    reference_text_path: Path
    reference_text: str
    output_path: Path
    seed: int | None
    language: str
    speed_scale: float | None = None


def _required_text(payload: dict[str, object], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def load_request(request_json: Path) -> WslTtsRequest:
    payload = json.loads(request_json.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("request JSON must be an object")

    model = _required_text(payload, "model")
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"unsupported WSL TTS model: {model}")

    reference_audio_path = Path(_required_text(payload, "referenceAudioPath")).expanduser()
    if not reference_audio_path.is_file():
        raise FileNotFoundError(f"reference audio not found: {reference_audio_path}")

    reference_text_path = Path(_required_text(payload, "referenceTextPath")).expanduser()
    if not reference_text_path.is_file():
        raise FileNotFoundError(f"reference text not found: {reference_text_path}")
    reference_text = reference_text_path.read_text(encoding="utf-8-sig").strip()
    if not reference_text:
        raise ValueError(f"reference text is empty: {reference_text_path}")

    output_path = Path(_required_text(payload, "outputPath")).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_seed = payload.get("seed")
    seed = int(raw_seed) if raw_seed is not None and str(raw_seed).strip() else None
    raw_speed_scale = payload.get("speedScale")
    speed_scale = float(raw_speed_scale) if raw_speed_scale is not None and str(raw_speed_scale).strip() else None
    return WslTtsRequest(
        model=model,
        model_id=str(payload.get("modelId") or "").strip(),
        text=_required_text(payload, "text"),
        reference_audio_path=reference_audio_path,
        reference_text_path=reference_text_path,
        reference_text=reference_text,
        output_path=output_path,
        seed=seed,
        speed_scale=speed_scale,
        language=str(payload.get("language") or "ja").strip() or "ja",
    )


def _base_dir() -> Path:
    return Path(os.environ.get("LOCAL_TTS_WSL_HOME", "~/.local/share/local-tts-service")).expanduser()


def _model_dir(key: str) -> Path:
    name = f"LOCAL_TTS_{key.upper()}_MODEL_DIR"
    return Path(os.environ.get(name, _base_dir() / "models" / key)).expanduser()


def _vendor_dir(key: str) -> Path:
    name = f"LOCAL_TTS_{key.upper()}_VENDOR_DIR"
    return Path(os.environ.get(name, _base_dir() / "vendors" / key)).expanduser()


def _run(command: list[str], *, cwd: Path, label: str) -> None:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}: {details}")


def _copy_generated_wav(directory: Path, output_path: Path, *, exclude: set[Path] | None = None) -> None:
    excluded = {item.resolve() for item in (exclude or set())}
    candidates = [
        item
        for item in directory.rglob("*.wav")
        if item.is_file() and item.resolve() not in excluded and item.stat().st_size > 44
    ]
    if not candidates:
        raise RuntimeError(f"inference did not create a WAV under {directory}")
    source = max(candidates, key=lambda item: item.stat().st_mtime_ns)
    shutil.copy2(source, output_path)
