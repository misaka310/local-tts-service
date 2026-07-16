from __future__ import annotations

import json
import sys
from dataclasses import fields

from pathlib import Path
import wave

import torch


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


def _resolve_checkpoint(checkpoint: str):
    from huggingface_hub import hf_hub_download

    raw = str(checkpoint or "").strip()
    if not raw:
        raise ValueError("checkpoint is required")
    local_path = Path(raw)
    if local_path.is_dir():
        model_path = local_path / "model.safetensors"
        if not model_path.is_file():
            raise ValueError(f"model.safetensors not found in checkpoint directory: {local_path}")
        return str(model_path.resolve())
    if local_path.is_file():
        return str(Path(raw).resolve())
    return hf_hub_download(repo_id=raw, filename="model.safetensors")


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


def _patch_model_config(config_module, inference_runtime_module):
    original_cls = config_module.ModelConfig
    if getattr(original_cls, "_local_tts_dual_patch", False):
        return original_cls

    allowed_fields = {field.name for field in fields(original_cls)}
    original_init = original_cls.__init__

    def _compat_init(self, **kwargs):
        object.__setattr__(self, "_explicit_use_speaker_condition", kwargs.get("use_speaker_condition"))
        filtered = {key: value for key, value in kwargs.items() if key in allowed_fields}
        original_init(self, **filtered)

    original_cls.__init__ = _compat_init
    original_cls._local_tts_dual_patch = True
    inference_runtime_module.ModelConfig = original_cls
    if "use_speaker_condition" in allowed_fields:
        return original_cls

    def _use_speaker_condition(self) -> bool:
        explicit = getattr(self, "_explicit_use_speaker_condition", None)
        if explicit is not None:
            return bool(explicit)
        if bool(getattr(self, "force_dual_condition", False)):
            return True
        return not bool(self.use_caption_condition)

    original_cls.use_speaker_condition = property(_use_speaker_condition)
    return original_cls


def main() -> int:
    def _patch_model_constructor_precision(inference_runtime_module, precision: str) -> None:
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

        def _construct_with_target_dtype(*args, **kwargs):
            previous_dtype = torch.get_default_dtype()
            torch.set_default_dtype(target_dtype)
            try:
                return original_constructor(*args, **kwargs)
            finally:
                torch.set_default_dtype(previous_dtype)

        _construct_with_target_dtype._local_tts_precision_patch = True
        inference_runtime_module.TextToLatentRFDiT = _construct_with_target_dtype

    def _patch_safetensors_load_device(inference_runtime_module, model_device: str) -> None:
        resolved_device = inference_runtime_module.resolve_runtime_device(model_device)
        if resolved_device.type != "cuda":
            return

        def _load_checkpoint_from_safetensors_on_device(path: Path):
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
            _load_checkpoint_from_safetensors_on_device
        )

    if len(sys.argv) != 2:
        raise SystemExit("usage: run_irodori_voicedesign.py <request.json>")

    payload = _load_request(Path(sys.argv[1]))
    wrapper_dir = Path(str(payload.get("wrapperDir") or "")).resolve()
    if not wrapper_dir.is_dir():
        raise ValueError(f"wrapperDir not found: {wrapper_dir}")
    if str(wrapper_dir) not in sys.path:
        sys.path.insert(0, str(wrapper_dir))

    import irodori_tts.config as config_module
    import irodori_tts.inference_runtime as inference_runtime_module
    _patch_model_config(config_module, inference_runtime_module)
    model_device = _resolve_runtime_device(payload.get("modelDevice"))
    model_precision = _resolve_runtime_precision(payload.get("modelPrecision"), model_device)
    codec_device = _resolve_runtime_device(payload.get("codecDevice") or model_device)
    codec_precision = _resolve_runtime_precision(payload.get("codecPrecision") or "fp32", codec_device)
    _patch_model_constructor_precision(inference_runtime_module, model_precision)
    _patch_safetensors_load_device(inference_runtime_module, model_device)

    RuntimeKey = inference_runtime_module.RuntimeKey
    SamplingRequest = inference_runtime_module.SamplingRequest
    get_cached_runtime = inference_runtime_module.get_cached_runtime

    checkpoint_path = _resolve_checkpoint(str(payload.get("checkpoint") or ""))
    runtime_key = RuntimeKey(
        checkpoint=checkpoint_path,
        model_device=model_device,
        model_precision=model_precision,
        codec_repo=str(payload.get("codecRepo") or "Aratako/Semantic-DACVAE-Japanese-32dim"),
        codec_device=codec_device,
        codec_precision=codec_precision,
        compile_model=False,
        compile_dynamic=False,
    )
    runtime, _ = get_cached_runtime(runtime_key)
    setattr(runtime.model_cfg, "force_dual_condition", bool(payload.get("enableReferenceWithCaption")))

    output_path = Path(str(payload.get("outputPath") or "")).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reference_audio_path = str(payload.get("referenceAudioPath") or "").strip() or None
    caption = str(payload.get("caption") or "").strip() or None
    request = SamplingRequest(
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

    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "outputPath": str(output_path),
                "captionInjectionMode": "separate_target" if caption else "none",
                "usedSeed": int(result.used_seed),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
