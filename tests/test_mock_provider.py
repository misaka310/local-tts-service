from __future__ import annotations

import wave

from local_tts_service.runtimes.base import SynthesizeRequest
from local_tts_service.runtimes.mock_wav import MockWavRuntime


def test_mock_runtime_generates_wav(tmp_path) -> None:
    runtime = MockWavRuntime(output_dir=tmp_path, duration_sec=0.1, sample_rate=16000)
    result = runtime.synthesize(
        SynthesizeRequest(
            text="hello",
            request_id="req-1",
            model_name="mock",
            output_basename="tts-req-1",
        )
    )

    assert result.audio_path.exists()
    assert result.model == "mock"
    assert result.runtime == "mock_wav"
    with wave.open(str(result.audio_path), "rb") as fp:
        assert fp.getframerate() == 16000
        assert fp.getnchannels() == 1
