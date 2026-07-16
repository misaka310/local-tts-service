from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download one Hugging Face repository snapshot into a local directory.")
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--local-dir", required=True)
    parser.add_argument("--cache-dir", default="")
    parser.add_argument("--revision", default="")
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:  # pragma: no cover - setup script surface
        print(f"huggingface_hub is required: {exc}", file=sys.stderr)
        return 2

    local_dir = Path(args.local_dir).resolve()
    local_dir.mkdir(parents=True, exist_ok=True)

    kwargs: dict[str, object] = {
        "repo_id": args.repo_id,
        "local_dir": str(local_dir),
        "local_dir_use_symlinks": False,
        "resume_download": True,
    }
    if args.cache_dir:
        cache_dir = Path(args.cache_dir).resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        kwargs["cache_dir"] = str(cache_dir)
    if args.revision:
        kwargs["revision"] = args.revision
    if os.environ.get("HF_TOKEN"):
        kwargs["token"] = os.environ["HF_TOKEN"]

    print(f"[INFO] downloading {args.repo_id} -> {local_dir}")
    snapshot_download(**kwargs)
    print(f"[DONE] downloaded {args.repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
