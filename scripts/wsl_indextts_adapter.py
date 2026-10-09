from __future__ import annotations

import os
from pathlib import Path
import sys

from scripts.wsl_tts_infer import WslTtsRequest, _model_dir, _vendor_dir


def generate_indextts_2_5(request: WslTtsRequest) -> None:
    """Run official IndexTTS 2.5 voice cloning in its isolated WSL environment."""
    if request.reference_audio_path is None:
        raise ValueError("IndexTTS 2.5 requires a reference audio file")
    vendor = _vendor_dir("indextts_2_5")
    model = _model_dir("indextts_2_5")
    config = model / "config.yaml"
    if not (vendor / "indextts/infer_v2_5.py").is_file():
        raise FileNotFoundError(f"IndexTTS 2.5 source missing: {vendor}")
    if not config.is_file():
        raise FileNotFoundError(f"IndexTTS 2.5 config missing: {config}")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("IndexTTS 2.5 CUDA is unavailable; CPU fallback is disabled")
    from indextts.infer_v2_5 import IndexTTS2

    language = {"ja": "JA", "japanese": "JA", "en": "EN",
                "english": "EN", "zh": "ZH", "chinese": "ZH",
                "es": "ES", "spanish": "ES"}.get(request.language.lower())
    if not language:
        raise ValueError(f"IndexTTS 2.5 unsupported language: {request.language}")
    if request.seed is not None:
        torch.manual_seed(request.seed)
        torch.cuda.manual_seed_all(request.seed)
    # The upstream module uses relative paths when locating auxiliary checkpoints.
    previous_cwd = Path.cwd()
    os.chdir(vendor)
    try:
        tts = IndexTTS2(cfg_path=str(config), model_dir=str(model),
                        use_bf16=True, use_cuda_kernel=False, use_deepspeed=False)
        duration_factor = 1.0 if request.speed_scale is None else 1.0 / request.speed_scale
        result = tts.infer(
            spk_audio_prompt=str(request.reference_audio_path), text=request.text,
            lang=language, output_path=str(request.output_path),
            duration_factor=duration_factor, verbose=True,
        )
        if not request.output_path.is_file():
            raise RuntimeError(f"IndexTTS 2.5 created no WAV (result={result!r})")
        print(f"[TRACE] IndexTTS 2.5 device=cuda dtype=bf16 gpu={torch.cuda.get_device_name()}", file=sys.stderr)
    finally:
        os.chdir(previous_cwd)
