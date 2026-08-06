from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "rvc-persistent.local.json"
RUNTIME_ROOT = REPO_ROOT / "runtime" / "persistent-rvc"
INPUT_ROOT = RUNTIME_ROOT / "inputs"
CONVERTED_ROOT = RUNTIME_ROOT / "converted"
STATE_PATH = RUNTIME_ROOT / "state.json"
EVENTS_PATH = RUNTIME_ROOT / "events.jsonl"
MAX_BODY_BYTES = 1_000_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def append_event(event: str, **fields: Any) -> None:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": utc_now(), "event": event, **fields}, ensure_ascii=False) + "\n")


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    required = (
        "host",
        "port",
        "upstreamBaseUrl",
        "upstreamHealthPath",
        "upstreamSpeakPath",
        "defaultModel",
        "defaultVoiceId",
        "rvcPythonPath",
        "rvcCwd",
        "rvcModelPath",
        "rvcIndexPath",
        "rvcModelId",
    )
    missing = [name for name in required if config.get(name) in (None, "")]
    if missing:
        raise ValueError(f"missing persistent RVC config values: {', '.join(missing)}")
    return config


def join_url(base: str, path_or_url: str) -> str:
    value = str(path_or_url or "").strip()
    if value.startswith(("http://", "https://")):
        return value
    return urllib.parse.urljoin(base.rstrip("/") + "/", value.lstrip("/"))


def request_json(url: str, *, payload: dict[str, Any] | None = None, timeout: float = 15.0) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    value = json.loads(body or "{}")
    if not isinstance(value, dict):
        raise RuntimeError(f"non-object JSON response from {url}")
    return value


def safe_request_id(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return text[:120] or f"rvc-{uuid.uuid4().hex}"


def upstream_speak_payload(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    translated = dict(payload)
    translated["model"] = str(payload.get("model") or config["defaultModel"])
    translated["voiceId"] = str(payload.get("voiceId") or config["defaultVoiceId"])
    for name in ("voiceProfile", "referenceVoice", "ttsProfile", "voiceVolume", "playLocal"):
        translated.pop(name, None)
    return translated


def upstream_health_ready(config: dict[str, Any], health: dict[str, Any]) -> bool:
    if not bool(health.get("ok")):
        return False
    runtime = health.get("voiceRuntime")
    if isinstance(runtime, dict):
        return bool(runtime.get("ready"))
    models = health.get("availableModels")
    return (
        health.get("service") == "local-tts-service"
        and health.get("status") == "healthy"
        and isinstance(models, list)
        and str(config["defaultModel"]) in models
    )


class PersistentRvcService:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path.resolve()
        self.config = load_config(self.config_path)
        self.lock = threading.RLock()
        self.conversion_lock = threading.Lock()
        self.started_at = utc_now()
        self.status = "starting"
        self.last_health: dict[str, Any] = {}
        self.last_request: dict[str, Any] = {}
        self.last_conversion: dict[str, Any] = {}
        self.last_error = ""
        self.rvc_engine: Any = None
        self.wavfile: Any = None
        self.engine_loaded_at = ""
        self.warmup_result: dict[str, Any] = {}
        self._health_cache_at = 0.0
        self._health_cache: dict[str, Any] = {}
        self._initialize_engine()
        self.status = "running"
        self.persist()

    @property
    def timeouts(self) -> dict[str, float]:
        raw = self.config.get("timeouts") or {}
        return {
            "health": float(raw.get("healthSeconds", 5)),
            "speak": float(raw.get("speakSeconds", 180)),
            "download": float(raw.get("audioDownloadSeconds", 30)),
        }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "status": self.status,
                "pid": os.getpid(),
                "startedAt": self.started_at,
                "updatedAt": utc_now(),
                "configPath": str(self.config_path),
                "modelId": str(self.config["rvcModelId"]),
                "upstreamBaseUrl": str(self.config["upstreamBaseUrl"]),
                "defaultModel": str(self.config["defaultModel"]),
                "defaultVoiceId": str(self.config["defaultVoiceId"]),
                "modelPath": str(self.config["rvcModelPath"]),
                "indexPath": str(self.config["rvcIndexPath"]),
                "engineLoadedAt": self.engine_loaded_at,
                "warmup": dict(self.warmup_result),
                "lastHealth": dict(self.last_health),
                "lastRequest": dict(self.last_request),
                "lastConversion": dict(self.last_conversion),
                "lastError": self.last_error,
            }

    def persist(self) -> None:
        atomic_write_json(STATE_PATH, self.snapshot())

    def prerequisites(self) -> dict[str, bool]:
        return {
            "python": Path(str(self.config["rvcPythonPath"])).is_file(),
            "cwd": Path(str(self.config["rvcCwd"])).is_dir(),
            "model": Path(str(self.config["rvcModelPath"])).is_file(),
            "index": Path(str(self.config["rvcIndexPath"])).is_file(),
        }

    def _initialize_engine(self) -> None:
        missing = [name for name, present in self.prerequisites().items() if not present]
        if missing:
            raise RuntimeError(f"RVC prerequisites are missing: {', '.join(missing)}")
        rvc_cwd = Path(str(self.config["rvcCwd"])).resolve()
        model_path = Path(str(self.config["rvcModelPath"])).resolve()
        os.environ["weight_root"] = str(model_path.parent)
        os.environ["index_root"] = str(rvc_cwd / "logs")
        os.environ["rmvpe_root"] = str(rvc_cwd / "assets" / "rmvpe")
        if str(rvc_cwd) not in sys.path:
            sys.path.insert(0, str(rvc_cwd))
        os.chdir(rvc_cwd)
        from configs.config import Config as RvcConfig  # type: ignore
        from infer.modules.vc.modules import VC  # type: ignore
        from scipy.io import wavfile  # type: ignore

        started = time.perf_counter()
        engine = VC(RvcConfig())
        engine.get_vc(model_path.name)
        self.rvc_engine = engine
        self.wavfile = wavfile
        self.engine_loaded_at = utc_now()
        self.warmup_result = {"completed": False, "loadSeconds": time.perf_counter() - started}
        if bool(self.config.get("warmupOnStart", True)):
            self._warmup()

    def _convert(self, source_path: Path) -> tuple[Any, Any]:
        params = dict(self.config.get("rvc") or {})
        return self.rvc_engine.vc_single(
            0,
            str(source_path.resolve()),
            int(params.get("f0upKey", 0)),
            None,
            str(params.get("f0method", "rmvpe")),
            str(Path(str(self.config["rvcIndexPath"])).resolve()),
            None,
            float(params.get("indexRate", 0.35)),
            int(params.get("filterRadius", 3)),
            int(params.get("resampleSr", 0)),
            float(params.get("rmsMixRate", 1.0)),
            float(params.get("protect", 0.33)),
        )

    def _warmup(self) -> None:
        import numpy as np  # type: ignore

        INPUT_ROOT.mkdir(parents=True, exist_ok=True)
        CONVERTED_ROOT.mkdir(parents=True, exist_ok=True)
        input_path = INPUT_ROOT / "warmup.wav"
        output_path = CONVERTED_ROOT / "warmup.wav"
        sample_rate = 40000
        timeline = np.arange(int(sample_rate * 1.5), dtype=np.float32) / sample_rate
        audio = (0.025 * np.sin(2 * np.pi * 220.0 * timeline)).astype(np.float32)
        self.wavfile.write(str(input_path), sample_rate, audio)
        started = time.perf_counter()
        info, wav_opt = self._convert(input_path)
        if wav_opt is None:
            raise RuntimeError(f"RVC warmup failed: {info}")
        self.wavfile.write(str(output_path), wav_opt[0], wav_opt[1])
        self.warmup_result = {
            **self.warmup_result,
            "completed": True,
            "conversionSeconds": time.perf_counter() - started,
            "completedAt": utc_now(),
        }

    def health(self, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        with self.lock:
            if not force and self._health_cache and now - self._health_cache_at < 2.0:
                return dict(self._health_cache)
        prerequisites = self.prerequisites()
        upstream: dict[str, Any] = {}
        error = ""
        try:
            upstream = request_json(
                join_url(str(self.config["upstreamBaseUrl"]), str(self.config["upstreamHealthPath"])),
                timeout=self.timeouts["health"],
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        upstream_ready = upstream_health_ready(self.config, upstream)
        engine_ready = self.rvc_engine is not None and self.wavfile is not None and bool(self.warmup_result.get("completed"))
        ready = all(prerequisites.values()) and upstream_ready and engine_ready and not error
        result = {
            "ok": ready,
            "service": "local-tts-persistent-rvc",
            "mode": "rvc",
            "voiceRuntime": {
                "ready": ready,
                "mode": "rvc",
                "voiceId": str(self.config["defaultVoiceId"]),
                "modelId": str(self.config["rvcModelId"]),
            },
            "prerequisites": prerequisites,
            "upstream": upstream,
            "rvc": {
                "ok": engine_ready,
                "engine": "persistent-vc",
                "baseUrl": f"http://{self.config['host']}:{int(self.config['port'])}",
                "modelId": str(self.config["rvcModelId"]),
                "warmup": dict(self.warmup_result),
            },
            "error": error,
            "runtime": self.snapshot(),
        }
        with self.lock:
            self.last_health = {
                "ok": ready,
                "updatedAt": utc_now(),
                "prerequisites": prerequisites,
                "upstreamReady": upstream_ready,
                "rvcReady": engine_ready,
                "error": error,
            }
            self.last_error = error
            self._health_cache = dict(result)
            self._health_cache_at = now
        self.persist()
        return result

    def _download(self, audio_url: str, request_id: str) -> Path:
        INPUT_ROOT.mkdir(parents=True, exist_ok=True)
        target = INPUT_ROOT / f"{safe_request_id(request_id)}-{uuid.uuid4().hex[:8]}.wav"
        with urllib.request.urlopen(audio_url, timeout=self.timeouts["download"]) as response:
            target.write_bytes(response.read())
        if target.stat().st_size < 256:
            raise RuntimeError(f"upstream WAV is unexpectedly small: {target}")
        return target

    def speak(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = safe_request_id(payload.get("requestId"))
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("text is required")
        started = time.perf_counter()
        with self.lock:
            self.last_request = {"requestId": request_id, "text": text, "startedAt": utc_now()}
            self.last_error = ""
        self.persist()
        append_event("speak_started", requestId=request_id, text=text)
        try:
            upstream = request_json(
                join_url(str(self.config["upstreamBaseUrl"]), str(self.config["upstreamSpeakPath"])),
                payload=upstream_speak_payload(self.config, payload),
                timeout=self.timeouts["speak"],
            )
            if not upstream.get("ok") or not upstream.get("audioUrl"):
                raise RuntimeError(f"upstream TTS generation failed: {upstream!r}")
            source_url = join_url(str(self.config["upstreamBaseUrl"]), str(upstream["audioUrl"]))
            source_path = self._download(source_url, request_id)
            conversion_started = time.perf_counter()
            CONVERTED_ROOT.mkdir(parents=True, exist_ok=True)
            converted_path = CONVERTED_ROOT / f"{request_id}-{uuid.uuid4().hex[:8]}.wav"
            with self.conversion_lock:
                info, wav_opt = self._convert(source_path)
                if wav_opt is None:
                    raise RuntimeError(f"RVC conversion failed: {info}")
                self.wavfile.write(str(converted_path), wav_opt[0], wav_opt[1])
            converted_url = f"http://{self.config['host']}:{int(self.config['port'])}/audio/{urllib.parse.quote(converted_path.name)}"
            completed = {
                "requestId": request_id,
                "modelId": str(self.config["rvcModelId"]),
                "sourceAudioUrl": source_url,
                "convertedAudioUrl": converted_url,
                "convertedPath": str(converted_path),
                "ttsSeconds": conversion_started - started,
                "rvcSeconds": time.perf_counter() - conversion_started,
                "totalSeconds": time.perf_counter() - started,
                "completedAt": utc_now(),
            }
            with self.lock:
                self.last_conversion = completed
                self.last_error = ""
            self.persist()
            append_event("speak_completed", **completed)
            response = dict(upstream)
            response.update(
                {
                    "audioUrl": converted_url,
                    "rvcApplied": True,
                    "rvcModel": str(self.config["rvcModelId"]),
                    "rvcResult": {
                        "sourceAudioUrl": source_url,
                        "convertedAudioUrl": converted_url,
                        "timing": {
                            "ttsSeconds": completed["ttsSeconds"],
                            "rvcSeconds": completed["rvcSeconds"],
                            "totalSeconds": completed["totalSeconds"],
                        },
                    },
                }
            )
            return response
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            with self.lock:
                self.last_error = error
                self.last_request = {**self.last_request, "failedAt": utc_now(), "error": error}
            self.persist()
            append_event("speak_failed", requestId=request_id, error=error, traceback=traceback.format_exc())
            raise


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body is too large")
        value = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            value = self.server.service.health(force=True)
            self._json(HTTPStatus.OK if value.get("ok") else HTTPStatus.SERVICE_UNAVAILABLE, value)
            return
        if path == "/state":
            self._json(HTTPStatus.OK, {"ok": True, "runtime": self.server.service.snapshot()})
            return
        if path.startswith("/audio/"):
            name = Path(urllib.parse.unquote(path[len("/audio/") :])).name
            target = CONVERTED_ROOT / name
            if not name or not target.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "audio_not_found"})
                return
            body = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        try:
            payload = self._body()
            if self.path == "/v1/speak":
                self._json(HTTPStatus.OK, self.server.service.speak(payload))
                return
            if self.path == "/v1/playback/stop":
                self._json(HTTPStatus.OK, {"ok": True, "status": "no_local_playback"})
                return
            if self.path == "/shutdown":
                self._json(HTTPStatus.OK, {"ok": True, "status": "stopping"})
                self.server.service.status = "stopping"
                self.server.service.persist()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})


class Server(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], service: PersistentRvcService) -> None:
        self.service = service
        super().__init__(address, Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generic persistent RVC service for local-tts-service.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    sys.argv = sys.argv[:1]
    service = PersistentRvcService(args.config)
    server = Server((str(service.config["host"]), int(service.config["port"])), service)
    append_event("service_started", pid=os.getpid(), configPath=str(args.config.resolve()))
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        service.status = "stopped"
        service.persist()
        server.server_close()
        append_event("service_stopped", pid=os.getpid())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
