from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any
from uuid import uuid4

from ..errors import ProviderError
from ..models import ModelConfig
from .base import BaseRuntime, SynthesizeRequest, SynthesizeResult


_RESPONSE_PREFIX = "LOCAL_TTS_JSON:"


@dataclass(frozen=True)
class IrodoriDirectAvailability:
    available: bool
    reason: str | None = None


class IrodoriVoiceDesignDirectRuntime(BaseRuntime):
    """Runs Irodori in one persistent, strictly offline worker process."""

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
        startup_timeout_sec: int = 1800,
        model_device: str = "auto",
        model_precision: str = "auto",
        codec_device: str = "auto",
        codec_precision: str = "fp32",
        codec_repo: str = "./runtime/models/irodori/Semantic-DACVAE-Japanese-32dim",
        text_processor_repo: str = "llm-jp/llm-jp-3-150m",
        text_processor_dir: str | Path = "./runtime/models/irodori/tokenizers/llm-jp-3-150m",
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
        self.startup_timeout_sec = int(startup_timeout_sec)
        self.model_device = str(model_device).strip() or "auto"
        self.model_precision = str(model_precision).strip() or "auto"
        self.codec_device = str(codec_device).strip() or self.model_device
        self.codec_precision = str(codec_precision).strip() or "fp32"
        self.codec_repo = str(self._resolve_repo_path(codec_repo))
        self.text_processor_repo = str(text_processor_repo).strip() or "llm-jp/llm-jp-3-150m"
        self.text_processor_dir = self._resolve_repo_path(text_processor_dir)
        self._runtime_metadata_cache: dict[str, Any] | None = None
        self._worker: subprocess.Popen[str] | None = None
        self._worker_events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._worker_lock = threading.Lock()
        self._stderr_lines: deque[str] = deque(maxlen=60)
        self._prepared_models: set[str] = set()
        self._startup_errors: dict[str, str] = {}

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
                env=self._offline_environment(),
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

    def _checkpoint_for(self, model_cfg: ModelConfig) -> str:
        if model_cfg.checkpoint is not None:
            checkpoint_path = model_cfg.checkpoint
            if not checkpoint_path.is_absolute():
                checkpoint_path = self.root_dir / checkpoint_path
            return str(checkpoint_path.resolve())
        if self.checkpoint:
            return str(self._resolve_repo_path(self.checkpoint))
        return ""

    def _display_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root_dir).as_posix()
        except ValueError:
            return str(path.resolve())

    @staticmethod
    def _text_processor_files_present(path: Path) -> bool:
        if not path.is_dir() or not (path / "tokenizer_config.json").is_file():
            return False
        candidates = (
            "tokenizer.json",
            "tokenizer.model",
            "spiece.model",
            "sentencepiece.bpe.model",
            "vocab.json",
        )
        return any((path / name).is_file() for name in candidates)

    def get_static_model_availability(
        self, model_name: str, model_cfg: ModelConfig
    ) -> IrodoriDirectAvailability:
        missing: list[str] = []
        if not self.python_executable or not Path(self.python_executable).is_file():
            missing.append(f"Pythonがありません: {self.python_executable or '未設定'}")
        if not self.wrapper_dir.is_dir():
            missing.append(f"Irodori runtimeがありません: {self._display_path(self.wrapper_dir)}")
        helper_script = self.root_dir / "scripts" / "run_irodori_voicedesign.py"
        if not helper_script.is_file():
            missing.append(f"実行スクリプトがありません: {self._display_path(helper_script)}")
        checkpoint_value = self._checkpoint_for(model_cfg)
        checkpoint = Path(checkpoint_value) if checkpoint_value else None
        if checkpoint is None or not checkpoint.is_file():
            expected = checkpoint or (
                self.root_dir / "runtime" / "models" / "irodori" / model_name / "model.safetensors"
            )
            missing.append(f"checkpointがありません: {self._display_path(expected)}")
        codec_path = Path(self.codec_repo)
        if not codec_path.exists():
            missing.append(f"codecがありません: {self._display_path(codec_path)}")
        if not self._text_processor_files_present(self.text_processor_dir):
            missing.append(
                "Tokenizerがありません: "
                f"{self._display_path(self.text_processor_dir)} に必要なTokenizer一式を配置してください"
            )
        if missing:
            return IrodoriDirectAvailability(False, " / ".join(missing))
        return IrodoriDirectAvailability(True, None)

    def get_model_availability(
        self, model_name: str, model_cfg: ModelConfig
    ) -> IrodoriDirectAvailability:
        static = self.get_static_model_availability(model_name, model_cfg)
        if not static.available:
            return static
        startup_error = self._startup_errors.get(model_name)
        if startup_error:
            return IrodoriDirectAvailability(False, startup_error)
        return IrodoriDirectAvailability(True, None)

    @staticmethod
    def _offline_environment() -> dict[str, str]:
        env = os.environ.copy()
        for name in (
            "HF_HUB_OFFLINE",
            "TRANSFORMERS_OFFLINE",
            "HF_DATASETS_OFFLINE",
            "HF_HUB_DISABLE_TELEMETRY",
            "DO_NOT_TRACK",
            "PYTHONUTF8",
        ):
            env[name] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _read_worker_stdout(self, stream) -> None:  # type: ignore[no-untyped-def]
        for raw_line in iter(stream.readline, ""):
            line = raw_line.strip()
            if not line.startswith(_RESPONSE_PREFIX):
                continue
            try:
                event = json.loads(line[len(_RESPONSE_PREFIX) :])
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                self._worker_events.put(event)

    def _read_worker_stderr(self, stream) -> None:  # type: ignore[no-untyped-def]
        for raw_line in iter(stream.readline, ""):
            line = raw_line.rstrip()
            if line:
                self._stderr_lines.append(line)

    def _worker_is_alive(self) -> bool:
        return self._worker is not None and self._worker.poll() is None

    def _drain_worker_events(self) -> None:
        while True:
            try:
                self._worker_events.get_nowait()
            except queue.Empty:
                return

    def _stop_worker_process(self, worker: subprocess.Popen[str]) -> None:
        if worker.poll() is not None:
            return
        worker.terminate()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=5)

    def _mark_worker_failed(
        self,
        reason: str,
        *,
        worker: subprocess.Popen[str] | None = None,
        terminate: bool = False,
    ) -> None:
        affected_worker = worker or self._worker
        if worker is not None and self._worker is not worker:
            return
        prepared_models = tuple(self._prepared_models)
        self._worker = None
        self._prepared_models.clear()
        message = f"Irodori runtimeが停止しました: {reason}. サービスを再起動してください"
        for model_name in prepared_models:
            self._startup_errors[model_name] = message
        if terminate and affected_worker is not None:
            self._stop_worker_process(affected_worker)
        self._drain_worker_events()

    def _start_worker(self) -> None:
        if self._worker_is_alive():
            return
        if self._worker is not None:
            self._mark_worker_failed("worker process exited", worker=self._worker)
        self._stderr_lines.clear()
        helper_script = (self.root_dir / "scripts" / "run_irodori_voicedesign.py").resolve()
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = int(subprocess.CREATE_NO_WINDOW)
        try:
            self._worker = subprocess.Popen(
                [self.python_executable, str(helper_script), "--worker"],
                cwd=str(self.root_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=self._offline_environment(),
                creationflags=creationflags,
            )
        except OSError as exc:
            raise ProviderError(f"Irodori runtimeを起動できません: {exc}") from exc
        assert self._worker.stdout is not None
        assert self._worker.stderr is not None
        threading.Thread(
            target=self._read_worker_stdout,
            args=(self._worker.stdout,),
            daemon=True,
            name="irodori-worker-stdout",
        ).start()
        threading.Thread(
            target=self._read_worker_stderr,
            args=(self._worker.stderr,),
            daemon=True,
            name="irodori-worker-stderr",
        ).start()

    def _request_worker(self, payload: dict[str, Any], timeout_sec: int) -> dict[str, Any]:
        request_id = str(payload.get("protocolRequestId") or uuid4().hex)
        payload["protocolRequestId"] = request_id
        with self._worker_lock:
            self._start_worker()
            worker = self._worker
            if worker is None or worker.stdin is None or worker.poll() is not None:
                raise ProviderError("Irodori runtimeが起動していません")
            try:
                worker.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                worker.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._mark_worker_failed(str(exc), worker=worker, terminate=True)
                raise ProviderError(f"Irodori runtimeへ要求を送信できません: {exc}") from exc
            deadline = time.monotonic() + max(1, int(timeout_sec))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._mark_worker_failed(
                        f"request timed out after {timeout_sec}s",
                        worker=worker,
                        terminate=True,
                    )
                    raise ProviderError(f"Irodori runtime timed out after {timeout_sec}s")
                try:
                    event = self._worker_events.get(timeout=min(remaining, 1.0))
                except queue.Empty:
                    if worker.poll() is not None:
                        detail = "\n".join(self._stderr_lines) or f"exit code {worker.returncode}"
                        self._mark_worker_failed(detail, worker=worker)
                        raise ProviderError(f"Irodori runtimeが終了しました: {detail}")
                    continue
                if str(event.get("protocolRequestId") or "") != request_id:
                    continue
                if not bool(event.get("ok")):
                    detail = str(event.get("error") or "unknown Irodori worker error")
                    raise ProviderError(detail)
                return event

    def _runtime_payload(self, model_name: str, model_cfg: ModelConfig) -> dict[str, Any]:
        return {
            "modelName": model_name,
            "checkpoint": self._checkpoint_for(model_cfg),
            "wrapperDir": str(self.wrapper_dir),
            "modelDevice": self.model_device,
            "modelPrecision": self.model_precision,
            "codecDevice": self.codec_device,
            "codecPrecision": self.codec_precision,
            "codecRepo": self.codec_repo,
            "textProcessorRepo": self.text_processor_repo,
            "textProcessorDir": str(self.text_processor_dir),
        }

    def prepare_model(self, model_name: str) -> IrodoriDirectAvailability:
        model_cfg = self.models.get(model_name)
        if model_cfg is None or model_cfg.runtime != self.name:
            return IrodoriDirectAvailability(False, f"model is not configured for Irodori: {model_name}")
        static = self.get_static_model_availability(model_name, model_cfg)
        if not static.available:
            self._startup_errors[model_name] = static.reason or "Irodoriの必要ファイルが不足しています"
            return static
        if model_name in self._prepared_models and self._worker_is_alive():
            return IrodoriDirectAvailability(True, None)
        if model_name in self._prepared_models:
            self._mark_worker_failed("worker process exited", worker=self._worker)
        payload = {"action": "preload", **self._runtime_payload(model_name, model_cfg)}
        try:
            result = self._request_worker(payload, self.startup_timeout_sec)
        except ProviderError as exc:
            reason = f"Irodoriの事前ロードに失敗しました: {exc}"
            self._startup_errors[model_name] = reason
            return IrodoriDirectAvailability(False, reason)
        if int(result.get("externalNetworkAttempts") or 0) != 0:
            reason = "Irodoriの事前ロード中に外部通信が検出されました"
            self._startup_errors[model_name] = reason
            return IrodoriDirectAvailability(False, reason)
        self._prepared_models.add(model_name)
        self._startup_errors.pop(model_name, None)
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

        if request.model_name not in self._prepared_models:
            prepared = self.prepare_model(request.model_name)
            if not prepared.available:
                raise ProviderError(
                    prepared.reason
                    or "Irodori runtimeの準備が完了していません。サービスを再起動してください"
                )
        elif not self._worker_is_alive():
            self._mark_worker_failed("worker process exited", worker=self._worker)
            reason = self._startup_errors.get(request.model_name)
            raise ProviderError(
                reason
                or "Irodori runtimeの準備が完了していません。サービスを再起動してください"
            )

        out_file = self.output_dir / f"{request.output_basename}.wav"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "action": "synthesize",
            **self._runtime_payload(request.model_name, model_cfg),
            "text": request.text,
            "caption": request.caption,
            "referenceAudioPath": (
                str(request.reference_audio_path) if request.reference_audio_path else None
            ),
            "enableReferenceWithCaption": bool(
                request.caption and request.reference_audio_path
            ),
            "outputPath": str(out_file),
            "seed": request.seed,
            "durationScale": 1.0 / request.speed_scale if request.speed_scale else 1.0,
            "cfgScaleCaption": (
                request.style_strength
                if request.caption and request.style_strength is not None
                else (3.0 if request.caption else None)
            ),
        }
        try:
            result_payload = self._request_worker(payload, self.timeout_sec)
        except ProviderError as exc:
            raise ProviderError(f"{runtime_label} runtime failed: {exc}") from exc
        if int(result_payload.get("externalNetworkAttempts") or 0) != 0:
            raise ProviderError(f"{runtime_label} runtime attempted external network access")

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

    def close(self) -> None:
        worker = self._worker
        self._worker = None
        self._prepared_models.clear()
        if worker is None:
            return
        try:
            if worker.poll() is None and worker.stdin is not None:
                worker.stdin.write(
                    json.dumps(
                        {"action": "shutdown", "protocolRequestId": uuid4().hex},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                worker.stdin.flush()
                worker.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            self._stop_worker_process(worker)
