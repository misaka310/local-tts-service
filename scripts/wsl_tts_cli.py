from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

from scripts.wsl_tts_infer import load_request
from scripts.wsl_tts_runner import GENERATORS, validate_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one WSL-isolated zero-shot TTS model.")
    parser.add_argument("--request-json", required=True)
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()
    try:
        request = load_request(Path(args.request_json))
        if args.output_path:
            request = replace(request, output_path=Path(args.output_path).expanduser())
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
        if request.output_path.exists():
            request.output_path.unlink()
        GENERATORS[request.model](request)
        validate_output(request.output_path)
        print(f"[DONE] {request.model}: {request.output_path}", flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
