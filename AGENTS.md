# AGENTS.md

このリポジトリを変更するAIエージェント向けの作業規約です。

## 利用者向け導線を守る

- 利用者向けの入口はリポジトリ直下の `local-tts.bat` 1つだけにする。初回・通常起動を自動判定し、修復は `-ForceSetup`、診断は `-Check` で同じ入口から実行する。開発・検証用コマンドは `scripts/` と `docs/development.md` に置く。
- 公開用の初期設定はIrodori v3を既定にし、Qwen3-TTSはVoice Clone 1.7Bだけを標準導入する。Qwen3-TTS Voice Designは標準設定・通常UI・初回ダウンロードへ戻さない。
- セットアップやモデル追加で、既存の通常生成・比較・RVC・履歴・参照音声のUXを勝手に変更しない。
- 「使い方」は画面が開いている時点で起動済みとして、最初の生成、目的選択、参照音声、困ったとき、注意事項の順を維持する。起動方法は次回起動などの補足に留め、長文分割の大きな重複説明を戻さない。
- 参照音声は「新しく登録」と「登録済み音声」を分離し、マイク・音声ファイル・動画URLの3方法を維持する。内部実装名にかかわらず、利用者向け表示には特定サービス名を出さない。登録フォームと管理画面を同時表示しない。
- 利用できないモデル自体は一覧から消さず、選択不可と具体的な理由を表示する。一方、選択中モデルが対応しない入力項目や調整項目はグレーアウトで残さず、その項目自体を表示しない。
- RVCは完全な `.pth` と `.index` の組がない場合に変換フォームを表示せず、`models/rvc` の配置先、作成ガイド、再読み込み導線を表示する。複数の完全なモデルは画面で切り替えられる状態を維持する。
- 参照音声の登録ID変更では、音声・文章・アーカイブ状態を保持し、通常生成・モデル比較・RVC・履歴の保存済み参照IDも新しいIDへ移行する。

## READMEの対象読者を守る

- READMEは初見の通常利用者向け入口に限定し、140行以内を維持する。
- READMEには、できること、必要環境、`local-tts.bat`による起動、最初の生成、保存場所、利用上の注意、利用者向け文書へのリンクだけを置く。
- 内部構成、API一覧、テスト手順、公開監査、実装ファイル一覧はREADMEへ書かず、`docs/`へ分離する。
- リポジトリ番号、個人向け呼称、ローカル絶対パスなど、一般利用者に意味がない内輪表現を利用者向け文書へ出さない。
- セットアップや画面機能を変更した場合は、READMEだけを追記して肥大化させず、`docs/user-guide.md`、`docs/setup.md`、`docs/development.md`の適切な文書を更新する。

## 公開リポの安全

- `config/config.local.json`、`runtime/`、`reference/voices/`、音声・動画・モデル重み・トークン・個人パスをコミットしない。
- `reference/workflows/` は公開ワークフローとしてGit管理する。
- 公開前に public history 監査を実行し、working treeの検出を0件にする。履歴書き換えは明示承認なしで行わない。

## 検証

変更内容に応じて最低限、次を実行する。

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

セットアップ、設定、API、画面文言を変えた場合は、READMEと `docs/` も同じ変更で更新する。

## 責務境界

- `frontend/server.js` はルーティングと設定読込に限定し、HTTP共通処理・音声処理・参照音声・RVCは `frontend/server/` に置く。
- `frontend/public/app.js` は画面全体の接続に限定し、モデル定義・純粋計算・メディア同期・専用画面は別ファイルへ分ける。
- 新しい独立機能を既存の巨大ファイルへ直接追加する前に、`docs/architecture.md` の既存モジュールへ置けないか確認する。
# Refactored change locations

- Put browser normalization in `frontend/public/generation-core.js` and RVC pure UI state in `frontend/public/rvc/`.
- Put Node TTS normalization in `frontend/server/tts-request.js` and RVC implementation in `frontend/server/rvc/`.
- Put FastAPI HTTP boundaries in `src/local_tts_service/api/`, catalog/health logic in `services/`, and synthesis workflow logic in `synthesis/`. Preserve compatibility facades.
- Run `scripts/cleanup-runtime-artifacts.ps1` without `-Apply` first; its default mode never deletes files.
