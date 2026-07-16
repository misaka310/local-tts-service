from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from ..models import SpeakRequest

@dataclass(frozen=True)
class NormalizedRequest:
    payload: SpeakRequest
    caption: str | None
    instruction: str | None

def normalize_request(payload: SpeakRequest, model_cfg: Any) -> NormalizedRequest:
    supports_caption = bool(getattr(model_cfg, "supports_caption", False))
    supports_instruction = bool(getattr(model_cfg, "supports_instruction", False))
    caption = payload.caption
    if not caption and supports_caption: caption = payload.instruction or payload.styleCaption
    instruction = payload.instruction
    if not instruction and supports_instruction: instruction = payload.styleCaption or caption
    normalized = payload.model_copy(update={"caption": caption, "instruction": instruction, "language": payload.language or getattr(model_cfg, "default_language", None), "speedScale": payload.speedScale if getattr(model_cfg, "supports_speed_control", False) else None, "styleStrength": payload.styleStrength if getattr(model_cfg, "supports_style_strength", False) else None})
    return NormalizedRequest(normalized, caption, instruction)
