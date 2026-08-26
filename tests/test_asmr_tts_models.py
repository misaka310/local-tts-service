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
