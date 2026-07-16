from __future__ import annotations

from local_tts_service.models import ModelConfig
from local_tts_service.runtimes.qwen3_tts import Qwen3TTSRuntime


def test_dependency_availability_check_does_not_import_heavy_module(monkeypatch) -> None:
    imported: list[str] = []

    def fail_if_imported(module_name: str):
        imported.append(module_name)
        raise AssertionError("availability checks must not import heavy model packages")

    monkeypatch.setattr("local_tts_service.runtimes.qwen3_tts.importlib.import_module", fail_if_imported)
    monkeypatch.setattr("local_tts_service.runtimes.qwen3_tts.importlib.util.find_spec", lambda _: object())

    runtime = object.__new__(Qwen3TTSRuntime)

    assert runtime._has_dependency("qwen_tts") is True
    assert imported == []


def test_resolve_model_path_finds_setup_download_directory(tmp_path) -> None:
    model_dir = tmp_path / "Qwen__Qwen3-TTS-12Hz-1.7B-VoiceDesign"
    model_dir.mkdir()
    runtime = Qwen3TTSRuntime(
        output_dir=tmp_path / "audio",
        models={},
        vendor_dir=tmp_path,
        allow_download=False,
    )
    model = ModelConfig(
        runtime="qwen3_tts",
        model_id="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    )

    assert runtime._resolve_model_path("qwen3_tts_design_1_7b", model) == model_dir
