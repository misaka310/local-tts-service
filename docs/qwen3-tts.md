# Qwen3-TTS

今回の追加対象は `Qwen3-TTS` のみです。`Qwen3-Omni`、`Qwen3.5-Omni`、その他の Omni 系や別候補の調査はこのリポジトリ変更に含めていません。

## 追加モデル

- `qwen3_tts_clone_0_6b`
  - 表示名: `Qwen3-TTS Voice Clone 0.6B`
  - 公式モデルID: `Qwen/Qwen3-TTS-12Hz-0.6B-Base`
- `qwen3_tts_clone_1_7b`
  - 表示名: `Qwen3-TTS Voice Clone 1.7B`
  - 公式モデルID: `Qwen/Qwen3-TTS-12Hz-1.7B-Base`

標準の`local-tts.bat`ではVoice Clone 1.7Bだけをダウンロードします。Voice Designは標準設定と通常UIから除外されています。

## モデル未取得時の挙動

- サービスは巨大モデルを自動ダウンロードしません。
- `qwen-tts` と `transformers` が実行環境に無い場合も `available=false` になります。
- モデル本体がローカルに見つからない場合、`/v1/models` では `available=false` と `unavailableReason` を返します。
- UI では未導入モデルを disabled 表示にし、同じ理由を画面に出します。

## 想定保存先

- Hugging Face cache:
  - `C:/Users/<user>/.cache/huggingface/hub/models--Qwen--Qwen3-TTS-12Hz-.../snapshots/<revision>/`
- ローカル vendor:
  - `runtime/vendor/qwen3-tts/<model directory>/`

`/v1/models` で `available=true` になる条件は次の両方です。

1. `qwen-tts` と `transformers` をサービス実行環境で import できる
2. 対象 `modelId` のローカル実体が Hugging Face cache または `runtime/vendor/qwen3-tts/` に存在する

## reference voice の置き方

Qwen3-TTS Voice Clone は `reference/voices/{voiceId}/` 配下の次を使います。

- `voice.wav`
- `voice.txt`

`voice.txt` が無い voice は `irodori` では使えても、Qwen3-TTS Voice Clone では使えません。UI では警告を出し、API では明確なエラーを返します。

## language

- 既定`language`は`Japanese`です。

## probe

出力先:

- `runtime/audio/qwen3_tts_probe/manifest.json`
- `runtime/audio/qwen3_tts_probe/manifest.csv`
- `runtime/audio/qwen3_tts_probe/index.html`

生成コマンド:

```powershell
python .\scripts\generate_qwen3_tts_probe.py
```

- 利用可能なモデルだけ生成します。
- 未導入モデルは `manifest` に `status=unavailable` と理由を書きます。
- `index.html` ではモデルごとの audio player と metadata を確認できます。

## disabled になる主な理由

- `qwen-tts` が未インストール
- `transformers` が未インストール
- 公式モデルIDのローカル実体が無い
- Qwen3-TTS Voice Clone で `voice.txt` が無い
