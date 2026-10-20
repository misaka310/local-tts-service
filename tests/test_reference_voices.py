from __future__ import annotations

from local_tts_service.reference_voices import find_reference_voice, scan_reference_voices


def test_scan_reference_voices_rejects_invalid_directory_name(tmp_path) -> None:
    invalid_dir = tmp_path / "bad voice"
    invalid_dir.mkdir(parents=True, exist_ok=True)
    (invalid_dir / "voice.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")

    voices = scan_reference_voices(tmp_path)

    assert len(voices) == 1
    assert voices[0].voice_id == "bad voice"
    assert voices[0].enabled is False
    assert "voiceId must use only" in str(voices[0].error_reason)


def test_scan_reference_voices_requires_text_when_requested(tmp_path) -> None:
    voice_dir = tmp_path / "person_a"
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "voice.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")

    voices = scan_reference_voices(tmp_path, require_reference_text=True)

    assert len(voices) == 1
    assert voices[0].enabled is False
    assert voices[0].has_reference_audio is True
    assert voices[0].has_reference_text is False
    assert voices[0].error_reason == "missing: voice.txt or text.txt"


def test_scan_reference_voices_accepts_voice_txt_when_requested(tmp_path) -> None:
    voice_dir = tmp_path / "person_a"
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "voice.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    (voice_dir / "voice.txt").write_text("hello", encoding="utf-8")

    voices = scan_reference_voices(tmp_path, require_reference_text=True)

    assert len(voices) == 1
    assert voices[0].enabled is True
    assert voices[0].has_reference_text is True
    assert voices[0].text_path.name == "voice.txt"


def test_find_reference_voice_returns_enabled_item(tmp_path) -> None:
    voice_dir = tmp_path / "person_a"
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "voice.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    (voice_dir / "text.txt").write_text("hello", encoding="utf-8")

    voice = find_reference_voice(tmp_path, "person_a", require_reference_text=True)

    assert voice is not None
    assert voice.enabled is True


def test_find_reference_voice_prefers_voice_txt_when_both_exist(tmp_path) -> None:
    voice_dir = tmp_path / "person_a"
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "voice.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    (voice_dir / "text.txt").write_text("legacy", encoding="utf-8")
    (voice_dir / "voice.txt").write_text("preferred", encoding="utf-8")

    voice = find_reference_voice(tmp_path, "person_a", require_reference_text=True)

    assert voice is not None
    assert voice.enabled is True
    assert voice.text_path.name == "voice.txt"


def test_scan_reference_voices_skips_archive_directories(tmp_path) -> None:
    voice_dir = tmp_path / "person_a"
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "voice.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")

    archived_voice_dir = tmp_path / "_archive_20260705" / "legacy_voice"
    archived_voice_dir.mkdir(parents=True, exist_ok=True)
    (archived_voice_dir / "voice.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")

    voices = scan_reference_voices(tmp_path)

    assert [voice.voice_id for voice in voices] == ["person_a"]
