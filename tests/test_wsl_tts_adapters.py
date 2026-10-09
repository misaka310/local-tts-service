from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import types
import wave

import numpy as np
import soundfile as sf

from scripts import t5gemma_offline_infer, wsl_tts_adapters
from scripts.wsl_tts_infer import WslTtsRequest


def test_force_torch_compile_eager_uses_supported_stance() -> None:
    calls: list[str] = []

    class Compiler:
        @staticmethod
        def set_stance(value: str) -> None:
            calls.append(value)

    class Torch:
        compiler = Compiler()

        @staticmethod
        def compile(model=None, **kwargs):
            del kwargs
            return model

    torch = Torch()
    assert wsl_tts_adapters._force_torch_compile_eager(torch) is True
    assert calls == ["force_eager"]
    assert torch.compile("model", fullgraph=True) == "model"
    assert torch.compile(fullgraph=True)("decorated") == "decorated"


def test_force_torch_compile_eager_is_optional() -> None:
    assert wsl_tts_adapters._force_torch_compile_eager(object()) is False


def test_enable_low_memory_torch_load_memory_maps_cpu_paths(tmp_path: Path) -> None:
    calls: list[tuple[tuple, dict]] = []

    class Torch:
        @staticmethod
        def load(*args, **kwargs):
            calls.append((args, kwargs))
            return "loaded"

    torch = Torch()
    checkpoint = tmp_path / "model.pt"
    assert wsl_tts_adapters._enable_low_memory_torch_load(torch) is True
    assert torch.load(checkpoint, map_location="cpu") == "loaded"
    assert calls == [((checkpoint,), {"map_location": "cpu", "mmap": True})]


def test_firered_fallback_uses_first_reference_sentence() -> None:
    assert wsl_tts_adapters._first_reference_sentence(
        "いや、私はダルシムで勝つよ。普通に みんなに。うん。"
    ) == "いや、私はダルシムで勝つよ。"
    assert wsl_tts_adapters._first_reference_sentence("句点なしの参照文") == "句点なしの参照文"


def test_firered_fallback_crops_reference_to_three_seconds(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    target = tmp_path / "target.wav"
    sf.write(source, np.linspace(-0.2, 0.2, 80000, dtype=np.float32), 16000, subtype="PCM_16")

    wsl_tts_adapters._write_firered_reference_crop(source, target, max_seconds=3.0)

    info = sf.info(target)
    assert info.samplerate == 16000
    assert info.frames == 48000
    assert info.subtype == "PCM_16"


def test_enable_low_memory_torch_load_preserves_non_cpu_options(tmp_path: Path) -> None:
    calls: list[tuple[tuple, dict]] = []

    class Torch:
        @staticmethod
        def load(*args, **kwargs):
            calls.append((args, kwargs))
            return "loaded"

    torch = Torch()
    checkpoint = tmp_path / "model.pt"
    assert wsl_tts_adapters._enable_low_memory_torch_load(torch) is True
    assert torch.load(checkpoint, map_location="cuda", mmap=False) == "loaded"
    assert calls == [((checkpoint,), {"map_location": "cuda", "mmap": False})]


def test_t5gemma_offline_wrapper_disables_torch_compile() -> None:
    calls: list[str] = []

    class Compiler:
        @staticmethod
        def set_stance(value: str) -> None:
            calls.append(value)

    class Torch:
        compiler = Compiler()

        @staticmethod
        def compile(model=None, **kwargs):
            del kwargs
            return model

    torch = Torch()
    assert t5gemma_offline_infer.force_torch_compile_eager(torch) is True
    assert calls == ["force_eager"]
    assert torch.compile("model", fullgraph=True) == "model"
    assert torch.compile(fullgraph=True)("decorated") == "decorated"


def test_t5gemma_offline_wrapper_reads_dependency_ids(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    text_key = "text_" + "tokenizer_name"
    (model_dir / "config.json").write_text(
        json.dumps(
            {
                text_key: "example/text-model",
                "xcodec2_model_name": "example/audio-model",
            }
        ),
        encoding="utf-8",
    )

    assert t5gemma_offline_infer.read_dependency_ids(model_dir) == (
        "example/text-model",
        "example/audio-model",
    )


def test_t5gemma_offline_wrapper_checks_only_cached_dependency_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    text_key = "text_" + "tokenizer_name"
    (model_dir / "config.json").write_text(
        json.dumps(
            {
                text_key: "example/text-model",
                "xcodec2_model_name": "example/audio-model",
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    def fake_snapshot_download(**kwargs):
        calls.append(dict(kwargs))
        target = tmp_path / f"snapshot-{len(calls)}"
        target.mkdir()
        return str(target)

    fake_hub = types.ModuleType("huggingface_hub")
    fake_hub.snapshot_download = fake_snapshot_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)

    primary_dir, codec_dir = t5gemma_offline_infer.ensure_cached_dependencies(model_dir)

    assert primary_dir == (tmp_path / "snapshot-1").resolve()
    assert codec_dir == (tmp_path / "snapshot-2").resolve()
    assert calls[0]["repo_id"] == "example/text-model"
    assert calls[0]["local_files_only"] is True
    assert calls[0]["allow_patterns"] == list(
        t5gemma_offline_infer.TEXT_TOKENIZER_ALLOW_PATTERNS
    )
    assert calls[1] == {
        "repo_id": "example/audio-model",
        "local_files_only": True,
    }


def test_t5gemma_offline_wrapper_redirects_primary_loader(tmp_path: Path) -> None:
    calls: list[tuple[object, tuple, dict]] = []

    class BaseLoader:
        @classmethod
        def from_pretrained(cls, name, *args, **kwargs):
            del cls
            calls.append((name, args, kwargs))
            return "loaded"

    local_dir = tmp_path / "cached"
    proxy = t5gemma_offline_infer.local_loader_proxy(
        BaseLoader,
        repo_id="example/text-model",
        local_dir=local_dir,
    )

    assert proxy.from_pretrained("example/text-model", revision="main") == "loaded"
    assert calls == [
        (local_dir, (), {"revision": "main", "local_files_only": True})
    ]


def test_t5gemma_normalizes_float_wav_to_pcm16(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
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
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
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

    assert "HF_HUB_OFFLINE" not in os.environ
    assert "TRANSFORMERS_OFFLINE" not in os.environ
    with wave.open(str(output_path), "rb") as wav:
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16000
        assert wav.getnframes() == 3200
