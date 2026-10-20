# reference

このディレクトリは、公開可能なワークフロー定義と、利用者がローカルで追加する参照音声を分けて管理します。

- `workflows/`: API向けのComfyUIワークフロー定義。Git管理対象です。
- `voices/<voiceId>/voice.wav`: 利用者が権利を持つ参照音声。Git管理対象外です。
- `voices/<voiceId>/voice.txt`: `voice.wav`で実際に読まれている文章。Git管理対象外です。

参照音声は、本人の同意または適切な利用権限がある素材だけを使用してください。セットアップ時に `reference/voices/` は自動作成され、UIの「参照音声」タブから録音・登録できます。
