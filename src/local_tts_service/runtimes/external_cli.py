from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
from typing import Any

from ..errors import ProviderError
from ..models import ModelConfig
from .base import BaseRuntime, SynthesizeRequest, SynthesizeResult


@dataclass(frozen=True)
class ExternalCliAvailability:
    available: bool
    reason: str | None = None


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Terminate the command and its descendants after a timeout."""

    if process.poll() is not None:
        return
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode == 0:
            return
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except (OSError, ProcessLookupError):
            pass
    if process.poll() is None:
        process.kill()


def _run_external_command(
    command: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    popen_kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


class ExternalCliRuntime(BaseRuntime):
    name = "external_cli"

    def __init__(
        self,
        *,
        output_dir: Path,
        models: dict[str, ModelConfig],
        root_dir: Path,
        request_dir: Path,
        commands: dict[str, Any],
        availability_commands: dict[str, Any] | None = None,
        timeout_sec: int = 1800,
        dry_run: bool = False,
    ) -> None:
        self.output_dir = output_dir
        self.models = models
        self.root_dir = root_dir
        self.request_dir = request_dir
        self.commands = commands
        self.availability_commands = availability_commands or {}
        self.timeout_sec = timeout_sec
        self.dry_run = dry_run

    def get_static_model_availability(self, model_name: str, model_cfg: ModelConfig) -> ExternalCliAvailability:
        command_key = str(model_cfg.external_command_key or "").strip()
        if not command_key:
            return ExternalCliAvailability(False, f"externalCommandKey is not configured for model: {model_name}")

        command = self.commands.get(command_key)
        if not isinstance(command, list) or not command:
            return ExternalCliAvailability(False, f"external command is not configured: {command_key}")

        missing_scripts = self._missing_script_paths(command)
        if missing_scripts:
            return ExternalCliAvailability(False, "missing external command script(s): " + ", ".join(missing_scripts))

        if model_cfg.requires_trained_checkpoint and model_cfg.checkpoint_dir is not None and not model_cfg.checkpoint_dir.exists():
            return ExternalCliAvailability(False, f"trained checkpoint directory not found: {model_cfg.checkpoint_dir}")

        return ExternalCliAvailability(True, None)

    def get_model_availability(self, model_name: str, model_cfg: ModelConfig) -> ExternalCliAvailability:
        static_availability = self.get_static_model_availability(model_name, model_cfg)
        if not static_availability.available:
            return static_availability

        command_key = str(model_cfg.external_command_key or "").strip()
        availability_command = self.availability_commands.get(command_key)
        if isinstance(availability_command, list) and availability_command:
            formatted_command = [self._format_availability_arg(str(part), model_name=model_name) for part in availability_command]
            missing_availability_scripts = self._missing_script_paths(formatted_command)
            if missing_availability_scripts:
                return ExternalCliAvailability(
                    False,
                    "missing availability check script(s): " + ", ".join(missing_availability_scripts),
                )
            try:
                completed = _run_external_command(
                    formatted_command,
                    cwd=self.root_dir,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                    timeout=60,
                )
            except subprocess.TimeoutExpired:
                return ExternalCliAvailability(False, f"モデル環境の確認が60秒でタイムアウトしました: {model_name}")
            except OSError as exc:
                return ExternalCliAvailability(False, f"モデル環境の確認を開始できません: {model_name}: {exc}")
            if completed.returncode != 0:
                details = ((completed.stderr or "").strip() or (completed.stdout or "").strip() or f"exit code {completed.returncode}")
                return ExternalCliAvailability(False, details)

        return ExternalCliAvailability(True, None)

    def synthesize(self, request: SynthesizeRequest) -> SynthesizeResult:
        model_cfg = self.models.get(request.model_name)
        if model_cfg is None:
            raise ProviderError(f"unknown model config: {request.model_name}")

        availability = self.get_model_availability(request.model_name, model_cfg)
        if not availability.available:
            raise ProviderError(availability.reason or f"model unavailable: {request.model_name}")

        command_key = str(model_cfg.external_command_key or "").strip()
        raw_command = self.commands.get(command_key)
        if not isinstance(raw_command, list) or not raw_command:
            raise ProviderError(f"external command is not configured: {command_key}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.request_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{request.output_basename}.wav"
        request_json_path = self.request_dir / f"{request.output_basename}.json"

        payload = self._build_payload(request, model_cfg, output_path)
        request_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        command = [
            self._format_arg(str(part), request_json_path=request_json_path, output_path=output_path)
            for part in raw_command
        ]

        if self.dry_run:
            raise ProviderError("external_cli dryRun is enabled; command was not executed")

        try:
            completed = _run_external_command(
                command,
                cwd=self.root_dir,
                timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"external command timed out after {self.timeout_sec}s: {command_key}") from exc
        except OSError as exc:
            raise ProviderError(f"failed to start external command {command_key}: {exc}") from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            details = stderr or stdout or f"exit code {completed.returncode}"
            raise ProviderError(f"external command failed: {command_key}: {details}")

        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise ProviderError(f"external command did not create output wav: {output_path}")

        return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=output_path)

    def _build_payload(self, request: SynthesizeRequest, model_cfg: ModelConfig, output_path: Path) -> dict[str, Any]:
        checkpoint_dir = str(model_cfg.checkpoint_dir) if model_cfg.checkpoint_dir is not None else ""
        return {
            "text": request.text,
            "requestId": request.request_id,
            "model": request.model_name,
            "modelId": model_cfg.model_id,
            "voiceId": request.voice_id,
            "language": request.language or model_cfg.default_language,
            "seed": request.seed,
            "speedScale": request.speed_scale,
            "styleStrength": request.style_strength,
            "caption": request.caption,
            "instruction": request.instruction,
            "voiceDescription": request.voice_description or model_cfg.voice_description,
            "referenceAudioPath": str(request.reference_audio_path) if request.reference_audio_path else "",
            "referenceTextPath": str(request.reference_text_path) if request.reference_text_path else "",
            "checkpointDir": checkpoint_dir,
            "textSplitMethod": model_cfg.text_split_method,
            "outputPath": str(output_path),
            "outputFormat": request.output_format,
        }

    def _format_arg(self, value: str, *, request_json_path: Path, output_path: Path) -> str:
        return (
            value.replace("{request_json}", str(request_json_path))
            .replace("{output_path}", str(output_path))
            .replace("{repo_root}", str(self.root_dir))
        )

    def _format_availability_arg(self, value: str, *, model_name: str) -> str:
        return value.replace("{model}", model_name).replace("{repo_root}", str(self.root_dir))

    def _missing_script_paths(self, command: list[Any]) -> list[str]:
        missing: list[str] = []
        for item in command:
            value = str(item)
            normalized = value.replace("\\", "/")
            if "/scripts/" not in normalized and not normalized.startswith("./scripts/") and not normalized.startswith("scripts/"):
                continue
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = self.root_dir / candidate
            if not candidate.exists():
                missing.append(str(candidate))
        return missing
