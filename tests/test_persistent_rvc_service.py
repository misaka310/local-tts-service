from __future__ import annotations

import importlib.util
import sys
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
            "defaultVoiceId": "suguha",
        }

    def test_upstream_payload_is_generic_and_strips_playback_fields(self) -> None:
        result = MODULE.upstream_speak_payload(
            self.config(),
            {
                "requestId": "request-1",
                "text": "テストです。",
                "referenceVoice": "suguha",
                "ttsProfile": "speed",
                "voiceVolume": 0.2,
                "playLocal": False,
            },
        )
        self.assertEqual(result["model"], "irodori_v3")
        self.assertEqual(result["voiceId"], "suguha")
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


if __name__ == "__main__":
    unittest.main()
