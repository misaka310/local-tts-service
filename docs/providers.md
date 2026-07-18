# Providers / Runtimes

## `irodori_voicedesign_direct`

`irodori_v2`、`irodori_v3`、`irodori_v3_voicedesign`を、ComfyUIを介さずリポジトリ内の専用Python環境から直接実行します。

- 標準の`local-tts.bat`がセットアップ時に`runtime/venv-irodori`、固定revisionの公式コード、各checkpoint、codec、Tokenizerを`runtime/`内へ導入します
- 通常起動時に既定のIrodoriモデルを完全ローカルから事前ロードし、生成時は常駐ワーカーで推論だけを行います
- worker内はTransformers/Hugging Faceのオフラインモードと外部ソケット遮断を有効にし、外部通信が検出された要求は失敗として扱います
- `irodori_v2`は参照音声なしで使用できます
- `irodori_v3`は参照音声なしでも使用でき、`voiceId`を指定した場合だけその音声を追加条件として使います
- 通常版v2/v3は`seed`と`speedScale`に対応します
- VoiceDesignはさらにcaptionと`styleStrength`に対応します

`voiceId`が指定された場合はserver側で解決し、runtimeへ`reference_audio_path`を渡します。未指定でも`requiresReferenceAudio=false`のIrodoriモデルは生成できます。モデルごとのcheckpointは`models.<id>.checkpoint`で指定し、起動時に専用Python、公式コード、checkpoint、codec、Tokenizerを検査します。不足時は欠けている項目と`runtime/models/...`の配置先を`unavailableReason`へ返します。通常起動・生成中にモデルやTokenizerを取得せず、Hugging Faceのログイン状態や認証トークンも参照しません。

## `comfyui`

Irodoriには使用しません。VoxCPM2などの互換modelを`config/config.local.json`へ追加した場合だけ使います。通常起動は対応modelと`externalServices.comfyui.enabled=true`の両方があるときだけComfyUIを起動します。

## `external_cli`

Windowsサービスから外部プロセスをJSONリクエストで呼ぶruntimeです。Sarashina2.2-TTS、FireRedTTS-2、T5Gemma-TTS、FishAudio S1-miniは、`wsl.exe`経由でこのruntimeを使用します。

処理経路:

```text
/v1/speak
  -> ExternalCliRuntime
  -> scripts/run-wsl-tts.ps1
  -> scripts/run_wsl_tts.sh
  -> scripts/wsl_tts_runner.py
  -> モデル専用venv / 公式コード
  -> 指定outputPathへWAV保存
```

payloadには次を含みます。

- `text`
- `model`
- `language`
- `seed`
- `referenceAudioPath`
- `referenceTextPath`
- `outputPath`

`referenceTextPath`はランナー側でUTF-8として読み取り、参照文字列とともに公式Zero-shot APIへ渡します。WindowsパスはPowerShellラッパーでWSLパスへ変換します。

### availability

`runtimes.external_cli.availabilityCommands`にモデルごとの確認コマンドを設定できます。WSLモデルでは次を実検査します。

- 専用venv
- 公式コードの実行入口
- 必須重み
- 固定コードrevision
- 固定モデルrevision
- 必要Pythonモジュール

確認失敗時は`/v1/models`で`available: false`となり、stderrを`unavailableReason`へ返します。生成コマンドの存在だけでは利用可能にしません。

### エラー処理

- 外部プロセスの終了コードをそのまま失敗として扱う
- stdout / stderrをUTF-8で取得
- timeoutをAPIエラーへ変換
- 出力WAVが存在しない、空、または指定パス外の場合は失敗

詳細は[`wsl-tts-models.md`](./wsl-tts-models.md)を参照してください。

## `qwen3_tts`

Qwen3-TTS Voice CloneをWindows側`.venv`で直接実行します。標準セットアップは1.7Bを導入し、0.6Bは任意追加モデルとして同じ`/v1/speak`経由で実行します。

## `mock_wav`

pytestとAPI smoke用です。実モデルの成功証拠には使用しません。

## `comfyui_voxcpm2`

既存のVoxCPM2 workflow用です。
