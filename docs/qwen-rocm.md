# Windows Radeon: Qwen3-TTS ROCm worker

This optional backend runs **Qwen3-TTS Voice Clone 1.7B** on an AMD Radeon AI PRO R9700 using a separate Python environment. The standard NVIDIA and CPU execution paths remain unchanged.

## Requirements and setup

- Windows with a supported Radeon GPU, driver, and AMD ROCm-enabled PyTorch environment
- Python 3.11 in the dedicated, locally managed `runtime/venv-qwen-rocm` environment
- Valid Qwen3-TTS 1.7B model files in the locally ignored model cache
- A registered voice with a matching WAV and transcript

The tested dependency combination was `torch[device-gfx1201]==2.12.0+rocm10.1.0`, `torchaudio==2.11.0+rocm10.1.0`, and `qwen-tts==0.1.1`. Confirm GPU/driver compatibility against AMD's current documentation before installing.

The worker is implemented in `scripts/qwen-rocm-worker.py` and is started by `scripts/start-qwen-rocm-worker.ps1`. Its default endpoint is `http://127.0.0.1:8731`; it binds to the local loopback interface, not a public network address. The usual `local-tts.bat` launcher starts or reuses the managed worker when it is configured and needed.

To enable frontend routing, set the following **only in the Git-ignored** `config/config.local.json`:

```json
{
  "deployment": {
    "qwenWorkerBaseUrl": "http://127.0.0.1:8731"
  }
}
```

Merge this field into an existing configuration rather than overwriting unrelated settings. Alternatively, set `LOCAL_TTS_QWEN_WORKER_BASE_URL` for the frontend process. Leave the setting unset on systems that do not use the separate Radeon worker.

## API and behavior

- The worker supports `qwen3_tts_clone_1_7b`, with `POST /api/speak` for generation, `GET /api/health` for health, and local WAV retrieval.
- The frontend selectively routes this model and its generated WAV files to the configured ROCm worker. Other models continue to use their configured execution path.
- The UI retains model discovery and voice selection when the standard worker is temporarily unavailable, using the optional ROCm worker where applicable.
- The ROCm worker requires a verified usable Radeon GPU. If the GPU cannot be used, it reports an error instead of silently switching generation to CPU.
- Model weights, reference audio, generated WAV files, benchmark output, and machine-specific configuration stay outside version control.

## Verification

Run `npm test` in `frontend/` to test proxy selection, health fallback, discovery timeouts, and standard routing behavior. Run the repository Python test suite and setup validation when changing the runtime.

For device acceptance, check `torch.version.hip`, `torch.cuda.is_available()`, and the recognized GPU model in the dedicated ROCm environment. Perform an actual voice-clone generation from the normal UI, verify HTTP success, a nonempty RIFF/WAV result, and playback availability. A successful HTTP response alone does not certify perceived audio quality or long-running reliability.

This document describes the portable setup contract. Machine-specific troubleshooting logs, local task scheduler configuration, performance snapshots, and test recordings are not part of the public repository.
