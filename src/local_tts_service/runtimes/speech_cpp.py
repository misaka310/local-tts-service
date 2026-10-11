from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ProviderError
from ..models import ModelConfig
from .base import BaseRuntime, SynthesizeRequest, SynthesizeResult

_METRIC_RE = re.compile(r"^metrics\.(?P<name>[A-Za-z0-9_.]+)=(?P<value>.+)$")


@dataclass(frozen=True)
class SpeechCppAvailability:
    available: bool
    reason: str | None = None


class SpeechCppRuntime(BaseRuntime):
    """Run Irodori through the audio.cpp/speech.cpp GGUF CLI."""

    name = "speech_cpp"

    def __init__(
        self,
        *,
        output_dir: Path,
        models: dict[str, ModelConfig],
        root_dir: Path,
        executable: str | Path,
        model_path: str | Path,
        backend: str = "cuda",
        device: int = 0,
        timeout_sec: int = 1800,
    ) -> None:
        self.output_dir = output_dir.resolve()
        self.models = models
        self.root_dir = root_dir.resolve()
        self.executable = self._resolve_path(executable)
        self.model_path = self._resolve_path(model_path)
        self.backend = str(backend or "cuda").strip().lower() or "cuda"
        self.device = int(device)
        self.timeout_sec = int(timeout_sec)

    def _resolve_path(self, value: str | Path) -> Path:
        path = Path(str(value).strip()).expanduser()
        if not path.is_absolute():
            path = self.root_dir / path
        return path.resolve()

    @staticmethod
    def _creationflags() -> int:
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            return int(subprocess.CREATE_NO_WINDOW)
        return 0

    def get_static_model_availability(
        self, model_name: str, model_cfg: ModelConfig
    ) -> SpeechCppAvailability:
        missing: list[str] = []
        if not self.executable.is_file():
            missing.append(f"audiocpp_cliがありません: {self.executable}")
        if not self.model_path.is_file():
            missing.append(f"GGUFモデルがありません: {self.model_path}")
        if missing:
            return SpeechCppAvailability(False, " / ".join(missing))
        if model_cfg.runtime != self.name:
            return SpeechCppAvailability(False, f"model is not configured for speech.cpp: {model_name}")
        return SpeechCppAvailability(True, None)

    def get_model_availability(
        self, model_name: str, model_cfg: ModelConfig
    ) -> SpeechCppAvailability:
        return self.get_static_model_availability(model_name, model_cfg)

    @staticmethod
    def _runtime_options(model_cfg: ModelConfig) -> dict[str, Any]:
        options = dict(model_cfg.runtime_options or {})
        allowed = {"numInferenceSteps", "optimizationProfile", "codecPrecision"}
        unknown = sorted(set(options) - allowed)
        if unknown:
            raise ProviderError("unsupported speech.cpp runtimeOptions: " + ", ".join(unknown))
        return options

    def build_command(self, request: SynthesizeRequest) -> tuple[list[str], Path]:
        model_cfg = self.models.get(request.model_name)
        if model_cfg is None:
            raise ProviderError(f"model is not configured: {request.model_name}")
        options = self._runtime_options(model_cfg)
        steps = int(options.get("numInferenceSteps") or 0)
        if steps <= 0 and str(options.get("optimizationProfile") or "").strip() == "low_latency_8":
            steps = 8
        if steps <= 0:
            steps = 40

        output_path = (self.output_dir / f"{request.output_basename}.wav").resolve()
        has_reference = request.reference_audio_path is not None
        task = "clon" if has_reference else "tts"
        language = str(request.language or model_cfg.default_language or "ja").strip() or "ja"

        command = [
            str(self.executable),
            "--task",
            task,
            "--family",
            "irodori_tts",
            "--model",
            str(self.model_path),
            "--backend",
            self.backend,
            "--device",
            str(self.device),
            "--language",
            language,
            "--text",
            request.text,
        ]
        if has_reference:
            command.extend(["--voice-ref", str(request.reference_audio_path.resolve())])
        command.extend(
            [
                "--request-option",
                f"no_ref={'false' if has_reference else 'true'}",
                "--request-option",
                f"num_inference_steps={steps}",
            ]
        )
        if request.seed is not None:
            command.extend(["--request-option", f"seed={int(request.seed)}"])
        if request.speed_scale is not None:
            command.extend(
                [
                    "--request-option",
                    f"duration_scale={1.0 / float(request.speed_scale):g}",
                ]
            )
        command.extend(["--out", str(output_path), "--metrics"])
        return command, output_path

    @staticmethod
    def _parse_metrics(stdout: str, *, process_wall_sec: float) -> dict[str, Any]:
        metrics: dict[str, Any] = {"processWallSec": process_wall_sec}
        for raw_line in stdout.splitlines():
            match = _METRIC_RE.match(raw_line.strip())
            if match is None:
                continue
            name = match.group("name")
            raw_value = match.group("value").strip()
            try:
                value: Any = float(raw_value)
            except ValueError:
                value = raw_value
            metrics[name] = value
        return metrics

    def synthesize(self, request: SynthesizeRequest) -> SynthesizeResult:
        model_cfg = self.models.get(request.model_name)
        if model_cfg is None:
            raise ProviderError(f"model is not configured: {request.model_name}")
        availability = self.get_static_model_availability(request.model_name, model_cfg)
        if not availability.available:
            raise ProviderError(availability.reason or "speech.cpp is unavailable")
        if request.caption:
            raise ProviderError(f"caption is not supported for model: {request.model_name}")
        if request.reference_audio_path is not None and not request.reference_audio_path.is_file():
            raise ProviderError(f"referenceAudioPath not found: {request.reference_audio_path}")

        command, output_path = self.build_command(request)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.executable.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_sec,
                check=False,
                creationflags=self._creationflags(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProviderError(f"speech.cpp runtime failed: {exc}") from exc
        process_wall_sec = time.perf_counter() - started
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise ProviderError(
                f"speech.cpp runtime failed with exit code {completed.returncode}: {detail}"
            )
        if not output_path.is_file():
            raise ProviderError(f"speech.cpp runtime did not create output file: {output_path}")

        return SynthesizeResult(
            runtime=self.name,
            model=request.model_name,
            audio_path=output_path,
            caption_injection_mode="none",
            timings=self._parse_metrics(completed.stdout or "", process_wall_sec=process_wall_sec),
        )
