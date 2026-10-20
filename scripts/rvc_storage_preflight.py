from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

DEFAULT_MINIMUM_FREE_GIB = 0.0


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(f"設定ファイルを読み込めません: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"設定ファイルの形式が不正です: {path}")
    return value


def real_path(path: Path) -> Path:
    return Path(os.path.realpath(path))


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def infer_managed_storage_root(config: dict[str, Any], model_path: Path, override: str = "") -> Path:
    candidates: list[Path] = []
    for raw in (
        override,
        str(config.get("storageRoot") or ""),
        os.environ.get("RVC_STORAGE_ROOT", ""),
    ):
        if raw.strip():
            candidates.append(Path(raw).expanduser())

    resolved_model = real_path(model_path)
    candidates.extend(resolved_model.parents)

    for candidate in candidates:
        resolved = real_path(candidate)
        if (resolved / "storage-map.json").is_file() and (resolved / "_management").is_dir():
            return resolved

    raise RuntimeError(
        "管理対象のRVC保管場所を特定できません。保管ドライブが接続され、"
        "RVC_STORAGE_ROOTまたは設定のstorageRootが正しいことを確認してください。"
    )


def select_storage_root(config: dict[str, Any], model_path: Path, override: str = "") -> Path:
    raw_root = override or str(config.get("storageRoot") or "") or os.environ.get("RVC_STORAGE_ROOT", "")
    if raw_root.strip():
        return real_path(Path(raw_root).expanduser())
    return real_path(model_path).parent


def validate_storage(
    config_path: Path,
    *,
    storage_root_override: str = "",
    minimum_free_gib_override: float | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = read_json(config_path)

    model_path = Path(str(config.get("rvcModelPath") or "")).expanduser()
    index_path = Path(str(config.get("rvcIndexPath") or "")).expanduser()
    model_id = str(config.get("rvcModelId") or "").strip()
    if not model_path.is_file():
        raise RuntimeError(f"RVCモデルが見つかりません: {model_path}")
    if not index_path.is_file():
        raise RuntimeError(f"RVCインデックスが見つかりません: {index_path}")
    if model_path.stat().st_size <= 0 or index_path.stat().st_size <= 0:
        raise RuntimeError("RVCモデルまたはインデックスが空です。")

    resolved_model = real_path(model_path)
    resolved_index = real_path(index_path)
    managed_storage = bool(config.get("requireManagedStorage", False))
    storage_map_path: Path | None = None
    manifest_path: Path | None = None
    checked: list[dict[str, Any]] = []

    if managed_storage:
        storage_root = infer_managed_storage_root(config, model_path, storage_root_override)
        if not is_relative_to(resolved_model, storage_root) or not is_relative_to(resolved_index, storage_root):
            raise RuntimeError(
                "RVCモデルの実体が正規保管場所の外にあります。"
                f" storage={storage_root}, model={resolved_model}, index={resolved_index}"
            )

        storage_map_path = storage_root / "storage-map.json"
        storage_map = read_json(storage_map_path)
        entries = storage_map.get("entries")
        if not isinstance(entries, list) or not entries:
            raise RuntimeError(f"RVC保管台帳が空または不正です: {storage_map_path}")
        invalid_entries = [
            str(item.get("name") or "unknown") if isinstance(item, dict) else "invalid_entry"
            for item in entries
            if not isinstance(item, dict) or str(item.get("state") or "") not in {"migrated", "linked"}
        ]
        if invalid_entries:
            raise RuntimeError("RVC保管台帳に未接続項目があります: " + ", ".join(invalid_entries))

        manifest_path = storage_root / "_management" / "critical-artifacts.sha256.json"
        manifest = read_json(manifest_path)
        files = manifest.get("files")
        if not isinstance(files, list):
            raise RuntimeError(f"RVC重要ファイル台帳が不正です: {manifest_path}")
        manifest_by_path = {
            str(item.get("path") or "").replace("\\", "/"): item
            for item in files
            if isinstance(item, dict)
        }
        for artifact in (resolved_model, resolved_index):
            relative = artifact.relative_to(storage_root).as_posix()
            item = manifest_by_path.get(relative)
            if item is None:
                raise RuntimeError(f"RVC重要ファイル台帳に登録されていません: {relative}")
            expected_size = int(item.get("bytes") or 0)
            actual_size = artifact.stat().st_size
            if expected_size != actual_size:
                raise RuntimeError(
                    f"RVC重要ファイルのサイズが台帳と一致しません: {relative}: "
                    f"expected={expected_size}, actual={actual_size}"
                )
            checked.append({"path": relative, "bytes": actual_size})
    else:
        storage_root = select_storage_root(config, model_path, storage_root_override)
        checked = [
            {"path": str(resolved_model), "bytes": resolved_model.stat().st_size},
            {"path": str(resolved_index), "bytes": resolved_index.stat().st_size},
        ]

    configured_minimum = config.get("minimumFreeSpaceGiB")
    minimum_free_gib = (
        float(minimum_free_gib_override)
        if minimum_free_gib_override is not None
        else float(configured_minimum if configured_minimum is not None else DEFAULT_MINIMUM_FREE_GIB)
    )
    if minimum_free_gib < 0:
        raise RuntimeError("minimumFreeSpaceGiBには0以上を指定してください。")
    free_bytes = shutil.disk_usage(storage_root).free
    minimum_bytes = int(minimum_free_gib * 1024**3)
    if free_bytes < minimum_bytes:
        raise RuntimeError(
            "RVC保管ドライブの空き容量が不足しています: "
            f"free={free_bytes / 1024**3:.2f} GiB, required={minimum_free_gib:.2f} GiB"
        )

    return {
        "ok": True,
        "status": "ready",
        "message": "RVC保管場所とモデルを確認しました。",
        "managedStorage": managed_storage,
        "storageRoot": str(storage_root),
        "freeGiB": round(free_bytes / 1024**3, 2),
        "minimumFreeGiB": minimum_free_gib,
        "modelId": model_id,
        "artifacts": checked,
        "storageMap": str(storage_map_path) if storage_map_path is not None else "",
        "criticalManifest": str(manifest_path) if manifest_path is not None else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate RVC model storage before runtime startup.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--storage-root", default="")
    parser.add_argument("--minimum-free-gib", type=float)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = validate_storage(
            args.config,
            storage_root_override=args.storage_root,
            minimum_free_gib_override=args.minimum_free_gib,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print(result["message"])
            print(f"storage: {result['storageRoot']}")
            print(f"free: {result['freeGiB']} GiB")
        return 0
    except Exception as exc:
        result = {
            "ok": False,
            "status": "storage_unavailable",
            "message": f"RVC保管場所を使用できません: {exc}",
            "errorType": type(exc).__name__,
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print(result["message"], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
