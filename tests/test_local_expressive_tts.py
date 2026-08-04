from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import wave

from local_tts_service.config import load_config
from local_tts_service.models import SpeakRequest
from local_tts_service.synthesis.capability_validator import validate_instruction_requirements
from scripts.local_expressive_tts_infer import _chatterbox_exaggeration, load_request

ROOT = Path(__file__).resolve().parent.parent


def _write_pcm16_wav(path: Path, *, duration_sec: float = 1.0, sample_rate: int = 16000) -> None:
    frame_count = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frame_count)


def test_expressive_models_are_registered_with_native_windows_commands() -> None:
    config = load_config(ROOT)
    chatterbox = config.models["chatterbox_multilingual_v3"]
    cosyvoice = config.models["fun_cosyvoice3_0_5b"]

    assert chatterbox.runtime == "external_cli"
    assert chatterbox.model_id == "ResembleAI/chatterbox"
    assert chatterbox.external_command_key == "chatterbox"
    assert chatterbox.requires_reference_audio is True
    assert chatterbox.requires_reference_text is False
    assert chatterbox.supports_style_strength is True
    assert chatterbox.default_language == "ja"

    assert cosyvoice.runtime == "external_cli"
    assert cosyvoice.model_id == "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"
    assert cosyvoice.external_command_key == "cosyvoice"
    assert cosyvoice.requires_reference_audio is True
    assert cosyvoice.requires_reference_text is False
    assert cosyvoice.supports_instruction is True
    assert cosyvoice.supports_style_strength is False
    assert cosyvoice.supports_speed_control is True
    assert cosyvoice.default_language == "ja"

    runtime = config.runtimes["external_cli"]
    for command_key in ("chatterbox", "cosyvoice"):
        command = runtime["commands"][command_key]
        availability = runtime["availabilityCommands"][command_key]
        assert command[:3] == ["powershell", "-NoProfile", "-ExecutionPolicy"]
        assert "./scripts/run-local-expressive-tts.ps1" in command
        assert availability[:3] == ["powershell", "-NoProfile", "-ExecutionPolicy"]
        assert "./scripts/check-local-expressive-tts.ps1" in availability


def test_chatterbox_request_does_not_require_reference_transcript(tmp_path: Path) -> None:
    audio = tmp_path / "voice.wav"
    _write_pcm16_wav(audio)
    request_path = tmp_path / "request.json"
    output = tmp_path / "out.wav"
    request_path.write_text(
        json.dumps(
            {
                "model": "chatterbox_multilingual_v3",
                "modelId": "ResembleAI/chatterbox",
                "text": "うれしくて、思わず笑っちゃった！",
                "language": "Japanese",
                "styleStrength": 3.0,
                "referenceAudioPath": str(audio),
                "referenceTextPath": "",
                "outputPath": str(output),
                "seed": 42,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    request = load_request(request_path)

    assert request.model == "chatterbox_multilingual_v3"
    assert request.reference_text_path is None
    assert request.reference_text == ""
    assert request.language == "Japanese"
    assert request.style_strength == 3.0
    assert request.seed == 42


def test_chatterbox_style_strength_maps_public_range_to_native_exaggeration() -> None:
    assert _chatterbox_exaggeration(None) == 0.7
    assert _chatterbox_exaggeration(1.0) == 0.0
    assert _chatterbox_exaggeration(3.0) == 0.8
    assert _chatterbox_exaggeration(6.0) == 2.0
    assert _chatterbox_exaggeration(99.0) == 2.0


def test_cosyvoice_request_accepts_normal_japanese_and_instruction(tmp_path: Path) -> None:
    audio = tmp_path / "voice.wav"
    _write_pcm16_wav(audio)
    request_path = tmp_path / "request.json"
    output = tmp_path / "out.wav"
    request_path.write_text(
        json.dumps(
            {
                "model": "fun_cosyvoice3_0_5b",
                "modelId": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
                "text": "やった、ついに成功したよ！",
                "language": "ja",
                "styleStrength": 5.5,
                "speedScale": 1.05,
                "instruction": "とても嬉しそうに、少し弾んだ声で話してください。",
                "referenceAudioPath": str(audio),
                "referenceTextPath": "",
                "outputPath": str(output),
                "seed": 7,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    request = load_request(request_path)

    assert request.model == "fun_cosyvoice3_0_5b"
    assert request.reference_text_path is None
    assert request.reference_text == ""
    assert request.language == "ja"
    assert request.style_strength == 5.5
    assert request.speed_scale == 1.05
    assert "嬉しそう" in request.instruction
    assert request.seed == 7


def test_setup_pins_blackwell_compatible_torch_and_upstream_revisions() -> None:
    source = (ROOT / "scripts" / "setup_local_expressive_tts.py").read_text(encoding="utf-8")

    assert 'TORCH_VERSION = "2.10.0"' in source
    assert 'TORCH_INDEX = "https://download.pytorch.org/whl/cu128"' in source
    assert "5de7a54aa4e5e2baadb0182dde554908b48b85c2" in source
    assert "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18" in source
    assert "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc" in source
    assert "29e01c4e8d000f4bcd70751be16fa94bf3d85a18" in source
    assert "automatic_katakana_normalization" in source
    assert 'model_id="pengzhendong/wetext"' in source
    assert '"torchcodec' not in source


def test_cosyvoice_windows_path_uses_local_wetext_and_soundfile_io() -> None:
    source = (ROOT / "scripts" / "local_expressive_tts_infer.py").read_text(encoding="utf-8")

    assert 'ROOT / "runtime" / "models" / "wetext"' in source
    assert 'modelscope.snapshot_download = local_modelscope_snapshot' in source
    assert 'torchaudio.load = soundfile_load' in source
    assert 'sf.write(request.output_path' in source
    assert 'torchaudio.save(' not in source


def test_standalone_style_strength_is_allowed_for_direct_exaggeration_models() -> None:
    payload = SpeakRequest(
        text="感情強度だけで生成します。",
        model="chatterbox_multilingual_v3",
        styleStrength=1.6,
    )
    model_cfg = SimpleNamespace(supports_caption=False, supports_instruction=False)

    validate_instruction_requirements(payload, "chatterbox_multilingual_v3", model_cfg)


def test_companion_restarts_stale_launcher_instead_of_waiting_forever() -> None:
    source = (ROOT / "scripts" / "start-local-tts-companion.ps1").read_text(encoding="utf-8")
    detached = (ROOT / "scripts" / "start-local-tts-companion-detached.ps1").read_text(encoding="utf-8")
    launcher = (ROOT / "src" / "LocalTtsNoWindowLauncher.cs").read_text(encoding="utf-8")

    assert "$launcherAgeSeconds" in source
    assert "$maximumStartupAgeSeconds" in source
    assert "Stop-Process -Id ([int]$existingLauncher.ProcessId)" in source
    assert "$existingLauncher = $null" in source
    assert "[switch]$NoOpenBrowser" in detached
    assert "$arguments += '-NoOpenBrowser'" in detached
    assert "C:\\00_dev" not in source
    assert "C:\\00_dev" not in detached
    assert "StandardOutputEncoding = new UTF8Encoding(false)" in launcher
    assert "StandardErrorEncoding = new UTF8Encoding(false)" in launcher
