"""Loopback-only Qwen3-TTS ROCm worker. No CPU fallback or GUI changes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
import time
import uuid
from urllib.parse import quote, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "runtime/models/huggingface/Qwen__Qwen3-TTS-12Hz-1.7B-Base"
OUTPUT = ROOT / "runtime/audio/qwen-r9700"
REFERENCES = ROOT / "runtime/qwen-rocm/references"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
AUDIO_RE = re.compile(r"^/audio/qwen-r9700/([0-9a-f]{32})\.wav$")
MAX_AUDIO = 12 * 1024 * 1024
LOCK = Lock()
QWEN = None

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

def reference_base():
    local = ROOT / "config/config.local.json"
    if not local.is_file():
        return ""
    data = json.loads(local.read_text(encoding="utf-8-sig"))
    url = str(data.get("deployment", {}).get("workerBaseUrl") or "").rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
        return ""
    return url

def reference(voice_id):
    if not ID_RE.fullmatch(voice_id):
        raise ValueError("invalid voiceId")
    folder = REFERENCES / voice_id
    wav, txt = folder / "voice.wav", folder / "voice.txt"
    if wav.is_file() and txt.is_file() and txt.read_text(encoding="utf-8-sig").strip():
        return wav, txt.read_text(encoding="utf-8-sig").strip()
    base = reference_base()
    if not base:
        raise ValueError("reference voice is missing and remote worker is not configured")
    with urlopen(base + "/api/reference-voices", timeout=15) as response:
        voice_data = response.read(512 * 1024)
    voices = json.loads(voice_data.decode("utf-8")).get("voices", [])
    info = next((v for v in voices if v.get("voiceId") == voice_id), None)
    if not info or not info.get("hasReferenceAudio") or not info.get("hasReferenceText"):
        raise ValueError("reference voice requires voice.wav and matching text")
    ref_text = str(info.get("referenceText") or "").strip()
    if not ref_text:
        raise ValueError("remote reference transcript unavailable")
    with urlopen(base + "/api/reference-voices/" + quote(voice_id) + "/audio", timeout=20) as response:
        audio = response.read(MAX_AUDIO + 1)
    if not audio or len(audio) > MAX_AUDIO or audio[:4] != b"RIFF":
        raise ValueError("invalid or oversized reference WAV")
    folder.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(audio)
    txt.write_text(ref_text + "\n", encoding="utf-8")
    return wav, ref_text

def load_model():
    global QWEN
    import torch
    if not torch.cuda.is_available() or not torch.version.hip or "R9700" not in torch.cuda.get_device_name(0):
        raise RuntimeError("R9700 ROCm GPU unavailable (CPU fallback forbidden)")
    if QWEN is None:
        from qwen_tts import Qwen3TTSModel
        if not (MODEL / "model.safetensors").is_file():
            raise RuntimeError("Qwen3-TTS 1.7B model missing")
        QWEN = Qwen3TTSModel.from_pretrained(
            str(MODEL),device_map="cuda:0",dtype=torch.bfloat16,
            attn_implementation="sdpa",local_files_only=True)
    return QWEN

def generate(payload):
    import numpy as np
    import soundfile as sf
    import torch
    model_name = str(payload.get("model") or "")
    if model_name != "qwen3_tts_clone_1_7b":
        raise ValueError("this worker supports only qwen3_tts_clone_1_7b")
    text = str(payload.get("text") or "").strip()
    if not text or len(text) > 4000:
        raise ValueError("text is required (maximum 4000 characters)")
    voice_id = str(payload.get("voiceId") or "").strip()
    with LOCK:
        wav_path, ref_text = reference(voice_id)
        start = time.perf_counter()
        model = load_model()
        load_time = time.perf_counter() - start
        start = time.perf_counter()
        prompt = model.create_voice_clone_prompt(
            ref_audio=str(wav_path),ref_text=ref_text,x_vector_only_mode=False)
        kwargs = dict(text=text,language=str(payload.get("language") or "Japanese"),
                      voice_clone_prompt=prompt,non_streaming_mode=True)
        if payload.get("seed") is not None:
            kwargs["seed"] = int(payload["seed"])
        wavs, rate = model.generate_voice_clone(**kwargs)
        torch.cuda.synchronize()
        generated = time.perf_counter() - start
        array = np.asarray(wavs[0])
        if not np.isfinite(array).all() or float(np.sqrt(np.mean(array * array))) <= 1e-5:
            raise RuntimeError("generated audio was silent or invalid")
        OUTPUT.mkdir(parents=True, exist_ok=True)
        file_id = uuid.uuid4().hex
        filename = OUTPUT / (file_id + ".wav")
        sf.write(str(filename), array, int(rate))
        return {"ok": True, "result": {
            "ok": True, "model": model_name, "runtime": "qwen3_tts",
            "voiceId": voice_id, "audioUrl": "/audio/qwen-r9700/" + file_id + ".wav",
            "timings": {"loadModelSec": round(load_time,3), "generateSec": round(generated,3)},
            "audioSha256": hashlib.sha256(filename.read_bytes()).hexdigest()
        }}

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.path == "/api/models":
            try:
                import torch
                ready = bool(torch.cuda.is_available() and torch.version.hip and
                             "R9700" in torch.cuda.get_device_name(0) and
                             (MODEL / "model.safetensors").is_file())
            except Exception:
                ready = False
            self.send_json(200, {"ok": True, "models": [{
                "id": "qwen3_tts_clone_1_7b", "model": "qwen3_tts_clone_1_7b",
                "label": "Qwen3-TTS Voice Clone 1.7B", "family": "qwen3_tts",
                "runtime": "qwen3_tts", "available": ready, "enabled": True,
                "supportsVoiceClone": True, "supportsReferenceVoice": True,
                "requiresReferenceAudio": True, "requiresReferenceText": True,
                "supportsSeed": True, "supportsLanguage": True,
                "defaultLanguage": "Japanese",
                "unavailableReason": None if ready else "R9700 ROCm or model files unavailable"
            }]})
            return
        if self.path == "/api/reference-voices":
            voices = []
            if REFERENCES.is_dir():
                for folder in sorted(REFERENCES.iterdir()):
                    if not folder.is_dir() or not ID_RE.fullmatch(folder.name):
                        continue
                    wav, txt = folder / "voice.wav", folder / "voice.txt"
                    if not wav.is_file() or not txt.is_file():
                        continue
                    ref_text = txt.read_text(encoding="utf-8-sig").strip()
                    if not ref_text:
                        continue
                    voices.append({"voiceId": folder.name, "label": folder.name,
                                   "enabled": True, "hasReferenceAudio": True,
                                   "hasReferenceText": True, "referenceText": ref_text})
            self.send_json(200, {"ok": True, "backendAvailable": True, "voices": voices})
            return
        if self.path == "/api/health":
            try:
                import torch
                ready = bool(torch.cuda.is_available() and torch.version.hip
                             and "R9700" in torch.cuda.get_device_name(0))
                self.send_json(200 if ready else 503,{"ok":ready,"gpu":"R9700" if ready else None})
            except Exception as e:
                self.send_json(503,{"ok":False,"error":type(e).__name__})
            return
        match = AUDIO_RE.fullmatch(self.path)
        if not match:
            self.send_json(404,{"ok":False,"error":"not found"})
            return
        path = OUTPUT / (match.group(1) + ".wav")
        if not path.is_file():
            self.send_json(404,{"ok":False,"error":"audio not found"})
            return
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        header = self.headers.get("Range", "")
        if header:
            parsed = re.fullmatch(r"bytes=(\d+)-(\d*)",header)
            if not parsed:
                self.send_json(416,{"ok":False,"error":"invalid range"})
                return
            start = int(parsed.group(1))
            end = min(size-1,int(parsed.group(2))) if parsed.group(2) else size-1
            if start > end or start >= size:
                self.send_json(416,{"ok":False,"error":"invalid range"})
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type","audio/wav")
        self.send_header("Accept-Ranges","bytes")
        self.send_header("Content-Length",str(end-start+1))
        if status == 206:
            self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as file:
            file.seek(start)
            self.wfile.write(file.read(end-start+1))
    def do_POST(self):
        if self.path != "/api/speak":
            self.send_json(404,{"ok":False,"error":"not found"})
            return
        try:
            size = int(self.headers.get("Content-Length","0"))
            if size <= 0 or size > 32768:
                raise ValueError("request too large or empty")
            payload = json.loads(self.rfile.read(size))
            self.send_json(200,generate(payload))
        except (ValueError, TypeError) as e:
            self.send_json(400,{"ok":False,"error":str(e),"errorMessage":str(e)})
        except Exception as e:
            self.log_error("Qwen generation failed: %s",type(e).__name__)
            self.send_json(502,{"ok":False,"error":str(e),"errorMessage":str(e)})
    def log_message(self, format, *args):
        # Keep request metadata out of logs.
        pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8731)
    options = parser.parse_args()
    import torch
    if not torch.cuda.is_available() or not torch.version.hip or "R9700" not in torch.cuda.get_device_name(0):
        raise SystemExit("R9700 ROCm GPU required; CPU fallback is forbidden")
    print("Qwen3-TTS R9700 worker listening on 127.0.0.1:" + str(options.port),flush=True)
    ThreadingHTTPServer(("127.0.0.1",options.port),Handler).serve_forever()
