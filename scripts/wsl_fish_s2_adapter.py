from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile

from scripts.wsl_tts_infer import WslTtsRequest, _model_dir, _run, _vendor_dir


def generate_fish_s2_pro(request: WslTtsRequest) -> None:
    """Run the official Fish S2 Pro three-stage reference-cloning CLI."""
    if not request.reference_audio_path or not request.reference_text:
        raise ValueError("Fish S2 Pro requires an aligned reference WAV and transcript")
    vendor = _vendor_dir("fish_s2_pro")
    model = _model_dir("fish_s2_pro")
    codec = vendor / "fish_speech/models/dac/inference.py"
    semantic = vendor / "fish_speech/models/text2semantic/inference.py"
    checkpoint = model / "codec.pth"
    if not codec.is_file() or not semantic.is_file():
        raise FileNotFoundError(f"Fish S2 Pro source missing: {vendor}")
    if not checkpoint.is_file() or not (model / "model.safetensors.index.json").is_file():
        raise FileNotFoundError(f"Fish S2 Pro checkpoints missing: {model}")

    with tempfile.TemporaryDirectory(prefix="fish-s2-pro-") as raw:
        work = Path(raw)
        _run([
            sys.executable, str(codec), "-i", str(request.reference_audio_path),
            "--checkpoint-path", str(checkpoint),
        ], cwd=work, label="Fish S2 Pro reference encoding")
        tokens = work / "fake.npy"
        if not tokens.is_file():
            raise RuntimeError("Fish S2 Pro reference encoding did not create fake.npy")
        command = [
            sys.executable, str(semantic), "--text", request.text,
            "--prompt-text", request.reference_text, "--prompt-tokens", str(tokens),
            "--checkpoint-path", str(model), "--num-samples", "1",
            "--output-dir", str(work),
        ]
        device = os.environ.get("LOCAL_TTS_FISH_S2_SEMANTIC_DEVICE", "cuda").strip().lower()
        if device not in {"cpu", "cuda"}:
            raise ValueError(f"invalid Fish S2 semantic device: {device}")
        command += ["--device", device]
        if request.seed is not None:
            command += ["--seed", str(request.seed)]
        _run(command, cwd=work, label="Fish S2 Pro semantic generation")
        codes = sorted(work.glob("codes_*.npy"))
        if not codes:
            raise RuntimeError("Fish S2 Pro semantic generation created no codes")
        source_preview = work / "fake.wav"
        source_preview.unlink(missing_ok=True)
        _run([
            sys.executable, str(codec), "-i", str(codes[0]),
            "--checkpoint-path", str(checkpoint),
        ], cwd=work, label="Fish S2 Pro waveform decoding")
        generated = work / (codes[0].stem + ".wav")
        # Upstream decoder currently writes fake.wav for codes_*.npy;
        # never accidentally return the reference preview.
        candidates = [p for p in work.glob("*.wav") if p.stat().st_size > 44]
        if not candidates:
            raise RuntimeError("Fish S2 Pro waveform decoder produced no audio")
        import shutil
        shutil.copy2(max(candidates, key=lambda p: p.stat().st_mtime_ns), request.output_path)
