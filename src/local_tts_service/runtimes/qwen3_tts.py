from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import importlib
import json
import re
import time

import soundfile as sf
import torch

from ..errors import ProviderError
from ..models import ModelConfig
from .base import BaseRuntime, SynthesizeRequest, SynthesizeResult


@dataclass(frozen=True)
class Qwen3TTSAvailability:
    available: bool
    reason: str | None
    model_path: Path | None


class Qwen3TTSRuntime(BaseRuntime):
    name = "qwen3_tts"

    def __init__(
        self,
        *,
        output_dir: Path,
        models: dict[str, ModelConfig],
        device: str = "auto",
        dtype: str = "auto",
        attn_implementation: str | None = None,
        hf_cache_dir: Path | None = None,
        vendor_dir: Path | None = None,
        allow_download: bool = False,
    ) -> None:
        self.output_dir = output_dir
        self.models = models
        self.device = device
        self.dtype = dtype
        self.attn_implementation = str(attn_implementation or "").strip() or None
        self.hf_cache_dir = hf_cache_dir
        self.vendor_dir = vendor_dir
        self.allow_download = allow_download
        self._loaded_models: dict[str, Any] = {}
        self._clone_prompt_cache: dict[str, Any] = {}
        self._log_path = (output_dir.parent / "logs" / "qwen3_tts_runtime.log").resolve()

    def get_model_availability(self, model_name: str, model_cfg: ModelConfig) -> Qwen3TTSAvailability:
        reasons: list[str] = []
        model_path = self._resolve_model_path(model_name, model_cfg)
        if model_path is None:
            reasons.append("model files not found in local Hugging Face cache or runtime/vendor/qwen3-tts")
        if not self._has_dependency("qwen_tts"):
            reasons.append("qwen-tts Python package is not installed in the service environment")
        if not self._has_dependency("transformers"):
            reasons.append("transformers Python package is not installed in the service environment")
        return Qwen3TTSAvailability(
            available=not reasons,
            reason="; ".join(reasons) if reasons else None,
            model_path=model_path,
        )

    def synthesize(self, request: SynthesizeRequest) -> SynthesizeResult:
        model_cfg = self.models.get(request.model_name)
        if model_cfg is None:
            raise ProviderError(f"unknown model config: {request.model_name}")

        availability = self.get_model_availability(request.model_name, model_cfg)
        if not availability.available or availability.model_path is None:
            raise ProviderError(availability.reason or f"model unavailable: {request.model_name}")

        language = request.language or model_cfg.default_language or "Japanese"
        request_label = request.request_id or request.output_basename or request.model_name
        timings: dict[str, Any] = {
            "importSec": None,
            "loadModelSec": None,
            "loadReferenceSec": None,
            "generateSec": None,
            "saveSec": None,
            "totalSec": None,
        }
        total_t0 = time.perf_counter()

        load_t0 = time.perf_counter()
        self._log(f"{request_label} start load model")
        model = self._load_model(request.model_name, availability.model_path)
        self._sync_cuda()
        model_device = getattr(model, "device", None)
        model_dtype = getattr(getattr(model, "model", None), "dtype", None)
        self._log(
            f"{request_label} done load model elapsed={time.perf_counter() - load_t0:.3f}s "
            f"device={model_device} dtype={model_dtype}"
        )
        timings["loadModelSec"] = round(time.perf_counter() - load_t0, 3)
        output_path = self.output_dir / f"{request.output_basename}.wav"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if model_cfg.supports_voice_design:
            instruction = str(request.instruction or request.caption or "").strip()
            if not instruction:
                raise ProviderError(f"instruction is required for model: {request.model_name}")
            gen_t0 = time.perf_counter()
            self._log(f"{request_label} start generate")
            wavs, sample_rate = model.generate_voice_design(
                text=request.text,
                language=language,
                instruct=instruction,
                seed=request.seed,
                non_streaming_mode=True,
            )
            self._sync_cuda()
            self._log(
                f"{request_label} done generate elapsed={time.perf_counter() - gen_t0:.3f}s "
                f"sample_rate={sample_rate} num_wavs={len(wavs)}"
            )
            timings["generateSec"] = round(time.perf_counter() - gen_t0, 3)
        elif model_cfg.supports_voice_clone:
            if request.reference_audio_path is None:
                raise ProviderError(f"voice.wav is required for model: {request.model_name}")
            if request.reference_text_path is None or not request.reference_text_path.is_file():
                raise ProviderError(f"voice.txt is required for model: {request.model_name}")
            ref_text = request.reference_text_path.read_text(encoding="utf-8-sig").strip()
            if not ref_text:
                raise ProviderError(f"voice.txt is empty for voiceId: {request.voice_id}")

            cache_key = self._build_prompt_cache_key(request.model_name, request.reference_audio_path, request.reference_text_path)
            prompt = self._clone_prompt_cache.get(cache_key)
            if prompt is None:
                ref_t0 = time.perf_counter()
                self._log(f"{request_label} start load reference")
                prompt = model.create_voice_clone_prompt(
                    ref_audio=str(request.reference_audio_path),
                    ref_text=ref_text,
                    x_vector_only_mode=False,
                )
                self._sync_cuda()
                self._log(
                    f"{request_label} done load reference elapsed={time.perf_counter() - ref_t0:.3f}s "
                    f"prompt_items={len(prompt)}"
                )
                timings["loadReferenceSec"] = round(time.perf_counter() - ref_t0, 3)
                self._clone_prompt_cache[cache_key] = prompt
            else:
                self._log(f"{request_label} reuse cached reference prompt")
                timings["loadReferenceSec"] = 0.0
            gen_t0 = time.perf_counter()
            self._log(f"{request_label} start generate")
            wavs, sample_rate = model.generate_voice_clone(
                text=request.text,
                language=language,
                voice_clone_prompt=prompt,
                seed=request.seed,
                non_streaming_mode=True,
            )
            self._sync_cuda()
            self._log(
                f"{request_label} done generate elapsed={time.perf_counter() - gen_t0:.3f}s "
                f"sample_rate={sample_rate} num_wavs={len(wavs)}"
            )
            timings["generateSec"] = round(time.perf_counter() - gen_t0, 3)
        else:
            raise ProviderError(f"unsupported Qwen3-TTS mode for model: {request.model_name}")

        save_t0 = time.perf_counter()
        self._log(f"{request_label} start save wav")
        sf.write(output_path, wavs[0], sample_rate)
        self._log(
            f"{request_label} done save wav elapsed={time.perf_counter() - save_t0:.3f}s "
            f"output={output_path} bytes={output_path.stat().st_size}"
        )
        timings["saveSec"] = round(time.perf_counter() - save_t0, 3)
        timings["totalSec"] = round(time.perf_counter() - total_t0, 3)
        return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=output_path, timings=timings)

    def _build_prompt_cache_key(self, model_name: str, ref_audio: Path, ref_text: Path) -> str:
        audio_stat = ref_audio.stat()
        text_stat = ref_text.stat()
        return json.dumps(
            {
                "model": model_name,
                "audio": str(ref_audio.resolve()),
                "audioMtimeNs": audio_stat.st_mtime_ns,
                "text": str(ref_text.resolve()),
                "textMtimeNs": text_stat.st_mtime_ns,
            },
            sort_keys=True,
        )

    def _load_model(self, model_name: str, model_path: Path) -> Any:
        if model_name in self._loaded_models:
            return self._loaded_models[model_name]

        try:
            qwen_tts = importlib.import_module("qwen_tts")
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"failed to import qwen_tts: {exc}") from exc

        load_kwargs: dict[str, Any] = {
            "pretrained_model_name_or_path": str(model_path),
            "local_files_only": not self.allow_download,
        }
        resolved_device = self._resolve_device()
        if resolved_device:
            load_kwargs["device_map"] = resolved_device
        resolved_dtype = self._resolve_dtype(resolved_device)
        if resolved_dtype is not None:
            load_kwargs["dtype"] = resolved_dtype
        if self.attn_implementation:
            load_kwargs["attn_implementation"] = self.attn_implementation

        try:
            loaded = qwen_tts.Qwen3TTSModel.from_pretrained(**load_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"failed to load Qwen3-TTS model {model_name}: {exc}") from exc
        self._loaded_models[model_name] = loaded
        return loaded

    def _resolve_model_path(self, model_name: str, model_cfg: ModelConfig) -> Path | None:
        candidates: list[Path] = []
        if self.vendor_dir is not None:
            model_id = str(model_cfg.model_id or "").strip()
            setup_dir_name = re.sub(r"[^A-Za-z0-9_.-]+", "__", model_id)
            candidates.extend(
                [
                    self.vendor_dir / model_name,
                    self.vendor_dir / model_id.split("/")[-1],
                    self.vendor_dir / setup_dir_name,
                ]
            )

        model_id = str(model_cfg.model_id or "").strip()
        if model_id:
            hub_root = self.hf_cache_dir or (Path.home() / ".cache" / "huggingface" / "hub")
            parts = model_id.split("/")
            if len(parts) == 2:
                repo_dir = hub_root / f"models--{parts[0]}--{parts[1]}"
                snapshots_dir = repo_dir / "snapshots"
                if snapshots_dir.is_dir():
                    candidates.extend(sorted((item for item in snapshots_dir.iterdir() if item.is_dir()), reverse=True))

        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        return None

    def _resolve_device(self) -> str:
        configured = str(self.device or "auto").strip().lower()
        if configured and configured != "auto":
            return configured
        return "cuda:0" if torch.cuda.is_available() else "cpu"

    def _resolve_dtype(self, device: str) -> Any | None:
        configured = str(self.dtype or "auto").strip().lower()
        if configured in {"", "auto"}:
            return torch.bfloat16 if device.startswith("cuda") else torch.float32
        mapping = {
            "bf16": torch.bfloat16,
            "bfloat16": torch.bfloat16,
            "fp16": torch.float16,
            "float16": torch.float16,
            "fp32": torch.float32,
            "float32": torch.float32,
        }
        return mapping.get(configured)

    def _has_dependency(self, module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except Exception:  # noqa: BLE001
            return False
        return True

    def _sync_cuda(self) -> None:
        if torch.cuda.is_available():
            torch.cuda.synchronize()

    def _log(self, message: str) -> None:
        timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")
        line = f"[{timestamp}] {message}"
        print(line, flush=True)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")
