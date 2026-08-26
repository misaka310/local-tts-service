from __future__ import annotations

import json
from pathlib import Path

from local_tts_service.config import load_config


ROOT = Path(__file__).resolve().parent.parent


def test_asmr_models_are_registered_with_expected_capabilities() -> None:
    config = load_config(ROOT)

    orpheus = config.models["orpheus_3b_asmr"]
    assert orpheus.runtime == "external_cli"
    assert orpheus.model_id == "nyuuzyou/Orpheus-3B-ASMR"
    assert orpheus.external_command_key == "orpheus_asmr"
    assert orpheus.requires_reference_audio is False
    assert orpheus.requires_reference_text is False
    assert orpheus.supports_reference_voice is False
    assert orpheus.supports_voice_clone is False
    assert orpheus.default_language == "en"

    ming = config.models["ming_omni_tts_0_5b"]
    assert ming.runtime == "external_cli"
    assert ming.model_id == "inclusionAI/Ming-omni-tts-0.5B"
    assert ming.external_command_key == "ming_omni_tts"
    assert ming.requires_reference_audio is False
    assert ming.requires_reference_text is False
    assert ming.supports_reference_voice is True
    assert ming.supports_voice_clone is True
    assert ming.supports_instruction is True
    assert ming.default_language == "zh"


def test_asmr_request_contract_allows_no_reference(tmp_path: Path) -> None:
    from scripts.wsl_tts_infer import load_request

    orpheus_path = tmp_path / "orpheus.json"
    orpheus_path.write_text(
        json.dumps(
            {
                "model": "orpheus_3b_asmr",
                "modelId": "nyuuzyou/Orpheus-3B-ASMR",
                "text": "You can relax now while I speak softly beside you.",
                "outputPath": str(tmp_path / "orpheus.wav"),
            }
        ),
        encoding="utf-8",
    )
    orpheus = load_request(orpheus_path)
    assert orpheus.reference_audio_path is None
    assert orpheus.reference_text_path is None
    assert orpheus.language == "en"

    ming_path = tmp_path / "ming.json"
    ming_path.write_text(
        json.dumps(
            {
                "model": "ming_omni_tts_0_5b",
                "modelId": "inclusionAI/Ming-omni-tts-0.5B",
                "text": "今晚可以安心休息。",
                "instruction": "ASMR whisper, very low volume, close microphone, slow and breathy",
                "outputPath": str(tmp_path / "ming.wav"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ming = load_request(ming_path)
    assert ming.reference_audio_path is None
    assert ming.reference_text_path is None
    assert ming.language == "zh"
    assert ming.instruction == "ASMR whisper, very low volume, close microphone, slow and breathy"


def test_asmr_dispatch_and_setup_targets_are_wired() -> None:
    from scripts.wsl_tts_bridge import environment_key_for_model
    from scripts.wsl_tts_runner import GENERATORS

    assert environment_key_for_model("orpheus_3b_asmr") == "orpheus_asmr"
    assert environment_key_for_model("ming_omni_tts_0_5b") == "ming_omni_tts"
    assert "orpheus_3b_asmr" in GENERATORS
    assert "ming_omni_tts_0_5b" in GENERATORS

    setup_source = (ROOT / "scripts" / "setup_wsl_tts_models.sh").read_text(encoding="utf-8")
    assert "want_asmr orpheus_asmr" in setup_source
    assert "want_asmr ming_omni_tts" in setup_source
    assert "onnxruntime-gpu" in setup_source


def test_orpheus_setup_uses_cpu_orpheus_cpp_and_local_asmr_gguf() -> None:
    setup_source = (ROOT / "scripts" / "setup_wsl_tts_models.sh").read_text(encoding="utf-8")
    check_source = (ROOT / "scripts" / "check_wsl_tts.sh").read_text(encoding="utf-8")
    adapter_source = (ROOT / "scripts" / "wsl_asmr_tts_adapters.py").read_text(encoding="utf-8")

    assert "https://github.com/freddyaboulton/orpheus-cpp.git" in setup_source
    assert "ed126bea531ea9d53ef7564b00e8bc23f8f9aebe" in setup_source
    assert "HummingbirdCake/Orpheus-3B-ASMR-Q4_K_M-GGUF" in setup_source
    assert "orpheus-3b-asmr-q4_k_m.gguf" in setup_source
    assert "onnx-community/snac_24khz-ONNX" in setup_source
    assert "snac-decoder_model.onnx" in setup_source
    assert 'hf download "$ORPHEUS_SNAC_REPO" "$ORPHEUS_SNAC_FILE" --revision "$ORPHEUS_SNAC_REV" --quiet' in setup_source
    assert "llama-cpp-python" in setup_source
    assert "https://abetlen.github.io/llama-cpp-python/whl/cpu" in setup_source
    assert "canopyai/Orpheus-TTS.git" not in setup_source

    assert 'REQUIRED_MODEL="orpheus-3b-asmr-q4_k_m.gguf"' in check_source
    assert 'REQUIRED_MODEL_EXTRA="snac-decoder_model.onnx"' in check_source
    assert 'IMPORT_MODULE="orpheus_cpp"' in check_source
    assert 'REQUIRE_TORCH="0"' in check_source

    assert "OrpheusCpp" in adapter_source
    assert "n_gpu_layers=0" in adapter_source
    assert "HummingbirdCake/Orpheus-3B-ASMR-Q4_K_M-GGUF" in adapter_source
    assert "snac-decoder_model.onnx" in adapter_source
    assert "VLLM_USE_V2_MODEL_RUNNER" not in adapter_source
    assert "OrpheusModel" not in adapter_source


def test_orpheus_snac_session_disables_onnx_memory_reuse() -> None:
    from scripts.wsl_asmr_tts_adapters import _create_orpheus_snac_session

    calls: dict[str, object] = {}

    class FakeSessionOptions:
        def __init__(self) -> None:
            self.enable_mem_reuse = True

    class FakeOnnxRuntime:
        SessionOptions = FakeSessionOptions

        @staticmethod
        def InferenceSession(path, *, sess_options, providers):
            calls["path"] = path
            calls["enable_mem_reuse"] = sess_options.enable_mem_reuse
            calls["providers"] = providers
            return "session"

    session = _create_orpheus_snac_session(FakeOnnxRuntime, Path("decoder.onnx"))

    assert session == "session"
    assert calls == {
        "path": "decoder.onnx",
        "enable_mem_reuse": False,
        "providers": ["CPUExecutionProvider"],
    }


def test_orpheus_constructor_uses_local_cpu_snac_and_bounded_llama_context() -> None:
    from scripts.wsl_asmr_tts_adapters import _construct_orpheus_model_with_local_snac

    calls: dict[str, object] = {}

    class FakeSessionOptions:
        def __init__(self) -> None:
            self.enable_mem_reuse = True

    class FakeOnnxRuntime:
        SessionOptions = FakeSessionOptions

        @staticmethod
        def InferenceSession(path, *args, **kwargs):
            calls["path"] = str(path)
            session_options = kwargs.get("sess_options")
            calls["enable_mem_reuse"] = getattr(session_options, "enable_mem_reuse", None)
            calls["providers"] = kwargs.get("providers")
            return "cpu-session"

    class FakeLlamaModule:
        class Llama:
            def __init__(self, *args, **kwargs) -> None:
                calls["llama_args"] = args
                calls["llama_kwargs"] = dict(kwargs)

    original_inference_session = FakeOnnxRuntime.InferenceSession
    original_llama = FakeLlamaModule.Llama

    class FakeModule:
        onnxruntime = FakeOnnxRuntime

    class FakeOrpheus:
        def __init__(self, **kwargs) -> None:
            calls["constructor_kwargs"] = kwargs
            self._model = FakeLlamaModule.Llama(
                model_path="model.gguf",
                n_ctx=0,
                n_gpu_layers=kwargs["n_gpu_layers"],
            )
            self._snac_session = FakeModule.onnxruntime.InferenceSession(
                "decoder.onnx",
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )

    model = _construct_orpheus_model_with_local_snac(
        FakeOrpheus,
        FakeModule,
        Path("decoder.onnx"),
        llama_cpp_module=FakeLlamaModule,
    )

    assert model._snac_session == "cpu-session"
    assert calls["enable_mem_reuse"] is False
    assert calls["providers"] == ["CPUExecutionProvider"]
    assert calls["llama_kwargs"] == {
        "model_path": "model.gguf",
        "n_ctx": 4096,
        "n_gpu_layers": 0,
    }
    assert calls["constructor_kwargs"] == {
        "n_gpu_layers": 0,
        "n_threads": 0,
        "verbose": False,
        "lang": "en",
    }
    assert FakeOnnxRuntime.InferenceSession is original_inference_session
    assert FakeLlamaModule.Llama is original_llama


def test_real_verifier_supports_optional_asmr_models_without_forced_reference() -> None:
    verify_py = (ROOT / "scripts" / "verify_wsl_tts_models.py").read_text(encoding="utf-8")
    verify_ps1 = (ROOT / "scripts" / "verify-wsl-tts-models.ps1").read_text(encoding="utf-8")

    assert '"orpheus_3b_asmr"' in verify_py
    assert '"ming_omni_tts_0_5b"' in verify_py
    assert 'REFERENCE_MODELS = set(MODELS) - {"orpheus_3b_asmr"}' in verify_py
    assert "MODEL_TEXT = {" in verify_py
    assert '"orpheus_3b_asmr": "You can relax now while I speak softly beside you.' in verify_py
    assert "orpheus_3b_asmr" in verify_ps1
    assert "ming_omni_tts_0_5b" in verify_ps1


def test_wsl_failure_path_keeps_actionable_diagnostics() -> None:
    cli_source = (ROOT / "scripts" / "wsl_tts_cli.py").read_text(encoding="utf-8")
    shell_source = (ROOT / "scripts" / "run_wsl_tts.sh").read_text(encoding="utf-8")
    powershell_source = (ROOT / "scripts" / "run-wsl-tts.ps1").read_text(encoding="utf-8")
    adapter_source = (ROOT / "scripts" / "wsl_asmr_tts_adapters.py").read_text(encoding="utf-8")

    assert "faulthandler.enable(all_threads=True)" in cli_source
    assert "except SystemExit as exc" in cli_source
    assert "SystemExit(code=" in cli_source
    assert "python exited with status" in shell_source
    assert "$Succeeded = $false" in powershell_source
    assert "if ($Succeeded)" in powershell_source
    assert "Remove-Item -LiteralPath $StdoutLog" in powershell_source
    assert "Remove-Item -LiteralPath $StderrLog" in powershell_source
    assert "[TRACE] orpheus:model-load:start" in adapter_source
    assert "[TRACE] orpheus:model-load:done" in adapter_source
    assert "[TRACE] orpheus:tts:start" in adapter_source
    assert "[TRACE] orpheus:tts:done" in adapter_source
    assert "[TRACE] orpheus:wav:done" in adapter_source
