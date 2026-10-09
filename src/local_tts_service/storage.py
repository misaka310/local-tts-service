from __future__ import annotations

import hashlib
import re
import time
import uuid
import wave
from contextlib import closing
from pathlib import Path

from .errors import NotFoundError, RequestValidationError

_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def safe_request_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = f"req-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in raw).strip("-")
    return safe[:120] or f"req-{uuid.uuid4().hex[:8]}"


def build_output_basename(text: str, request_id: str) -> str:
    digest = sha1_text(text)[:12]
    safe_req = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in request_id).strip("-")
    safe_req = safe_req[:40] or f"req-{uuid.uuid4().hex[:8]}"
    return f"tts-{safe_req}-{digest}"


def ensure_safe_audio_filename(filename: str) -> str:
    raw = str(filename or "").strip()
    if not raw:
        raise RequestValidationError("audio filename is empty")
    if Path(raw).name != raw:
        raise RequestValidationError("invalid audio filename")
    if not _SAFE_FILENAME_RE.fullmatch(raw):
        raise RequestValidationError("invalid audio filename")
    return raw


def resolve_audio_path(audio_dir: Path, filename: str) -> Path:
    safe_name = ensure_safe_audio_filename(filename)
    path = (audio_dir / safe_name).resolve()
    if not path.is_file():
        raise NotFoundError("audio not found")
    return path


def build_audio_url(public_base_url: str, filename: str) -> str:
    safe_name = ensure_safe_audio_filename(filename)
    return f"{public_base_url.rstrip('/')}/audio/{safe_name}"


def write_silence_wav(path: Path, duration_sec: float = 1.0, sample_rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.05, float(duration_sec))
    rate = max(8000, int(sample_rate))
    frames = int(duration * rate)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(b"\x00\x00" * frames)


def concat_wav_files(sources: list[Path], destination: Path, *, pause_between_chunks_ms: int = 0) -> None:
    if not sources:
        raise ValueError("sources is empty")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(wave.open(str(sources[0]), "rb")) as first:
        params = {
            "nchannels": first.getnchannels(),
            "sampwidth": first.getsampwidth(),
            "framerate": first.getframerate(),
            "comptype": first.getcomptype(),
            "compname": first.getcompname(),
        }

    with closing(wave.open(str(destination), "wb")) as out_fp:
        out_fp.setnchannels(params["nchannels"])
        out_fp.setsampwidth(params["sampwidth"])
        out_fp.setframerate(params["framerate"])
        out_fp.setcomptype(params["comptype"], params["compname"])
        pause_frames = max(0, int(pause_between_chunks_ms)) * params["framerate"] // 1000
        silence_bytes = b"\x00" * (pause_frames * params["nchannels"] * params["sampwidth"])

        for index, source in enumerate(sources):
            with closing(wave.open(str(source), "rb")) as in_fp:
                current = (
                    in_fp.getnchannels(),
                    in_fp.getsampwidth(),
                    in_fp.getframerate(),
                    in_fp.getcomptype(),
                )
                expected = (
                    params["nchannels"],
                    params["sampwidth"],
                    params["framerate"],
                    params["comptype"],
                )
                if current != expected:
                    raise ValueError(f"incompatible wav parameters: {source}")
                out_fp.writeframes(in_fp.readframes(in_fp.getnframes()))
                if silence_bytes and index < len(sources) - 1:
                    out_fp.writeframes(silence_bytes)
