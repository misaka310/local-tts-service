from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import uuid

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
import torch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from local_tts_service.config import load_config
from local_tts_service.server import _build_runtime_registry, create_app

MODELS = [
    "sarashina2_2_tts",
    "fireredtts2",
    "t5gemma_tts_2b_2b",
    "fish_s1_mini",
    "qwen3_tts_clone_0_6b",
    "qwen3_tts_clone_1_7b",
]
TARGET_TEXT = "こんにちは。音声生成の確認です。日本語を自然に読み上げられるか確認しています。"
OUTPUT_DIR = ROOT / "runtime" / "audio" / "model-smoke"

MODEL_SPECS: dict[str, dict[str, object]] = {
    "sarashina2_2_tts": {
        "displayName": "Sarashina2.2-TTS",
        "officialModelId": "sbintuitions/sarashina2.2-tts",
        "officialCodeRepository": "https://github.com/sbintuitions/sarashina2.2-tts.git",
        "codeRevision": "e0ac9c99160ea4bf8dde46892892c945e66fcc13",
        "modelRevision": "8d30bd523b1fa217ab0b4cd32c9275d4f222fbcd",
        "executionEnvironment": "WSL Ubuntu / dedicated Python 3.11 venv",
        "dtype": "official CUDA implementation default (not overridden)",
        "quantization": "none",
    },
    "fireredtts2": {
        "displayName": "FireRedTTS-2",
        "officialModelId": "FireRedTeam/FireRedTTS2",
        "officialCodeRepository": "https://github.com/FireRedTeam/FireRedTTS2.git",
        "codeRevision": "404f3f61d25bb4804859b588a6a734bf8468090c",
        "modelRevision": "4af3f5cc4963373b86b52d750220d4de85261f05",
        "executionEnvironment": "WSL Ubuntu / dedicated Python 3.11 venv",
        "dtype": "official CUDA implementation default (not overridden)",
        "quantization": "none",
    },
    "t5gemma_tts_2b_2b": {
        "displayName": "T5Gemma-TTS 2B-2B",
        "officialModelId": "Aratako/T5Gemma-TTS-2b-2b",
        "officialCodeRepository": "https://github.com/Aratako/T5Gemma-TTS.git",
        "codeRevision": "c8722b37e1aca0e21f85185188755e164c316828",
        "modelRevision": "e548f8358891975e61d2107e3d7ccc47b1b7294e",
        "executionEnvironment": "WSL Ubuntu / dedicated Python 3.11 venv",
        "dtype": "bfloat16 with upstream accelerate device mapping",
        "quantization": "none",
    },
    "fish_s1_mini": {
        "displayName": "FishAudio S1-mini",
        "officialModelId": "fishaudio/s1-mini",
        "officialCodeRepository": "https://github.com/fishaudio/fish-speech.git",
        "codeRevision": "23a4beb06952a6cc29813851309184ec1c498cac",
        "modelRevision": "f4b445029346701e082b60bb63fcc2d1bb17a0e2",
        "executionEnvironment": "WSL Ubuntu / dedicated Python 3.11 venv / S1-compatible code",
        "dtype": "official S1 CUDA implementation default (not overridden)",
        "quantization": "none",
    },
    "qwen3_tts_clone_0_6b": {
        "displayName": "Qwen3-TTS Voice Clone 0.6B",
        "officialModelId": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        "officialCodeRepository": "qwen-tts Python package",
        "executionEnvironment": "Windows service .venv / in-process qwen3_tts runtime",
        "dtype": "bfloat16 on CUDA (runtime auto setting)",
        "quantization": "none",
    },
    "qwen3_tts_clone_1_7b": {
        "displayName": "Qwen3-TTS Voice Clone 1.7B",
        "officialModelId": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "officialCodeRepository": "qwen-tts Python package",
        "executionEnvironment": "Windows service .venv / in-process qwen3_tts runtime",
        "dtype": "bfloat16 on CUDA (runtime auto setting)",
        "quantization": "none",
    },
}

WSL_ENV_KEYS = {
    "sarashina2_2_tts": "sarashina",
    "fireredtts2": "fireredtts2",
    "t5gemma_tts_2b_2b": "t5gemma",
    "fish_s1_mini": "fish_s1_mini",
}


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def find_reference_voice() -> str:
    voices_root = ROOT / "reference" / "voices"
    requested = os.environ.get("LOCAL_TTS_REFERENCE_VOICE", "").strip()
    preferred = [name for name in (requested, "default") if name]
    candidates = [voices_root / name for name in preferred]
    candidates.extend(sorted(item for item in voices_root.iterdir() if item.is_dir()))
    seen: set[Path] = set()
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        if (item / ".archived").exists():
            continue
        if (item / "voice.wav").is_file() and (item / "voice.txt").is_file():
            if (item / "voice.txt").read_text(encoding="utf-8-sig").strip():
                return item.name
    raise RuntimeError("no active reference voice with voice.wav and voice.txt was found")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_wav(path: Path) -> dict[str, object]:
    samples, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    if samples.size == 0 or sample_rate <= 0:
        raise RuntimeError("WAV has no samples")
    duration = float(samples.shape[0]) / float(sample_rate)
    absolute = np.abs(samples)
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    peak = float(np.max(absolute))
    silence_ratio = float(np.mean(absolute < 1e-4))
    if not math.isfinite(rms) or rms <= 1e-5:
        raise RuntimeError(f"WAV is silent or invalid: rms={rms}")
    if duration <= 0:
        raise RuntimeError(f"WAV duration is invalid: {duration}")
    return {
        "sampleRate": int(sample_rate),
        "channels": int(samples.shape[1]),
        "durationSec": round(duration, 3),
        "rms": round(rms, 8),
        "peak": round(peak, 8),
        "silenceRatio": round(silence_ratio, 8),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def read_wsl_manifest(env_key: str) -> dict[str, object] | None:
    command = [
        "wsl.exe",
        "--exec",
        "bash",
        "-lc",
        f"cat ~/.local/share/local-tts-service/manifests/{env_key}.json",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def runtime_environment() -> dict[str, object]:
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    return {
        "hostPlatform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": package_version("transformers"),
        "qwenTts": package_version("qwen-tts"),
        "cudaAvailable": torch.cuda.is_available(),
        "torchCuda": torch.version.cuda,
        "gpu": gpu_name,
    }


def qwen_runtime_metadata(config: object, models: list[str]) -> dict[str, dict[str, object]]:
    registry = _build_runtime_registry(config)
    runtime = registry.get("qwen3_tts")
    result: dict[str, dict[str, object]] = {}
    if runtime is None:
        return result
    for model_name in models:
        model_cfg = config.models.get(model_name)
        if model_cfg is None:
            continue
        availability = runtime.get_model_availability(model_name, model_cfg)
        model_path = availability.model_path
        revision = None
        if model_path is not None and model_path.parent.name == "snapshots":
            revision = model_path.name
        result[model_name] = {
            "resolvedModelPath": str(model_path) if model_path is not None else None,
            "modelRevision": revision,
            "codeRevision": f"qwen-tts {package_version('qwen-tts') or 'unknown'}",
            "resolvedDevice": runtime._resolve_device(),
            "resolvedDtype": str(runtime._resolve_dtype(runtime._resolve_device())),
        }
    return result


def failure_message(response_text: str) -> str:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return response_text
    if not isinstance(payload, dict):
        return response_text
    return str(payload.get("errorMessage") or payload.get("unavailableReason") or payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify real TTS generation through the 30 service /v1/speak API.")
    parser.add_argument("--models", nargs="+", choices=MODELS, default=MODELS)
    parser.add_argument("--voice-id", default="")
    args = parser.parse_args()
    selected_models = list(args.models)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    voice_id = args.voice_id.strip() or find_reference_voice()
    voice_dir = ROOT / "reference" / "voices" / voice_id
    reference_audio = voice_dir / "voice.wav"
    reference_text = voice_dir / "voice.txt"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]

    config = load_config(ROOT)
    qwen_metadata = qwen_runtime_metadata(
        config,
        [item for item in selected_models if item.startswith("qwen3_tts_")],
    )
    client = TestClient(create_app(ROOT))
    model_response = client.get("/v1/models")
    model_response.raise_for_status()
    model_payload = model_response.json()
    model_info = {
        str(item.get("id") or item.get("model")): item
        for item in model_payload.get("models", [])
        if isinstance(item, dict)
    }

    records: list[dict[str, object]] = []
    for index, model in enumerate(selected_models, start=1):
        started_perf = time.perf_counter()
        started_wall_ns = time.time_ns()
        target = OUTPUT_DIR / f"{run_id}-{model}.wav"
        target.unlink(missing_ok=True)
        info = model_info.get(model, {})
        spec = dict(MODEL_SPECS[model])
        if model in qwen_metadata:
            spec.update({key: value for key, value in qwen_metadata[model].items() if value is not None})
        env_key = WSL_ENV_KEYS.get(model)
        wsl_manifest = read_wsl_manifest(env_key) if env_key else None
        record: dict[str, object] = {
            "model": model,
            **spec,
            "referenceVoiceId": voice_id,
            "referenceAudioPath": str(reference_audio),
            "referenceTextPath": str(reference_text),
            "requestId": f"model-smoke-{run_id}-{model}",
            "status": "failed",
            "availableBeforeRun": bool(info.get("available", False)),
            "unavailableReasonBeforeRun": info.get("unavailableReason"),
            "wslManifest": wsl_manifest,
        }
        try:
            response = client.post(
                "/v1/speak",
                json={
                    "text": TARGET_TEXT,
                    "model": model,
                    "voiceId": voice_id,
                    "language": "Japanese" if model.startswith("qwen3_tts_") else "ja",
                    "seed": 260700 + index,
                    "requestId": record["requestId"],
                    "format": "wav",
                },
            )
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}: {failure_message(response.text)}")
            payload = response.json()
            if payload.get("ok") is not True:
                raise RuntimeError(str(payload.get("errorMessage") or payload))
            source = Path(str(payload.get("audioPath") or ""))
            if not source.is_file():
                raise RuntimeError(f"generated audio path does not exist: {source}")
            if source.stat().st_mtime_ns + 2_000_000_000 < started_wall_ns:
                raise RuntimeError(f"generated audio is older than this run: {source}")
            shutil.copy2(source, target)
            record.update(inspect_wav(target))
            record.update(
                {
                    "status": "passed",
                    "apiStatusCode": response.status_code,
                    "apiOk": payload.get("ok"),
                    "apiAudioPath": str(source),
                    "outputWavPath": str(target),
                    "runtime": payload.get("runtime"),
                    "seedUsed": payload.get("seedUsed"),
                    "apiTimings": payload.get("timings"),
                    "elapsedSec": round(time.perf_counter() - started_perf, 3),
                    "newFileVerified": True,
                }
            )
        except Exception as exc:  # noqa: BLE001
            record.update(
                {
                    "error": str(exc),
                    "elapsedSec": round(time.perf_counter() - started_perf, 3),
                    "newFileVerified": False,
                }
            )
        records.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)

    passed_count = sum(item["status"] == "passed" for item in records)
    manifest = {
        "runId": run_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "apiEndpoint": "/v1/speak",
        "text": TARGET_TEXT,
        "referenceVoiceId": voice_id,
        "referenceAudioSha256": sha256_file(reference_audio),
        "referenceTextSha256": sha256_file(reference_text),
        "environment": runtime_environment(),
        "requestedModels": selected_models,
        "passedCount": passed_count,
        "failedCount": len(records) - passed_count,
        "allPassed": passed_count == len(records),
        "models": records,
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"manifest: {manifest_path}")
    return 0 if manifest["allPassed"] else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())
