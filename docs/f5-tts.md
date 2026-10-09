# F5-TTS Japanese voice cloning

F5-TTS is an optional Japanese zero-shot voice-cloning model. It is installed in its own Python environment and is not downloaded during the standard application setup.

## Sources and fixed versions

- Model: [`Jmica/F5TTS`](https://huggingface.co/Jmica/F5TTS), checkpoint `JA_21999120`
- Model revision: `6bed3f318d92e37b97164ece0e2f90153b09a4e5`
- Runtime package: `f5-tts==1.1.20`
- Model files: checkpoint, Japanese vocabulary, and the model README
- Code license: MIT, as published by [SWivid/F5-TTS](https://github.com/SWivid/F5-TTS/blob/main/LICENSE)

The Japanese checkpoint is non-commercial. Its [Hugging Face README](https://huggingface.co/Jmica/F5TTS/raw/main/README.md) says CC BY-NC 4.0, while the repository metadata lists CC BY-NC-SA 4.0. Treat the weights as non-commercial and check the current terms with the publisher before redistribution or other uses affected by the difference. The code license does not change the model-weight terms.

## Install and check

Run the setup script from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-f5-tts.ps1
```

The script creates a dedicated environment under `runtime/`, installs the pinned package versions, downloads the fixed model revision, and checks that the runtime can start. The Japanese checkpoint is several gigabytes. Review the available storage before starting setup.

To check an existing installation without generating audio:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-f5-tts.ps1 -Check
```

## Generate speech

Select **F5-TTS Zero-shot**, choose a registered reference voice, and provide the exact text spoken in `voice.wav` as `voice.txt`. The model is Japanese-only. Setup does not download model files when the application starts.

On Windows, F5-TTS reads reference WAV audio through the installed SoundFile package, so reference decoding does not depend on FFmpeg DLLs loaded by TorchCodec.
