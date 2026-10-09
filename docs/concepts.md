# 用語整理

## local-tts-service

- 他リポジトリや付属frontendから呼ぶ共通TTS APIです。
- 主な入口は`POST /v1/speak`と`model`指定です。

## model

- API利用者が選ぶ音声生成方式です。
- 例: `irodori_v3`、`irodori_v3_voicedesign`、`qwen3_tts_clone_1_7b`、`mock`。
- 各modelは`models.<model>.runtime`で実行基盤へ割り当てられます。

## runtime

- modelを実際に動かす実装です。
- 標準経路は`irodori_voicedesign_direct`、`qwen3_tts`、`external_cli`です。
- `mock_wav`はテスト用です。
- `comfyui`と`comfyui_voxcpm2`はVoxCPM2互換などを追加する場合だけ使う任意runtimeで、標準設定・通常起動では使用しません。

## optional external service

- 通常のバックエンドとfrontend以外に、明示的に追加する実行サービスです。
- ComfyUIは、対応modelが設定され、かつ`externalServices.comfyui.enabled=true`の場合だけ起動・確認します。
- GPT-SoVITSは`externalServices.gptSovits.enabled=true`の場合だけ起動します。vendorフォルダが存在するだけでは有効になりません。

## reference/

- `reference/voices/`は参照音声と対応文章を管理します。
- `reference/workflows/`は任意のworkflow互換機能で使う公開定義です。Irodoriの標準経路はworkflowを使いません。

## frontend

- 手動生成、比較、参照音声管理、RVC変換を行う付属UIです。
- `local-tts.bat`は初回セットアップの要否を判定し、必要な場合はセットアップ後に、準備済みの場合はそのままバックエンドとfrontendを起動します。
- frontendだけを個別に確認する場合は`scripts/start-tts-frontend.ps1`を使います。
