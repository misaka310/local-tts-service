from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import torch

from run_irodori_voicedesign import _patch_model_config, _resolve_checkpoint, _write_wav


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "runtime" / "verification" / "native-synthesis-controls"
TEXT = "今日はいい天気ですね。落ち着いて確認します。"
CAPTION = "明るく自然で、少し嬉しそうな話し方。聞き取りやすく話す。"
SEED = 260711


def _load_local_settings() -> tuple[dict[str, object], Path]:
    config_path = ROOT / "config" / "config.local.json"
    if not config_path.is_file():
        raise FileNotFoundError("config/config.local.json is required for the real Irodori verification")
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    runtime = config.get("runtimes", {}).get("irodori_voicedesign_direct", {})
    if not isinstance(runtime, dict):
        raise ValueError("runtimes.irodori_voicedesign_direct is not configured")
    voice_id = str(config.get("defaultReferenceVoice") or "").strip()
    if not voice_id:
        raise ValueError("defaultReferenceVoice is not configured")
    reference_audio = ROOT / "reference" / "voices" / voice_id / "voice.wav"
    if not reference_audio.is_file():
        raise FileNotFoundError(f"reference voice not found: {reference_audio}")
    return runtime, reference_audio


def _duration_seconds(result) -> float:  # noqa: ANN001
    frames = int(result.audio.shape[-1])
    return round(frames / float(result.sample_rate), 4)


def main() -> int:
    runtime_settings, reference_audio = _load_local_settings()
    wrapper_dir = (ROOT / str(runtime_settings.get("wrapperDir") or "")).resolve()
    if not wrapper_dir.is_dir():
        raise FileNotFoundError(f"Irodori wrapper not found: {wrapper_dir}")
    if str(wrapper_dir) not in sys.path:
        sys.path.insert(0, str(wrapper_dir))

    import irodori_tts.config as config_module
    import irodori_tts.inference_runtime as inference_runtime_module

    _patch_model_config(config_module, inference_runtime_module)
    RuntimeKey = inference_runtime_module.RuntimeKey
    SamplingRequest = inference_runtime_module.SamplingRequest
    get_cached_runtime = inference_runtime_module.get_cached_runtime

    checkpoint = _resolve_checkpoint(str(runtime_settings.get("checkpoint") or ""))
    runtime_key = RuntimeKey(
        checkpoint=checkpoint,
        model_device=str(runtime_settings.get("modelDevice") or "cuda"),
        model_precision=str(runtime_settings.get("modelPrecision") or "bf16"),
        codec_repo=str(runtime_settings.get("codecRepo") or "Aratako/Semantic-DACVAE-Japanese-32dim"),
        codec_device=str(runtime_settings.get("codecDevice") or runtime_settings.get("modelDevice") or "cuda"),
        codec_precision=str(runtime_settings.get("codecPrecision") or "fp32"),
        compile_model=False,
        compile_dynamic=False,
    )
    runtime, _ = get_cached_runtime(runtime_key)
    setattr(runtime.model_cfg, "force_dual_condition", True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    variants = {
        "slow": {"speedScale": 0.85, "styleStrength": 3.0},
        "fast": {"speedScale": 1.15, "styleStrength": 3.0},
        "style_low": {"speedScale": 1.0, "styleStrength": 2.0},
        "style_high": {"speedScale": 1.0, "styleStrength": 5.0},
    }
    report: dict[str, object] = {
        "ok": False,
        "text": TEXT,
        "caption": CAPTION,
        "seed": SEED,
        "referenceAudio": str(reference_audio),
        "variants": {},
    }

    for name, controls in variants.items():
        speed_scale = float(controls["speedScale"])
        style_strength = float(controls["styleStrength"])
        request = SamplingRequest(
            text=TEXT,
            caption=CAPTION,
            ref_wav=str(reference_audio),
            no_ref=False,
            seed=SEED,
            duration_scale=1.0 / speed_scale,
            cfg_scale_caption=style_strength,
        )
        result = runtime.synthesize(request)
        output_path = OUTPUT_DIR / f"{name}.wav"
        _write_wav(output_path, result.audio.to(torch.float32), int(result.sample_rate))
        report["variants"][name] = {
            "speedScale": speed_scale,
            "durationScale": round(1.0 / speed_scale, 6),
            "styleStrength": style_strength,
            "durationSec": _duration_seconds(result),
            "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "outputPath": str(output_path),
        }

    variants_report = report["variants"]
    slow_duration = float(variants_report["slow"]["durationSec"])
    fast_duration = float(variants_report["fast"]["durationSec"])
    style_low_hash = str(variants_report["style_low"]["sha256"])
    style_high_hash = str(variants_report["style_high"]["sha256"])
    speed_changed_duration = fast_duration < slow_duration
    style_changed_waveform = style_low_hash != style_high_hash
    report["checks"] = {
        "fasterSettingProducedShorterAudio": speed_changed_duration,
        "styleStrengthChangedWaveform": style_changed_waveform,
    }
    report["ok"] = speed_changed_duration and style_changed_waveform
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
