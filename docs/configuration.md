# 設定

## 基本

- `defaultModel`の既定値は`irodori_v3`
- `defaultReferenceVoice`はUIのおすすめ候補用。公開用の初期値は空です。
- `voiceId`未指定時の自動fallbackはなし
- `chunking.pauseBetweenChunksMs`はchunk結合時の無音挿入に使う

## 例

```json
{
  "defaultModel": "irodori_v3",
  "defaultReferenceVoice": "",
  "referenceVoicesDir": "./reference/voices",
  "chunking": {
    "softChunkChars": 120,
    "maxChunkChars": 200,
    "hardLimitChars": 260,
    "pauseBetweenChunksMs": 250
  }
}
```

## Irodoriモデル

Irodoriは`local-tts.bat`の標準セットアップでリポジトリ内の`runtime/`へ導入し、`irodori_voicedesign_direct` runtimeから直接実行します。通常起動は既定モデルをローカルcheckpoint・codec・Tokenizerから事前ロードし、生成要求では同じ常駐ワーカーへ本文と生成条件だけを送ります。常駐ワーカーは最後の処理完了から既定600秒（10分）使われないと正常終了し、次の生成要求でモデルを含めて自動再起動します。`idleTimeoutSec`で秒数を変更でき、0以下では自動終了しません。環境変数`LOCAL_TTS_IRODORI_IDLE_TIMEOUT_SEC`でも上書きできます。v2・v3は参照音声なしでも生成でき、参照音声を指定した場合だけ話者条件として使います。v3 VoiceDesign・v4 Smallは参照音声またはcaption（画面上の「話し方メモ」）のどちらかが必要で、両方を指定すると話者条件と話し方条件を同時に使用します。v2は`seed`、v3は`seed`と`speedScale`、v3 VoiceDesignとv4 Smallはさらにcaptionと`styleStrength`へ対応します。v2にはduration predictorがないため、このリポジトリでは話速設定を表示・送信しません。

```json
{
  "models": {
    "irodori_v3": {
      "runtime": "irodori_voicedesign_direct",
      "modelId": "Aratako/Irodori-TTS-500M-v3",
      "checkpoint": "./runtime/models/irodori/Irodori-TTS-500M-v3/model.safetensors",
      "requiresReferenceAudio": false,
      "supportsSeed": true,
      "supportsSpeedControl": true,
      "supportsReferenceVoice": true
    }
  },
  "runtimes": {
    "irodori_voicedesign_direct": {
      "pythonExecutable": "./runtime/venv-irodori/Scripts/python.exe",
      "wrapperDir": "./runtime/vendor/Irodori-TTS-upstream",
      "startupTimeoutSec": 1800,
      "idleTimeoutSec": 600,
      "codecRepo": "./runtime/models/irodori/Semantic-DACVAE-Japanese-32dim/weights.pth",
      "textProcessorRepo": "llm-jp/llm-jp-3-150m",
      "textProcessorDir": "./runtime/models/irodori/tokenizers/llm-jp-3-150m"
    }
  }
}
```

## WSL Zero-shot TTS

4モデルは`external_cli`runtimeを使用します。各モデルに`externalCommandKey`を指定し、通常生成とモデル比較で必要な参照入力を宣言します。

```json
{
  "models": {
    "sarashina2_2_tts": {
      "runtime": "external_cli",
      "externalCommandKey": "sarashina",
      "requiresReferenceAudio": true,
      "requiresReferenceText": true,
      "supportsInstruction": false
    },
    "fireredtts2": {
      "runtime": "external_cli",
      "externalCommandKey": "fireredtts2",
      "requiresReferenceAudio": true,
      "requiresReferenceText": true,
      "supportsInstruction": false
    },
    "t5gemma_tts_2b_2b": {
      "runtime": "external_cli",
      "externalCommandKey": "t5gemma",
      "requiresReferenceAudio": true,
      "requiresReferenceText": true,
      "supportsInstruction": false
    },
    "fish_s1_mini": {
      "runtime": "external_cli",
      "externalCommandKey": "fish_s1_mini",
      "requiresReferenceAudio": true,
      "requiresReferenceText": true,
      "supportsInstruction": false
    }
  }
}
```

runtime設定例:

```json
{
  "runtimes": {
    "external_cli": {
      "timeoutSec": 1800,
      "commands": {
        "sarashina": ["powershell", "-NoProfile", "-File", "./scripts/run-wsl-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
        "fireredtts2": ["powershell", "-NoProfile", "-File", "./scripts/run-wsl-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
        "t5gemma": ["powershell", "-NoProfile", "-File", "./scripts/run-wsl-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"],
        "fish_s1_mini": ["powershell", "-NoProfile", "-File", "./scripts/run-wsl-tts.ps1", "-RequestJson", "{request_json}", "-OutputPath", "{output_path}"]
      },
      "availabilityCommands": {
        "sarashina": ["powershell", "-NoProfile", "-File", "./scripts/check-wsl-tts.ps1", "-Model", "sarashina2_2_tts"],
        "fireredtts2": ["powershell", "-NoProfile", "-File", "./scripts/check-wsl-tts.ps1", "-Model", "fireredtts2"],
        "t5gemma": ["powershell", "-NoProfile", "-File", "./scripts/check-wsl-tts.ps1", "-Model", "t5gemma_tts_2b_2b"],
        "fish_s1_mini": ["powershell", "-NoProfile", "-File", "./scripts/check-wsl-tts.ps1", "-Model", "fish_s1_mini"]
      }
    }
  }
}
```

`availabilityCommands`はモデルの専用venv、コード、重み、固定revision、必要importを確認します。確認失敗時は`/v1/models`の`available`が`false`になり、`unavailableReason`がUIへ表示されます。

通常は既定設定をそのまま使用し、個人用のWSLパスやモデル保存先を`config/config.local.json`へ直書きしません。保存先を変更する場合はWSL側の`LOCAL_TTS_WSL_HOME`環境変数を使用します。

## ComfyUI関連

標準の`config/config.example.json`にはComfyUI設定を含めません。IrodoriとQwen3-TTSはComfyUIを使いません。

VoxCPM2互換などを追加する場合だけ、`config/config.local.json`へ次をまとめて追加します。

- `runtime`が`comfyui`または`comfyui_voxcpm2`のmodel定義
- `externalServices.comfyui.enabled=true`
- `externalServices.comfyui.rootDir`と`startCommand`
- `runtimes.comfyui`または`runtimes.comfyui_voxcpm2`の接続先・入出力先

通常起動は「対応modelが存在する」「serviceが明示的に有効」の両方を満たす場合だけComfyUIを起動・確認します。古い`enabled=true`だけが残っていても、対応modelがなければ無視します。

## GPT-SoVITS関連

公開用の初期設定では`externalServices.gptSovits.enabled`は`false`です。任意ランタイムを導入した後に明示的に`true`へ変更した場合だけ通常起動へ含めます。vendorフォルダが存在するだけでは有効にならず、通常起動だけでclone・インストールすることもありません。
