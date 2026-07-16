from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

from scripts.wsl_tts_infer import WslTtsRequest, _base_dir, _copy_generated_wav, _model_dir, _run, _vendor_dir


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
    from fireredtts2.fireredtts2 import FireRedTTS2

    model_dir = _model_dir("fireredtts2")
    if not model_dir.is_dir():
        raise FileNotFoundError(f"FireRedTTS-2 model directory not found: {model_dir}")
    if request.seed is not None:
        torch.manual_seed(request.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(request.seed)
    with tempfile.TemporaryDirectory(prefix="fireredtts2-") as raw_tmp:
        tmp_dir = Path(raw_tmp)
        reference_pcm16 = tmp_dir / "reference_pcm16.wav"
        reference_audio, reference_rate = sf.read(request.reference_audio_path, dtype="float32", always_2d=False)
        sf.write(reference_pcm16, reference_audio, reference_rate, subtype="PCM_16")
        model = FireRedTTS2(pretrained_dir=str(model_dir), gen_type="monologue", device="cuda")
        audio = model.generate_monologue(
            text=request.text,
            prompt_wav=str(reference_pcm16),
            prompt_text=request.reference_text,
        )
        output = audio.detach().cpu().float().numpy()
        if output.ndim == 2 and output.shape[0] <= 2:
            output = np.transpose(output)
        sf.write(request.output_path, output, 24000, subtype="PCM_16")


def generate_t5gemma(request: WslTtsRequest) -> None:
    import soundfile as sf

    vendor_dir = _vendor_dir("t5gemma")
    model_dir = _model_dir("t5gemma")
    script = vendor_dir / "inference_commandline_hf.py"
    if not script.is_file():
        raise FileNotFoundError(f"T5Gemma inference script not found: {script}")
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
        _run(command, cwd=vendor_dir, label="T5Gemma-TTS inference")
        generated = tmp_dir / "generated.wav"
        if not generated.is_file():
            raise RuntimeError(f"T5Gemma-TTS did not create {generated}")
        audio, sample_rate = sf.read(generated, dtype="float32", always_2d=False)
        sf.write(request.output_path, audio, sample_rate, subtype="PCM_16")
