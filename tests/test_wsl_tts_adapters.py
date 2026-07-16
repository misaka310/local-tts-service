from __future__ import annotations

from pathlib import Path
import wave

import numpy as np
import soundfile as sf

from scripts import wsl_tts_adapters
from scripts.wsl_tts_infer import WslTtsRequest


def test_t5gemma_normalizes_float_wav_to_pcm16(tmp_path: Path, monkeypatch) -> None:
    vendor_dir = tmp_path / "vendor"
    model_dir = tmp_path / "model"
    vendor_dir.mkdir()
    model_dir.mkdir()
    (vendor_dir / "inference_commandline_hf.py").write_text("# test stub\n", encoding="utf-8")

    reference_audio = tmp_path / "reference.wav"
    reference_text = tmp_path / "reference.txt"
    sf.write(reference_audio, np.zeros(64000, dtype=np.float32), 16000, subtype="PCM_16")
    reference_text.write_text("参照音声です。", encoding="utf-8")
    output_path = tmp_path / "output.wav"

    def fake_run(command: list[str], *, cwd: Path, label: str) -> None:
        assert "--low_vram" not in command
        assert float(command[command.index("--target_duration") + 1]) == 3.2
        output_dir = Path(command[command.index("--output_dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        samples = np.linspace(-0.25, 0.25, 3200, dtype=np.float32)
        sf.write(output_dir / "generated.wav", samples, 16000, subtype="FLOAT")

    monkeypatch.setattr(wsl_tts_adapters, "_vendor_dir", lambda _: vendor_dir)
    monkeypatch.setattr(wsl_tts_adapters, "_model_dir", lambda _: model_dir)
    monkeypatch.setattr(wsl_tts_adapters, "_run", fake_run)

    request = WslTtsRequest(
        model="t5gemma_tts_2b_2b",
        model_id="Aratako/T5Gemma-TTS-2b-2b",
        text="参照音声です。",
        reference_audio_path=reference_audio,
        reference_text_path=reference_text,
        reference_text="参照音声です。",
        output_path=output_path,
        seed=1,
        speed_scale=1.25,
        language="ja",
    )

    wsl_tts_adapters.generate_t5gemma(request)

    with wave.open(str(output_path), "rb") as wav:
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16000
        assert wav.getnframes() == 3200
