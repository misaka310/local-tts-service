from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
import traceback
from dataclasses import fields
from pathlib import Path
import wave

for _offline_name in (
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "HF_DATASETS_OFFLINE",
    "HF_HUB_DISABLE_TELEMETRY",
    "DO_NOT_TRACK",
):
    os.environ[_offline_name] = "1"

import torch

_RESPONSE_PREFIX = "LOCAL_TTS_JSON:"
_EXTERNAL_NETWORK_ATTEMPTS: list[str] = []
_NETWORK_GUARD_INSTALLED = False


def _install_external_network_guard() -> None:
    global _NETWORK_GUARD_INSTALLED
    if _NETWORK_GUARD_INSTALLED:
        return
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection

    def is_local(address: object) -> bool:
        if not isinstance(address, tuple) or not address:
            return False
        host = str(address[0]).strip().lower()
        return host in {"127.0.0.1", "::1", "localhost"}

    def guarded_connect(sock, address):  # noqa: ANN001
        if is_local(address):
            return original_connect(sock, address)
        _EXTERNAL_NETWORK_ATTEMPTS.append(str(address))
        raise OSError(f"external network access is disabled for Irodori: {address}")

    def guarded_connect_ex(sock, address):  # noqa: ANN001
        if is_local(address):
            return original_connect_ex(sock, address)
        _EXTERNAL_NETWORK_ATTEMPTS.append(str(address))
        return 10013

    def guarded_create_connection(address, *args, **kwargs):  # noqa: ANN001
        if is_local(address):
            return original_create_connection(address, *args, **kwargs)
        _EXTERNAL_NETWORK_ATTEMPTS.append(str(address))
        raise OSError(f"external network access is disabled for Irodori: {address}")

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    _NETWORK_GUARD_INSTALLED = True


def _resolve_runtime_device(requested_device: object) -> str:
    device = str(requested_device or "auto").strip().lower()
    if device in {"", "auto"}:
        return "cuda" if torch.cuda.is_available() else "cpu"
    if device.startswith("cuda") and not torch.cuda.is_available():
        return "cpu"
    return device


def _resolve_runtime_precision(requested_precision: object, device: str) -> str:
    precision = str(requested_precision or "auto").strip().lower()
    if precision in {"", "auto"}:
        return "bf16" if device.startswith("cuda") else "fp32"
    if device == "cpu" and precision in {"bf16", "bfloat16", "fp16", "float16"}:
        return "fp32"
    return precision


def _load_request(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("request payload must be a JSON object")
    return payload


def _resolve_checkpoint(checkpoint: str) -> str:
    raw = str(checkpoint or "").strip()
    if not raw:
        raise ValueError("checkpoint is required")
    local_path = Path(raw).resolve()
    if local_path.is_dir():
        local_path = local_path / "model.safetensors"
    if not local_path.is_file():
        raise ValueError(
            f"checkpointがありません: {local_path}. runtime/models/irodori/... に配置してください"
        )
    return str(local_path)


def _write_wav(output_path: Path, waveform, sample_rate: int) -> None:
    waveform = waveform.detach().cpu()
    if waveform.ndim == 1:
        waveform = waveform.unsqueeze(0)
    waveform = waveform.clamp(-1.0, 1.0)
    pcm = (waveform * 32767.0).round().to(dtype=torch.int16)
    channels = int(pcm.shape[0])
    interleaved = pcm.transpose(0, 1).contiguous().numpy().tobytes()
    with wave.open(str(output_path), "wb") as fp:
        fp.setnchannels(channels)
        fp.setsampwidth(2)
        fp.setframerate(int(sample_rate))
        fp.writeframes(interleaved)


def _patch_model_config(config_module, inference_runtime_module):  # noqa: ANN001
    original_cls = config_module.ModelConfig
    if getattr(original_cls, "_local_tts_dual_patch", False):
        return original_cls
    allowed_fields = {field.name for field in fields(original_cls)}
    original_init = original_cls.__init__

    def compat_init(self, **kwargs):  # noqa: ANN001
        object.__setattr__(self, "_explicit_use_speaker_condition", kwargs.get("use_speaker_condition"))
        filtered = {key: value for key, value in kwargs.items() if key in allowed_fields}
        original_init(self, **filtered)

    original_cls.__init__ = compat_init
    original_cls._local_tts_dual_patch = True
    inference_runtime_module.ModelConfig = original_cls
    if "use_speaker_condition" in allowed_fields:
        return original_cls

    def use_speaker_condition(self) -> bool:  # noqa: ANN001
        explicit = getattr(self, "_explicit_use_speaker_condition", None)
        if explicit is not None:
            return bool(explicit)
        if bool(getattr(self, "force_dual_condition", False)):
            return True
        return not bool(self.use_caption_condition)

    original_cls.use_speaker_condition = property(use_speaker_condition)
    return original_cls


def _patch_model_constructor_precision(inference_runtime_module, precision: str) -> None:  # noqa: ANN001
    dtype_by_name = {
        "bf16": torch.bfloat16,
        "bfloat16": torch.bfloat16,
        "fp16": torch.float16,
        "float16": torch.float16,
        "fp32": torch.float32,
        "float32": torch.float32,
    }
    target_dtype = dtype_by_name.get(str(precision or "").strip().lower())
    if target_dtype is None or target_dtype == torch.float32:
        return
    original_constructor = inference_runtime_module.TextToLatentRFDiT
    if getattr(original_constructor, "_local_tts_precision_patch", False):
        return

    def construct_with_target_dtype(*args, **kwargs):  # noqa: ANN002,ANN003
        previous_dtype = torch.get_default_dtype()
        torch.set_default_dtype(target_dtype)
        try:
            return original_constructor(*args, **kwargs)
        finally:
            torch.set_default_dtype(previous_dtype)

    construct_with_target_dtype._local_tts_precision_patch = True
    inference_runtime_module.TextToLatentRFDiT = construct_with_target_dtype


def _patch_safetensors_load_device(inference_runtime_module, model_device: str) -> None:  # noqa: ANN001
    resolved_device = inference_runtime_module.resolve_runtime_device(model_device)
    if resolved_device.type != "cuda":
        return

    def load_checkpoint_from_safetensors_on_device(path: Path):
        model_state = inference_runtime_module.load_safetensors_file(
            str(path),
            device=str(resolved_device),
        )
        if not isinstance(model_state, dict) or not model_state:
            raise ValueError(f"Safetensors checkpoint has no model weights: {path}")
        with inference_runtime_module.safe_open(
            str(path), framework="pt", device="cpu"
        ) as handle:
            metadata = handle.metadata() or {}
        parse_quantization_metadata = getattr(
            inference_runtime_module, "parse_quantization_metadata", None
        )
        if callable(parse_quantization_metadata) and parse_quantization_metadata(metadata) is not None:
            model_state, _ = inference_runtime_module.unflatten_quantized_state_dict(
                model_state,
                metadata=metadata,
            )
        flat_config = inference_runtime_module._parse_json_mapping(
            metadata.get(inference_runtime_module._CONFIG_META_KEY),
            field=inference_runtime_module._CONFIG_META_KEY,
            path=path,
            required=True,
        )
        model_cfg, inference_cfg = inference_runtime_module._split_flat_checkpoint_config(
            path=path,
            flat_config=flat_config,
        )
        text_encoder_meta_key = getattr(
            inference_runtime_module, "_TEXT_ENCODER_CONFIG_META_KEY", None
        )
        if text_encoder_meta_key:
            text_encoder_config = inference_runtime_module._parse_json_mapping(
                metadata.get(text_encoder_meta_key),
                field=text_encoder_meta_key,
                path=path,
            )
            return model_state, model_cfg, inference_cfg, text_encoder_config
        return model_state, model_cfg, inference_cfg

    inference_runtime_module._load_checkpoint_from_safetensors = (
        load_checkpoint_from_safetensors_on_device
    )


def _patch_text_processor_loader(wrapper_dir: Path, expected_repo: str, local_dir: Path) -> None:
    if not local_dir.is_dir():
        raise ValueError(f"Tokenizerがありません: {local_dir}")
    if str(wrapper_dir) not in sys.path:
        sys.path.insert(0, str(wrapper_dir))
    import irodori_tts.tokenizer as text_module

    processor_cls = text_module.PretrainedTextTokenizer
    original = getattr(processor_cls, "_local_tts_original_loader", None)
    if original is None:
        original = processor_cls.from_pretrained.__func__
        processor_cls._local_tts_original_loader = staticmethod(original)
    mappings = getattr(processor_cls, "_local_tts_processor_mappings", {})
    mappings[str(expected_repo)] = str(local_dir.resolve())
    processor_cls._local_tts_processor_mappings = mappings

    def local_loader(
        cls,
        repo_id: str,
        add_bos: bool = True,
        local_files_only: bool = False,
        revision: str | None = None,
        **kwargs,
    ):
        del local_files_only, revision, kwargs
        location = cls._local_tts_processor_mappings.get(str(repo_id))
        if location is None:
            candidate = Path(str(repo_id)).resolve()
            if not candidate.exists():
                raise ValueError(
                    f"Tokenizerはローカル配置のみ利用できます: {repo_id}. runtime/models/irodori/tokenizers/ に配置してください"
                )
            location = str(candidate)
        return cls._local_tts_original_loader(
            cls,
            location,
            add_bos=add_bos,
            local_files_only=True,
        )

    processor_cls.from_pretrained = classmethod(local_loader)


def _get_runtime(payload: dict[str, object]):
    wrapper_dir = Path(str(payload.get("wrapperDir") or "")).resolve()
    if not wrapper_dir.is_dir():
        raise ValueError(f"wrapperDir not found: {wrapper_dir}")
    if str(wrapper_dir) not in sys.path:
        sys.path.insert(0, str(wrapper_dir))

    expected_repo = str(payload.get("textProcessorRepo") or "").strip()
    local_dir = Path(str(payload.get("textProcessorDir") or "")).resolve()
    _patch_text_processor_loader(wrapper_dir, expected_repo, local_dir)

    import irodori_tts.config as config_module
    import irodori_tts.inference_runtime as inference_runtime_module

    _patch_model_config(config_module, inference_runtime_module)
    model_device = _resolve_runtime_device(payload.get("modelDevice"))
    model_precision = _resolve_runtime_precision(payload.get("modelPrecision"), model_device)
    codec_device = _resolve_runtime_device(payload.get("codecDevice") or model_device)
    codec_precision = _resolve_runtime_precision(payload.get("codecPrecision") or "fp32", codec_device)
    _patch_model_constructor_precision(inference_runtime_module, model_precision)
    _patch_safetensors_load_device(inference_runtime_module, model_device)

    checkpoint_path = _resolve_checkpoint(str(payload.get("checkpoint") or ""))
    codec_path = Path(str(payload.get("codecRepo") or "")).resolve()
    if not codec_path.exists():
        raise ValueError(
            f"codecがありません: {codec_path}. runtime/models/irodori/... に配置してください"
        )
    runtime_key = inference_runtime_module.RuntimeKey(
        checkpoint=checkpoint_path,
        model_device=model_device,
        model_precision=model_precision,
        codec_repo=str(codec_path),
        codec_device=codec_device,
        codec_precision=codec_precision,
        compile_model=False,
        compile_dynamic=False,
    )
    runtime, _ = inference_runtime_module.get_cached_runtime(runtime_key)
    return runtime, inference_runtime_module


def _optimization_settings(payload: dict[str, object]) -> dict[str, object] | None:
    profile = str(payload.get("optimizationProfile") or "").strip().lower()
    if not profile:
        return None
    if profile != "low_latency_8":
        raise ValueError(f"unknown optimization profile: {profile}")
    return {
        "profile": profile,
        "numSteps": 8,
        "referenceMode": "latent",
        "schedule": "sway",
        "swayCoeff": -1.0,
        "contextKvCache": True,
        "watermark": True,
        "cfgScaleText": 3.0,
        "cfgScaleSpeaker": 6.0,
        "decodeMode": "sequential",
        "trimTail": True,
    }


def _reference_latent_cache(
    payload: dict[str, object],
    runtime,
    inference_runtime_module,
    reference_audio_path: str | None,
) -> tuple[str | None, bool]:
    if not reference_audio_path:
        return None, False
    source = Path(reference_audio_path).resolve()
    if not source.is_file():
        raise ValueError(f"referenceAudioPath not found: {source}")
    cache_dir = Path(str(payload.get("referenceCacheDir") or "")).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    stat = source.stat()
    fingerprint = "\n".join(
        (
            str(source),
            str(stat.st_size),
            str(stat.st_mtime_ns),
            str(payload.get("codecRepo") or ""),
            str(payload.get("codecPrecision") or ""),
            "normalize_db=-16.0",
            "ensure_max=true",
        )
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
    cache_path = cache_dir / f"{source.stem}-{digest}.pt"
    if cache_path.is_file():
        return str(cache_path), True

    wav, sample_rate = inference_runtime_module._load_audio(str(source))
    latent = runtime.codec.encode_waveform(
        wav.unsqueeze(0),
        sample_rate=int(sample_rate),
        normalize_db=-16.0,
        ensure_max=True,
    ).cpu()
    temporary = cache_path.with_name(f".{cache_path.name}.{os.getpid()}.tmp")
    torch.save(latent, temporary)
    temporary.replace(cache_path)
    return str(cache_path), False


def _synthesize(payload: dict[str, object]) -> dict[str, object]:
    runtime, inference_runtime_module = _get_runtime(payload)
    setattr(runtime.model_cfg, "force_dual_condition", bool(payload.get("enableReferenceWithCaption")))
    output_path = Path(str(payload.get("outputPath") or "")).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reference_audio_path = str(payload.get("referenceAudioPath") or "").strip() or None
    caption = str(payload.get("caption") or "").strip() or None
    settings = _optimization_settings(payload)

    reference_latent_path = None
    reference_cache_hit = False
    use_reference_latent = bool(settings and settings["referenceMode"] == "latent")
    if use_reference_latent:
        reference_latent_path, reference_cache_hit = _reference_latent_cache(
            payload,
            runtime,
            inference_runtime_module,
            reference_audio_path,
        )

    request_kwargs: dict[str, object] = {
        "text": str(payload.get("text") or ""),
        "caption": caption,
        "ref_wav": None if use_reference_latent else reference_audio_path,
        "ref_latent": reference_latent_path,
        "no_ref": not bool(reference_latent_path or reference_audio_path),
        "seed": payload.get("seed"),
        "duration_scale": float(payload.get("durationScale") or 1.0),
        "cfg_scale_caption": float(payload.get("cfgScaleCaption") or 3.0),
    }
    if settings:
        request_kwargs.update(
            {
                "cfg_scale_text": float(settings["cfgScaleText"]),
                "cfg_scale_speaker": float(settings["cfgScaleSpeaker"]),
                "num_steps": int(settings["numSteps"]),
                "t_schedule_mode": str(settings["schedule"]),
                "sway_coeff": float(settings["swayCoeff"]),
                "context_kv_cache": bool(settings["contextKvCache"]),
                "decode_mode": str(settings["decodeMode"]),
                "trim_tail": bool(settings["trimTail"]),
            }
        )
    request = inference_runtime_module.SamplingRequest(**request_kwargs)

    watermarker = getattr(runtime, "watermarker", None)
    watermark_model = getattr(watermarker, "model", None)
    original_measure_start = getattr(inference_runtime_module, "_measure_start", None)
    original_measure_end = getattr(inference_runtime_module, "_measure_end", None)
    low_latency = settings is not None
    if low_latency and watermarker is not None and not bool(settings["watermark"]):
        watermarker.model = None
    if low_latency and callable(original_measure_start) and callable(original_measure_end):
        inference_runtime_module._measure_start = lambda _device, *_extra: time.perf_counter()
        inference_runtime_module._measure_end = (
            lambda _device, started, *_extra: time.perf_counter() - started
        )
    try:
        if low_latency and torch.cuda.is_available():
            torch.cuda.synchronize()
        inference_started = time.perf_counter()
        result = runtime.synthesize(request)
        if low_latency and torch.cuda.is_available():
            torch.cuda.synchronize()
        inference_wall_sec = time.perf_counter() - inference_started
    finally:
        if callable(original_measure_start) and callable(original_measure_end):
            inference_runtime_module._measure_start = original_measure_start
            inference_runtime_module._measure_end = original_measure_end
        if watermarker is not None:
            watermarker.model = watermark_model

    serialization_started = time.perf_counter()
    _write_wav(output_path, result.audio.to(torch.float32), int(result.sample_rate))
    serialization_sec = time.perf_counter() - serialization_started
    response: dict[str, object] = {
        "ok": True,
        "outputPath": str(output_path),
        "captionInjectionMode": "separate_target" if caption else "none",
        "usedSeed": int(result.used_seed),
        "externalNetworkAttempts": len(_EXTERNAL_NETWORK_ATTEMPTS),
    }
    if settings:
        audio_sec = float(result.audio.shape[-1]) / float(result.sample_rate)
        response["timings"] = {
            "profile": str(settings["profile"]),
            "inferenceSec": inference_wall_sec,
            "serializationSec": serialization_sec,
            "totalSec": inference_wall_sec + serialization_sec,
            "audioSec": audio_sec,
            "rtf": inference_wall_sec / audio_sec if audio_sec > 0 else None,
            "stageTimingMode": "disabled_low_latency_path",
            "referenceCacheHit": reference_cache_hit,
            "settings": {
                "numSteps": int(settings["numSteps"]),
                "schedule": str(settings["schedule"]),
                "contextKvCache": bool(settings["contextKvCache"]),
                "gpuStageSync": False,
                "watermark": bool(settings["watermark"]),
                "referenceMode": str(settings["referenceMode"]),
                "cfgScaleText": float(settings["cfgScaleText"]),
                "cfgScaleSpeaker": float(settings["cfgScaleSpeaker"]),
                "decodeMode": str(settings["decodeMode"]),
                "trimTail": bool(settings["trimTail"]),
                "modelPrecision": str(payload.get("modelPrecision") or ""),
                "codecPrecision": str(payload.get("codecPrecision") or ""),
            },
        }
    return response


def _emit(payload: dict[str, object]) -> None:
    sys.stdout.write(_RESPONSE_PREFIX + json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _worker_main() -> int:
    _install_external_network_guard()
    for line in sys.stdin:
        protocol_id = ""
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("worker request must be an object")
            protocol_id = str(payload.get("protocolRequestId") or "")
            action = str(payload.get("action") or "")
            if action == "shutdown":
                _emit({"ok": True, "protocolRequestId": protocol_id})
                return 0
            if action == "preload":
                _get_runtime(payload)
                result: dict[str, object] = {
                    "ok": True,
                    "modelName": str(payload.get("modelName") or ""),
                    "externalNetworkAttempts": len(_EXTERNAL_NETWORK_ATTEMPTS),
                }
            elif action == "synthesize":
                result = _synthesize(payload)
            else:
                raise ValueError(f"unknown worker action: {action}")
            result["protocolRequestId"] = protocol_id
            _emit(result)
        except Exception as exc:
            _emit(
                {
                    "ok": False,
                    "protocolRequestId": protocol_id,
                    "error": traceback.format_exc().strip() or str(exc),
                    "externalNetworkAttempts": len(_EXTERNAL_NETWORK_ATTEMPTS),
                }
            )
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--worker":
        return _worker_main()
    if len(sys.argv) != 2:
        raise SystemExit("usage: run_irodori_voicedesign.py <request.json> | --worker")
    _install_external_network_guard()
    payload = _load_request(Path(sys.argv[1]))
    result = _synthesize(payload)
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
