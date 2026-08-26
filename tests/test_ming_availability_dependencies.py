from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_ming_availability_checks_constructor_time_dependencies() -> None:
    source = (ROOT / "scripts" / "check_wsl_tts.sh").read_text(encoding="utf-8")

    assert 'IMPORT_MODULE_EXTRA="torchaudio yaml numpy loguru huggingface_hub onnxruntime"' in source


def test_ming_setup_installs_upstream_missing_loguru_dependency() -> None:
    source = (ROOT / "scripts" / "setup_wsl_tts_models.sh").read_text(encoding="utf-8")

    assert 'uv pip install --python "$python" inflect onnxruntime-gpu loguru' in source
