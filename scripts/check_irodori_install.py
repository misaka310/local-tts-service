from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_irodori_install.py <source-root>", file=sys.stderr)
        return 2
    source_root = Path(sys.argv[1]).resolve()
    if not source_root.is_dir():
        print(f"Irodori source directory not found: {source_root}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(source_root))
    import dacvae  # noqa: F401
    import torch
    import irodori_tts.inference_runtime  # noqa: F401

    print(f"Irodori imports ready: torch={torch.__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
