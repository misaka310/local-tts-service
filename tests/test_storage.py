from __future__ import annotations

import wave

from local_tts_service.storage import build_output_basename, concat_wav_files, ensure_safe_audio_filename, safe_request_id, write_silence_wav


def test_safe_request_id() -> None:
    rid = safe_request_id("hello/world")
    assert "/" not in rid
    assert rid


def test_build_output_basename_prefix() -> None:
    name = build_output_basename("text", "req-1")
    assert name.startswith("tts-")


def test_safe_audio_filename_blocks_traversal() -> None:
    try:
        ensure_safe_audio_filename("../evil.wav")
        assert False, "should fail"
    except Exception:
        pass


def test_concat_wav_files_inserts_configured_pause(tmp_path) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    merged = tmp_path / "merged.wav"
    write_silence_wav(first, duration_sec=0.05, sample_rate=8000)
    write_silence_wav(second, duration_sec=0.05, sample_rate=8000)

    concat_wav_files([first, second], merged, pause_between_chunks_ms=20)

    with wave.open(str(merged), "rb") as fp:
        assert fp.getframerate() == 8000
        assert fp.getnframes() == 960
