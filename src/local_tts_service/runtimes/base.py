from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SynthesizeRequest:
    text: str
    request_id: str
    model_name: str
    output_basename: str
    seed: int | None = None
    speed_scale: float | None = None
    style_strength: float | None = None
    caption: str | None = None
    instruction: str | None = None
    language: str | None = None
    voice_description: str | None = None
    voice_id: str | None = None
    reference_audio_path: Path | None = None
    reference_text_path: Path | None = None
    output_format: str = "wav"


@dataclass(frozen=True)
class SynthesizeResult:
    runtime: str
    model: str
    audio_path: Path
    caption_injection_mode: str | None = None
    timings: dict[str, Any] | None = None


class BaseRuntime:
    name: str = "base"

    def synthesize(self, request: SynthesizeRequest) -> SynthesizeResult:
        raise NotImplementedError
