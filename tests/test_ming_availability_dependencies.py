from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_ming_availability_checks_constructor_time_dependencies() -> None:
    source = (ROOT / "scripts" / "check_wsl_tts.sh").read_text(encoding="utf-8")

    assert 'IMPORT_MODULE_EXTRA="torchaudio yaml numpy loguru huggingface_hub onnxruntime"' in source
