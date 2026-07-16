# クリーン環境での初回導入検証

## 結論

実際の初回導入を証明するには、開発PCの既存環境を使わず、**別のWindows 10 / 11環境で新規cloneから `scripts/verify-clean-install.bat` を実行**します。

この検証は、公開時の最短導線に必要なものを対象にします。

- 固定版Python 3.11のアプリ内新規インストールとSHA-256確認
- pipキャッシュを使わないPython依存関係の新規インストール
- NVIDIA GPUありでは`torch` / `torchaudio` 2.8.0 + CUDA 12.8、GPUなしでは`2.8.0+cpu`の同一ペアを公式PyTorch indexから固定導入
- Windowsでは管理者権限を要求しないVisual C++ランタイムDLLの仮想環境内導入
- 検証専用npmキャッシュを使ったNode依存関係の新規インストール
- 通常利用中の8730・5177とは競合しない、検証専用の空きポート自動割り当て
- `config/config.example.json` から `config/config.local.json` の自動作成
- Qwen3-TTS Voice Clone 1.7Bの新規ダウンロード
- Irodoriの新規セットアップと既定のIrodori v3による生成
- backend / frontendの起動
- frontend API経由の実音声生成
- 生成WAVのRIFFヘッダー、サイズ、SHA-256確認

Sarashina、FireRedTTS-2、T5Gemma、FishAudio、GPT-SoVITS、ComfyUI、RVCなどの任意追加機能は、この最短導線の検証対象外です。

## 推奨する検証環境

**最も確実なのは、NVIDIA GPUを搭載した別PC、または同じPCの別SSDへ入れたクリーンなWindowsです。** 実際にCUDAを使った音声生成まで確認できるためです。

Windows SandboxやVirtualBoxでも、依存関係の導入、モデルのダウンロード、設定作成、サービス起動までは確認できます。ただし通常のVirtualBox環境ではNVIDIA GPUをCUDA推論へそのまま渡せないため、そこでの成功だけではGPU実生成の証明になりません。

## 事前準備

検証用Windowsへ事前にPython、Git、Node.jsを入れる必要はありません。

- Python 3.11は検証時に固定版を`runtime/tools/python311/`へ導入
- システムGitは不要（固定版MinGitをアプリ内へ導入し、Irodoriの取得に使用）
- Node.jsは検証時に固定版を`runtime/tools/node/`へ導入
- NVIDIAドライバー
- 安定したインターネット回線
- モデル、Python環境、npm依存を保存できる十分な空き容量

リポジトリは新規cloneしてください。次が存在しない状態で始めます。

- `config/config.local.json`
- `.venv/`
- `frontend/node_modules/`
- `runtime/models/huggingface/`

## 実行方法

エクスプローラーから `scripts/verify-clean-install.bat` をダブルクリックするか、コマンドプロンプトから実行します。

```bat
scripts\verify-clean-install.bat
```

PowerShellから本体を直接実行する場合:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-clean-install.ps1
```

ブラウザも最後に開く場合:

```bat
scripts\verify-clean-install.bat -OpenBrowser
```

## PASSの条件

次をすべて満たしたときだけPASSです。

1. 既存のローカル設定、仮想環境、node_modules、モデルがない。
2. Python 3.11がない場合、固定版が`runtime/tools/python311/`へ新規導入される。
3. `config/config.example.json` から `config/config.local.json` が作成される。
4. `Qwen/Qwen3-TTS-12Hz-1.7B-Base` が新規取得される。
5. `torch`と`torchaudio`が同じ2.8.0系列になり、GPUなしでは両方`2.8.0+cpu`かつ`torch.cuda.is_available()`が`false`になる。NVIDIA GPUがある場合はCUDAが利用可能になる。
6. Windowsではシステム全体へVisual C++再頒布可能パッケージを入れなくてもPyTorchを読み込める。
7. backendとfrontendが起動する。
8. `/api/models` で既定モデルが利用可能になる。
9. `/api/speak` から実際に音声を生成できる。
10. 保存されたファイルが44バイトを超えるRIFF WAVである。

結果は次へ保存されます。

```text
runtime/clean-install-verification/clean-install-report.json
runtime/clean-install-verification/generated.wav
```

`clean-install-report.json` にはOS、Python、Node、npm、検出したNVIDIA GPU、`torch` / `torchaudio` / CUDA状態、モデル状態、WAVサイズ、SHA-256が入ります。PyTorch importに失敗した場合は、完全なstderrと終了コードを`error`に保存します。

## 開発PCでできる事前確認

既存環境を使った次の実行は、スクリプトの構文と必要コマンドだけを確認します。

```bat
scripts\verify-clean-install.bat -AllowExistingState -PreflightOnly
```

これはモデルの新規ダウンロードや実生成を行わないため、公開前のクリーン導入検証の代わりにはなりません。

## 設定ファイルの扱い

`config/config.local.json` は各PC固有の設定なのでGitへ含めません。公開するテンプレートは `config/config.example.json` だけで十分です。初回セットアップがテンプレートを `config/config.local.json` へコピーし、その後のローカル変更はGit管理外になります。

検証後に初期状態から再試験する場合は、検証用PCを初期化するか、クリーンなOSスナップショットへ戻してからリポジトリを再cloneしてください。
