from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
MODEL_REVISION = "dab70521e0956e3db91fb887d36c9a07d21ebc0b"
PROCESS_MODE_BACKGROUND_BEGIN = 0x00100000


def _enter_windows_background_mode() -> None:
    if os.name != "nt":
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.SetPriorityClass.restype = ctypes.c_int
    if not kernel32.SetPriorityClass(
        kernel32.GetCurrentProcess(), PROCESS_MODE_BACKGROUND_BEGIN
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def download_model(model_root: Path, cache_dir: Path | None = None) -> Path:
    _enter_windows_background_mode()
    model_root = Path(model_root).expanduser().resolve()
    model_root.mkdir(parents=True, exist_ok=True)
    download_options: dict[str, object] = {
        "repo_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "local_dir": str(model_root),
        "token": False,
    }
    if cache_dir is not None:
        cache_dir = Path(cache_dir).expanduser().resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        download_options["cache_dir"] = str(cache_dir)
    snapshot = Path(
        snapshot_download(**download_options)
    )
    if not (snapshot / "config.json").is_file():
        raise RuntimeError(f"Qwen3-TTS config.json is missing under {snapshot}")
    weights = [*snapshot.glob("*.safetensors"), *snapshot.glob("*.bin")]
    if not weights:
        raise RuntimeError(f"Qwen3-TTS model weights are missing under {snapshot}")
    total_bytes = sum(path.stat().st_size for path in weights)
    print(
        f"Qwen3-TTS model ready: {snapshot} "
        f"({len(weights)} weight file(s), {total_bytes} bytes)",
        flush=True,
    )
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    download_model(args.model_root, args.cache_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
