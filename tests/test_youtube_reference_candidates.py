from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "youtube_reference_candidates.py"
SPEC = importlib.util.spec_from_file_location("youtube_reference_candidates", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
    ],
)
def test_validate_youtube_url_accepts_single_video_urls(url: str) -> None:
    assert MODULE.validate_youtube_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "file:///tmp/audio.wav",
        "https://www.youtube.com/playlist?list=PL123",
        "https://www.youtube.com/watch?v=",
    ],
)
def test_validate_youtube_url_rejects_non_video_urls(url: str) -> None:
    with pytest.raises(ValueError):
        MODULE.validate_youtube_url(url)


def test_validate_youtube_url_uses_generic_unsupported_message() -> None:
    with pytest.raises(ValueError, match="このURLには対応していません"):
        MODULE.validate_youtube_url("https://example.com/video")


def test_parse_vtt_and_build_candidates(tmp_path: Path) -> None:
    vtt = tmp_path / "sample.ja.vtt"
    vtt.write_text(
        """WEBVTT

00:00:01.000 --> 00:00:03.100
こんにちは。今日は音声の確認をします。

00:00:03.150 --> 00:00:06.200
自然な話し方で、ゆっくり読んでいます。

00:00:08.000 --> 00:00:10.000
[音楽]

00:00:11.000 --> 00:00:14.100
次の候補も、聞き取りやすい文章です。

00:00:14.150 --> 00:00:17.000
背景の音が少ない部分を選びます。
""",
        encoding="utf-8",
    )

    cues = MODULE.parse_vtt(vtt)
    assert len(cues) == 5
    candidates = MODULE.build_candidate_windows(cues, max_candidates=3)
    assert candidates
    assert all(3.0 <= end - start <= 10.0 for start, end, _, _ in candidates)
    assert all("音楽" not in text for _, _, text, _ in candidates)
    assert any("こんにちは" in text for _, _, text, _ in candidates)


def test_clean_caption_text_removes_markup_and_spacing() -> None:
    assert MODULE.clean_caption_text("<c> こんにちは </c>   世界 &amp; テスト") == "こんにちは 世界 & テスト"


def test_parse_vtt_removes_youtube_rolling_caption_duplicates(tmp_path: Path) -> None:
    vtt = tmp_path / "rolling.ja.vtt"
    vtt.write_text(
        """WEBVTT

00:00:00.320 --> 00:00:04.789 align:start position:0%
で<00:00:00.480><c>も</c><00:00:00.719><c>本当</c><00:00:01.120><c>に</c>

00:00:04.789 --> 00:00:04.799 align:start position:0%
でも本当に

00:00:04.799 --> 00:00:07.710 align:start position:0%
でも本当に
みんな<00:00:05.200><c>に</c><00:00:06.279><c>会え</c><00:00:07.040><c>た</c>

00:00:07.710 --> 00:00:07.720 align:start position:0%
みんなに会えた

00:00:07.720 --> 00:00:10.430 align:start position:0%
みんなに会えた
今日は楽しいです
""",
        encoding="utf-8",
    )

    cues = MODULE.parse_vtt(vtt)

    assert [(cue.start, cue.end, cue.text) for cue in cues] == [
        (0.32, 4.789, "でも本当に"),
        (4.799, 7.71, "みんなに会えた"),
        (7.72, 10.43, "今日は楽しいです"),
    ]


def test_parse_vtt_keeps_an_intentional_repeated_sentence(tmp_path: Path) -> None:
    vtt = tmp_path / "repeated.ja.vtt"
    vtt.write_text(
        """WEBVTT

00:00:01.000 --> 00:00:03.000
もう一度

00:00:03.100 --> 00:00:05.500
もう一度
""",
        encoding="utf-8",
    )

    cues = MODULE.parse_vtt(vtt)

    assert [cue.text for cue in cues] == ["もう一度", "もう一度"]


def test_download_rejects_videos_over_twenty_minutes_before_media_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE, "resolve_ytdlp", lambda _repo_root: "yt-dlp")

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        filter_index = command.index("--match-filter")
        assert command[filter_index + 1] == "duration <= 1200"
        return SimpleNamespace(
            returncode=1,
            stderr="ERROR: video does not pass filter (duration <= 1200)",
            stdout="",
        )

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="20分を超える動画には対応していません"):
        MODULE.download_youtube_assets(
            tmp_path,
            tmp_path / "job",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )


def test_subtitle_429_keeps_downloaded_audio_and_falls_back_to_whisper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE, "resolve_ytdlp", lambda _repo_root: "yt-dlp")
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        if "--skip-download" not in command:
            (job_dir / "source.webm").write_bytes(b"audio")
            (job_dir / "source.info.json").write_text(
                json.dumps({"id": "dQw4w9WgXcQ", "title": "sample", "duration": 60}),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        return SimpleNamespace(
            returncode=1,
            stderr=(
                "WARNING: The extractor specified to use impersonation for this download, "
                "but no impersonate target is available.\n"
                "ERROR: Unable to download video subtitles for 'en': HTTP Error 429: Too Many Requests"
            ),
            stdout="",
        )

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    audio_path, info = MODULE.download_youtube_assets(
        tmp_path,
        job_dir,
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )

    assert audio_path == job_dir / "source.webm"
    assert len(calls) == 2
    assert "--write-subs" not in calls[0]
    assert "--skip-download" in calls[1]
    assert info["subtitleWarning"] == "字幕を取得できなかったため、Whisperで文字起こしします。"

    monkeypatch.setattr(
        MODULE,
        "transcribe_with_whisper",
        lambda _audio_path, model_name, _language: [MODULE.Cue(1.0, 5.0, f"Whisper {model_name}")],
    )
    cues, source = MODULE.choose_transcript(job_dir, audio_path, "small", "ja")
    assert [cue.text for cue in cues] == ["Whisper small"]
    assert source == "whisper:small"


def test_build_candidate_windows_does_not_backfill_overlapping_duplicates() -> None:
    cues = [
        MODULE.Cue(0.0, 2.0, "最初の文章です"),
        MODULE.Cue(2.0, 4.0, "次の文章です"),
        MODULE.Cue(4.0, 6.0, "さらに続く文章です"),
        MODULE.Cue(6.0, 8.0, "別の話題に移ります"),
        MODULE.Cue(8.0, 10.0, "最後の文章です"),
    ]

    candidates = MODULE.build_candidate_windows(cues, max_candidates=5)

    for index, candidate in enumerate(candidates):
        for other in candidates[index + 1 :]:
            overlap = max(0.0, min(candidate[1], other[1]) - max(candidate[0], other[0]))
            assert overlap <= 0.5


def test_build_candidate_windows_skips_ranges_already_shown() -> None:
    cues = [
        MODULE.Cue(0.0, 3.0, "最初の候補です"),
        MODULE.Cue(3.1, 6.2, "二つ目の候補です"),
        MODULE.Cue(6.3, 9.5, "三つ目の候補です"),
        MODULE.Cue(9.6, 12.8, "四つ目の候補です"),
    ]

    candidates = MODULE.build_candidate_windows(
        cues,
        max_candidates=5,
        excluded_ranges=[(0.0, 6.2)],
    )

    assert candidates
    assert all(start >= 6.2 for start, _end, _text, _score in candidates)
