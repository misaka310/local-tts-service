from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_ming_real_verifier_uses_the_no_reference_happy_path() -> None:
    source = (ROOT / "scripts" / "verify_wsl_tts_models.py").read_text(encoding="utf-8")

    assert 'REFERENCE_MODELS = set(MODELS) - {"orpheus_3b_asmr", "ming_omni_tts_0_5b"}' in source
