# API

The service exposes frontend proxy endpoints under `/api/*` and keeps `/v1/*` compatibility endpoints for older clients.

## Health

### `GET /api/health`

Returns frontend/backend health information. The payload includes backend health under `health`.

```json
{
  "ok": true,
  "health": {
    "status": "healthy",
    "defaultModel": "irodori_v3"
  }
}
```

### `GET /health`

Backend health endpoint. It returns service state, runtimes used by configured models, models available from the lightweight static check, and output directories. Optional runtime implementations that no configured model uses are not listed.

## Models

### `GET /api/models`

Returns the model list used by the browser UI. Each model includes availability and capability flags.

Important fields:

- `id` / `model`: model identifier sent to `/api/speak`
- `label`: display name
- `runtime`: provider/runtime name
- `available` / `enabled`: whether the model can be selected
- `unavailableReason`: human-readable reason when unavailable
- `supportsReferenceVoice`
- `requiresReferenceAudio`
- `requiresReferenceText`
- `supportsInstruction`
- `supportsLanguage`
- `supportsSeed`
- `supportsSpeedControl`: accepts the independent `speedScale` synthesis parameter
- `supportsStyleStrength`: accepts the independent `styleStrength` synthesis parameter
- `chunking`: default chunk limits for long text

### `GET /v1/models`

モデル一覧と利用可否を返します。既定の`probe=true`は従来互換で、External CLIモデルの`availabilityCommands`を実行して外部環境まで詳細確認します。

通常起動など、登録情報とローカルの静的状態だけを短時間で確認する場合は`GET /v1/models?probe=false`を使います。この場合もモデルID、表示名、runtime、機能フラグ、`available`、`unavailableReason`は返りますが、WSLコマンドなどの外部プローブは実行しません。frontendの`/api/models`も`/health`内の軽量モデル情報を使用します。

## Reference voices

### `GET /api/reference-voices`

Returns configured reference voices.

```json
{
  "ok": true,
  "defaultReferenceVoice": "sample_neutral",
  "voices": [
    {
      "voiceId": "sample_neutral",
      "displayName": "sample_neutral",
      "enabled": true,
      "archived": false,
      "hasReferenceText": true,
      "audioDurationSec": 5.0,
      "minReferenceDurationSec": 3,
      "maxReferenceDurationSec": 10
    }
  ]
}
```

The frontend response also includes local management fields when available:

- `backendAvailable`: whether the TTS backend answered the listing request
- `referenceText`: current `voice.txt` or legacy `text.txt` content
- `archived`: whether the voice is hidden from the normal generation, comparison, and RVC selectors
- `audioUrl`: browser preview URL

### `POST /api/reference-voices`

Saves a microphone recording and the exact text that was read as `reference/voices/{voiceId}/voice.wav` and `voice.txt`. Non-WAV browser recordings are converted to WAV with FFmpeg.

```json
{
  "voiceId": "my_voice_01",
  "referenceText": "録音で実際に読んだ文章です。",
  "mimeType": "audio/webm",
  "dataUrl": "data:audio/webm;base64,..."
}
```

`voiceId` accepts ASCII letters, numbers, `_`, and `-`. Existing names are rejected so this endpoint cannot overwrite an existing reference voice. The saved audio is always normalized through FFmpeg and validated before the target directory is created.

### `POST /api/reference-voices/import`

Imports an audio file selected in the browser and stores it as `reference/voices/{voiceId}/voice.wav` with the exact spoken text in `voice.txt`.

Supported filename extensions:

- `.wav`
- `.mp3`
- `.m4a`
- `.flac`
- `.ogg`
- `.aac`

Request:

```json
{
  "voiceId": "my_file_voice",
  "referenceText": "音声内で実際に話している文章です。",
  "fileName": "sample.m4a",
  "mimeType": "audio/mp4",
  "dataUrl": "data:audio/mp4;base64,..."
}
```

The extension determines the allowed input type. `mimeType` is informational; the server maps supported extensions to a known MIME type and converts the data with FFmpeg. WAV inputs are also decoded and rewritten instead of being copied blindly, so corrupt RIFF data is rejected.

Validation failures return a Japanese message describing what the user should fix:

- `400`: missing or invalid `voiceId`, missing `referenceText`, empty/invalid data, unsupported extension, corrupt audio, conversion failure, or save failure
- `409`: the voice name already exists
- `200`: `voice.wav` and `voice.txt` were stored successfully

A duration outside the 3–10 second GPT-SoVITS recommendation is not rejected. The UI shows a warning because other models may still use the voice.

### `POST /api/reference-voices/{voiceId}/text`

Updates only the existing reference text while keeping `voice.wav` unchanged.

```json
{
  "referenceText": "修正後の録音テキストです。"
}
```

### `POST /api/reference-voices/{voiceId}/archive`

Keeps `voice.wav` and `voice.txt` in place while hiding or restoring the voice in the normal generation, comparison, and RVC selectors.

```json
{
  "archived": true
}
```

Set `archived` to `false` to restore the voice.

### `POST /api/reference-voices/{voiceId}/rename`

Renames the reference-voice directory while preserving `voice.wav`, `voice.txt`, and the archive marker.

```json
{
  "newVoiceId": "renamed_voice"
}
```

The new ID must use only ASCII letters, numbers, `_`, and `-`, and must not already exist.

### `POST /api/reference-voices/youtube/candidates`

Downloads one authorized YouTube video with yt-dlp, prefers available subtitles, falls back to faster-whisper when subtitles are unavailable, and returns ranked 3–10 second speech candidates. When `useDemucs` is enabled, each candidate also attempts background-music and accompaniment removal.

```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "rightsConfirmed": true,
  "useDemucs": true,
  "language": "ja",
  "whisperModel": "small",
  "maxCandidates": 5,
  "excludeRanges": [
    { "startSec": 12.0, "endSec": 19.0 }
  ]
}
```

`rightsConfirmed` must be `true`. Only single-video `youtube.com` and `youtu.be` URLs up to 20 minutes are accepted. `excludeRanges` is optional and is used when requesting another batch from the same URL; candidates overlapping those ranges by more than 0.5 seconds are skipped. The selector also avoids returning overlapping windows within one response instead of filling the requested count with duplicates. When subtitles are available, rolling YouTube auto-caption cues are normalized so repeated bridge lines do not appear multiple times in candidate transcripts. When subtitles are unavailable, faster-whisper is used; CPU fallback can take longer when GPU execution is unavailable. Candidate data is stored under `runtime/youtube-reference/{jobId}/` and is not committed to Git.

### `GET /api/reference-voices/youtube/jobs/{jobId}/audio/{candidateId}/{variant}`

Streams a candidate WAV. `variant` is `original` or `cleaned`. `cleaned` is available only when background-music and accompaniment removal succeeded.

### `POST /api/reference-voices/youtube/register`

Copies one candidate to a new `reference/voices/{voiceId}/voice.wav` and writes the reviewed transcript to `voice.txt`.

```json
{
  "jobId": "yt-20260710120000-ab12cd34",
  "candidateId": "c001",
  "voiceId": "authorized_voice_01",
  "referenceText": "確認・修正した文字起こしです。",
  "useCleaned": true,
  "rightsConfirmed": true
}
```

Existing voice names are rejected. If `useCleaned` is true but the separation engine did not produce a cleaned candidate, registration falls back to the original candidate.

### `GET /api/reference-voices/{voiceId}/audio`

Streams the selected reference voice audio for browser preview.

### `GET /v1/reference-voices`

Compatibility alias for reference voice listing.

## TTS generation

### `POST /api/speak`

Generates speech from text.

Request:

```json
{
  "model": "irodori_v3",
  "voiceId": "sample_neutral",
  "text": "これは音声合成の動作確認です。",
  "instruction": "明るく自然に話す",
  "language": "Japanese",
  "seed": 1001,
  "speedScale": 1.15,
  "styleStrength": 4.5,
  "format": "wav",
  "chunking": {
    "softChunkChars": 220,
    "maxChunkChars": 300,
    "hardLimitChars": 500,
    "pauseBetweenChunksMs": 250
  }
}
```

Response:

```json
{
  "ok": true,
  "result": {
    "model": "irodori_v3",
    "runtime": "comfyui",
    "voiceId": "sample_neutral",
    "audioUrl": "/audio/generated-file.wav",
    "filename": "generated-file.wav"
  }
}
```

Notes:

- `model` defaults to the configured default model when omitted.
- Models with `requiresReferenceAudio` require `voiceId`.
- Models with `requiresReferenceText` require `reference/voices/{voiceId}/voice.txt`.
- VoiceDesign models require `instruction`.
- `speedScale` is an independent speed multiplier. Values above `1.0` are faster and values below `1.0` are slower. It is ignored for models without `supportsSpeedControl`.
- `styleStrength` is an independent style-conditioning strength, not an instruction string. It is ignored for models without `supportsStyleStrength`.
- `chunking` is optional and is used by normal generation, model comparison, and TTS input before RVC conversion.

### `POST /v1/speak`

Compatibility alias for speech generation.

## RVC defaults

### `GET /api/rvc/defaults`

Returns frontend defaults for RVC conversion.

```json
{
  "ok": true,
  "defaults": {
    "indexRate": 0.35,
    "f0method": "rmvpe",
    "f0upKey": 0,
    "filterRadius": 3,
    "resampleSr": 0,
    "rmsMixRate": 1,
    "protect": 0.33,
    "modelPath": "",
    "indexPath": "",
    "inputSource": "mic",
    "externalAudioPath": "",
    "cleanExternalAudio": false,
    "demucsModel": "htdemucs_ft"
  },
  "modelRoot": "C:\\repo\\models\\rvc",
  "readyCount": 1,
  "guideUrl": "/rvc-model-guide.html",
  "models": [
    {
      "id": "my-voice",
      "label": "my_voice",
      "modelPath": "C:\\repo\\models\\rvc\\my_voice\\my_voice.pth",
      "indexPath": "C:\\repo\\models\\rvc\\my_voice\\my_voice.index",
      "ready": true,
      "errorReason": ""
    }
  ]
}
```

The catalog scans `models/rvc`. A ready model requires both one `.pth` and one `.index` in the same model directory. Incomplete entries are returned with `ready: false` and an `errorReason` so the UI can show the setup page instead of a broken conversion form.

## RVC recording

### `POST /api/rvc/recording`

Accepts a browser-recorded audio data URL, stores it as a local wav input, and returns a reusable recording object.

Request:

```json
{
  "dataUrl": "data:audio/webm;base64,...",
  "mimeType": "audio/webm",
  "scriptText": "録音したセリフ"
}
```

Response:

```json
{
  "ok": true,
  "recording": {
    "filename": "mic-recording.wav",
    "path": "runtime/audio/rvc-input/mic-recording.wav",
    "url": "/audio/rvc-input/mic-recording.wav",
    "durationSec": 3.2,
    "scriptText": "録音したセリフ"
  }
}
```

## RVC conversion

### `POST /api/rvc/convert`

Converts an input audio file with RVC. The input can come from TTS generation, an existing local audio path, or a saved mic recording. External file inputs support wav, m4a, mp3, flac, ogg, and aac. Non-wav inputs are converted to an internal wav intermediate before RVC runs.

TTS input request:

```json
{
  "text": "こんにちは",
  "model": "irodori_v3",
  "voiceId": "sample_neutral",
  "seed": 1001,
  "chunking": {
    "softChunkChars": 220,
    "maxChunkChars": 300,
    "hardLimitChars": 500,
    "pauseBetweenChunksMs": 250
  },
  "rvc": {
    "inputSource": "tts",
    "indexRate": 0.35,
    "f0method": "rmvpe",
    "f0upKey": 0,
    "protect": 0.33,
    "modelPath": "",
    "indexPath": ""
  }
}
```

Existing audio file or mic input request:

```json
{
  "rvc": {
    "inputSource": "file",
    "externalAudioPath": "runtime/audio/input.m4a",
    "indexRate": 0.35,
    "f0method": "rmvpe",
    "f0upKey": 0,
    "protect": 0.33,
    "modelPath": "",
    "indexPath": ""
  }
}
```

Response:

```json
{
  "ok": true,
  "result": {
    "id": "rvc-job-id",
    "input": { "source": "tts" },
    "intermediate": {
      "url": "/audio/input.wav",
      "filename": "input.wav"
    },
    "converted": {
      "url": "/audio/converted.wav",
      "filename": "converted.wav"
    },
    "rvc": {
      "indexRate": 0.35,
      "f0method": "rmvpe",
      "f0upKey": 0,
      "protect": 0.33
    }
  }
}
```

### `GET /api/rvc/audio/{kind}/{filename}`

Streams RVC input, intermediate, converted, or denoised WAV files. Responses include `Content-Length`, advertise `Accept-Ranges: bytes`, and return `206 Partial Content` for valid byte-range requests so browser players can determine duration and seek correctly.

### `POST /api/rvc/denoise`

Creates a separate lightly denoised copy of an existing RVC output. The original converted wav is not overwritten. This endpoint is intended for audible hiss, high-frequency fizz, or steady background noise in the RVC result; it is not a replacement for correcting RVC model or parameter problems.

Request:

```json
{
  "filename": "rvc-converted-job-ir035-f00-rm100-pr33.wav"
}
```

Response:

```json
{
  "ok": true,
  "result": {
    "original": {
      "filename": "rvc-converted-job-ir035-f00-rm100-pr33.wav"
    },
    "denoised": {
      "filename": "rvc-converted-job-ir035-f00-rm100-pr33-denoised.wav",
      "url": "/api/rvc/audio/converted/rvc-converted-job-ir035-f00-rm100-pr33-denoised.wav"
    }
  }
}
```

## Audio files

### `GET /audio/{filename}`

Streams generated audio files from the local runtime audio directory. Runtime audio is ignored by Git and should not be committed.

## Deprecated compatibility endpoints

- `GET /v1/voices`
- `GET /v1/reference-voices`
- `GET /v1/models`
- `POST /v1/speak`
# Internal routing and compatibility

FastAPI HTTP boundaries are split under `src/local_tts_service/api/`, with shared health and model-catalog logic under `services/`. The Node proxy normalizes TTS input in `frontend/server/tts-request.js` and RVC input in `frontend/server/rvc/validation.js`. API paths, status handling, JSON shapes, and audio responses are unchanged. Browser validation serves input UX, Node validates proxy boundaries, and Python remains the authoritative validation layer.
