from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = REPO_ROOT / "scripts" / "f5_tts_runtime.py"


def _load_runtime():
    assert RUNTIME_PATH.is_file(), "the F5 runtime command builder is missing"
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("f5_tts_runtime_under_test", RUNTIME_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_f5_inference_arguments_use_japanese_checkpoint_and_request_inputs(tmp_path: Path) -> None:
    runtime = _load_runtime()
    basic_config = tmp_path / "venv" / "Lib" / "site-packages" / "f5_tts" / "infer" / "examples" / "basic" / "basic.toml"
    model_config = tmp_path / "venv" / "Lib" / "site-packages" / "f5_tts" / "configs" / "F5TTS_v1_Base.yaml"
    checkpoint = tmp_path / "models" / "f5-tts" / "JA_21999120" / "model_21999120.pt"
    vocab = tmp_path / "models" / "f5-tts" / "JA_21999120" / "vocab_japanese.txt"
    reference = tmp_path / "reference-voices" / "voice.wav"
    output = tmp_path / "f5 output.wav"
    reference_text = "これは参照音声の内容です。"
    text = "これはF5-TTSの日本語生成確認です。"

    arguments = runtime.build_inference_arguments(
        basic_config=basic_config,
        model_config=model_config,
        checkpoint=checkpoint,
        vocab=vocab,
        reference_audio=reference,
        reference_text=reference_text,
        text=text,
        output_path=output,
        device="cuda:0",
    )

    assert arguments == [
        "-c",
        str(basic_config),
        "-mc",
        str(model_config),
        "-m",
        "F5TTS_v1_Base",
        "-p",
        str(checkpoint),
        "-v",
        str(vocab),
        "-r",
        str(reference),
        "-s",
        reference_text,
        "-t",
        text,
        "-o",
        str(tmp_path),
        "-w",
        output.name,
        "--device",
        "cuda:0",
    ]


def test_f5_setup_pins_windows_compatible_torch_and_torchcodec() -> None:
    setup_script = REPO_ROOT / "scripts" / "setup-f5-tts.ps1"
    source = setup_script.read_text(encoding="utf-8-sig")

    assert "https://download.pytorch.org/whl/cu128" in source
    assert "torch==2.10.0" in source
    assert "torchaudio==2.10.0" in source
    assert "torchcodec==0.10.0" in source


def test_f5_namespace_package_uses_filesystem_search_locations(tmp_path: Path, monkeypatch) -> None:
    runtime = _load_runtime()
    incomplete = tmp_path / "first" / "f5_tts"
    complete = tmp_path / "second" / "f5_tts"
    required = (
        Path("infer") / "examples" / "basic" / "basic.toml",
        Path("configs") / "F5TTS_v1_Base.yaml",
    )
    (incomplete / required[0]).parent.mkdir(parents=True)
    (incomplete / required[0]).write_text("config", encoding="utf-8")
    for relative in required:
        target = complete / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("config", encoding="utf-8")

    class NamespacePackageSpec:
        def __init__(self) -> None:
            self.submodule_search_locations = [str(incomplete), str(complete)]

    monkeypatch.setattr(runtime.importlib.util, "find_spec", lambda _: NamespacePackageSpec())

    assert runtime._resolve_f5_package_root() == complete


def test_f5_reference_audio_load_uses_soundfile_channels_first(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    import numpy as np

    runtime = _load_runtime()
    reference_audio = tmp_path / "reference.wav"
    audio = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]], dtype=np.float32)
    read_calls = []

    def read(source, *, dtype, always_2d):
        read_calls.append((source, dtype, always_2d))
        return audio, 24000

    def unexpected_torchaudio_load(*args, **kwargs):
        raise AssertionError("TorchAudio's TorchCodec-backed loader should not be called")

    fake_torchaudio = SimpleNamespace(load=unexpected_torchaudio_load)
    monkeypatch.setitem(sys.modules, "soundfile", SimpleNamespace(read=read))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(from_numpy=lambda tensor: tensor))
    monkeypatch.setitem(sys.modules, "torchaudio", fake_torchaudio)

    runtime._patch_torchaudio_load_with_soundfile()
    waveform, sample_rate = fake_torchaudio.load(reference_audio)

    assert read_calls == [(reference_audio, "float32", True)]
    assert sample_rate == 24000
    assert np.array_equal(waveform, audio.T)
    assert waveform.flags.c_contiguous
