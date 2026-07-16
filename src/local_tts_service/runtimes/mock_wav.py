from __future__ import annotations

from pathlib import Path

from ..storage import write_silence_wav
from .base import BaseRuntime, SynthesizeRequest, SynthesizeResult


class MockWavRuntime(BaseRuntime):
    name = "mock_wav"

    def __init__(self, output_dir: Path, duration_sec: float = 1.2, sample_rate: int = 24000) -> None:
        self.output_dir = output_dir
        self.duration_sec = duration_sec
        self.sample_rate = sample_rate

    def synthesize(self, request: SynthesizeRequest) -> SynthesizeResult:
        output = self.output_dir / f"{request.output_basename}.wav"
        write_silence_wav(output, duration_sec=self.duration_sec, sample_rate=self.sample_rate)
        return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=output)
