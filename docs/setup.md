# セットアップガイド

## 必要環境

- Windows 10 / 11（64bit）
- NVIDIA GPU推奨
- モデルと実行環境を保存できる空き容量
- 自動取得を使う場合だけインターネット接続

Python 3.11、Node.js、Gitはアプリ内の `runtime/tools/` へ自動導入されるため、通常はWindowsへ別途インストールする必要はありません。

## 初回セットアップと起動

リポジトリ直下の `local-tts.bat` をダブルクリックします。

```powershell
local-tts.bat
```

必要な環境が不足している場合は自動でセットアップし、完了後にサービスとブラウザを起動します。準備済みの場合はセットアップを繰り返さず、そのまま起動します。

初回セットアップの主な内容:

- `config/config.example.json` から `config/config.local.json` を作成
- 固定版Python 3.11を公式配布元から取得し、SHA-256検証後にアプリ内へ導入
- Python仮想環境、依存パッケージ、Windows用のアプリ内VC++ランタイムを導入
- NVIDIA GPU検出時に検証済みCUDA版PyTorchを導入
- 固定版Node.jsを公式配布元から取得し、SHA-256検証後に保存
- 固定版MinGitを公式配布元から取得し、SHA-256検証後に保存
- frontend依存を導入
- Qwen3-TTS Voice Clone 1.7Bモデルを取得
- Irodori v2 / v3 / v3 VoiceDesign、codec、Tokenizerをリポジトリ内へ導入
- FFmpegを導入
- yt-dlpとfaster-whisperを確認
- BGM・伴奏除去用のDemucs環境を導入
- サービスを起動してブラウザを開く

動画URLから参照音声を作るためのツールもセットアップに含まれます。文字起こしモデルやBGM・伴奏除去モデルは、機能を初めて使った時に追加ダウンロードされる場合があります。

## Irodori v3の完全オフライン配置

別PCなどで取得済みの実行環境とモデルを配置すれば、通常起動と生成はネットワークなしで動作します。Irodori v3には次が必要です。

```text
runtime/venv-irodori/Scripts/python.exe
runtime/vendor/Irodori-TTS-upstream/
runtime/models/irodori/Irodori-TTS-500M-v3/model.safetensors
runtime/models/irodori/Semantic-DACVAE-Japanese-32dim/weights.pth
runtime/models/irodori/tokenizers/llm-jp-3-150m/tokenizer.json
runtime/models/irodori/tokenizers/llm-jp-3-150m/tokenizer_config.json
runtime/models/irodori/tokenizers/llm-jp-3-150m/special_tokens_map.json
```

起動時にcheckpoint、codec、Tokenizer、専用Python、Irodoriコードを検査し、既定のIrodori v3を事前ロードします。不足時は「○○がありません」と配置先を表示し、生成ボタンでは取得や初期化を行いません。通常起動と生成はHugging Faceのログイン状態や認証トークンに依存しません。

## 2回目以降

同じ `local-tts.bat` をダブルクリックします。

通常起動ではモデルやTokenizerをダウンロードせず、全WSLモデルの外部確認も行いません。バックエンド起動中に既定のIrodori v3をローカルから事前ロードし、準備完了後にブラウザを開きます。

## 修復セットアップ

途中でセットアップに失敗した場合や、必要な環境を作り直す場合:

```powershell
local-tts.bat -ForceSetup
```

既存のローカル設定、参照音声、モデル、生成物を削除せず、不足している依存関係を再確認します。

## 診断

起動できない場合:

```powershell
local-tts.bat -Check
```

より詳しい外部サービス確認は開発者向けスクリプトを直接使います。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-local-tts.ps1 -Deep -CheckOptionalServices
```

## 標準セットアップに含まれるもの

| 機能・モデル | 初回セットアップ後 | 追加作業 |
|---|---:|---|
| Qwen3-TTS Voice Clone 1.7B | 使用可能 | 参照音声と一致する書き起こし |
| Irodori v2 / v3 / v3 VoiceDesign | 使用可能 | なし |
| 動画URL候補抽出 | 使用可能 | 初回利用時に音声認識モデルを取得する場合あり |
| BGM・伴奏除去 | 使用可能 | 初回利用時にDemucsモデルを取得する場合あり |
| Qwen3-TTS Voice Clone 0.6B | 未導入 | 追加モデルと参照音声 |
| GPT-SoVITS | 無効 | vendorセットアップと設定変更 |
| RVC | 声モデル未配置 | `.pth` と `.index` を配置 |
| WSL追加モデル | 無効 | 個別セットアップ |
| VoxCPM2互換 | 無効 | ComfyUIと設定追加 |

## RVCモデルを追加する

RVCの声モデルは自動ダウンロードされません。同じモデルの `.pth` と `.index` をモデルごとのフォルダーへ配置します。

```text
models/rvc/my_voice/
├── my_voice.pth
└── my_voice.index
```

RVCタブがこのフォルダーを自動検出します。使用可能な組がない場合は、変換画面の代わりに配置先と作成ガイドが表示されます。

## 参照音声を登録する

ブラウザの「参照音声」から次の方法を選べます。

1. マイクで録音
2. 音声ファイルから登録
3. 動画URLから登録

参照音声は次の場所に保存されます。

```text
reference/voices/<voiceId>/voice.wav
reference/voices/<voiceId>/voice.txt
```

音声内で実際に話している文章を正確に入力してください。目安は3〜10秒、1人の声、BGM・反響・ノイズが少ない音声です。

## 任意モデルを追加する

### WSLモデル

Sarashina2.2-TTS、FireRedTTS-2、T5Gemma-TTS、FishAudio S1-miniはWSL内の個別環境へ導入します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-wsl-tts-models.ps1 -Model all
```

詳細は [wsl-tts-models.md](./wsl-tts-models.md) を参照してください。

### GPT-SoVITS

GPT-SoVITSを使う場合は、開発者向けセットアップを実行して `config/config.local.json` で有効化します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-gpt-sovits.ps1
```

### VoxCPM2互換

VoxCPM2互換は標準設定に含まれません。ComfyUIの配置先と起動設定を `config/config.local.json` へ追加してください。

## プロセス管理

起動したサービスの情報は `runtime/processes/` に保存され、同じ起動セッションのWindows Job Objectにも登録されます。通常起動では、このアプリ専用のクラシックコンソールを1枚作成します。専用コンソールはサービスの実行中に開いたままになり、そこで`Ctrl+C`を押すか専用コンソールを閉じると、そのセッションで開始したサービスだけを終了します。起動元のPowerShellやWindows Terminalとは分離されているため、それらを閉じる必要はありません。次回起動時は、PID、起動時刻、コマンド識別情報、リポジトリパスが一致する、このアプリが管理する旧プロセスだけを整理してから再起動します。

同じポートを無関係なアプリが使用している場合、そのプロセスは終了せず、起動を中断して使用中のURLを表示します。別アプリを終了するかポート設定を変更してください。

## ローカルデータ

次のデータはGit管理対象外です。

- `config/config.local.json`
- `runtime/`
- `reference/voices/`
- `models/rvc/` 内のモデル本体
- 生成音声、キャッシュ、ログ

設定例やソースコードへ個人用の絶対パスやトークンを書き込まないでください。

## クリーンインストール検証

新規Windows環境で依存関係、モデル取得、起動、実WAV生成まで確認する場合:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-clean-install.ps1
```

詳細は [clean-install-verification.md](./clean-install-verification.md) を参照してください。
