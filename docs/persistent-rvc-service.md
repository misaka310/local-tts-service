# Persistent RVC Service

## Responsibility

This repository owns generic RVC inference. The persistent service loads one configured `.pth`/`.index` pair, HuBERT, and RMVPE once, completes warmup, accepts text-to-voice requests, and serves converted WAV files. It has no knowledge of ChatGPT, browser tabs, Companion, Echo Show, or microphone control.

Consumers own their own integration concerns. For example, a ChatGPT bridge may select this service as its voice API, but it must not move the RVC engine into the ChatGPT repository.

## Local configuration

Copy `config/rvc-persistent.example.json` to the ignored `config/rvc-persistent.local.json` and set:

- upstream Local TTS Service URL and model
- default voice ID
- RVC Python and working directory
- model and index paths
- RVC parameters

Model weights, the local config, converted audio, logs, and runtime state are not committed.

## Entrypoints

```powershell
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts\start-persistent-rvc-service.ps1
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts\stop-persistent-rvc-service.ps1
```

The start entrypoint first runs `scripts/rvc_storage_preflight.py`, then starts the normal Local TTS Service when needed, and reports ready only after the configured model is loaded and warmup is complete.

The storage preflight always verifies that the configured `.pth` and `.index` exist, are non-empty, and that the configured storage location satisfies `minimumFreeSpaceGiB` when a threshold is set.

For a managed installation, set `requireManagedStorage=true`, `storageRoot`, and an explicit free-space threshold in the ignored local config. Strict mode resolves NTFS junctions and additionally verifies:

- `storage-map.json` reports every managed location as `migrated` or `linked`
- the configured `.pth` and `.index` are inside the managed root
- both files are registered in `_management/critical-artifacts.sha256.json`
- both files still match the recorded sizes

If the storage drive is disconnected or inconsistent, startup fails before an RVC runtime is launched and returns a user-readable storage error instead of downloading or rebuilding files automatically. Generic installations remain usable without the private managed-storage layout.

## HTTP contract

- `GET /health`: generic service, upstream, prerequisite, model, and warmup readiness
- `GET /state`: local runtime state
- `POST /v1/speak`: generate upstream TTS, apply RVC, and return `audioUrl`, `rvcApplied=true`, and `rvcModel`
- `POST /v1/playback/stop`: compatibility no-op because this service does not own audio playback
- `POST /shutdown`: scoped service shutdown
- `GET /audio/<name>`: converted WAV delivery

The `/v1/speak` request uses generic fields such as `requestId`, `text`, `model`, `voiceId`, and `language`. Integration-specific playback or browser fields are stripped before calling the upstream TTS API.
