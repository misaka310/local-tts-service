from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from local_tts_service.config import load_config
from local_tts_service.server import create_app
from local_tts_service.qwen3_tts_probe import (
    QWEN3_TTS_PROBE_DIR,
    build_qwen3_tts_probe_payload,
    build_qwen3_tts_probe_record,
    build_qwen3_tts_probe_targets,
    write_qwen3_tts_probe_index,
    write_qwen3_tts_probe_manifest,
)
from fastapi.testclient import TestClient


def _get_json(url: str) -> dict[str, object]:
    try:
        with urlopen(Request(url, method="GET"), timeout=15) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(detail or f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=3600) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(detail or "{}")
        except json.JSONDecodeError as json_exc:
            raise RuntimeError(detail or f"HTTP {exc.code}") from json_exc
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def main() -> int:
    config = load_config(ROOT_DIR)
    base_url = config.public_base_url.rstrip("/")
    output_dir = ROOT_DIR / QWEN3_TTS_PROBE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    local_client = TestClient(create_app(ROOT_DIR))
    local_models_payload = local_client.get("/v1/models").json()
    local_model_map = {
        str(item.get("id") or item.get("model") or ""): item
        for item in list(local_models_payload.get("models") or [])
        if isinstance(item, dict)
    }

    try:
        models_response = _get_json(f"{base_url}/v1/models")
    except Exception as exc:  # noqa: BLE001
        records = [
            build_qwen3_tts_probe_record(
                target,
                status="error",
                available=False,
                unavailable_reason="backend unavailable",
                audio_path="",
                audio_url="",
                error_message=str(exc),
            )
            for target in build_qwen3_tts_probe_targets()
        ]
        write_qwen3_tts_probe_manifest(records, output_dir)
        write_qwen3_tts_probe_index(records, output_dir)
        return 1

    model_map = {
        str(item.get("id") or item.get("model") or ""): item
        for item in list(models_response.get("models") or [])
        if isinstance(item, dict)
    }

    records: list[dict[str, object]] = []
    for target in build_qwen3_tts_probe_targets():
        model_info = model_map.get(target.model, {})
        if not model_info:
            model_info = local_model_map.get(target.model, {})
        available = bool(model_info.get("available", False))
        unavailable_reason = str(model_info.get("unavailableReason") or "").strip() or None
        if unavailable_reason is None:
            unavailable_reason = str(local_model_map.get(target.model, {}).get("unavailableReason") or "").strip() or None

        if target.model.startswith("qwen3_tts") and not available:
            records.append(
                build_qwen3_tts_probe_record(
                    target,
                    status="unavailable",
                    available=False,
                    unavailable_reason=unavailable_reason,
                    audio_path="",
                    audio_url="",
                    error_message=None,
                )
            )
            continue

        payload = build_qwen3_tts_probe_payload(target)
        try:
            request_t0 = time.perf_counter()
            speak = _post_json(f"{base_url}/v1/speak", payload)
            request_elapsed = round(time.perf_counter() - request_t0, 3)
            if speak.get("ok") is not True:
                raise RuntimeError(str(speak.get("errorMessage") or speak.get("error") or "speak failed"))
            source_path = Path(str(speak.get("audioPath") or "")).resolve()
            audio_path = output_dir / target.filename
            if source_path.is_file():
                if audio_path.exists():
                    audio_path.unlink()
                shutil.move(str(source_path), str(audio_path))
            else:
                raise RuntimeError(f"generated file not found: {source_path}")
            timings = speak.get("timings") if isinstance(speak.get("timings"), dict) else {}
            if not timings:
                timings = {
                    "importSec": None,
                    "loadModelSec": None,
                    "loadReferenceSec": None,
                    "generateSec": None,
                    "saveSec": None,
                    "totalSec": request_elapsed,
                }
            elif timings.get("totalSec") is None:
                timings["totalSec"] = request_elapsed
            records.append(
                build_qwen3_tts_probe_record(
                    target,
                    status="generated",
                    available=bool(speak.get("available", True)),
                    unavailable_reason=str(speak.get("unavailableReason") or "").strip() or unavailable_reason,
                    audio_path=str(audio_path),
                    audio_url=target.filename,
                    error_message=None,
                    timings=timings,
                )
            )
        except Exception as exc:  # noqa: BLE001
            records.append(
                build_qwen3_tts_probe_record(
                    target,
                    status="error",
                    available=available,
                    unavailable_reason=unavailable_reason,
                    audio_path="",
                    audio_url="",
                    error_message=str(exc),
                    timings={
                        "importSec": None,
                        "loadModelSec": None,
                        "loadReferenceSec": None,
                        "generateSec": None,
                        "saveSec": None,
                        "totalSec": None,
                    },
                )
            )

    write_qwen3_tts_probe_manifest(records, output_dir)
    write_qwen3_tts_probe_index(records, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
