from types import SimpleNamespace
import pytest

from local_tts_service.errors import RequestValidationError
from local_tts_service.models import SpeakRequest
from local_tts_service.synthesis.capability_validator import validate_model_capabilities
from local_tts_service.synthesis.chunking import merge_chunking_override, should_keep_chunk_files, split_text_for_chunks
from local_tts_service.synthesis.request_normalizer import normalize_request
from local_tts_service.synthesis_service import SynthesisService


def _model(**overrides):
    values = {"supports_caption": False, "supports_instruction": False, "supports_speed_control": False, "supports_style_strength": False, "default_language": None}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_compatibility_module_keeps_synthesis_service_export() -> None:
    assert SynthesisService.__module__ == "local_tts_service.synthesis.service"


def test_chunking_override_normalizes_ordered_limits() -> None:
    result = merge_chunking_override({"softChunkChars": 100, "maxChunkChars": 150}, {"softChunkChars": 5, "maxChunkChars": 10, "pauseBetweenChunksMs": -2})
    assert result["softChunkChars"] == 20
    assert result["maxChunkChars"] == 20
    assert result["hardLimitChars"] >= 20
    assert result["pauseBetweenChunksMs"] == 0


def test_split_text_never_exceeds_max_for_hard_piece() -> None:
    chunks = split_text_for_chunks("x" * 61, soft_chunk_chars=10, max_chunk_chars=20, hard_limit_chars=30)
    assert "".join(chunks) == "x" * 61
    assert max(map(len, chunks)) <= 20


def test_request_normalizer_maps_style_caption_to_instruction() -> None:
    payload = SpeakRequest(text="hello", model="design", styleCaption="calm")
    result = normalize_request(payload, _model(supports_instruction=True, default_language="Japanese"))
    assert result.instruction == "calm"
    assert result.payload.language == "Japanese"


def test_capability_validator_rejects_unsupported_caption() -> None:
    with pytest.raises(RequestValidationError, match="caption is not supported"):
        validate_model_capabilities(SpeakRequest(text="hello", model="plain", caption="calm"), "plain", _model())

def test_chunk_retention_environment_overrides_config(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_TTS_KEEP_CHUNKS", "true")
    assert should_keep_chunk_files({"keepChunkFiles": False}) is True
    monkeypatch.setenv("LOCAL_TTS_KEEP_CHUNKS", "0")
    assert should_keep_chunk_files({"keepChunkFiles": True}) is False
