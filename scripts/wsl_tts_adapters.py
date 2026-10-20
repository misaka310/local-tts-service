from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile

from scripts.wsl_tts_infer import WslTtsRequest, _base_dir, _copy_generated_wav, _model_dir, _run, _vendor_dir


def _force_torch_compile_eager(torch_module: object) -> bool:
    """Avoid FireRed's first-run Inductor workers on memory-limited WSL."""

    changed = False
    compiler = getattr(torch_module, "compiler", None)
    set_stance = getattr(compiler, "set_stance", None)
    if callable(set_stance):
        set_stance("force_eager")
        changed = True

    compile_fn = getattr(torch_module, "compile", None)
    if callable(compile_fn):
        def eager_compile(model=None, *args, **kwargs):
            del args, kwargs
            if model is None:
                return lambda inner: inner
            return model

        setattr(torch_module, "compile", eager_compile)
        changed = True
    return changed


def _enable_low_memory_torch_load(torch_module: object) -> bool:
    """Memory-map CPU checkpoint loads so FireRed does not duplicate multi-GB weights."""

    load_fn = getattr(torch_module, "load", None)
    if not callable(load_fn):
        return False

    def low_memory_load(*args, **kwargs):
        source = args[0] if args else kwargs.get("f")
        if isinstance(source, (str, os.PathLike)) and kwargs.get("map_location") == "cpu":
            kwargs.setdefault("mmap", True)
        return load_fn(*args, **kwargs)

    setattr(torch_module, "load", low_memory_load)
    return True


def _first_reference_sentence(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return normalized
    match = re.match(r"^.*?[。！？!?]", normalized)
    return match.group(0) if match else normalized


def _write_firered_reference_crop(source: Path, target: Path, *, max_seconds: float = 3.0) -> None:
    import soundfile as sf

    audio, sample_rate = sf.read(source, dtype="float32", always_2d=False)
    frame_count = max(1, min(len(audio), int(sample_rate * max_seconds)))
    sf.write(target, audio[:frame_count], sample_rate, subtype="PCM_16")


def generate_sarashina(request: WslTtsRequest) -> None:
    from sarashina_tts.generate.generate import SarashinaTTSGenerator

    model_dir = _model_dir("sarashina")
    generator = SarashinaTTSGenerator(
        model_dir=str(model_dir),
        model_id="sbintuitions/sarashina2.2-tts",
        watermark=True,
    )
    prompt_path = str(request.reference_audio_path)
    audio_codes = generator._extract_audio_prompt_tokens(audio_prompt_path=prompt_path)
    flow_embedding = generator._extract_zero_shot_embedding(audio_prompt_path=prompt_path)
    prompt_feat = generator._extract_audio_prompt_feat(audio_prompt_path=prompt_path)
    wavs = generator.generate(
        [request.text],
        flow_embedding=flow_embedding,
        audio_prompt_text=request.reference_text,
        audio_prompt_tokens=audio_codes,
        audio_prompt_feat=prompt_feat,
        audio_prompt_path=prompt_path,
        flow_embedding_only=False,
    )
    with tempfile.TemporaryDirectory(prefix="sarashina-tts-") as raw_tmp:
        tmp_dir = Path(raw_tmp)
        generator.save_audios(wavs, output_dir=str(tmp_dir))
        _copy_generated_wav(tmp_dir, request.output_path)


def generate_firered(request: WslTtsRequest) -> None:
    import numpy as np
    import soundfile as sf
    import torch

    if _force_torch_compile_eager(torch):
        print("[INFO] fireredtts2: torch.compile forced to eager mode", file=sys.stderr, flush=True)
    if _enable_low_memory_torch_load(torch):
        print("[INFO] fireredtts2: CPU checkpoints will be memory-mapped", file=sys.stderr, flush=True)
    from fireredtts2.fireredtts2 import FireRedTTS2

    model_dir = _model_dir("fireredtts2")
    if not model_dir.is_dir():
        raise FileNotFoundError(f"FireRedTTS-2 model directory not found: {model_dir}")
    def apply_seed() -> None:
        if request.seed is None:
            return
        torch.manual_seed(request.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(request.seed)

    apply_seed()
    with tempfile.TemporaryDirectory(prefix="fireredtts2-") as raw_tmp:
        tmp_dir = Path(raw_tmp)
        reference_pcm16 = tmp_dir / "reference_pcm16.wav"
        reference_audio, reference_rate = sf.read(request.reference_audio_path, dtype="float32", always_2d=False)
        sf.write(reference_pcm16, reference_audio, reference_rate, subtype="PCM_16")
        model = FireRedTTS2(pretrained_dir=str(model_dir), gen_type="monologue", device="cuda")
        try:
            audio = model.generate_monologue(
                text=request.text,
                prompt_wav=str(reference_pcm16),
                prompt_text=request.reference_text,
            )
        except RuntimeError as exc:
            if "non-empty TensorList" not in str(exc):
                raise
            fallback_reference = tmp_dir / "reference_fallback_pcm16.wav"
            fallback_text = _first_reference_sentence(request.reference_text)
            if not fallback_text:
                raise
            _write_firered_reference_crop(request.reference_audio_path, fallback_reference, max_seconds=3.0)
            print(
                "[INFO] fireredtts2: retrying with a 3-second aligned reference after empty generation",
                file=sys.stderr,
                flush=True,
            )
            apply_seed()
            audio = model.generate_monologue(
                text=request.text,
                prompt_wav=str(fallback_reference),
                prompt_text=fallback_text,
            )
        output = audio.detach().cpu().float().numpy()
        if output.ndim == 2 and output.shape[0] <= 2:
            output = np.transpose(output)
        sf.write(request.output_path, output, 24000, subtype="PCM_16")


def generate_t5gemma(request: WslTtsRequest) -> None:
    import soundfile as sf

    vendor_dir = _vendor_dir("t5gemma")
    model_dir = _model_dir("t5gemma")
    vendor_script = vendor_dir / "inference_commandline_hf.py"
    script = Path(__file__).resolve().with_name("t5gemma_offline_infer.py")
    if not vendor_script.is_file():
        raise FileNotFoundError(f"T5Gemma inference script not found: {vendor_script}")
    if not script.is_file():
        raise FileNotFoundError(f"T5Gemma offline wrapper not found: {script}")
    if not model_dir.is_dir():
        raise FileNotFoundError(f"T5Gemma model directory not found: {model_dir}")
    target_duration: float | None = None
    if request.speed_scale is not None:
        if request.speed_scale <= 0:
            raise ValueError("speed_scale must be greater than 0")
        reference_duration = float(sf.info(request.reference_audio_path).duration)
        reference_units = max(1, len("".join(request.reference_text.split())))
        target_units = max(1, len("".join(request.text.split())))
        natural_duration = reference_duration * target_units / reference_units
        target_duration = round(max(0.5, min(100.0, natural_duration / request.speed_scale)), 3)
    with tempfile.TemporaryDirectory(prefix="t5gemma-tts-") as raw_tmp:
        tmp_dir = Path(raw_tmp)
        command = [
            sys.executable,
            str(script),
            "--vendor_dir",
            str(vendor_dir),
            "--model_dir",
            str(model_dir),
            "--target_text",
            request.text,
            "--reference_text",
            request.reference_text,
            "--reference_speech",
            str(request.reference_audio_path),
            "--lang",
            "ja",
            "--seed",
            str(request.seed if request.seed is not None else 1),
            "--output_dir",
            str(tmp_dir),
        ]
        if target_duration is not None:
            command.extend(["--target_duration", str(target_duration)])
        offline_keys = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
        previous_offline = {key: os.environ.get(key) for key in offline_keys}
        try:
            for key in offline_keys:
                os.environ[key] = "1"
            _run(command, cwd=vendor_dir, label="T5Gemma-TTS inference")
        finally:
            for key, value in previous_offline.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        generated = tmp_dir / "generated.wav"
        if not generated.is_file():
            raise RuntimeError(f"T5Gemma-TTS did not create {generated}")
        audio, sample_rate = sf.read(generated, dtype="float32", always_2d=False)
        sf.write(request.output_path, audio, sample_rate, subtype="PCM_16")
