# トラブルシューティング

## `local-tts.bat` で起動しない

初回・通常起動ともに `local-tts.bat` を使用します。不足している環境は自動セットアップされます。

原因を切り分ける場合は `local-tts.bat -Check` を実行し、次を確認します。

- `.venv` があるか
- `pip install -r config/requirements.txt` を実行済みか
- `config/config.local.json` の JSON が壊れていないか
- `runtime/logs/` にエラーが出ていないか

### `npm command not found` / Node.jsが見つからない

標準セットアップ後は`runtime/tools/node/`の`node.exe`と`npm.cmd`を使うため、Windows全体のPATHへNode.jsを追加する必要はありません。`runtime/tools/node/`がない、または途中までしか展開されていない場合は、`local-tts.bat -ForceSetup`を実行してください。公式ZIPを再取得し、SHA-256確認後に同じ場所へ修復します。

`LOCAL_TTS_NODE_DIR`を設定している場合は、そのディレクトリに`node.exe`と`npm.cmd`が両方あるか確認してください。誤った指定は自動的に別のNode.jsへ切り替えず、明示エラーになります。

### 起動が長時間止まって見える

通常起動の末尾には、バックエンドhealth、軽量モデル確認、frontend起動、合計の時間が表示されます。通常起動は`/v1/models?probe=false`を使うため、未使用のWSLモデル確認を待ちません。詳細な外部プローブが必要な場合だけ`local-tts.bat -Check`または`GET /v1/models`を使ってください。

CPU音声生成は推論処理なので長時間かかる場合がありますが、アプリ起動が数分止まる問題とは分けて確認してください。`local-tts-service is running` が表示された後に、このアプリ専用のターミナルが残るのは正常です。停止する場合はその専用ターミナルで`Ctrl+C`を押すか、専用ターミナルを閉じてください。起動元のPowerShellやWindows Terminalを閉じる必要はありません。

### ポートが使用中と表示される

通常起動はポート所有者を無差別に終了しません。表示されたURLを使用している別アプリを終了するか、`config/config.local.json` のバックエンド・フロントエンドポートを変更してから再実行してください。

## ComfyUI が起動しない

標準設定にはComfyUI項目がなく、通常起動でも表示・起動・health確認を行いません。VoxCPM2互換などの対応modelを追加し、`externalServices.comfyui.enabled=true`も設定した場合だけ、次を確認します。古い有効設定だけが残っていても、対応modelがなければ通常起動は無視します。

- `externalServices.comfyui.rootDir` が正しいか
- `externalServices.comfyui.startCommand` が正しいか
- `runtimes.comfyui.launchWorkingDir` が正しいか
- `runtime/logs/comfyui-runtime.out.log`
- `runtime/logs/comfyui-runtime.err.log`

## Irodori が失敗する

`irodori_v3`は参照音声なしでも生成できます。`voiceId`を指定した場合だけ、`reference/voices/<voiceId>/voice.wav`が存在するか確認してください。

- `runtime/venv-irodori/Scripts/python.exe`があるか
- checkpointとcodecが`runtime/models/irodori/`にあるか
- `runtime/models/irodori/tokenizers/llm-jp-3-150m/`に`tokenizer.json`と`tokenizer_config.json`があるか
- 起動時の「○○がありません」に表示された配置先を確認
- `GET /health/deep`の`modelChecks.irodori_v3`を確認
- `runtime/logs/local-tts-service.err.log`のIrodori workerエラーを確認
- `runtime/logs/irodori-worker.log`の終了コードとworker標準エラーを確認

生成ボタンを押した時に401やHugging Faceへの接続が出るのは正常ではありません。通常起動・生成は完全ローカルで動作し、認証トークンを必要としません。

生成の間にIrodori workerが終了していた場合、次の生成要求で1回自動的にworkerとモデルを再準備します。RVC診断の`partialResult.stage`が`tts`、`rvcStarted`が`false`の場合は、RVC変換ではなく前段の`POST /v1/speak`が最初の失敗です。

Windowsイベントログに`nvlddmkm`エラーが繰り返し記録され、`nvidia-smi`も初期化できない場合は、モデルやRVC設定ではなくNVIDIAドライバ側の状態を先に復旧してください。worker再起動にも失敗する状態ではWindows再起動後に再確認します。

## chunk 結合がおかしい

- `runtime/audio/chunks/<requestId>/` に chunk が出ているか
- `chunking.pauseBetweenChunksMs` の値が大きすぎないか

長文分割の通常操作は、通常生成・モデル比較・RVC変換にあるツールチップを確認してください。

## 参照音声を登録できない

### 音声ファイルを選べない・登録ボタンが有効にならない

- 対応形式は wav / mp3 / m4a / flac / ogg / aac です。
- 参照音声名は半角英数字・`_`・`-`のみ、80文字以内です。
- 同じ参照音声名は上書きできません。別名を入力してください。
- 音声内で実際に話している文章を入力してください。
- ブラウザへ絶対パスを入力する方式ではなく、ファイル選択ボタンを使ってください。

### 「WAVへ変換できませんでした」「音声の長さを確認できませんでした」

- 空ファイルや壊れたファイルでないか、通常の音楽プレーヤーで再生できるか確認してください。
- 拡張子だけを変更したファイルは使えません。元の形式のまま選び直してください。
- `runtime/tools/ffmpeg/`または設定済みFFmpegが利用できるか確認してください。
- 失敗時は不完全な `reference/voices/<voiceId>/` を残さない設計です。同名を再利用できない場合は、既存フォルダに手動配置したファイルがないか確認してください。

### 3〜10秒の範囲外という警告が出る

登録自体は禁止されません。GPT-SoVITSでは3〜10秒が推奨範囲ですが、別の音声クローンモデルでは利用できる場合があります。品質を上げる場合は、1人がはっきり話し、BGM・反響・ノイズが少ない区間へ切り出してください。

### 登録した音声を通常生成で使えない

登録完了後の `通常生成で使う` を押すと音声は選択されます。現在のTTSモデルが参照音声非対応の場合は、画面の案内に従って音声クローン対応モデルへ変更してください。選択肢に出ない場合は `参照音声` → `登録済み音声`でアーカイブ状態を確認し、再読込してください。

### 登録済み文章を修正したい・音声を一時的に隠したい

`参照音声` → `登録済み音声`を開きます。音声を選択すると、プレビュー、`voice.txt`の文章修正、アーカイブと復元を行えます。アーカイブしても `voice.wav` と `voice.txt` は削除されません。

## YouTube候補の文字起こしがおかしい

- YouTube自動字幕のローリング表示による同一文の繰り返しは、候補作成時に除去します。
- 字幕そのものが誤っている場合は、候補カードの文字起こしを聞こえた内容へ修正してから登録してください。
- 文字起こし欄は内容に合わせて縦へ自動拡張します。古い表示が残る場合はブラウザを再読み込みしてください。
- 字幕がない場合やHTTP 429などで字幕取得に失敗した場合は、音声取得をやり直さずfaster-whisperへ自動で切り替わります。GPUが使えない環境ではCPU処理となり、時間がかかります。
- 元音声とBGM・伴奏除去後の音声を聴き比べ、声が欠ける場合は元音声を使ってください。
- 自分が権利を持つ動画、または音声の利用・加工について明確な許可がある動画だけを使用してください。

## VoiceDesign 追記

- `irodori_v3_voicedesign` 失敗時は helper の traceback までエラー本文に含めて返します。
- 参照テキスト必須で `voice.txt` / `text.txt` が両方無い場合は `missing: voice.txt or text.txt` を返します。
- caption が本文読み上げに混ざる `merged_input` は使わず、今回の成功モードは `separate_target` のみです。

## Refactored diagnostics

Inspect browser diagnostics, then the Node proxy, then the Python API. RVC configuration resolution is in `frontend/server/rvc/config.js`, boundary errors in `validation.js`, and synthesis errors in `src/local_tts_service/synthesis/`. Before cleaning artifacts, run `scripts/cleanup-runtime-artifacts.ps1` without `-Apply` and confirm every candidate is an old file below `runtime/`.
