from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import runpy
import shutil
import sys
import tempfile
import wave
from pathlib import Path

if __package__:
    from .runtime_paths import resolve_runtime_root
else:
    from runtime_paths import resolve_runtime_root

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = resolve_runtime_root(REPO_ROOT)
MODEL_ROOT = RUNTIME_ROOT / "models" / "f5-tts" / "JA_21999120"
MODEL_NAME = "F5TTS_v1_Base"
INFERENCE_MODULE = "f5_tts.infer.infer_cli"


def build_inference_arguments(
    *,
    basic_config: Path,
    model_config: Path,
    checkpoint: Path,
    vocab: Path,
    reference_audio: Path,
    reference_text: str,
    text: str,
    output_path: Path,
    device: str,
) -> list[str]:
    output_path = Path(output_path)
    return [
        "-c", str(basic_config),
        "-mc", str(model_config),
        "-m", MODEL_NAME,
        "-p", str(checkpoint),
        "-v", str(vocab),
        "-r", str(reference_audio),
        "-s", reference_text,
        "-t", text,
        "-o", str(output_path.parent),
        "-w", output_path.name,
        "--device", device,
    ]


def _begin_background_mode() -> tuple[object, object] | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.SetPriorityClass.restype = ctypes.c_int
    process = kernel32.GetCurrentProcess()
    if not kernel32.SetPriorityClass(process, 0x00100000):
        raise ctypes.WinError(ctypes.get_last_error())
    print("Windows background CPU and I/O scheduling: enabled", flush=True)
    return kernel32, process


def _end_background_mode(handle: tuple[object, object] | None) -> None:
    if handle is not None and not handle[0].SetPriorityClass(handle[1], 0x00200000):
        raise ctypes.WinError(ctypes.get_last_error())


def _patch_torchaudio_load_with_soundfile() -> None:
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio

    def soundfile_load(source: object, *args: object, **kwargs: object) -> tuple[object, int]:
        del args, kwargs
        audio, sample_rate = sf.read(source, dtype="float32", always_2d=True)
        channels_first = np.ascontiguousarray(audio.T)
        return torch.from_numpy(channels_first), int(sample_rate)

    torchaudio.load = soundfile_load


def _required(payload: dict[str, object], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _verify_wav(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 44:
        raise RuntimeError(f"F5-TTS did not create a non-empty WAV: {path}")
    with wave.open(str(path), "rb") as audio:
        if audio.getnframes() < 1 or audio.getframerate() < 1 or audio.getnchannels() < 1:
            raise RuntimeError(f"F5-TTS created an invalid WAV: {path}")


def _resolve_f5_package_root() -> Path:
    spec = importlib.util.find_spec("f5_tts")
    locations = getattr(spec, "submodule_search_locations", None)
    if not locations:
        raise ModuleNotFoundError("F5-TTS package was not found in its dedicated environment")

    required_paths = (
        Path("infer") / "examples" / "basic" / "basic.toml",
        Path("configs") / "F5TTS_v1_Base.yaml",
    )
    roots = [Path(location) for location in locations]
    for root in roots:
        if all((root / relative).is_file() for relative in required_paths):
            return root

    diagnostics = []
    for root in roots:
        missing = [str(relative) for relative in required_paths if not (root / relative).is_file()]
        diagnostics.append(f"{root}: missing {', '.join(missing)}")
    raise FileNotFoundError("F5-TTS package files are missing: " + "; ".join(diagnostics))


def run_request(request_json: Path, output_path: Path) -> None:
    payload = json.loads(Path(request_json).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("model") != "f5_tts_zero_shot":
        raise ValueError("unsupported F5-TTS request")
    text = _required(payload, "text")
    reference_audio = Path(_required(payload, "referenceAudioPath")).expanduser().resolve()
    reference_text_path = Path(_required(payload, "referenceTextPath")).expanduser().resolve()
    if not reference_audio.is_file():
        raise FileNotFoundError(f"F5-TTS reference audio not found: {reference_audio}")
    if not reference_text_path.is_file():
        raise FileNotFoundError(f"F5-TTS reference text not found: {reference_text_path}")
    reference_text = reference_text_path.read_text(encoding="utf-8-sig").strip()
    if not reference_text:
        raise ValueError("F5-TTS reference text is empty")

    checkpoint = MODEL_ROOT / "model_21999120.pt"
    vocab = MODEL_ROOT / "vocab_japanese.txt"
    for path in (checkpoint, vocab):
        if not path.is_file():
            raise FileNotFoundError(f"F5-TTS Japanese model file is missing: {path}")

    package_root = _resolve_f5_package_root()
    basic_config = package_root / "infer" / "examples" / "basic" / "basic.toml"
    model_config = package_root / "configs" / "F5TTS_v1_Base.yaml"
    for path in (basic_config, model_config):
        if not path.is_file():
            raise FileNotFoundError(f"F5-TTS package file is missing: {path}")

    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_root = RUNTIME_ROOT / "temp"
    hf_cache = RUNTIME_ROOT / "hf-cache"
    temp_root.mkdir(parents=True, exist_ok=True)
    hf_cache.mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "HF_HOME": str(hf_cache),
        "HF_HUB_CACHE": str(hf_cache / "hub"),
        "TRANSFORMERS_CACHE": str(hf_cache / "transformers"),
        "TORCH_HOME": str(RUNTIME_ROOT / "cache" / "torch"),
        "TMP": str(temp_root),
        "TEMP": str(temp_root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    sys.dont_write_bytecode = True
    device = str(os.environ.get("LOCAL_TTS_F5_DEVICE") or "cuda:0").strip()

    with tempfile.TemporaryDirectory(prefix="f5-tts-", dir=str(temp_root)) as temp_dir:
        temp_output = Path(temp_dir) / "generated.wav"
        arguments = build_inference_arguments(
            basic_config=basic_config,
            model_config=model_config,
            checkpoint=checkpoint,
            vocab=vocab,
            reference_audio=reference_audio,
            reference_text=reference_text,
            text=text,
            output_path=temp_output,
            device=device,
        )
        previous_argv = sys.argv
        background = _begin_background_mode()
        try:
            sys.argv = [INFERENCE_MODULE, *arguments]
            if os.name == "nt":
                # TorchAudio 2.10 routes WAV loading through TorchCodec, which requires FFmpeg DLLs on Windows.
                # F5-TTS reference audio is WAV, so reuse the installed SoundFile decoder instead.
                _patch_torchaudio_load_with_soundfile()
            runpy.run_module(INFERENCE_MODULE, run_name="__main__", alter_sys=True)
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise RuntimeError(f"F5-TTS exited with code {exc.code}") from exc
        finally:
            sys.argv = previous_argv
            _end_background_mode(background)
        _verify_wav(temp_output)
        shutil.copy2(temp_output, output_path)
    _verify_wav(output_path)
    print(f"F5-TTS generated {output_path} ({output_path.stat().st_size} bytes)", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    args = parser.parse_args()
    run_request(args.request_json, args.output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
