from __future__ import annotations

import json
import shutil
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def get_iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_audio_duration_sec(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        with wave.open(str(path), "rb") as fp:
            frames = fp.getnframes()
            rate = fp.getframerate()
    except (wave.Error, OSError):
        return None
    if rate <= 0:
        return None
    return round(frames / rate, 3)


def build_file_info(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "filename": path.name,
        "sizeBytes": path.stat().st_size if path.is_file() else None,
        "durationSec": get_audio_duration_sec(path),
        "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat() if path.is_file() else None,
    }


def ensure_original_backup(voice_dir: Path) -> Path:
    active = voice_dir / "voice.wav"
    original = voice_dir / "voice_original.wav"
    if not active.is_file():
        raise FileNotFoundError(f"reference voice not found: {active}")
    if not original.exists():
        shutil.copy2(active, original)
    return original


def detect_cleanup_method() -> dict[str, object]:
    try:
        proc = subprocess.run(
            ["demucs", "--help"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
    except FileNotFoundError:
        return {
            "methodId": "none",
            "label": "unavailable",
            "available": False,
            "reason": "BGM・伴奏除去コマンドが見つかりません",
        }
    if proc.returncode == 0:
        return {
            "methodId": "demucs_vocals",
            "label": "BGM・伴奏除去",
            "available": True,
            "reason": None,
        }
    return {
        "methodId": "none",
        "label": "unavailable",
        "available": False,
        "reason": (proc.stderr or proc.stdout or "").strip() or "BGM・伴奏除去の確認に失敗しました",
    }


def run_demucs_cleanup(*, input_path: Path, output_path: Path, work_dir: Path) -> dict[str, object]:
    work_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "demucs",
        "--two-stems",
        "vocals",
        "-n",
        "htdemucs",
        "-o",
        str(work_dir),
        str(input_path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=3600,
        check=False,
        creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "").strip() or "BGM・伴奏除去に失敗しました")

    stem_path = work_dir / "htdemucs" / input_path.stem / "vocals.wav"
    if not stem_path.is_file():
        raise RuntimeError(f"BGM・伴奏除去後の音声が見つかりません: {stem_path}")
    shutil.copy2(stem_path, output_path)
    return {
        "command": cmd,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "stemPath": str(stem_path),
    }


def default_reference_paths(root_dir: Path) -> dict[str, Path]:
    voice_dir = (root_dir / "reference" / "voices" / "sample_voice_base").resolve()
    cleanup_dir = (root_dir / "runtime" / "audio" / "sample_voice_reference_cleanup").resolve()
    return {
        "voiceDir": voice_dir,
        "active": voice_dir / "voice.wav",
        "original": voice_dir / "voice_original.wav",
        "clean": voice_dir / "voice_clean.wav",
        "manifest": cleanup_dir / "manifest.json",
        "workDir": cleanup_dir / "work",
    }


def read_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"runs": [], "adoptions": []}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        return {"runs": [], "adoptions": []}
    payload.setdefault("runs", [])
    payload.setdefault("adoptions", [])
    return payload


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_run_manifest(manifest_path: Path, run_record: dict[str, object]) -> dict[str, object]:
    payload = read_manifest(manifest_path)
    runs = payload.setdefault("runs", [])
    if isinstance(runs, list):
        runs.append(run_record)
    payload["latest"] = run_record
    write_manifest(manifest_path, payload)
    return payload


def append_adoption_manifest(manifest_path: Path, adoption_record: dict[str, object]) -> dict[str, object]:
    payload = read_manifest(manifest_path)
    adoptions = payload.setdefault("adoptions", [])
    if isinstance(adoptions, list):
        adoptions.append(adoption_record)
    payload["latestAdoption"] = adoption_record
    write_manifest(manifest_path, payload)
    return payload


def apply_clean_to_voice(*, active_path: Path, clean_path: Path, original_path: Path, manifest_path: Path) -> dict[str, object]:
    if not clean_path.is_file():
        raise FileNotFoundError(f"clean reference not found: {clean_path}")
    if not original_path.is_file():
        raise FileNotFoundError(f"original backup not found: {original_path}")
    backup_before_apply = active_path.with_name(f"voice_applied_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
    if active_path.is_file():
        shutil.copy2(active_path, backup_before_apply)
    shutil.copy2(clean_path, active_path)
    record = {
        "appliedAt": get_iso_timestamp(),
        "activePath": str(active_path),
        "cleanPath": str(clean_path),
        "originalPath": str(original_path),
        "backupBeforeApplyPath": str(backup_before_apply),
        "activeInfo": build_file_info(active_path),
        "cleanInfo": build_file_info(clean_path),
        "originalInfo": build_file_info(original_path),
    }
    append_adoption_manifest(manifest_path, record)
    return record
