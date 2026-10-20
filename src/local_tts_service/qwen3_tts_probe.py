from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path

from .audio_file_utils import get_iso_timestamp, get_wav_duration_sec

QWEN3_TTS_PROBE_DIR = "runtime/audio/qwen3_tts_probe"
QWEN3_TTS_PROBE_TEXT = "これは音声合成の比較テストです。"
QWEN3_TTS_PROBE_VOICE_ID = "sample_neutral"
QWEN3_TTS_PROBE_LANGUAGE = "Japanese"
QWEN3_TTS_PROBE_SEED = 1001


@dataclass(frozen=True)
class Qwen3TTSProbeTarget:
    id: str
    model: str
    runtime: str
    model_id: str | None
    voice_id: str | None
    text: str
    instruction: str | None
    language: str
    seed: int
    filename: str


def build_qwen3_tts_probe_targets() -> list[Qwen3TTSProbeTarget]:
    return [
        Qwen3TTSProbeTarget(
            id="irodori_v3_probe",
            model="irodori_v3",
            runtime="comfyui",
            model_id=None,
            voice_id=QWEN3_TTS_PROBE_VOICE_ID,
            text=QWEN3_TTS_PROBE_TEXT,
            instruction=None,
            language=QWEN3_TTS_PROBE_LANGUAGE,
            seed=QWEN3_TTS_PROBE_SEED,
            filename="irodori_v3__sample_neutral__seed1001.wav",
        ),
        Qwen3TTSProbeTarget(
            id="qwen3_tts_clone_0_6b_probe",
            model="qwen3_tts_clone_0_6b",
            runtime="qwen3_tts",
            model_id="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            voice_id=QWEN3_TTS_PROBE_VOICE_ID,
            text=QWEN3_TTS_PROBE_TEXT,
            instruction=None,
            language=QWEN3_TTS_PROBE_LANGUAGE,
            seed=QWEN3_TTS_PROBE_SEED,
            filename="qwen3_tts_clone_0_6b__sample_neutral__seed1001.wav",
        ),
        Qwen3TTSProbeTarget(
            id="qwen3_tts_clone_1_7b_probe",
            model="qwen3_tts_clone_1_7b",
            runtime="qwen3_tts",
            model_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            voice_id=QWEN3_TTS_PROBE_VOICE_ID,
            text=QWEN3_TTS_PROBE_TEXT,
            instruction=None,
            language=QWEN3_TTS_PROBE_LANGUAGE,
            seed=QWEN3_TTS_PROBE_SEED,
            filename="qwen3_tts_clone_1_7b__sample_neutral__seed1001.wav",
        ),
    ]


def build_qwen3_tts_probe_payload(target: Qwen3TTSProbeTarget) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": target.model,
        "text": target.text,
        "requestId": target.id,
        "format": "wav",
        "language": target.language,
        "seed": target.seed,
    }
    if target.voice_id:
        payload["voiceId"] = target.voice_id
    if target.instruction:
        payload["instruction"] = target.instruction
    return payload


def build_qwen3_tts_probe_record(
    target: Qwen3TTSProbeTarget,
    *,
    status: str,
    available: bool,
    unavailable_reason: str | None,
    audio_path: str,
    audio_url: str,
    created_at: str | None = None,
    error_message: str | None = None,
    timings: dict[str, object] | None = None,
) -> dict[str, object]:
    file_path = Path(audio_path) if audio_path else None
    file_size_bytes = file_path.stat().st_size if file_path and file_path.is_file() else None
    duration_sec = get_wav_duration_sec(file_path) if file_path and file_path.is_file() else None
    normalized_status = status
    if status == "generated" and (file_path is None or not file_path.is_file() or not file_size_bytes or file_size_bytes <= 0):
        normalized_status = "failed"
        error_message = error_message or "generated wav is missing or 0 byte"
    return {
        "id": target.id,
        "filename": target.filename,
        "model": target.model,
        "runtime": target.runtime,
        "modelId": target.model_id,
        "voiceId": target.voice_id,
        "text": target.text,
        "instruction": target.instruction,
        "language": target.language,
        "seed": target.seed,
        "status": normalized_status,
        "available": available,
        "unavailableReason": unavailable_reason,
        "audioPath": audio_path,
        "audioUrl": audio_url,
        "durationSec": duration_sec,
        "fileSizeBytes": file_size_bytes,
        "createdAt": created_at or get_iso_timestamp(),
        "errorMessage": error_message,
        "timings": timings
        or {
            "importSec": None,
            "loadModelSec": None,
            "loadReferenceSec": None,
            "generateSec": None,
            "saveSec": None,
            "totalSec": None,
        },
    }


def write_qwen3_tts_probe_manifest(records: list[dict[str, object]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = [
        "id",
        "filename",
        "model",
        "runtime",
        "modelId",
        "voiceId",
        "text",
        "instruction",
        "language",
        "seed",
        "status",
        "available",
        "unavailableReason",
        "audioPath",
        "audioUrl",
        "durationSec",
        "fileSizeBytes",
        "createdAt",
        "errorMessage",
        "timings",
    ]
    with (output_dir / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def write_qwen3_tts_probe_index(records: list[dict[str, object]], output_dir: Path) -> None:
    cards = []
    for record in records:
        filename = str(record.get("filename") or "")
        audio_url = str(record.get("audioUrl") or "").strip()
        timings = record.get("timings") if isinstance(record.get("timings"), dict) else {}
        player = (
            f"<audio controls preload='none' src='{html.escape(audio_url or filename)}'></audio>"
            if str(record.get("status") or "") == "generated"
            else "<p class='empty'>audio unavailable</p>"
        )
        cards.append(
            "<article class='card'>"
            f"<h2>{html.escape(str(record.get('model') or ''))}</h2>"
            f"<p><strong>modelId:</strong> {html.escape(str(record.get('modelId') or '-'))}</p>"
            f"<p><strong>runtime:</strong> {html.escape(str(record.get('runtime') or ''))}</p>"
            f"<p><strong>voiceId:</strong> {html.escape(str(record.get('voiceId') or '-'))}</p>"
            f"<p><strong>instruction:</strong> {html.escape(str(record.get('instruction') or '-'))}</p>"
            f"<p><strong>seed:</strong> {html.escape(str(record.get('seed') or '-'))}</p>"
            f"<p><strong>status:</strong> {html.escape(str(record.get('status') or ''))}</p>"
            f"<p><strong>unavailableReason:</strong> {html.escape(str(record.get('unavailableReason') or '-'))}</p>"
            f"<p><strong>errorMessage:</strong> {html.escape(str(record.get('errorMessage') or '-'))}</p>"
            f"<p><strong>filename:</strong> {html.escape(filename)}</p>"
            f"<p><strong>timings:</strong> import={html.escape(str(timings.get('importSec'))) if timings else '-'} / "
            f"loadModel={html.escape(str(timings.get('loadModelSec'))) if timings else '-'} / "
            f"loadReference={html.escape(str(timings.get('loadReferenceSec'))) if timings else '-'} / "
            f"generate={html.escape(str(timings.get('generateSec'))) if timings else '-'} / "
            f"save={html.escape(str(timings.get('saveSec'))) if timings else '-'} / "
            f"total={html.escape(str(timings.get('totalSec'))) if timings else '-'}</p>"
            f"{player}"
            "</article>"
        )

    html_text = (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Qwen3-TTS Probe</title>"
        "<style>"
        "body{font-family:'Yu Gothic UI','Hiragino Sans','Meiryo',sans-serif;margin:24px;background:#f8f4ec;color:#1e1e1e;}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;}"
        ".card{background:#fff;border:1px solid #dccfbf;border-radius:16px;padding:16px;box-shadow:0 12px 28px rgba(0,0,0,.08);}"
        "audio{width:100%;margin-top:12px;} .empty{color:#8a5a44;} p{line-height:1.6;}"
        "</style></head><body>"
        "<h1>Qwen3-TTS probe</h1>"
        "<div class='grid'>"
        f"{''.join(cards)}"
        "</div></body></html>"
    )
    (output_dir / "index.html").write_text(html_text, encoding="utf-8")
