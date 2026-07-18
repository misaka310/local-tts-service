from __future__ import annotations

import json
import os
import socket
import sys
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

    def local_loader(cls, repo_id: str, add_bos: bool = True, local_files_only: bool = False):
        del local_files_only
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


def _synthesize(payload: dict[str, object]) -> dict[str, object]:
    runtime, inference_runtime_module = _get_runtime(payload)
    setattr(runtime.model_cfg, "force_dual_condition", bool(payload.get("enableReferenceWithCaption")))
    output_path = Path(str(payload.get("outputPath") or "")).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reference_audio_path = str(payload.get("referenceAudioPath") or "").strip() or None
    caption = str(payload.get("caption") or "").strip() or None
    request = inference_runtime_module.SamplingRequest(
        text=str(payload.get("text") or ""),
        caption=caption,
        ref_wav=reference_audio_path,
        no_ref=reference_audio_path is None,
        seed=payload.get("seed"),
        duration_scale=float(payload.get("durationScale") or 1.0),
        cfg_scale_caption=float(payload.get("cfgScaleCaption") or 3.0),
    )
    result = runtime.synthesize(request)
    _write_wav(output_path, result.audio.to(torch.float32), int(result.sample_rate))
    return {
        "ok": True,
        "outputPath": str(output_path),
        "captionInjectionMode": "separate_target" if caption else "none",
        "usedSeed": int(result.used_seed),
        "externalNetworkAttempts": len(_EXTERNAL_NETWORK_ATTEMPTS),
    }


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
