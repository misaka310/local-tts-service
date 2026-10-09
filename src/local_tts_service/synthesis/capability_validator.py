from __future__ import annotations
from typing import Any
from ..errors import RequestValidationError
from ..models import SpeakRequest

def validate_model_capabilities(payload: SpeakRequest, model_name: str, model_cfg: Any) -> None:
    caption = bool(getattr(model_cfg, "supports_caption", False)); instruction = bool(getattr(model_cfg, "supports_instruction", False))
    if payload.caption and not caption: raise RequestValidationError(f"caption is not supported for model: {model_name}")
    if payload.styleCaption and not (caption or instruction): raise RequestValidationError(f"styleCaption is not supported for model: {model_name}")
    if payload.instruction and not (instruction or caption): raise RequestValidationError(f"instruction is not supported for model: {model_name}")
    if payload.speedScale is not None and not getattr(model_cfg, "supports_speed_control", False): raise RequestValidationError(f"speedScale is not supported for model: {model_name}")
    if payload.styleStrength is not None and not getattr(model_cfg, "supports_style_strength", False): raise RequestValidationError(f"styleStrength is not supported for model: {model_name}")

def validate_instruction_requirements(payload: SpeakRequest, model_name: str, model_cfg: Any) -> None:
    prompt_controls_supported = bool(
        getattr(model_cfg, "supports_caption", False)
        or getattr(model_cfg, "supports_instruction", False)
    )
    if payload.styleStrength is not None and prompt_controls_supported and not (payload.caption or payload.instruction):
        raise RequestValidationError("styleStrength requires instruction or caption")

def validate_voice_design_instruction(
    payload: SpeakRequest,
    model_name: str,
    model_cfg: Any,
    *,
    reference_voice: Any | None = None,
) -> None:
    has_reference_voice = reference_voice is not None
    if (
        getattr(model_cfg, "supports_voice_design", False)
        and not has_reference_voice
        and not str(payload.instruction or "").strip()
    ):
        raise RequestValidationError(f"instruction is required for model: {model_name}")
