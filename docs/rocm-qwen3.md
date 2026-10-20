# Radeon (ROCm) で Qwen3-TTS Voice Clone を実行する

この機能は既存の `Qwen3-TTS Voice Clone 1.7B` を通常生成・比較画面から使用するための実行環境分離です。モデルの種類やライセンス表示、参照音声の登録手順は変更しません。

## 実行のしくみ

- 通常の Windows アプリ（5177 / 8730）は既存の Python 3.11 環境で動かします。
- Qwen3-TTS の推論のみ、別途導入済みの AMD ROCm 対応 Python 環境で実行します。
- ROCm 環境をアプリのセットアップで CUDA / CPU の PyTorch に上書きしません。
- Qwen のモデルファイルと参照音声 WAV / TXT は既存ストレージから使い、WAV は従来の生成物ディレクトリへ保存します。ネットワークからの重み取得を許可しません。
- ROCm GPU が確認できない場合は CPU 推論に黙って切り替えず、モデルを利用不可にします。

## 設定

Radeon に対応した PyTorch と `qwen-tts` と `soundfile` が動作する**独立した** Python 実行環境を用意します。AMD の対応OS・GPU・PyTorch/Pythonバージョンは公式資料を確認してください（ https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityrad/windows/windows_compatibility.html ）。

`config/config.local.json` の `runtimes.qwen3_tts` に、次の項目を追加します。

```json
{
  "runtimes": {
    "qwen3_tts": {
      "isolatedPythonExecutable": "./runtime/venvs/qwen3-rocm/Scripts/python.exe",
      "requireRocm": true
    }
  }
}
```

これは追加項目の例であり、既存の `config.local.json` 全体を置き換えないでください。成功済みのROCｍ対応Python環境が別の場所にある場合は、その実行ファイルのパスを指定します。絶対パスはローカル設定にのみ保存し、公開Gitへ追加しません。

`python.exe scripts/qwen3_isolated_runner.py --check` を**ROCm 環境のPython**で実行すると、GPUの利用可否をJSONで確認できます。起動時のモデル一覧もこのチェックを使います。通常生成や比較では今までと同じ `Qwen3-TTS Voice Clone 1.7B` を選びます。参照音声には WAV と転写テキストが必要です。

## 確認

1. `--check` で `backend=rocm`, `gpuAvailable=true` を確認する。
2. 登録済みの参照音声を使い通常生成で新規WAVを作る。
3. WAVの長さ、サンプルレート、音量（無音でないこと）、SHA-256を記録する。
4. 実機のGPU使用状況を確認する。

**実機確認ができていない状態は Radeon 対応の完了ではありません。** NVIDIA / CPU の標準セットアップは従来通りです。
