from __future__ import annotations

import os
from pathlib import Path


def _resolve_link_root(repo_root: Path, name: str) -> Path:
    link_root = Path(repo_root) / name
    try:
        target = os.readlink(link_root)
    except (OSError, NotImplementedError):
        return link_root

    prefix = chr(92) * 2 + "?" + chr(92)
    if os.name == "nt" and target.startswith(prefix):
        target = target[len(prefix):]
    target_path = Path(target)
    if not target_path.is_absolute():
        target_path = link_root.parent / target_path
    return Path(os.path.normpath(target_path))


def resolve_runtime_root(repo_root: Path) -> Path:
    configured = os.environ.get("LOCAL_TTS_RUNTIME_ROOT")
    if configured:
        return Path(configured)
    return _resolve_link_root(repo_root, "runtime")


def resolve_reference_root(repo_root: Path) -> Path:
    return _resolve_link_root(repo_root, "reference")
