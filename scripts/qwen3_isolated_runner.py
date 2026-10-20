"""Run Qwen3-TTS in a separately installed ROCm Python environment.

This script is intentionally invoked with that environment's interpreter. The
normal Windows service process does not have to use the ROCm PyTorch build.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys


def rocm_status() -> dict[str, object]:
    """Report real PyTorch/HIP availability, never assume any GPU is ROCm."""
    try:
        import torch
        hip_version = str(getattr(torch.version, "hip", "") or "").strip()
        available = bool(hip_version and torch.cuda.is_available() and torch.cuda.device_count() > 0)
        gpu_name = str(torch.cuda.get_device_name(0)) if available else ""
        package_ready = importlib.util.find_spec("qwen_tts") is not None
        soundfile_ready = importlib.util.find_spec("soundfile") is not None
        reason = ""
        if not available:
            reason = "ROCm GPU is unavailable in the isolated Python environment"
        elif not package_ready or not soundfile_ready:
            reason = "qwen-tts or soundfile is missing from the ROCm environment"
        return {
            "ok": bool(available and package_ready and soundfile_ready),
            "backend": "rocm" if hip_version else "other",
            "gpuAvailable": available,
            "gpuName": gpu_name,
            "hipVersion": hip_version,
            "torchVersion": str(torch.__version__),
            "reason": reason,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "backend": "unknown", "gpuAvailable": False, "reason": f"ROCm probe failed: {exc}"}


def generate(payload: dict[str, object]) -> Path:
    status = rocm_status()
    if not status["ok"]:
        raise RuntimeError(str(status.get("reason") or "ROCm GPU is unavailable"))
    # Never let Transformers download weights during generation.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"

    model_path = Path(str(payload["modelPath"])).resolve()
    if not model_path.is_dir():
        raise ValueError(f"Qwen3-TTS model directory was not found: {model_path}")
    output_path = Path(str(payload["outputPath"])).resolve()
    if output_path.suffix.lower() != ".wav":
        raise ValueError("only .wav output is supported")
    audio_path = Path(str(payload["referenceAudioPath"])).resolve()
    text_path = Path(str(payload["referenceTextPath"])).resolve()
    if not audio_path.is_file() or not text_path.is_file():
        raise ValueError("registered reference WAV and transcription TXT are both required")

    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    reference_text = text_path.read_text(encoding="utf-8-sig").strip()
    if not reference_text:
        raise ValueError("registered reference transcription is empty")
    model = Qwen3TTSModel.from_pretrained(
        pretrained_model_name_or_path=str(model_path),
        local_files_only=True,
        device_map="cuda:0",
        dtype=torch.bfloat16,
    )
    prompt = model.create_voice_clone_prompt(
        ref_audio=str(audio_path), ref_text=reference_text, x_vector_only_mode=False,
    )
    wavs, sample_rate = model.generate_voice_clone(
        text=str(payload["text"]),
        language=str(payload.get("language") or "Japanese"),
        voice_clone_prompt=prompt,
        seed=payload.get("seed"),
        non_streaming_mode=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, wavs[0], sample_rate)
    if not output_path.is_file() or output_path.stat().st_size < 44:
        raise RuntimeError("ROCm inference did not produce a valid WAV file")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--request-json", type=Path)
    args = parser.parse_args(argv)
    if args.check:
        status = rocm_status()
        print(json.dumps(status, ensure_ascii=False))
        return 0 if status["ok"] else 2
    try:
        payload = json.loads(args.request_json.read_text(encoding="utf-8"))
        result = generate(payload)
        print(json.dumps({"ok": True, "audioPath": str(result)}, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
