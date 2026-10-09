from __future__ import annotations

from pathlib import Path
import sys

_REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from local_tts_service.runtime_paths import resolve_reference_root, resolve_runtime_root  # noqa: E402

__all__ = ["resolve_reference_root", "resolve_runtime_root"]
