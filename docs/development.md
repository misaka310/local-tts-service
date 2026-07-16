# 開発・テスト手順

この文書はリポジトリを変更する開発者向けです。通常利用者はREADMEと利用ガイドだけで起動・操作できます。

## ローカル設定

初回セットアップ時に `config/config.example.json` から `config/config.local.json` を作成します。`config/config.local.json` はローカル専用で、Gitへコミットしません。

モデル別の設定例:

- `config/config.example.json`
- `config/config.irodori.example.json`
- `config/config.qwen3.example.json`

## 主なテスト

```powershell
python -m pytest --rootdir=. -c config/pytest.ini tests
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-setup-local-tts.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-managed-processes.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-managed-job.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-clean-install.ps1 -AllowExistingState -PreflightOnly
cd frontend
npm run check
npm test
npm run e2e:smoke
npm run e2e:reference-voices
npm run e2e:qwen-ui
npm run e2e:rvc-tabs
```

ローカルの実行環境がある場合だけ、次も実行します。

```powershell
npm run e2e:wsl-models-live
npm run e2e:rvc-convert
```

## クリーンインストール検証

新規Windows環境で依存関係、モデル取得、サービス起動、実WAV生成まで確認する場合:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-clean-install.ps1
```

詳細は [clean-install-verification.md](./clean-install-verification.md) を参照してください。

## 公開リポジトリへ含めないもの

- `config/config.local.json`
- `.env` / `.env.*`
- `runtime/`
- `reference/voices/`
- `data/source_audio/`
- 生成音声、動画、モデル重み、RVC index
- 個人パス、トークン、秘密情報

公開前の監査:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\audit-public-history.ps1
```

履歴書き換えは明示的な承認なしで実行しません。

## 関連資料

- [API](./api.md)
- [システム構成](./architecture.md)
- [フロントエンド構成](./frontend.md)
- [設定](./configuration.md)
- [プロバイダー](./providers.md)
