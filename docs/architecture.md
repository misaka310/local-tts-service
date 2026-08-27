# Architecture

この文書は、機能追加時に処理を巨大ファイルへ戻さないための責務境界を示します。

## 実行入口

- `src/local_tts_service/server.py`: 後方互換のASGI入口。実際のFastAPI構築は `src/local_tts_service/api/app.py`。
- `frontend/server.js`: ブラウザ向けHTTPルーティングと設定読込。
- `frontend/public/app.js`: 共有状態、初期API読込、Controllerへの依存注入、共通UI接続。

## 依存方向

```text
Browser DOM
  -> page controllers
  -> page workflow / generation-core
  -> frontend Node API
  -> FastAPI routers
  -> application services / synthesis workflow
  -> runtimes and external processes
```

上位層から下位層への依存だけを基本とし、サービス層からHTTPやDOMを参照しません。

## Voice Buttonsとの責務境界

Local TTS Serviceは、モデル、参照音声、推論runtime、汎用TTS API、no-window起動と停止など、再利用可能な音声生成基盤を所有します。Voice Buttons固有の40本の固定セリフ、会話5セット、カテゴリ、accepted SHA、Site向けrelease contract、SiteのWAV配置は所有しません。

Voice Buttons Siteは保守時だけLocal TTS Serviceの公開APIと起動契約を利用し、生成結果の受入・SHA判定・Site資産への反映を所有します。Site実行時はLocal TTS Service、localhost、GPUから独立します。個別製品のセリフ一覧やSite同期用generatorをLocal TTS Serviceへ追加しないでください。

## フロントエンドサーバー

`frontend/server.js`はルート判定とHTTPレスポンス組み立てを中心にし、実処理を次へ分離しています。

| モジュール | 責務 |
|---|---|
| `frontend/server/shared.js` | JSON読込、パス検証、ログ整形などの共通処理 |
| `frontend/server/http-utils.js` | JSON応答、リクエスト読込、TTS API呼出、静的配信 |
| `frontend/server/audio-utils.js` | WAV情報、録音データ、FFmpeg変換 |
| `frontend/server/reference-voices.js` | 参照音声一覧、録音・ファイル登録、文章更新、アーカイブ |
| `frontend/server/tts-request.js` | Node側のTTSリクエスト正規化 |
| `frontend/server/rvc/config.js` | RVC設定、環境変数、成果物パス |
| `frontend/server/rvc/model-catalog.js` | `models/rvc` のモデル検出、完全性判定、選択候補生成 |
| `frontend/server/rvc/validation.js` | RVC入力値とパラメータの検証 |
| `frontend/server/rvc/artifact-store.js` | 録音・変換後音声・ノイズ除去成果物 |
| `frontend/server/rvc/input-preparer.js` | TTS・ファイル・マイク入力のWAV準備 |
| `frontend/server/rvc/demucs-runner.js` | BGM・伴奏除去の実行 |
| `frontend/server/rvc/rvc-runner.js` | RVCコマンド構築と実行 |
| `frontend/server/rvc/conversion-service.js` | RVC変換全体のオーケストレーション |
| `frontend/server/rvc-service.js` | 旧importを維持する互換Facade |
| `frontend/youtube-reference.js` | YouTube由来の参照音声候補作成と登録 |

新しいAPIでは、`server.js`にファイル処理や外部コマンド実行を追加せず、対応するサービスへ置きます。

## 永続RVCサービス

`scripts/persistent_rvc_service.py` は、低遅延の連続利用向けにRVCモデル、HuBERT、RMVPEを1プロセスへ保持する汎用HTTPサービスです。設定はGit対象外の `config/rvc-persistent.local.json`、公開例は `config/rvc-persistent.example.json` に置きます。利用先固有のChatGPT、ブラウザ、再生デバイス、マイク制御は持ちません。詳細は `docs/persistent-rvc-service.md` を参照してください。

## ブラウザ画面

ビルドツールを使わず、`frontend/public/index.html`で依存順を明示しています。

1. `shared-ui.js`、`tts-api-client.js`
2. モデル定義・能力・chunk関連モジュール
3. `store.js`、`generation-core.js`、`audio-controller.js`
4. `frontend/public/rvc/`の純粋UIモジュール
5. `normal-controller.js`、`compare-controller.js`、`rvc/rvc-controller.js`
6. `normal-page.js`、`compare-page.js`、`rvc-page.js`
7. `app.js`
8. `reference-voices.js`、`reference-voices-ux.js`、`history.js`

### Controller境界

- ControllerはDOM要素と操作関数を明示的に受け取り、ページ固有イベントをbindします。
- `app.js`の`bindEvents()`には、タブ、共通chunk UI、診断ログ、参照音声再読込など画面横断処理だけを置きます。
- seed、chunk設定、モデル能力検証、TTSリクエスト構築、利用者向けエラー変換の正本は `generation-core.js`です。
- classic script互換のため、`normal-page.js`、`compare-page.js`、`rvc-page.js`は既存のページワークフローを保持します。新しいイベント処理をこれらと`app.js`へ重複追加しません。

### 参照音声の責務境界

- `index.html`: 「新しく登録」と「登録済み音声」、3つの登録方法、各フォームのDOM構造だけを持つ。
- `reference-voices.js`: 既存のマイク録音、YouTube候補、一覧、登録ID変更、文章修正、アーカイブを維持する。
- `reference-voices-ux.js`: サブタブ/方法切替、ローカルファイル選択、プレビュー、必須入力検証、完了パネル、文字起こし欄の自動拡張を担当する。
- `app.js`: `local-tts:use-reference-voice`を受け、通常生成へ移動して登録済み音声を選択する画面横断処理だけを持つ。
- `frontend/server/reference-voices.js`: 録音と音声ファイルを同じ保存パイプラインでFFmpeg変換・WAV検証し、成功後だけ`reference/voices/<voiceId>/`を作る。
- `frontend/youtube-reference.js`と`scripts/youtube_reference_candidates.py`: 候補生成、字幕/Whisper、ローリング字幕の重複除去、BGM・伴奏除去、登録用成果物を担当する。

新規登録成功は`local-tts:reference-voice-registered`、一覧再読込は`local-tts:reference-voices-changed`、登録ID変更は`local-tts:reference-voice-renamed`として分けます。文章修正やアーカイブを新規登録完了として扱いません。ID変更イベントは各画面の選択値と履歴内の参照ID移行に使います。

## FastAPI

| モジュール | 責務 |
|---|---|
| `src/local_tts_service/api/app.py` | FastAPI app factory、middleware、例外処理、router登録 |
| `src/local_tts_service/api/dependencies.py` | APIで共有するサービス依存 |
| `src/local_tts_service/api/routers/` | health、models、voices、speak、audioのHTTP境界 |
| `src/local_tts_service/services/health_service.py` | deep health診断 |
| `src/local_tts_service/services/model_catalog_service.py` | モデル利用可否とAPI表示情報 |
| `src/local_tts_service/server.py` | `server:app`と`create_app()`の互換入口 |

## 音声生成

`src/local_tts_service/synthesis/`へ次を分離しています。

- `capability_validator.py`: モデル能力と入力条件の検証
- `request_normalizer.py`: caption、instruction、language、制御値の正規化
- `chunking.py`: chunk設定と文章分割
- `chunked_synthesizer.py`: 分割生成、WAV結合、chunk後始末
- `service.py`: ワークフロー接続とレスポンス構築

`src/local_tts_service/synthesis_service.py`は既存importを維持する互換Facadeです。

## 実行生成物

chunkは実行IDごとのディレクトリへ保存し、結合成功後に既定で削除します。`chunking.keepChunkFiles`を有効にした場合のみ保持します。古い生成物を整理するときは、最初にdry-runで実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\cleanup-runtime-artifacts.ps1
```

実削除は出力を確認してから`-Apply`を付けます。

## 変更時の確認

```powershell
cd frontend
npm run check
npm test
npm run e2e:smoke
npm run e2e:reference-voices
npm run e2e:qwen-ui
npm run e2e:rvc-tabs
cd ..
python -m pytest --rootdir=. -c config/pytest.ini tests
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-setup-local-tts.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-managed-processes.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-clean-install.ps1 -AllowExistingState -PreflightOnly
```

`local_tts_service.server:app`、`create_app()`、`local_tts_service.synthesis_service.SynthesisService`、既存Node exports、APIパス、DOM ID、localStorageキーは互換対象です。
