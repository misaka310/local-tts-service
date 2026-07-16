# セキュリティ

## 基本
- デフォルト host は `127.0.0.1`
- 外部公開を前提にしない
- ローカル開発用途を前提

## CORS
- 初期値: `http://127.0.0.1`, `http://localhost`
- 必要最小限の origin のみ許可
- 例（本リポジトリfrontend）:
  - `http://127.0.0.1:5177`
  - `http://localhost:5177`
- `*` 常時許可は非推奨

## `/audio/{filename}`
- ファイル名のみ許可
- `../` などのディレクトリ移動を拒否
- 英数字/記号（`._-`）のみ許可

## Git 管理除外
- `config/config.local.json`
- `runtime/`
- `reference/`
- `*.wav`, `*.mp3`, `*.flac`
- `*.safetensors` などモデル重み

## プロセス終了
- 通常起動では、この起動のWindows Job Objectに入れたプロセスと、`runtime/processes/`のPID、起動時刻、コマンド識別情報、リポジトリパス、起動セッションが一致するプロセスだけを終了
- 同じポートを使用する無関係なプロセスは終了せず、ポート使用中として起動を中断
- `kill-tts-stack-ports.ps1` は通常起動から呼ばれない手動緊急用であり、実行すると指定ポートの所有プロセスを強制終了する

## 音声素材
- 参照音声、学習音声、声質変換モデルは本人同意または適切な利用権限がある素材だけを使用
- `reference/`、`runtime/`、`data/source_audio/` は公開しない
- 公開前に `scripts/audit-public-history.ps1` で現在ファイルとGit履歴を検査

## 運用上の注意
- 外部公開時は認証・アクセス制御を別途導入
- `publicBaseUrl` を外部URLにする場合は公開面が広がる
