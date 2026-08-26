from __future__ import annotations

import argparse
from dataclasses import replace
import faulthandler
from pathlib import Path
import sys

from scripts.wsl_tts_infer import load_request, resolve_reference_prompt
from scripts.wsl_tts_runner import GENERATORS, validate_output


def main() -> int:
    faulthandler.enable(all_threads=True)
    parser = argparse.ArgumentParser(description="Run one WSL-isolated zero-shot TTS model.")
    parser.add_argument("--request-json", required=True)
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()
    try:
        request = load_request(Path(args.request_json))
        request = resolve_reference_prompt(request)
        if args.output_path:
            request = replace(request, output_path=Path(args.output_path).expanduser())
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
        if request.output_path.exists():
            request.output_path.unlink()
        GENERATORS[request.model](request)
        validate_output(request.output_path)
        print(f"[DONE] {request.model}: {request.output_path}", flush=True)
        return 0
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
        if exit_code == 0:
            exit_code = 1
        print(f"[ERROR] SystemExit(code={exc.code!r})", file=sys.stderr, flush=True)
        return exit_code
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())