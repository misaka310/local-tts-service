# AGENTS.md

このリポジトリを変更するAIエージェント向けの作業規約です。

## 利用者向け導線

- 利用者向けの入口はリポジトリ直下の `local-tts.bat` 1つにする。初回・通常起動を自動判定し、修復は `-ForceSetup`、診断は `-Check` で同じ入口から実行する。
- 開発・検証用コマンドは `scripts/` と `docs/development.md` に置き、通常利用者向けREADMEへ内部運用を混ぜない。
- ブラウザE2Eはheadlessまたは隔離プロファイルで実行し、利用者が操作中のブラウザ状態へ依存しない。
- 公開用の初期設定はIrodori v3を既定にし、Qwen3-TTSはVoice Clone 1.7Bだけを標準導入する。Qwen3-TTS Voice Designは標準設定・通常UI・初回ダウンロードへ戻さない。
- セットアップやモデル追加で、既存の通常生成・比較・RVC・履歴・参照音声のUXを勝手に変更しない。
- 参照音声は「新しく登録」と「登録済み音声」を分離し、マイク・音声ファイル・動画URLの3方法を維持する。登録フォームと管理画面を同時表示しない。
- 利用できないモデル自体は一覧から消さず、選択不可と具体的な理由を表示する。選択中モデルが対応しない入力項目は表示しない。
- `Failed to fetch` などブラウザ由来の生エラーを利用者へそのまま表示せず、復旧操作が分かる文言へ変換する。
- モデル能力はUI表示、必須判定、リクエスト正規化、API検証、実エンジン呼出しまで同じ契約で扱う。
- RVCは完全な `.pth` と `.index` の組がない場合に変換フォームを表示せず、配置先、作成ガイド、再読み込み導線を表示する。
- 汎用のRVC推論、モデル読込、HuBERT/RMVPE、ウォームアップ、変換API、永続プロセスはこのリポジトリが所有する。利用先固有のUI、ブラウザ、端末、再生制御、マイク制御はAPI契約へ入れない。
- GPU常駐モデルの明示解放はruntime所有のAPIで行い、利用側からworker PIDを直接終了しない。

## READMEの対象読者

- READMEは初見の通常利用者向け入口に限定する。
- READMEには、できること、必要環境、`local-tts.bat`による起動、最初の生成、保存場所、利用上の注意、利用者向け文書へのリンクを中心に置く。
- 内部構成、API一覧、テスト手順、公開監査、実装ファイル一覧は `docs/` へ分離する。
- リポジトリ番号、個人向け呼称、ローカル絶対パス、別プロジェクト固有の名称や運用契約など、一般利用者に意味がない内輪表現を利用者向け文書へ出さない。
- 下流アプリとの統合方法が必要な場合も、特定アプリ名ではなく公開APIと一般的な利用契約として記述する。

## 公開リポの安全

- `config/config.local.json`、`runtime/`、`reference/voices/`、音声・動画・モデル重み・トークン・個人パスをコミットしない。
- `reference/workflows/` は公開ワークフローとしてGit管理する。
- 公開前にpublic history監査を実行し、working treeの検出を0件にする。履歴書き換えは明示承認なしで行わない。

## 責務境界

- `frontend/server.js` はルーティングと設定読込に限定し、HTTP共通処理・音声処理・参照音声・RVCは `frontend/server/` に置く。
- `frontend/public/app.js` は画面全体の接続に限定し、モデル定義・純粋計算・メディア同期・専用画面は別ファイルへ分ける。
- FastAPI HTTP境界は `src/local_tts_service/api/`、catalog/healthは `services/`、合成ワークフローは `synthesis/` に置く。
- このリポジトリは再利用可能なTTS/RVC基盤だけを所有する。下流アプリ固有のセリフ、表示資産、リリース契約、同期処理、製品固有設定は持ち込まない。

## 検証

変更内容に応じて最低限、次を実行する。

```powershell
python -m pytest --rootdir=. -c config/pytest.ini tests
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-setup-local-tts.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-managed-processes.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-managed-job.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-console-control.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-clean-install.ps1 -AllowExistingState -PreflightOnly
cd frontend
npm run check
npm test
npm run e2e:smoke
npm run e2e:reference-voices
npm run e2e:qwen-ui
npm run e2e:rvc-tabs
```

セットアップ、設定、API、画面文言を変えた場合は、READMEと `docs/` も同じ変更で更新する。

## 仕様の正本

- 仕様の正本は `README.md` と対応する `docs/`。
- 仕様変更時は実装と検証を同じ変更で更新する。
