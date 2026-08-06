from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rvc_storage_preflight as preflight  # noqa: E402


def build_storage(tmp_path: Path) -> tuple[Path, Path]:
    storage = tmp_path / "RVC"
    model_dir = storage / "deployed-models" / "local-tts-service-rvc" / "voice"
    model_dir.mkdir(parents=True)
    model = model_dir / "voice.pth"
    index = model_dir / "voice.index"
    model.write_bytes(b"model")
    index.write_bytes(b"index")
    (storage / "_management").mkdir()
    (storage / "storage-map.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "name": "local-tts-service-rvc",
                        "state": "migrated",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (storage / "_management" / "critical-artifacts.sha256.json").write_text(
        json.dumps(
            {
                "files": [
                    {"path": model.relative_to(storage).as_posix(), "bytes": model.stat().st_size, "sha256": "unused"},
                    {"path": index.relative_to(storage).as_posix(), "bytes": index.stat().st_size, "sha256": "unused"},
                ]
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "rvc.json"
    config.write_text(
        json.dumps(
            {
                "requireManagedStorage": True,
                "storageRoot": str(storage),
                "minimumFreeSpaceGiB": 40,
                "rvcModelPath": str(model),
                "rvcIndexPath": str(index),
                "rvcModelId": "voice",
            }
        ),
        encoding="utf-8",
    )
    return storage, config


def test_validate_storage_accepts_catalogued_pair(tmp_path: Path) -> None:
    storage, config = build_storage(tmp_path)
    with mock.patch.object(
        preflight.shutil,
        "disk_usage",
        return_value=SimpleNamespace(free=100 * 1024**3),
    ):
        result = preflight.validate_storage(config)

    assert result["ok"] is True
    assert Path(result["storageRoot"]) == storage.resolve()
    assert result["freeGiB"] == 100.0
    assert len(result["artifacts"]) == 2


def test_validate_storage_rejects_low_free_space(tmp_path: Path) -> None:
    _, config = build_storage(tmp_path)
    with mock.patch.object(
        preflight.shutil,
        "disk_usage",
        return_value=SimpleNamespace(free=10 * 1024**3),
    ):
        with pytest.raises(RuntimeError, match="空き容量が不足"):
            preflight.validate_storage(config)


def test_validate_storage_rejects_uncatalogued_model(tmp_path: Path) -> None:
    storage, config = build_storage(tmp_path)
    manifest = storage / "_management" / "critical-artifacts.sha256.json"
    manifest.write_text(json.dumps({"files": []}), encoding="utf-8")
    with mock.patch.object(
        preflight.shutil,
        "disk_usage",
        return_value=SimpleNamespace(free=100 * 1024**3),
    ):
        with pytest.raises(RuntimeError, match="台帳に登録されていません"):
            preflight.validate_storage(config)


def test_validate_storage_allows_unmanaged_generic_model_pair(tmp_path: Path) -> None:
    model = tmp_path / "voice.pth"
    index = tmp_path / "voice.index"
    model.write_bytes(b"model")
    index.write_bytes(b"index")
    config = tmp_path / "generic.json"
    config.write_text(
        json.dumps(
            {
                "rvcModelPath": str(model),
                "rvcIndexPath": str(index),
                "rvcModelId": "generic-voice",
            }
        ),
        encoding="utf-8",
    )
    with mock.patch.object(
        preflight.shutil,
        "disk_usage",
        return_value=SimpleNamespace(free=1 * 1024**3),
    ):
        result = preflight.validate_storage(config)

    assert result["ok"] is True
    assert result["managedStorage"] is False
    assert result["minimumFreeGiB"] == 0.0
    assert result["storageMap"] == ""
    assert result["criticalManifest"] == ""
