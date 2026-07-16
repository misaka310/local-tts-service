from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from ..errors import ProviderError
from ..models import ModelConfig
from .base import BaseRuntime, SynthesizeRequest, SynthesizeResult


@dataclass(frozen=True)
class IrodoriDirectAvailability:
    available: bool
    reason: str | None = None


class IrodoriVoiceDesignDirectRuntime(BaseRuntime):
    """Runs Irodori base and VoiceDesign checkpoints in a repo-local Python environment."""

    name = "irodori_voicedesign_direct"

    def __init__(
        self,
        *,
        output_dir: Path,
        models: dict[str, ModelConfig],
        root_dir: Path,
        python_executable: str,
        wrapper_dir: Path,
        checkpoint: str,
        timeout_sec: int = 1800,
        model_device: str = "auto",
        model_precision: str = "auto",
        codec_device: str = "auto",
        codec_precision: str = "fp32",
        codec_repo: str = "Aratako/Semantic-DACVAE-Japanese-32dim",
    ) -> None:
        self.output_dir = output_dir
        self.models = models
        self.root_dir = root_dir.resolve()
        self.python_executable = (
            str(self._resolve_repo_path(python_executable)) if str(python_executable).strip() else ""
        )
        self.wrapper_dir = self._resolve_repo_path(wrapper_dir)
        self.checkpoint = str(checkpoint).strip()
        self.timeout_sec = int(timeout_sec)
        self.model_device = str(model_device).strip() or "auto"
        self.model_precision = str(model_precision).strip() or "auto"
        self.codec_device = str(codec_device).strip() or self.model_device
        self.codec_precision = str(codec_precision).strip() or "fp32"
        raw_codec_repo = str(codec_repo).strip() or "Aratako/Semantic-DACVAE-Japanese-32dim"
        self.codec_repo = self._resolve_model_reference(raw_codec_repo)
        self._runtime_metadata_cache: dict[str, Any] | None = None

    @staticmethod
    def _resolved_device(requested_device: str, cuda_available: bool) -> str:
        requested = str(requested_device or "auto").strip().lower()
        if requested in {"", "auto"}:
            return "cuda" if cuda_available else "cpu"
        if requested.startswith("cuda") and not cuda_available:
            return "cpu"
        return requested

    def get_runtime_metadata(self) -> dict[str, Any]:
        if self._runtime_metadata_cache is not None:
            return dict(self._runtime_metadata_cache)

        requested = str(self.model_device or "auto").strip().lower() or "auto"
        metadata: dict[str, Any] = {
            "executionDevice": None,
            "cpuFallback": False,
            "performanceWarning": None,
        }
        if not self.python_executable or not Path(self.python_executable).is_file():
            self._runtime_metadata_cache = metadata
            return dict(metadata)

        probe = (
            "import json, torch; "
            "print(json.dumps({'cudaAvailable': bool(torch.cuda.is_available()), "
            "'torchVersion': str(torch.__version__)}))"
        )
        try:
            completed = subprocess.run(
                [self.python_executable, "-c", probe],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if completed.returncode == 0:
                output = (completed.stdout or "").strip().splitlines()
                payload = json.loads(output[-1]) if output else {}
                cuda_available = bool(payload.get("cudaAvailable"))
                resolved = self._resolved_device(requested, cuda_available)
                cpu_fallback = requested.startswith("cuda") and resolved == "cpu"
                metadata = {
                    "executionDevice": resolved,
                    "cpuFallback": cpu_fallback,
                    "performanceWarning": (
                        "Irodori\u306fCPU\u3067\u52d5\u4f5c\u3057\u3066\u3044\u307e\u3059\u3002GPU\u52d5\u4f5c\u3088\u308a\u5927\u5e45\u306b\u9045\u304f\u3001"
                        "\u97f3\u58f0\u751f\u6210\u306b\u6570\u5206\u304b\u304b\u308b\u5834\u5408\u304c\u3042\u308a\u307e\u3059\u3002"
                        if resolved == "cpu"
                        else None
                    ),
                }
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass

        self._runtime_metadata_cache = metadata
        return dict(metadata)

    def _resolve_repo_path(self, value: str | Path) -> Path:
        path = Path(str(value).strip())
        if not path.is_absolute():
            path = self.root_dir / path
        return path.resolve()

    def _resolve_model_reference(self, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        path = Path(raw)
        if (
            path.is_absolute()
            or raw.startswith(".")
            or raw.startswith("runtime/")
            or raw.startswith("runtime\\")
        ):
            return str(self._resolve_repo_path(raw))
        return raw

    def _checkpoint_for(self, model_cfg: ModelConfig) -> str:
        if model_cfg.checkpoint is not None:
            checkpoint_path = model_cfg.checkpoint
            if not checkpoint_path.is_absolute():
                checkpoint_path = self.root_dir / checkpoint_path
            return str(checkpoint_path.resolve())
        if self.checkpoint:
            return self._resolve_model_reference(self.checkpoint)
        return str(model_cfg.model_id or "").strip()

    @staticmethod
    def _local_reference_missing(value: str) -> bool:
        if not value:
            return True
        path = Path(value)
        return path.is_absolute() and not path.exists()

    def get_static_model_availability(
        self, model_name: str, model_cfg: ModelConfig
    ) -> IrodoriDirectAvailability:
        missing: list[str] = []
        if not self.python_executable or not Path(self.python_executable).is_file():
            missing.append(f"Python: {self.python_executable or '未設定'}")
        if not self.wrapper_dir.is_dir():
            missing.append(f"Irodoriソース: {self.wrapper_dir}")
        helper_script = self.root_dir / "scripts" / "run_irodori_voicedesign.py"
        if not helper_script.is_file():
            missing.append(f"実行スクリプト: {helper_script}")
        checkpoint = self._checkpoint_for(model_cfg)
        if not checkpoint:
            missing.append(f"モデル: {model_name}")
        elif self._local_reference_missing(checkpoint):
            missing.append(f"モデル: {checkpoint}")
        if self._local_reference_missing(self.codec_repo):
            missing.append(f"codec: {self.codec_repo}")
        if missing:
            return IrodoriDirectAvailability(
                False,
                "Irodoriのリポ内環境が不足しています。local-tts.bat -ForceSetup を実行してください: "
                + "; ".join(missing),
            )
        return IrodoriDirectAvailability(True, None)

    def get_model_availability(
        self, model_name: str, model_cfg: ModelConfig
    ) -> IrodoriDirectAvailability:
        static = self.get_static_model_availability(model_name, model_cfg)
        if not static.available:
            return static
        probe = (
            "import sys; "
            f"sys.path.insert(0, {str(self.wrapper_dir)!r}); "
            "import torch, dacvae; import irodori_tts.inference_runtime"
        )
        try:
            completed = subprocess.run(
                [self.python_executable, "-c", probe],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return IrodoriDirectAvailability(False, f"Irodori環境を確認できません: {exc}")
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "import failed").strip()
            return IrodoriDirectAvailability(False, f"Irodori環境のimportに失敗しました: {detail}")
        return IrodoriDirectAvailability(True, None)

    def synthesize(self, request: SynthesizeRequest) -> SynthesizeResult:
        model_cfg = self.models.get(request.model_name)
        if model_cfg is None:
            raise ProviderError(f"model is not configured: {request.model_name}")
        runtime_label = "VoiceDesign" if model_cfg.supports_caption else "Irodori"
        availability = self.get_static_model_availability(request.model_name, model_cfg)
        if not availability.available:
            raise ProviderError(
                availability.reason or f"Irodori model unavailable: {request.model_name}"
            )
        if request.caption and not model_cfg.supports_caption:
            raise ProviderError(f"caption is not supported for model: {request.model_name}")
        if request.reference_audio_path is not None and not request.reference_audio_path.is_file():
            raise ProviderError(f"referenceAudioPath not found: {request.reference_audio_path}")

        helper_script = (self.root_dir / "scripts" / "run_irodori_voicedesign.py").resolve()
        out_file = self.output_dir / f"{request.output_basename}.wav"
        out_file.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "text": request.text,
            "caption": request.caption,
            "referenceAudioPath": (
                str(request.reference_audio_path) if request.reference_audio_path else None
            ),
            "outputPath": str(out_file),
            "checkpoint": self._checkpoint_for(model_cfg),
            "wrapperDir": str(self.wrapper_dir),
            "modelDevice": self.model_device,
            "modelPrecision": self.model_precision,
            "codecDevice": self.codec_device,
            "codecPrecision": self.codec_precision,
            "codecRepo": self.codec_repo,
            "seed": request.seed,
            "durationScale": 1.0 / request.speed_scale if request.speed_scale else 1.0,
            "cfgScaleCaption": (
                request.style_strength
                if request.caption and request.style_strength is not None
                else (3.0 if request.caption else None)
            ),
        }

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        ) as fp:
            request_json_path = Path(fp.name)
            json.dump(payload, fp, ensure_ascii=False, indent=2)

        cmd = [self.python_executable, str(helper_script), str(request_json_path)]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                f"Irodori runtime timed out after {self.timeout_sec}s: {helper_script}"
            ) from exc
        finally:
            request_json_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            process_output = (proc.stderr or proc.stdout or "").strip()
            detail = f"process exited with code {proc.returncode}"
            if process_output:
                detail = f"{detail}\n{process_output}"
            else:
                detail = f"{detail} without stdout or stderr"
            raise ProviderError(f"{runtime_label} runtime failed: {detail}")

        stdout_text = (proc.stdout or "").strip()
        json_text = stdout_text.splitlines()[-1].strip() if "\n" in stdout_text else stdout_text
        try:
            result_payload: dict[str, Any] = json.loads(json_text or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"Irodori runtime returned invalid JSON: {stdout_text}"
            ) from exc

        output_path = Path(str(result_payload.get("outputPath") or out_file)).resolve()
        if not output_path.is_file():
            raise ProviderError(f"Irodori runtime did not create output file: {output_path}")

        caption_injection_mode = (
            str(result_payload.get("captionInjectionMode") or "").strip() or "none"
        )
        return SynthesizeResult(
            runtime=self.name,
            model=request.model_name,
            audio_path=output_path,
            caption_injection_mode=caption_injection_mode,
        )
