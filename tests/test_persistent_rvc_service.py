from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "persistent_rvc_service.py"
SPEC = importlib.util.spec_from_file_location("persistent_rvc_service", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PersistentRvcServiceContractTests(unittest.TestCase):
    def config(self) -> dict:
        return {
            "defaultModel": "irodori_v3",
            "defaultVoiceId": "sample_voice",
        }

    def test_upstream_payload_is_generic_and_strips_playback_fields(self) -> None:
        result = MODULE.upstream_speak_payload(
            self.config(),
            {
                "requestId": "request-1",
                "text": "テストです。",
                "referenceVoice": "sample_voice",
                "ttsProfile": "speed",
                "voiceVolume": 0.2,
                "playLocal": False,
            },
        )
        self.assertEqual(result["model"], "irodori_v3")
        self.assertEqual(result["voiceId"], "sample_voice")
        self.assertNotIn("referenceVoice", result)
        self.assertNotIn("ttsProfile", result)
        self.assertNotIn("voiceVolume", result)
        self.assertNotIn("playLocal", result)

    def test_health_accepts_local_tts_service_contract(self) -> None:
        health = {
            "ok": True,
            "service": "local-tts-service",
            "status": "healthy",
            "availableModels": ["irodori_v3"],
        }
        self.assertTrue(MODULE.upstream_health_ready(self.config(), health))
        self.assertFalse(MODULE.upstream_health_ready({"defaultModel": "missing"}, health))

    def test_request_id_is_sanitized(self) -> None:
        self.assertEqual(MODULE.safe_request_id("a b/日本語"), "a-b")
        self.assertTrue(MODULE.safe_request_id("").startswith("rvc-"))

    def test_config_rejects_non_loopback_bind_and_upstream(self) -> None:
        config = {
            "host": "0.0.0.0",
            "port": 8718,
            "upstreamBaseUrl": "http://127.0.0.1:8730",
            "upstreamHealthPath": "/health",
            "upstreamSpeakPath": "/v1/speak",
            "defaultModel": "irodori_v3",
            "defaultVoiceId": "voice",
            "rvcPythonPath": "python.exe",
            "rvcCwd": "rvc",
            "rvcModelPath": "voice.pth",
            "rvcIndexPath": "voice.index",
            "rvcModelId": "voice-model",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "loopback"):
                MODULE.load_config(path)
            config["host"] = "127.0.0.1"
            config["upstreamBaseUrl"] = "http://example.com:8730"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "loopback"):
                MODULE.load_config(path)

    def test_request_log_summary_does_not_retain_text(self) -> None:
        result = MODULE.request_log_summary("request-1", "秘密の読み上げ本文", "2026-08-09T00:00:00Z")
        self.assertEqual(result["requestId"], "request-1")
        self.assertEqual(result["textLength"], len("秘密の読み上げ本文"))
        self.assertEqual(result["startedAt"], "2026-08-09T00:00:00Z")
        self.assertNotIn("text", result)

    def test_upstream_audio_url_cannot_escape_configured_loopback_origin(self) -> None:
        self.assertEqual(
            MODULE.resolve_upstream_audio_url("http://127.0.0.1:8730", "/audio/test.wav"),
            "http://127.0.0.1:8730/audio/test.wav",
        )
        with self.assertRaisesRegex(ValueError, "upstream origin"):
            MODULE.resolve_upstream_audio_url("http://127.0.0.1:8730", "http://127.0.0.1:9999/audio/test.wav")
        with self.assertRaisesRegex(ValueError, "upstream"):
            MODULE.resolve_upstream_audio_url("http://127.0.0.1:8730", "https://example.com/audio/test.wav")

    def test_public_start_script_is_self_contained_and_no_window(self) -> None:
        source = (ROOT / "scripts" / "start-persistent-rvc-service.ps1").read_text(encoding="utf-8-sig")
        self.assertNotRegex(source, r"[A-Za-z]:\\")
        helper = (ROOT / "scripts" / "start_detached_process.py").read_text(encoding="utf-8-sig")
        self.assertIn("CREATE_NO_WINDOW", helper)
        self.assertIn("stdin=subprocess.DEVNULL", helper)

    def test_powershell_entrypoints_reject_non_loopback_endpoints(self) -> None:
        start_source = (ROOT / "scripts" / "start-persistent-rvc-service.ps1").read_text(encoding="utf-8-sig")
        stop_source = (ROOT / "scripts" / "stop-persistent-rvc-service.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Assert-LoopbackHost", start_source)
        self.assertIn("Assert-LoopbackUri", start_source)
        self.assertIn("Assert-LoopbackHost", stop_source)


if __name__ == "__main__":
    unittest.main()
