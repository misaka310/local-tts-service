from __future__ import annotations

from local_tts_service.models import SpeakRequest


def test_speak_request_validates_text() -> None:
    req = SpeakRequest(text="  hello  ")
    assert req.text == "hello"


def test_speak_request_rejects_empty_text() -> None:
    try:
        SpeakRequest(text="   ")
        assert False, "should fail"
    except Exception as exc:
        assert "text is empty" in str(exc)


def test_speak_request_normalizes_caption() -> None:
    req = SpeakRequest(text="hello", caption="  ASMR風  ")
    assert req.caption == "ASMR風"


def test_speak_request_accepts_voice_id() -> None:
    req = SpeakRequest(text="hello", voiceId="person_a")
    assert req.voiceId == "person_a"


def test_speak_request_rejects_invalid_voice_id() -> None:
    try:
        SpeakRequest(text="hello", voiceId="../secret")
        assert False, "should fail"
    except Exception as exc:
        assert "voiceId contains invalid path characters" in str(exc)


def test_speak_request_rejects_voice_id_with_spaces() -> None:
    try:
        SpeakRequest(text="hello", voiceId="person a")
        assert False, "should fail"
    except Exception as exc:
        assert "voiceId must use only" in str(exc)


def test_speak_request_accepts_optional_seed() -> None:
    req = SpeakRequest(text="hello", seed=1234)
    assert req.seed == 1234


def test_speak_request_accepts_instruction_and_language() -> None:
    req = SpeakRequest(text="hello", instruction="  calm  ", language="  Japanese  ")
    assert req.instruction == "calm"
    assert req.language == "Japanese"


def test_speak_request_accepts_native_synthesis_controls() -> None:
    req = SpeakRequest(text="hello", speedScale=1.15, styleStrength=4.5)
    assert req.speedScale == 1.15
    assert req.styleStrength == 4.5


def test_speak_request_rejects_out_of_range_native_synthesis_controls() -> None:
    for payload in ({"speedScale": 0.2}, {"speedScale": 2.5}, {"styleStrength": 0.5}, {"styleStrength": 8.0}):
        try:
            SpeakRequest(text="hello", **payload)
            assert False, f"should reject {payload}"
        except Exception as exc:
            assert "less than or equal" in str(exc) or "greater than or equal" in str(exc)
