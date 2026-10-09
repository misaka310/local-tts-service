from __future__ import annotations
from typing import Any
import os

def split_text_for_chunks(text: str, *, soft_chunk_chars: int, max_chunk_chars: int, hard_limit_chars: int) -> list[str]:
    normalized = str(text or "").strip()
    if len(normalized) <= max_chunk_chars:
        return [normalized]
    parts: list[str] = []
    current = ""
    tokens: list[str] = []
    start = 0
    for idx, ch in enumerate(normalized):
        if ch in "\n縲ゑｼ・ｼ・?":
            tokens.append(normalized[start : idx + 1]); start = idx + 1
    if start < len(normalized): tokens.append(normalized[start:])
    for token in tokens:
        piece = token.strip()
        if not piece: continue
        if len(piece) > hard_limit_chars:
            if current: parts.append(current); current = ""
            for offset in range(0, len(piece), max_chunk_chars): parts.append(piece[offset : offset + max_chunk_chars])
            continue
        if not current: current = piece; continue
        candidate = f"{current}\n{piece}"
        if len(candidate) <= soft_chunk_chars or (len(piece) <= max_chunk_chars and len(candidate) <= max_chunk_chars): current = candidate
        else: parts.append(current); current = piece
    if current: parts.append(current)
    return parts or [normalized]

def merge_chunking_override(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base or {})
    if override:
        for key in ("softChunkChars", "maxChunkChars", "hardLimitChars", "pauseBetweenChunksMs"):
            if key in override and override[key] is not None: merged[key] = int(override[key])
    soft = max(20, int(merged.get("softChunkChars", 120)))
    max_chars = max(soft, int(merged.get("maxChunkChars", max(soft, 200))))
    hard = max(max_chars, int(merged.get("hardLimitChars", max_chars)))
    pause = max(0, int(merged.get("pauseBetweenChunksMs", 0)))
    return {**merged, "softChunkChars": soft, "maxChunkChars": max_chars, "hardLimitChars": hard, "pauseBetweenChunksMs": pause, "keepChunkFiles": bool(merged.get("keepChunkFiles", False))}

def should_keep_chunk_files(chunking: dict[str, Any]) -> bool:
    value = os.getenv("LOCAL_TTS_KEEP_CHUNKS")
    if value is not None:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(chunking.get("keepChunkFiles", False))
