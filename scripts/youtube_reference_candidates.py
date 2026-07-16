from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
MAX_VIDEO_DURATION_SECONDS = 20 * 60
TIMING_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})\s+-->\s+"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})"
)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
NOISE_ONLY_RE = re.compile(
    r"^\s*[\[（(【].*(music|音楽|拍手|効果音|歓声|笑い|無音|bgm).*[\]）)】]\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    start_sec: float
    end_sec: float
    duration_sec: float
    text: str
    score: float
    original_filename: str


def validate_youtube_url(value: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise ValueError("動画URLが正しくありません") from exc
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in YOUTUBE_HOSTS:
        raise ValueError("このURLには対応していません")
    if parsed.hostname == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    else:
        video_id = ""
        if parsed.path == "/watch":
            from urllib.parse import parse_qs

            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
            parts = parsed.path.strip("/").split("/")
            video_id = parts[1] if len(parts) > 1 else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id or ""):
        raise ValueError("単一の動画URLを指定してください")
    return raw


def parse_timestamp(value: str) -> float:
    text = value.replace(",", ".")
    parts = text.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return float(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    raise ValueError(f"invalid timestamp: {value}")


def clean_caption_text(value: str) -> str:
    text = html.unescape(TAG_RE.sub("", str(value or "")))
    text = text.replace("&lrm;", "").replace("&rlm;", "")
    text = re.sub(r"<c[^>]*>|</c>", "", text)
    text = SPACE_RE.sub(" ", text).strip()
    return text


def _incremental_caption_text(text_lines: list[str], previous: Cue | None, start: float, end: float) -> str:
    cleaned_lines: list[str] = []
    for raw_line in text_lines:
        cleaned = clean_caption_text(raw_line)
        if cleaned and (not cleaned_lines or cleaned_lines[-1] != cleaned):
            cleaned_lines.append(cleaned)
    if not cleaned_lines:
        return ""

    near_previous = previous is not None and start <= previous.end + 0.12
    if previous and near_previous:
        if len(cleaned_lines) == 1 and cleaned_lines[0] == previous.text:
            return "" if end - start <= 0.05 else cleaned_lines[0]
        while len(cleaned_lines) > 1 and cleaned_lines[0] == previous.text:
            cleaned_lines.pop(0)

        combined = clean_caption_text(" ".join(cleaned_lines))
        if combined.startswith(previous.text):
            combined = combined[len(previous.text) :].strip(" 　、,")
        if combined == previous.text or (end - start <= 0.05 and previous.text in combined):
            return ""
        return combined

    return clean_caption_text(" ".join(cleaned_lines))


def parse_vtt(path: Path) -> list[Cue]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    cues: list[Cue] = []
    index = 0
    while index < len(lines):
        match = TIMING_RE.search(lines[index])
        if not match:
            index += 1
            continue
        start = parse_timestamp(match.group("start"))
        end = parse_timestamp(match.group("end"))
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index])
            index += 1
        text = _incremental_caption_text(text_lines, cues[-1] if cues else None, start, end)
        if text and end > start:
            cues.append(Cue(start=start, end=end, text=text))
        index += 1
    return cues


def _candidate_score(start: float, end: float, text: str) -> float:
    duration = end - start
    duration_penalty = abs(duration - 6.0) * 1.6
    text_length = len(text)
    text_penalty = 0.0
    if text_length < 8:
        text_penalty += (8 - text_length) * 0.8
    if text_length > 100:
        text_penalty += (text_length - 100) * 0.08
    punctuation_bonus = min(2.0, sum(text.count(mark) for mark in "。！？!?、," ) * 0.25)
    noise_penalty = 20.0 if NOISE_ONLY_RE.match(text) else 0.0
    repeated_penalty = 6.0 if re.search(r"(.)\1{5,}", text) else 0.0
    return round(100.0 - duration_penalty - text_penalty - noise_penalty - repeated_penalty + punctuation_bonus, 3)


def build_candidate_windows(
    cues: Iterable[Cue],
    *,
    min_duration: float = 3.0,
    max_duration: float = 10.0,
    max_candidates: int = 5,
    excluded_ranges: Iterable[tuple[float, float]] = (),
) -> list[tuple[float, float, str, float]]:
    source = [cue for cue in cues if cue.text and cue.end > cue.start and not NOISE_ONLY_RE.match(cue.text)]
    excluded = [(float(start), float(end)) for start, end in excluded_ranges if float(end) > float(start)]
    windows: list[tuple[float, float, str, float]] = []
    seen: set[str] = set()
    for start_index, first in enumerate(source):
        parts: list[str] = []
        start = first.start
        last_end = start
        for cue in source[start_index : start_index + 8]:
            if parts and cue.start - last_end > 1.4:
                break
            if cue.end - start > max_duration + 0.001:
                break
            if not parts or parts[-1] != cue.text:
                parts.append(cue.text)
            last_end = max(last_end, cue.end)
            duration = last_end - start
            if duration < min_duration:
                continue
            text = clean_caption_text(" ".join(parts))
            normalized = re.sub(r"[\s。、,.!?！？]+", "", text).lower()
            if len(normalized) < 4 or normalized in seen or NOISE_ONLY_RE.match(text):
                continue
            seen.add(normalized)
            windows.append((start, last_end, text, _candidate_score(start, last_end, text)))
    windows.sort(key=lambda item: (-item[3], abs((item[1] - item[0]) - 6.0), item[0]))
    selected: list[tuple[float, float, str, float]] = []
    for candidate in windows:
        start, end, _, _ = candidate
        if any(max(start, excluded_start) < min(end, excluded_end) - 0.5 for excluded_start, excluded_end in excluded):
            continue
        if any(max(start, existing[0]) < min(end, existing[1]) - 0.5 for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_candidates:
            break
    return selected


def _resolve_executable(repo_root: Path, env_name: str, names: list[str], local_candidates: list[Path]) -> str:
    env_value = os.environ.get(env_name, "").strip()
    if env_value and Path(env_value).is_file():
        return str(Path(env_value))
    for candidate in local_candidates:
        if candidate.is_file():
            return str(candidate)
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise RuntimeError(f"必要なコマンドが見つかりません: {env_name}")


def resolve_ytdlp(repo_root: Path) -> str:
    return _resolve_executable(
        repo_root,
        "LOCAL_TTS_YTDLP",
        ["yt-dlp", "yt-dlp.exe"],
        [
            repo_root / ".venv" / "Scripts" / "yt-dlp.exe",
            repo_root / "runtime" / "vendor" / "yt-dlp" / "yt-dlp.exe",
        ],
    )


def resolve_ffmpeg(repo_root: Path) -> str:
    env_value = os.environ.get("LOCAL_TTS_FFMPEG", "").strip()
    if env_value and Path(env_value).is_file():
        return env_value
    vendor_root = repo_root / "runtime" / "vendor" / "ffmpeg"
    if vendor_root.is_dir():
        found = next(vendor_root.rglob("ffmpeg.exe"), None)
        if found:
            return str(found)
    resolved = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if resolved:
        return resolved
    raise RuntimeError("FFmpegが見つかりません。local-tts.bat -ForceSetupでFFmpegを準備してください")


def _friendly_ytdlp_error(message: str) -> str:
    text = str(message or "").strip()
    lowered = text.lower()
    if "does not pass filter" in lowered and "duration" in lowered:
        return "20分を超える動画には対応していません"
    if "http error 429" in lowered or "too many requests" in lowered:
        return "動画配信元のアクセス制限（HTTP 429）で音声を取得できませんでした。しばらく待ってから再実行してください"

    useful_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("WARNING: The extractor specified to use impersonation")
    ]
    detail = useful_lines[-1] if useful_lines else "yt-dlpの処理に失敗しました"
    return f"動画URLから音声を取得できませんでした: {detail[-600:]}"


def download_youtube_assets(repo_root: Path, job_dir: Path, url: str) -> tuple[Path, dict]:
    ytdlp = resolve_ytdlp(repo_root)
    output_template = str(job_dir / "source.%(ext)s")
    media_command = [
        ytdlp,
        "--no-playlist",
        "--no-overwrites",
        "--match-filter",
        f"duration <= {MAX_VIDEO_DURATION_SECONDS}",
        "--write-info-json",
        "--max-filesize",
        "1500M",
        "-f",
        "bestaudio/best",
        "-o",
        output_template,
        url,
    ]
    media_completed = subprocess.run(
        media_command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        timeout=30 * 60,
    )
    if media_completed.returncode != 0:
        message = media_completed.stderr or media_completed.stdout or "yt-dlp failed"
        raise RuntimeError(_friendly_ytdlp_error(message))

    info_path = job_dir / "source.info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.is_file() else {}
    duration = float(info.get("duration") or 0)
    if duration and duration > MAX_VIDEO_DURATION_SECONDS:
        raise RuntimeError("20分を超える動画には対応していません")

    excluded = {".json", ".vtt", ".part", ".ytdl"}
    audio_files = [path for path in job_dir.glob("source.*") if path.suffix.lower() not in excluded and path.is_file()]
    if not audio_files:
        raise RuntimeError("ダウンロードした音声ファイルが見つかりません")
    audio_files.sort(key=lambda path: path.stat().st_size, reverse=True)

    subtitle_command = [
        ytdlp,
        "--no-playlist",
        "--skip-download",
        "--no-overwrites",
        "--write-subs",
        "--write-auto-subs",
        "--sub-format",
        "vtt",
        "--sub-langs",
        "ja.*,ja,en.*",
        "-o",
        output_template,
        url,
    ]
    try:
        subtitle_completed = subprocess.run(
            subtitle_command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=5 * 60,
        )
        if subtitle_completed.returncode != 0 or not any(job_dir.glob("source*.vtt")):
            info["subtitleWarning"] = "字幕を取得できなかったため、Whisperで文字起こしします。"
    except (OSError, subprocess.SubprocessError):
        info["subtitleWarning"] = "字幕を取得できなかったため、Whisperで文字起こしします。"

    return audio_files[0], info


def transcribe_with_whisper(audio_path: Path, model_name: str, language: str) -> list[Cue]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "字幕がない動画の文字起こしには faster-whisper が必要です。local-tts.bat -ForceSetupを実行してください"
        ) from exc
    def run_transcription(device: str, compute_type: str) -> list[Cue]:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        segments, _ = model.transcribe(
            str(audio_path),
            language=None if language == "auto" else language,
            vad_filter=True,
            beam_size=5,
        )
        return [
            Cue(float(segment.start), float(segment.end), clean_caption_text(segment.text))
            for segment in segments
            if segment.text.strip()
        ]

    try:
        return run_transcription("auto", "default")
    except Exception as auto_error:  # GPU/CUDA libraries vary across Windows environments.
        try:
            return run_transcription("cpu", "int8")
        except Exception as cpu_error:
            raise RuntimeError(
                f"Whisper文字起こしに失敗しました: auto={auto_error}; cpu={cpu_error}"
            ) from cpu_error


def choose_transcript(job_dir: Path, audio_path: Path, model_name: str, language: str) -> tuple[list[Cue], str]:
    subtitle_paths = sorted(job_dir.glob("source*.vtt"), key=lambda path: ("ja" not in path.name.lower(), path.name))
    for subtitle_path in subtitle_paths:
        cues = parse_vtt(subtitle_path)
        if cues:
            return cues, f"subtitle:{subtitle_path.name}"
    return transcribe_with_whisper(audio_path, model_name, language), f"whisper:{model_name}"


def extract_candidate_wav(ffmpeg: str, source_audio: Path, output_path: Path, start: float, end: float) -> None:
    padded_start = max(0.0, start - 0.12)
    duration = max(0.2, end - padded_start + 0.12)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{padded_start:.3f}",
        "-i",
        str(source_audio),
        "-t",
        f"{duration:.3f}",
        "-ac",
        "1",
        "-ar",
        "44100",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=5 * 60)
    if completed.returncode != 0:
        raise RuntimeError(f"候補区間の音声切り出しに失敗しました: {(completed.stderr or '').strip()[-1200:]}")


def run(request_path: Path, output_path: Path) -> dict:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    repo_root = Path(request["repoRoot"]).resolve()
    job_id = str(request["jobId"])
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,80}", job_id):
        raise ValueError("invalid jobId")
    url = validate_youtube_url(request.get("url", ""))
    max_candidates = max(1, min(8, int(request.get("maxCandidates", 5))))
    language = str(request.get("language", "ja")).strip() or "ja"
    whisper_model = str(request.get("whisperModel", "small")).strip() or "small"
    excluded_ranges: list[tuple[float, float]] = []
    for item in list(request.get("excludeRanges") or [])[:40]:
        if isinstance(item, dict):
            raw_start = item.get("startSec")
            raw_end = item.get("endSec")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            raw_start, raw_end = item
        else:
            continue
        try:
            start = float(raw_start)
            end = float(raw_end)
        except (TypeError, ValueError):
            continue
        if start >= 0 and end > start:
            excluded_ranges.append((start, end))
    job_dir = repo_root / "runtime" / "youtube-reference" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    source_audio, info = download_youtube_assets(repo_root, job_dir, url)
    cues, transcript_source = choose_transcript(job_dir, source_audio, whisper_model, language)
    windows = build_candidate_windows(cues, max_candidates=max_candidates, excluded_ranges=excluded_ranges)
    if not windows:
        message = "これまでと重ならない追加候補を見つけられませんでした" if excluded_ranges else "3〜10秒の適切な発話区間を見つけられませんでした"
        raise RuntimeError(message)

    ffmpeg = resolve_ffmpeg(repo_root)
    candidates: list[Candidate] = []
    for index, (start, end, text, score) in enumerate(windows, start=1):
        candidate_id = f"c{index:03d}"
        filename = f"{candidate_id}-original.wav"
        extract_candidate_wav(ffmpeg, source_audio, job_dir / filename, start, end)
        candidates.append(
            Candidate(
                candidate_id=candidate_id,
                start_sec=round(start, 3),
                end_sec=round(end, 3),
                duration_sec=round(end - start, 3),
                text=text,
                score=score,
                original_filename=filename,
            )
        )

    result = {
        "ok": True,
        "jobId": job_id,
        "title": str(info.get("title") or "YouTube video"),
        "videoId": str(info.get("id") or ""),
        "durationSec": float(info.get("duration") or 0),
        "transcriptSource": transcript_source,
        "subtitleWarning": str(info.get("subtitleWarning") or ""),
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = run(Path(args.request), Path(args.output))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary returns a concise error to Node.
        payload = {"ok": False, "error": str(exc)}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        request_path = Path(args.request)
        for temporary_path in request_path.parent.glob("source.*"):
            try:
                temporary_path.unlink()
            except OSError:
                pass
        try:
            request_path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
