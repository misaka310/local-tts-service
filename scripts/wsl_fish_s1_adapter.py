from __future__ import annotations

from pathlib import Path
import sys
import tempfile

from scripts.wsl_tts_infer import WslTtsRequest, _copy_generated_wav, _model_dir, _run, _vendor_dir


def generate_fish_s1(request: WslTtsRequest) -> None:
    vendor_dir = _vendor_dir("fish_s1_mini")
    model_dir = _model_dir("fish_s1_mini")
    codec_script = vendor_dir / "fish_speech" / "models" / "dac" / "inference.py"
    semantic_script = vendor_dir / "fish_speech" / "models" / "text2semantic" / "inference.py"
    codec_path = model_dir / "codec.pth"
    model_path = model_dir / "model.pth"
    if not codec_script.is_file() or not semantic_script.is_file():
        raise FileNotFoundError(f"Fish Speech S1-compatible inference code not found: {vendor_dir}")
    if not codec_path.is_file() or not model_path.is_file():
        raise FileNotFoundError(f"FishAudio S1-mini weights not found: {model_dir}")

    with tempfile.TemporaryDirectory(prefix="fish-s1-mini-") as raw_tmp:
        tmp_dir = Path(raw_tmp)
        _run(
            [
                sys.executable,
                str(codec_script),
                "-i",
                str(request.reference_audio_path),
                "--checkpoint-path",
                str(codec_path),
                "--config-name",
                "modded_dac_vq",
            ],
            cwd=tmp_dir,
            label="FishAudio reference encoding",
        )
        prompt_file = tmp_dir / "fake.npy"
        if not prompt_file.is_file():
            raise RuntimeError("FishAudio reference encoder did not create fake.npy")
        semantic_command = [
            sys.executable,
            str(semantic_script),
            "--text",
            request.text,
            "--prompt-text",
            request.reference_text,
            "--prompt-tokens",
            str(prompt_file),
            "--checkpoint-path",
            str(model_dir),
            "--num-samples",
            "1",
            "--output-dir",
            str(tmp_dir),
        ]
        if request.seed is not None:
            semantic_command.extend(["--seed", str(request.seed)])
        _run(semantic_command, cwd=tmp_dir, label="FishAudio semantic generation")
        code_files = sorted(tmp_dir.glob("codes_*.npy"))
        if not code_files:
            raise RuntimeError("FishAudio semantic generator did not create codes_*.npy")
        reference_preview = tmp_dir / "fake.wav"
        if reference_preview.exists():
            reference_preview.unlink()
        _run(
            [
                sys.executable,
                str(codec_script),
                "-i",
                str(code_files[0]),
                "--checkpoint-path",
                str(codec_path),
                "--config-name",
                "modded_dac_vq",
            ],
            cwd=tmp_dir,
            label="FishAudio waveform decoding",
        )
        _copy_generated_wav(tmp_dir, request.output_path)
