from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ID = "Jmica/F5TTS"
MODEL_REVISION = "6bed3f318d92e37b97164ece0e2f90153b09a4e5"
FILES = (
    "JA_21999120/model_21999120.pt",
    "JA_21999120/vocab_japanese.txt",
    "README.md",
)


def download_assets(model_root: Path) -> list[Path]:
    model_root = Path(model_root).expanduser().resolve()
    model_root.mkdir(parents=True, exist_ok=True)
    downloaded = [
        Path(
            hf_hub_download(
                repo_id=REPO_ID,
                revision=MODEL_REVISION,
                filename=filename,
                local_dir=str(model_root),
                token=False,
            )
        )
        for filename in FILES
    ]
    for path in downloaded:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"F5-TTS model asset is missing or empty: {path}")
        print(f"F5 asset ready: {path} ({path.stat().st_size} bytes)", flush=True)
    return downloaded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", type=Path, required=True)
    args = parser.parse_args()
    download_assets(args.model_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
