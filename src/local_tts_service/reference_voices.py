from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import wave

from .models import normalize_voice_id

VOICE_ID_ALIASES = {
    "sample_panicked": "sample_angry",
    "pani_doti": "sample_angry",
    "oko_doti": "sample_angry",
}

MIN_REFERENCE_AUDIO_SEC = 3.0
MAX_REFERENCE_AUDIO_SEC = 10.0


def gpt_sovits_duration_error(duration_sec: float | None) -> str | None:
    if duration_sec is None:
        return "voice.wav の長さを確認できません"
    if duration_sec < MIN_REFERENCE_AUDIO_SEC:
        return f"voice.wav が短すぎます: {duration_sec:.2f}秒。{MIN_REFERENCE_AUDIO_SEC:.0f}〜{MAX_REFERENCE_AUDIO_SEC:.0f}秒にしてください"
    if duration_sec > MAX_REFERENCE_AUDIO_SEC:
        return f"voice.wav が長すぎます: {duration_sec:.2f}秒。{MIN_REFERENCE_AUDIO_SEC:.0f}〜{MAX_REFERENCE_AUDIO_SEC:.0f}秒にしてください"
    return None


def _read_wav_duration_sec(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav:
            frame_rate = wav.getframerate()
            if frame_rate <= 0:
                return None
            return wav.getnframes() / float(frame_rate)
    except (OSError, EOFError, wave.Error):
        return None


def _resolve_reference_text_path(directory: Path) -> tuple[Path, bool]:
    preferred = directory / "voice.txt"
    legacy = directory / "text.txt"
    if preferred.is_file():
        return preferred, True
    if legacy.is_file():
        return legacy, True
    return preferred, False


@dataclass(frozen=True)
class ReferenceVoice:
    voice_id: str
    display_name: str
    directory: Path
    audio_path: Path
    text_path: Path
    has_reference_audio: bool
    has_reference_text: bool
    enabled: bool
    duration_sec: float | None = None
    min_duration_sec: float = MIN_REFERENCE_AUDIO_SEC
    max_duration_sec: float = MAX_REFERENCE_AUDIO_SEC
    error_reason: str | None = None


def scan_reference_voices(root_dir: Path, *, require_reference_text: bool = False) -> list[ReferenceVoice]:
    if not root_dir.exists() or not root_dir.is_dir():
        return []

    found: list[ReferenceVoice] = []
    for child in sorted(root_dir.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        if child.name.startswith("_archive"):
            continue
        voice_id = child.name.strip()
        if not voice_id:
            continue
        canonical_voice_id = VOICE_ID_ALIASES.get(voice_id, voice_id)
        if canonical_voice_id != voice_id and (root_dir / canonical_voice_id).is_dir():
            continue
        audio_path = child / "voice.wav"
        text_path, has_text = _resolve_reference_text_path(child)
        has_audio = audio_path.is_file()
        duration_sec = _read_wav_duration_sec(audio_path) if has_audio else None
        enabled = has_audio
        error_reason = None
        try:
            normalize_voice_id(canonical_voice_id)
        except ValueError as exc:
            enabled = False
            error_reason = str(exc)
        if enabled and require_reference_text and not has_text:
            enabled = False
            error_reason = "missing: voice.txt or text.txt"
        if error_reason is None and not enabled:
            error_reason = "missing: voice.wav"
        found.append(
            ReferenceVoice(
                voice_id=canonical_voice_id,
                display_name=canonical_voice_id,
                directory=child,
                audio_path=audio_path,
                text_path=text_path,
                has_reference_audio=has_audio,
                has_reference_text=has_text,
                enabled=enabled,
                duration_sec=duration_sec,
                error_reason=error_reason,
            )
        )
    return found


def find_reference_voice(root_dir: Path, voice_id: str, *, require_reference_text: bool = False) -> ReferenceVoice | None:
    normalized = normalize_voice_id(voice_id)
    if not normalized:
        return None
    normalized = VOICE_ID_ALIASES.get(normalized, normalized)
    for item in scan_reference_voices(root_dir, require_reference_text=require_reference_text):
        if item.voice_id == normalized:
            return item
    return None
