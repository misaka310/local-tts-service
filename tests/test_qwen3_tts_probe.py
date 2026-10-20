from __future__ import annotations

from local_tts_service.qwen3_tts_probe import (
    build_qwen3_tts_probe_payload,
    build_qwen3_tts_probe_record,
    build_qwen3_tts_probe_targets,
    write_qwen3_tts_probe_index,
    write_qwen3_tts_probe_manifest,
)


def test_build_qwen3_tts_probe_targets() -> None:
    targets = build_qwen3_tts_probe_targets()
    assert [item.model for item in targets] == [
        "irodori_v3",
        "qwen3_tts_clone_0_6b",
        "qwen3_tts_clone_1_7b",
    ]
    assert targets[0].voice_id == "sample_neutral"
    assert targets[-1].voice_id == "sample_neutral"


def test_build_qwen3_tts_probe_payload_for_clone() -> None:
    target = build_qwen3_tts_probe_targets()[-1]
    payload = build_qwen3_tts_probe_payload(target)
    assert payload["model"] == "qwen3_tts_clone_1_7b"
    assert payload["language"] == "Japanese"
    assert "instruction" not in payload
    assert payload["voiceId"] == "sample_neutral"


def test_write_qwen3_tts_probe_files(tmp_path) -> None:
    target = build_qwen3_tts_probe_targets()[0]
    record = build_qwen3_tts_probe_record(
        target,
        status="unavailable",
        available=False,
        unavailable_reason="model missing",
        audio_path="",
        audio_url="",
        error_message=None,
    )
    write_qwen3_tts_probe_manifest([record], tmp_path)
    write_qwen3_tts_probe_index([record], tmp_path)

    assert (tmp_path / "manifest.json").is_file()
    assert (tmp_path / "manifest.csv").is_file()
    assert (tmp_path / "index.html").is_file()
    assert "qwen3_tts_probe" not in (tmp_path / "index.html").read_text(encoding="utf-8")
