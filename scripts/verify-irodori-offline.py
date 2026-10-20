from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def _json_request(url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urlopen(request, timeout=30) as response:
        body = response.read()
    decoded = json.loads(body.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError(f"expected JSON object from {url}")
    return decoded


def _wait_for_health(base_url: str, process: subprocess.Popen[bytes], timeout_sec: int) -> float:
    started = time.perf_counter()
    deadline = started + timeout_sec
    last_error = ""
    while time.perf_counter() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"service exited during startup with code {process.returncode}")
        try:
            health = _json_request(f"{base_url}/health")
            if bool(health.get("ok")):
                return time.perf_counter() - started
            last_error = str(health)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"service did not become ready: {last_error}")


def _validate_wav(base_url: str, audio_url: str) -> int:
    parsed = urlsplit(audio_url)
    path_and_query = parsed.path or audio_url
    if parsed.query:
        path_and_query = f"{path_and_query}?{parsed.query}"
    absolute_url = f"{base_url}{path_and_query}"
    with urlopen(absolute_url, timeout=30) as response:
        audio = response.read()
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise RuntimeError(f"invalid WAV returned from {absolute_url}")
    return len(audio)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Irodori startup and two generations offline.")
    parser.add_argument("--port", type=int, default=18730)
    parser.add_argument("--startup-timeout", type=int, default=180)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    python_executable = root / ".venv" / "Scripts" / "python.exe"
    if not python_executable.is_file():
        raise RuntimeError(f"backend Python not found: {python_executable}")

    log_dir = root / "runtime" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "verify-irodori-offline.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["HF_DATASETS_OFFLINE"] = "1"
    env["HF_ENDPOINT"] = "http://127.0.0.1:9"
    base_url = f"http://127.0.0.1:{args.port}"

    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            [
                str(python_executable),
                "-m",
                "uvicorn",
                "local_tts_service.server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
            ],
            cwd=str(root),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            startup_sec = _wait_for_health(base_url, process, args.startup_timeout)
            generations: list[dict[str, object]] = []
            for index, text in enumerate(
                (
                    "完全ローカルで一回目の音声を生成します。",
                    "完全ローカルで二回目の音声を生成します。",
                ),
                start=1,
            ):
                started = time.perf_counter()
                response = _json_request(
                    f"{base_url}/v1/speak",
                    {
                        "text": text,
                        "model": "irodori_v3",
                        "requestId": f"offline-http-{index}",
                        "seed": 200 + index,
                        "speedScale": 1.0,
                        "format": "wav",
                    },
                )
                elapsed = time.perf_counter() - started
                if not bool(response.get("ok")):
                    raise RuntimeError(f"generation {index} failed: {response}")
                audio_url = str(response.get("audioUrl") or "")
                if not audio_url:
                    raise RuntimeError(f"generation {index} returned no audioUrl: {response}")
                wav_bytes = _validate_wav(base_url, audio_url)
                generations.append(
                    {
                        "run": index,
                        "seconds": round(elapsed, 3),
                        "audioUrl": audio_url,
                        "wavBytes": wav_bytes,
                    }
                )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "startupSeconds": round(startup_sec, 3),
                        "generations": generations,
                        "logPath": str(log_path),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"offline verification failed: {exc}", file=sys.stderr)
        raise
