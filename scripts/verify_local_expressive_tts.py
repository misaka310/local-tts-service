from __future__ import annotations

import argparse
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
import math
from pathlib import Path
import re
import subprocess
import unicodedata

import numpy as np
import soundfile as sf


def normalize_japanese(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龠々ー]", "", normalized)


def audio_metrics(path: Path) -> dict[str, object]:
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    if audio.size == 0 or sample_rate <= 0:
        raise RuntimeError(f"audio is empty: {path}")
    mono = audio.mean(axis=1)
    absolute = np.abs(mono)
    rms = float(np.sqrt(np.mean(np.square(mono), dtype=np.float64)))
    peak = float(np.max(absolute))
    duration_sec = float(len(mono) / sample_rate)
    silence_ratio = float(np.mean(absolute < 1e-4))
    clipping_ratio = float(np.mean(absolute >= 0.999))
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "durationSec": round(duration_sec, 3),
        "sampleRate": int(sample_rate),
        "channels": int(audio.shape[1]),
        "rms": round(rms, 6),
        "rmsDbfs": round(20.0 * math.log10(max(rms, 1e-12)), 2),
        "peak": round(peak, 6),
        "peakDbfs": round(20.0 * math.log10(max(peak, 1e-12)), 2),
        "silenceRatio": round(silence_ratio, 6),
        "clippingRatio": round(clipping_ratio, 6),
    }


def generation_result(request_path: Path) -> dict[str, object]:
    log_path = Path(f"{request_path}.local-expressive.stdout.log")
    if not log_path.is_file():
        raise FileNotFoundError(f"generation stdout log is missing: {log_path}")
    for line in reversed(log_path.read_text(encoding="utf-8-sig").splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict) and payload.get("model"):
            return payload
    raise RuntimeError(f"generation result JSON was not found in: {log_path}")


def resolve_cached_whisper_snapshot(model_name: str) -> Path:
    cache_root = Path.home() / ".cache" / "huggingface" / "hub"
    model_dir = cache_root / f"models--Systran--faster-whisper-{model_name}"
    snapshots = model_dir / "snapshots"
    candidates = sorted((item for item in snapshots.glob("*") if item.is_dir()), key=lambda p: p.stat().st_mtime_ns)
    if not candidates:
        raise FileNotFoundError(f"cached faster-whisper model is missing: {model_dir}")
    return candidates[-1]


def transcribe(path: Path, model_name: str) -> dict[str, object]:
    from faster_whisper import WhisperModel

    snapshot = resolve_cached_whisper_snapshot(model_name)
    model = WhisperModel(str(snapshot), device="cpu", compute_type="int8", local_files_only=True)
    segments, info = model.transcribe(
        str(path),
        language="ja",
        beam_size=5,
        vad_filter=False,
        condition_on_previous_text=False,
    )
    text = "".join(segment.text for segment in segments).strip()
    return {
        "model": f"Systran/faster-whisper-{model_name}",
        "snapshot": str(snapshot),
        "device": "cpu",
        "computeType": "int8",
        "language": info.language,
        "languageProbability": round(float(info.language_probability), 6),
        "text": text,
    }


def gpu_snapshot() -> dict[str, object]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return {"available": False, "error": (completed.stderr or completed.stdout).strip()}
    values = [item.strip() for item in completed.stdout.strip().splitlines()[0].split(",")]
    return {
        "available": True,
        "name": values[0],
        "driverVersion": values[1],
        "memoryTotalMiB": int(values[2]),
        "memoryUsedMiB": int(values[3]),
        "memoryFreeMiB": int(values[4]),
    }


def verify_item(request_path: Path, wav_path: Path, expected_text: str, whisper_model: str) -> dict[str, object]:
    request = json.loads(request_path.read_text(encoding="utf-8-sig"))
    generated = generation_result(request_path)
    metrics = audio_metrics(wav_path)
    asr = transcribe(wav_path, whisper_model)
    normalized_expected = normalize_japanese(expected_text)
    normalized_actual = normalize_japanese(str(asr["text"]))
    similarity = SequenceMatcher(None, normalized_expected, normalized_actual).ratio()
    structural_pass = bool(
        metrics["durationSec"] > 0.5
        and metrics["rms"] > 0.001
        and metrics["silenceRatio"] < 0.98
        and metrics["clippingRatio"] < 0.01
    )
    fidelity_pass = similarity >= 0.60
    return {
        "request": request,
        "generation": generated,
        "audio": metrics,
        "asr": asr,
        "textFidelity": {
            "expected": expected_text,
            "normalizedExpected": normalized_expected,
            "normalizedActual": normalized_actual,
            "similarity": round(similarity, 6),
            "minimumSimilarity": 0.60,
            "passed": fidelity_pass,
        },
        "structuralAudioPassed": structural_pass,
        "passed": structural_pass and fidelity_pass,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chatterbox-request", type=Path, required=True)
    parser.add_argument("--chatterbox-wav", type=Path, required=True)
    parser.add_argument("--cosyvoice-request", type=Path, required=True)
    parser.add_argument("--cosyvoice-wav", type=Path, required=True)
    parser.add_argument("--expected-text", required=True)
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    chatterbox = verify_item(
        args.chatterbox_request.resolve(),
        args.chatterbox_wav.resolve(),
        args.expected_text,
        args.whisper_model,
    )
    cosyvoice = verify_item(
        args.cosyvoice_request.resolve(),
        args.cosyvoice_wav.resolve(),
        args.expected_text,
        args.whisper_model,
    )
    payload = {
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
        "expectedText": args.expected_text,
        "gpu": gpu_snapshot(),
        "models": {
            "chatterbox_multilingual_v3": chatterbox,
            "fun_cosyvoice3_0_5b": cosyvoice,
        },
        "passed": bool(chatterbox["passed"] and cosyvoice["passed"]),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
