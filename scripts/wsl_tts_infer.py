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
    "orpheus_3b_asmr",
    "ming_omni_tts_0_5b",
}

REFERENCE_REQUIRED_MODELS = SUPPORTED_MODELS - {"orpheus_3b_asmr", "ming_omni_tts_0_5b"}


@dataclass(frozen=True)
class WslTtsRequest:
    model: str
    model_id: str
    text: str
    reference_audio_path: Path | None
    reference_text_path: Path | None
    reference_text: str | None
    output_path: Path
    seed: int | None
    language: str
    speed_scale: float | None = None
    instruction: str | None = None


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

    reference_audio_path: Path | None = None
    reference_text_path: Path | None = None
    reference_text: str | None = None
    reference_audio_raw = str(payload.get("referenceAudioPath") or "").strip()
    reference_text_raw = str(payload.get("referenceTextPath") or "").strip()
    if model in REFERENCE_REQUIRED_MODELS and (not reference_audio_raw or not reference_text_raw):
        raise ValueError(f"referenceAudioPath and referenceTextPath are required for model: {model}")
    if reference_audio_raw or reference_text_raw:
        if not reference_audio_raw or not reference_text_raw:
            raise ValueError("referenceAudioPath and referenceTextPath must be supplied together")
        reference_audio_path = Path(reference_audio_raw).expanduser()
        if not reference_audio_path.is_file():
            raise FileNotFoundError(f"reference audio not found: {reference_audio_path}")
        reference_text_path = Path(reference_text_raw).expanduser()
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
        language=str(
            payload.get("language")
            or ("en" if model == "orpheus_3b_asmr" else "zh" if model == "ming_omni_tts_0_5b" else "ja")
        ).strip(),
        instruction=str(payload.get("instruction") or "").strip() or None,
    )


REFERENCE_PROMPT_MIN_DURATION_SEC = 3.0
REFERENCE_PROMPT_MAX_DURATION_SEC = 10.0


def _wav_duration_sec(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            frame_rate = wav.getframerate()
            if frame_rate <= 0:
                raise ValueError(f"reference WAV has invalid sample rate: {path}")
            return wav.getnframes() / float(frame_rate)
    except (EOFError, wave.Error) as exc:
        raise ValueError(f"reference audio is not a readable PCM WAV: {path}: {exc}") from exc


def resolve_reference_prompt(request: WslTtsRequest) -> WslTtsRequest:
    """Use an aligned short companion when a selected voice contains a long prompt.

    The comparison UI may select a long Irodori reference profile. The WSL zero-shot
    engines expect a short prompt, so each long profile can provide voice_short.wav
    and voice_short.txt without changing the user-visible voice ID.
    """

    if request.reference_audio_path is None or request.reference_text_path is None:
        return request

    duration = _wav_duration_sec(request.reference_audio_path)
    if duration <= REFERENCE_PROMPT_MAX_DURATION_SEC:
        return request

    short_audio = request.reference_audio_path.with_name("voice_short.wav")
    short_text_path = request.reference_text_path.with_name("voice_short.txt")
    if not short_audio.is_file() or not short_text_path.is_file():
        raise ValueError(
            f"{request.model} requires a {REFERENCE_PROMPT_MIN_DURATION_SEC:.0f}-"
            f"{REFERENCE_PROMPT_MAX_DURATION_SEC:.0f} second reference prompt. "
            f"The selected reference is {duration:.2f} seconds and has no aligned "
            f"voice_short.wav / voice_short.txt companion: {request.reference_audio_path.parent}"
        )

    short_duration = _wav_duration_sec(short_audio)
    if not REFERENCE_PROMPT_MIN_DURATION_SEC <= short_duration <= REFERENCE_PROMPT_MAX_DURATION_SEC:
        raise ValueError(
            f"short reference must be {REFERENCE_PROMPT_MIN_DURATION_SEC:.0f}-"
            f"{REFERENCE_PROMPT_MAX_DURATION_SEC:.0f} seconds: "
            f"{short_audio} is {short_duration:.2f} seconds"
        )
    short_text = short_text_path.read_text(encoding="utf-8-sig").strip()
    if not short_text:
        raise ValueError(f"short reference text is empty: {short_text_path}")

    print(
        f"[INFO] {request.model}: using aligned short reference "
        f"{short_audio} ({short_duration:.2f}s) instead of {duration:.2f}s source",
        file=sys.stderr,
        flush=True,
    )
    return replace(
        request,
        reference_audio_path=short_audio,
        reference_text_path=short_text_path,
        reference_text=short_text,
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
