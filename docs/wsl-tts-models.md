# WSL Zero-shot TTSモデル

`local-tts-service`は、Windows側の既存`.venv`へ依存関係を混ぜず、次の4モデルをWSL内の専用環境から`external_cli`経由で実行します。通常生成・モデル比較とも既存UIを使用します。

| モデルID | 表示名 | 公式モデルID | 参照入力 | 日本語 | ライセンス上の注意 |
|---|---|---|---|---|---|
| `sarashina2_2_tts` | Sarashina2.2-TTS | `sbintuitions/sarashina2.2-tts` | `voice.wav` + `voice.txt` | 対応 | モデルは非商用。商用利用は提供元へ確認 |
| `fireredtts2` | FireRedTTS-2 | `FireRedTeam/FireRedTTS2` | `voice.wav` + `voice.txt` | 対応 | Apache-2.0 |
| `t5gemma_tts_2b_2b` | T5Gemma-TTS 2B-2B | `Aratako/T5Gemma-TTS-2b-2b` | `voice.wav` + `voice.txt` | 対応 | モデルはGemma利用条件とCC BY-NC 4.0系の制約を確認。コードはMIT |
| `fish_s1_mini` | FishAudio S1-mini | `fishaudio/s1-mini` | `voice.wav` + `voice.txt` | 対応 | CC BY-NC-SA 4.0 |

第三者の声を本人の同意なく複製・なりすまし用途へ使用しないでください。

## 固定revision

セットアップは公式コードと公式モデルを次へ固定します。

| モデル | 公式コード | コードrevision | モデルrevision |
|---|---|---|---|
| Sarashina2.2-TTS | `https://github.com/sbintuitions/sarashina2.2-tts.git` | `e0ac9c99160ea4bf8dde46892892c945e66fcc13` | `8d30bd523b1fa217ab0b4cd32c9275d4f222fbcd` |
| FireRedTTS-2 | `https://github.com/FireRedTeam/FireRedTTS2.git` | `404f3f61d25bb4804859b588a6a734bf8468090c` | `4af3f5cc4963373b86b52d750220d4de85261f05` |
| T5Gemma-TTS | `https://github.com/Aratako/T5Gemma-TTS.git` | `c8722b37e1aca0e21f85185188755e164c316828` | `e548f8358891975e61d2107e3d7ccc47b1b7294e` |
| FishAudio S1-mini | `https://github.com/fishaudio/fish-speech.git` | `23a4beb06952a6cc29813851309184ec1c498cac` | `f4b445029346701e082b60bb63fcc2d1bb17a0e2` |

FishAudioはS1-miniに対応する上記revisionを使用します。現行S2向けコードへ置き換えないでください。

## 実行環境

各モデルは次へ分離されます。

```text
~/.local/share/local-tts-service/
├── venvs/<model>/
├── vendors/<model>/
├── models/<model>/
├── manifests/<model>.json
└── logs/
```

共通条件:

- Python 3.11（`uv python install 3.11`）
- PyTorch 2.8.0 / torchvision 0.23.0 / torchaudio 2.8.0
- CUDA 12.8 wheel
- 1リクエストごとにWSLプロセスを起動し、モデルを同時常駐させない
- モデル・venv・キャッシュはGit管理対象外
- 通常起動時に巨大モデルを自動ダウンロードしない

モデル固有条件:

- FireRedTTS-2: `transformers==4.57.3`、`huggingface_hub<1.0`
- T5Gemma-TTS: 固定revisionの公式CLIには`--low_vram`引数がないため、公式実装のBF16・Accelerate device mappingをそのまま使用し、量子化はしない
- FishAudio S1-mini: S1互換依存を専用venvへ固定

## 事前条件

WSL内でGPUとHugging Face認証を確認します。

```bash
nvidia-smi
hf auth whoami
```

認証トークンをリポジトリやチャットへ貼り付けないでください。承認制モデルは、ブラウザでHugging Faceへログインし、対象モデルページの利用条件に同意・アクセス申請しておく必要があります。

## セットアップ

全モデル:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-wsl-tts-models.ps1 -Model all
```

個別:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-wsl-tts-models.ps1 -Model sarashina
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-wsl-tts-models.ps1 -Model fireredtts2
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-wsl-tts-models.ps1 -Model t5gemma
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-wsl-tts-models.ps1 -Model fish_s1_mini
```

バックグラウンド実行:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-wsl-tts-models.ps1 -Model all -Background
```

ログ:

```text
runtime/logs/setup-wsl-tts-models.log
runtime/logs/setup-wsl-tts-models.err.log
```

## availability判定

`/v1/models`はスクリプトの存在だけでは利用可能にしません。モデルごとに次を確認します。

- WSL専用Pythonが実行可能
- 公式コードの実行入口が存在
- 必須モデル重みが存在
- 導入manifestが存在
- GitのHEADが固定コードrevisionと一致
- manifestのモデルrevisionが固定値と一致
- `torch`とモデル固有Pythonモジュールをimport可能

個別確認:

```powershell
powershell -NoProfile -File .\scripts\check-wsl-tts.ps1 -Model sarashina2_2_tts
powershell -NoProfile -File .\scripts\check-wsl-tts.ps1 -Model fireredtts2
powershell -NoProfile -File .\scripts\check-wsl-tts.ps1 -Model t5gemma_tts_2b_2b
powershell -NoProfile -File .\scripts\check-wsl-tts.ps1 -Model fish_s1_mini
```

不足があるモデルはUIで選択不可になり、`unavailableReason`を通常生成とモデル比較に表示します。

## 参照音声

使用する参照音声フォルダには両方が必要です。

```text
reference/voices/<voiceId>/voice.wav
reference/voices/<voiceId>/voice.txt
```

`voice.txt`は`voice.wav`で実際に話している内容と一致させてください。

## 実生成検証

4つのWSLモデルと既存Qwen3-TTS 0.6B / 1.7Bを、`local-tts-service`の`/v1/speak` API経由で順番に生成します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-wsl-tts-models.ps1
```

モデル指定:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-wsl-tts-models.ps1 -Model sarashina2_2_tts,fish_s1_mini,qwen3_tts_clone_0_6b
```

検証内容:

- APIレスポンスが成功
- 今回の実行後に新規WAVが作成された
- WAVが破損しておらず0秒ではない
- ファイルサイズ、サンプルレート、チャンネル数、長さを記録
- RMS、peak、無音率、SHA-256を記録
- コードrevision、モデルrevision、dtype、実行環境、生成時間を記録

出力:

```text
runtime/audio/model-smoke/
├── <runId>-<modelId>.wav
└── manifest.json
```

1モデルでも失敗すればコマンドは失敗終了しますが、残りのモデル検証は続行します。

## UIライブ検証

最新バックエンドをテスト専用ポートで起動し、実Chromeからモデル表示、availability、生成ボタン、結果カード、音声メタデータ読込まで確認します。

```powershell
cd frontend
npm run e2e:wsl-models-live
```

結果は`runtime/logs/e2e-wsl-models-live-result.json`へ保存されます。

## 2026-07-11のローカル検証状況

- Sarashina2.2-TTS: API実生成成功
- FireRedTTS-2: API実生成成功
- T5Gemma-TTS: API実生成成功。公式float WAVをPCM16へ正規化して30へ返す
- FishAudio S1-mini: API実生成成功
- Qwen3-TTS 0.6B / 1.7B: 回帰生成成功
- 実Chrome: 4つのWSLモデルが通常生成・モデル比較で選択可能。T5Gemmaの生成ボタン実行、結果表示、音声メタデータ読込に成功

全6モデルを同一runIdで再生成した結果は`runtime/audio/model-smoke/manifest.json`に保存され、`passedCount: 6`、`failedCount: 0`、`allPassed: true`を確認しています。
