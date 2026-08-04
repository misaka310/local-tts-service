from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import random
import sys
import wave

SUPPORTED_MODELS = {"chatterbox_multilingual_v3", "fun_cosyvoice3_0_5b"}
ROOT = Path(__file__).resolve().parent.parent
MODEL_DIRS = {
    "chatterbox_multilingual_v3": ROOT / "runtime" / "models" / "chatterbox",
    "fun_cosyvoice3_0_5b": ROOT / "runtime" / "models" / "cosyvoice",
}
VENDOR_DIRS = {
    "chatterbox_multilingual_v3": ROOT / "runtime" / "vendor" / "chatterbox",
    "fun_cosyvoice3_0_5b": ROOT / "runtime" / "vendor" / "cosyvoice",
}


@dataclass(frozen=True)
class ExpressiveTtsRequest:
    model: str
    model_id: str
    text: str
    reference_audio_path: Path
    reference_text_path: Path | None
    reference_text: str
    output_path: Path
    seed: int
    language: str
    style_strength: float | None
    speed_scale: float | None
    instruction: str


def _required_text(payload: dict[str, object], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def load_request(request_json: Path, output_override: Path | None = None) -> ExpressiveTtsRequest:
    payload = json.loads(request_json.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("request JSON must be an object")

    model = _required_text(payload, "model")
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"unsupported local expressive TTS model: {model}")

    reference_audio_path = Path(_required_text(payload, "referenceAudioPath")).expanduser().resolve()
    if not reference_audio_path.is_file():
        raise FileNotFoundError(f"reference audio not found: {reference_audio_path}")

    raw_reference_text_path = str(payload.get("referenceTextPath") or "").strip()
    reference_text_path = Path(raw_reference_text_path).expanduser().resolve() if raw_reference_text_path else None
    reference_text = ""
    if reference_text_path is not None:
        if not reference_text_path.is_file():
            raise FileNotFoundError(f"reference text not found: {reference_text_path}")
        reference_text = reference_text_path.read_text(encoding="utf-8-sig").strip()

    output_path = output_override or Path(_required_text(payload, "outputPath")).expanduser()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_seed = payload.get("seed")
    seed = int(raw_seed) if raw_seed is not None and str(raw_seed).strip() else 1
    raw_style_strength = payload.get("styleStrength")
    style_strength = (
        float(raw_style_strength)
        if raw_style_strength is not None and str(raw_style_strength).strip()
        else None
    )
    raw_speed_scale = payload.get("speedScale")
    speed_scale = (
        float(raw_speed_scale)
        if raw_speed_scale is not None and str(raw_speed_scale).strip()
        else None
    )

    return ExpressiveTtsRequest(
        model=model,
        model_id=str(payload.get("modelId") or "").strip(),
        text=_required_text(payload, "text"),
        reference_audio_path=reference_audio_path,
        reference_text_path=reference_text_path,
        reference_text=reference_text,
        output_path=output_path,
        seed=seed,
        language=str(payload.get("language") or "ja").strip() or "ja",
        style_strength=style_strength,
        speed_scale=speed_scale,
        instruction=str(payload.get("instruction") or payload.get("caption") or "").strip(),
    )


def _query_free_vram_mib() -> int | None:
    import subprocess

    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if completed.returncode != 0:
            return None
        first = (completed.stdout or "").strip().splitlines()[0]
        return int(first.strip())
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def _prepare_device_environment(model: str) -> dict[str, object]:
    requested = str(os.environ.get("LOCAL_EXPRESSIVE_TTS_DEVICE") or "auto").strip().lower()
    if requested not in {"auto", "cpu", "cuda"}:
        raise ValueError("LOCAL_EXPRESSIVE_TTS_DEVICE must be auto, cpu, or cuda")
    free_vram_mib = _query_free_vram_mib()
    minimum_vram_mib = {
        "chatterbox_multilingual_v3": 6000,
        "fun_cosyvoice3_0_5b": 6500,
    }[model]
    selected = requested
    reason = "explicit override"
    if requested == "auto":
        if free_vram_mib is None:
            selected, reason = "cpu", "GPU free-memory check unavailable"
        elif free_vram_mib < minimum_vram_mib:
            selected, reason = "cpu", f"free VRAM {free_vram_mib} MiB is below {minimum_vram_mib} MiB"
        else:
            selected, reason = "cuda", f"free VRAM {free_vram_mib} MiB is sufficient"
    os.environ["LOCAL_EXPRESSIVE_TTS_SELECTED_DEVICE"] = selected
    if selected == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    return {
        "requestedDevice": requested,
        "selectedDevice": selected,
        "deviceSelectionReason": reason,
        "freeVramBeforeMiB": free_vram_mib,
        "minimumVramMiB": minimum_vram_mib,
    }


def _torch_cuda_available(torch_module: object) -> bool:
    try:
        return bool(
            torch_module.cuda.is_available()
            and torch_module.cuda.device_count() > 0
            and os.environ.get("LOCAL_EXPRESSIVE_TTS_SELECTED_DEVICE") != "cpu"
        )
    except (AssertionError, RuntimeError):
        return False


def _force_torch_cpu_if_selected(torch_module: object) -> None:
    if os.environ.get("LOCAL_EXPRESSIVE_TTS_SELECTED_DEVICE") == "cpu":
        torch_module.cuda.is_available = lambda: False
        torch_module.cuda.device_count = lambda: 0


def _apply_seed(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed % (2**32))
    except ImportError:
        pass
    import torch

    torch.manual_seed(seed)
    if _torch_cuda_available(torch):
        torch.cuda.manual_seed_all(seed)


def _resolved_device() -> tuple[str, str]:
    import torch

    if _torch_cuda_available(torch):
        return "cuda", torch.cuda.get_device_name(0)
    return "cpu", "cpu"


def _reset_peak_memory() -> None:
    import torch

    if _torch_cuda_available(torch):
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()


def _runtime_metadata() -> dict[str, object]:
    import torch

    device, device_name = _resolved_device()
    return {
        "device": "cuda:0" if device == "cuda" else "cpu",
        "deviceName": device_name,
        "torch": torch.__version__,
        "cuda": str(torch.version.cuda),
        "peakVramBytes": int(torch.cuda.max_memory_allocated()) if _torch_cuda_available(torch) else 0,
    }


def _normalize_chatterbox_language(language: str) -> str:
    aliases = {
        "japanese": "ja",
        "ja-jp": "ja",
        "english": "en",
        "en-us": "en",
        "en-gb": "en",
        "chinese": "zh",
        "korean": "ko",
    }
    normalized = str(language or "ja").strip().lower()
    return aliases.get(normalized, normalized)


def generate_chatterbox(request: ExpressiveTtsRequest) -> dict[str, object]:
    import soundfile as sf
    import torch

    _force_torch_cpu_if_selected(torch)
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    device, _ = _resolved_device()
    model_dir = MODEL_DIRS[request.model]
    required = (
        "ve.pt",
        "s3gen.pt",
        "t3_mtl23ls_v3.safetensors",
        "grapheme_mtl_merged_expanded_v1.json",
    )
    missing = [name for name in required if not (model_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Chatterbox model files are missing under {model_dir}: {', '.join(missing)}")

    _apply_seed(request.seed)
    _reset_peak_memory()
    exaggeration = 0.7 if request.style_strength is None else max(0.0, min(2.0, request.style_strength))
    cfg_weight = 0.3 if exaggeration >= 0.7 else 0.5
    model = ChatterboxMultilingualTTS.from_local(model_dir, device=device, t3_model="v3")
    waveform = model.generate(
        request.text,
        language_id=_normalize_chatterbox_language(request.language),
        audio_prompt_path=str(request.reference_audio_path),
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
        temperature=0.8,
    )
    audio = waveform.squeeze().detach().cpu().float().numpy()
    sf.write(request.output_path, audio, model.sr, subtype="PCM_16")
    metadata = {
        **_runtime_metadata(),
        "languageId": _normalize_chatterbox_language(request.language),
        "exaggeration": exaggeration,
        "cfgWeight": cfg_weight,
    }
    del model, waveform
    if _torch_cuda_available(torch):
        torch.cuda.empty_cache()
    return metadata


def _to_katakana(text: str) -> str:
    from pykakasi import kakasi

    converted = kakasi().convert(str(text or ""))
    katakana = "".join(str(item.get("kana") or item.get("orig") or "") for item in converted).strip()
    if not katakana:
        raise ValueError("CosyVoice Japanese normalization produced empty text")
    return katakana


def _cosyvoice_instruction(request: ExpressiveTtsRequest) -> str:
    instruction = request.instruction.strip()
    if instruction:
        if "<|endofprompt|>" not in instruction:
            instruction = f"You are a helpful assistant. {instruction}<|endofprompt|>"
        return instruction
    strength = 4.0 if request.style_strength is None else request.style_strength
    if strength >= 5.0:
        body = "请非常开心、充满兴奋地说一句话。"
    elif strength <= 2.0:
        body = "Please say a sentence in a very soft voice."
    else:
        body = "请自然、富有感情地说一句话。"
    return f"You are a helpful assistant. {body}<|endofprompt|>"


def generate_cosyvoice(request: ExpressiveTtsRequest) -> dict[str, object]:
    import numpy as np
    import soundfile as sf
    import torch

    _force_torch_cpu_if_selected(torch)
    import torchaudio

    def soundfile_load(source: object, *args: object, **kwargs: object) -> tuple[object, int]:
        del args, kwargs
        audio, sample_rate = sf.read(source, dtype="float32", always_2d=True)
        contiguous = np.ascontiguousarray(audio.T)
        return torch.from_numpy(contiguous), int(sample_rate)

    torchaudio.load = soundfile_load

    wetext_dir = ROOT / "runtime" / "models" / "wetext"
    required_wetext = (
        "en/tn/tagger.fst",
        "en/tn/verbalizer.fst",
        "zh/tn/tagger.fst",
        "zh/tn/verbalizer.fst",
    )
    missing_wetext = [name for name in required_wetext if not (wetext_dir / name).is_file()]
    if missing_wetext:
        raise FileNotFoundError(
            f"WeText files are missing under {wetext_dir}: {', '.join(missing_wetext)}"
        )
    import modelscope

    original_snapshot_download = modelscope.snapshot_download

    def local_modelscope_snapshot(model_id: str, *args: object, **kwargs: object) -> str:
        if model_id == "pengzhendong/wetext":
            return str(wetext_dir)
        return str(original_snapshot_download(model_id, *args, **kwargs))

    modelscope.snapshot_download = local_modelscope_snapshot

    vendor = VENDOR_DIRS[request.model]
    matcha = vendor / "third_party" / "Matcha-TTS"
    sys.path.insert(0, str(matcha))
    sys.path.insert(0, str(vendor))
    from cosyvoice.cli.cosyvoice import AutoModel

    model_dir = MODEL_DIRS[request.model]
    required = (
        "cosyvoice3.yaml",
        "llm.pt",
        "flow.pt",
        "hift.pt",
        "speech_tokenizer_v3.onnx",
        "campplus.onnx",
    )
    missing = [name for name in required if not (model_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"CosyVoice model files are missing under {model_dir}: {', '.join(missing)}")

    _apply_seed(request.seed)
    _reset_peak_memory()
    normalized_text = _to_katakana(request.text)
    instruction = _cosyvoice_instruction(request)
    speed = 1.0 if request.speed_scale is None else max(0.5, min(2.0, request.speed_scale))
    model = AutoModel(model_dir=str(model_dir), fp16=_torch_cuda_available(torch))
    chunks = [
        item["tts_speech"].detach().cpu()
        for item in model.inference_instruct2(
            normalized_text,
            instruction,
            str(request.reference_audio_path),
            stream=False,
            speed=speed,
            text_frontend=False,
        )
    ]
    if not chunks:
        raise RuntimeError("CosyVoice produced no audio chunks")
    waveform = torch.cat(chunks, dim=1)
    audio = waveform.squeeze().detach().cpu().float().numpy()
    sf.write(request.output_path, audio, model.sample_rate, subtype="PCM_16")
    metadata = {
        **_runtime_metadata(),
        "normalizedJapanese": normalized_text,
        "instruction": instruction,
        "speed": speed,
    }
    del model, waveform, chunks
    if _torch_cuda_available(torch):
        torch.cuda.empty_cache()
    return metadata


def validate_output(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size <= 44:
        raise RuntimeError(f"generated WAV is missing or empty: {path}")
    with path.open("rb") as fp:
        header = fp.read(12)
    if len(header) != 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise RuntimeError(f"generated file is not RIFF/WAVE: {path}")
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        if frames <= 0 or sample_rate <= 0:
            raise RuntimeError(f"generated WAV has no audio frames: {path}")
        duration_sec = frames / float(sample_rate)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "durationSec": round(duration_sec, 3),
        "sampleRate": sample_rate,
        "channels": channels,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", required=True, type=Path)
    parser.add_argument("--output-path", type=Path)
    args = parser.parse_args()

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HOME", str((ROOT / "runtime" / "hf-cache").resolve()))

    request = load_request(args.request_json.resolve(), args.output_path.resolve() if args.output_path else None)
    device_selection = _prepare_device_environment(request.model)
    if request.output_path.exists():
        request.output_path.unlink()
    if request.model == "chatterbox_multilingual_v3":
        runtime = generate_chatterbox(request)
    elif request.model == "fun_cosyvoice3_0_5b":
        runtime = generate_cosyvoice(request)
    else:  # pragma: no cover - guarded by load_request
        raise ValueError(f"unsupported model: {request.model}")

    result = validate_output(request.output_path)
    print(
        json.dumps(
            {
                "model": request.model,
                "modelId": request.model_id,
                "inputText": request.text,
                "language": request.language,
                "styleStrength": request.style_strength,
                "instructionRequested": request.instruction,
                "seed": request.seed,
                **device_selection,
                **runtime,
                **result,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
