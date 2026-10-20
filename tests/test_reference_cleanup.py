from __future__ import annotations

import json

from local_tts_service.reference_cleanup import (
    append_adoption_manifest,
    append_run_manifest,
    apply_clean_to_voice,
    build_file_info,
    default_reference_paths,
)


def test_default_reference_paths_target_sample_voice_base(tmp_path) -> None:
    paths = default_reference_paths(tmp_path)

    assert paths["voiceDir"].name == "sample_voice_base"
    assert paths["active"].name == "voice.wav"
    assert paths["clean"].name == "voice_clean.wav"


def test_append_run_manifest_creates_latest(tmp_path) -> None:
    manifest_path = tmp_path / "manifest.json"
    payload = append_run_manifest(manifest_path, {"status": "generated", "runAt": "2026-06-25T00:00:00+00:00"})

    assert payload["latest"]["status"] == "generated"
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(stored["runs"]) == 1


def test_apply_clean_to_voice_keeps_backup_and_logs(tmp_path) -> None:
    voice_dir = tmp_path / "reference" / "voices" / "sample_voice_base"
    voice_dir.mkdir(parents=True, exist_ok=True)
    active_path = voice_dir / "voice.wav"
    clean_path = voice_dir / "voice_clean.wav"
    original_path = voice_dir / "voice_original.wav"
    active_path.write_bytes(b"old-audio")
    clean_path.write_bytes(b"clean-audio")
    original_path.write_bytes(b"original-audio")
    manifest_path = tmp_path / "runtime" / "audio" / "sample_voice_reference_cleanup" / "manifest.json"

    record = apply_clean_to_voice(
        active_path=active_path,
        clean_path=clean_path,
        original_path=original_path,
        manifest_path=manifest_path,
    )

    assert active_path.read_bytes() == b"clean-audio"
    backup_path = tmp_path / record["backupBeforeApplyPath"]
    assert backup_path.exists()
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(stored["adoptions"]) == 1
    assert stored["latestAdoption"]["cleanPath"] == str(clean_path)
