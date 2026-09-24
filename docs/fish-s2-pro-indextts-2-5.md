# Fish Audio S2 Pro / IndexTTS 2.5（任意導入）

両モデルは既存のFish S1-mini、Irodori、Qwen環境とは別のWSL専用venv・モデルディレクトリで起動する。通常の初回セットアップでは大容量モデルを自動取得しない。ブラウザの通常生成とモデル比較には常に表示し、未導入なら選択不可として診断理由を示す。

| モデルID | 重み | 参照音声 | 参照書き起こし | 環境 |
| --- | --- | --- | --- | --- |
| `fish_s2_pro` | `fishaudio/s2-pro` | 必須 | 必須、音声の内容と一致 | Python 3.12、WSL CUDA 12.8 |
| `indextts_2_5` | `IndexTeam/IndexTTS-2.5` | 必須 | 不要 | Python 3.11、WSL CUDA |

## 必要条件

Fish S2 Proの公式推論ガイドは**24GB以上のVRAMを推奨**する。16GB以下のGPUで推論できると仮定して導入成功扱いにしない。IndexTTS 2.5はBF16とネイティブ話速制御（duration factor=1/speedScale、対応範囲0.5～2）を使い、モデルがCUDA非対応ならCPUへ黙ってフォールバックせず理由を返す。

公式上流リポジトリとHugging Faceのモデルrevisionをセットアップスクリプトで固定。モデルごとにvenv・vendor・重み・manifestを分ける。

## 利用条件

### Fish Audio S2 Pro

- ライセンス: **Fish Audio Research License**（2026-03-07更新）。
- 研究・非商用利用はライセンス条件に従って利用できる。
- **商用利用はFish Audioとの別途書面ライセンスが必要**。通常ライセンスだけでは商用権は付与されない。
- モデルや派生物、モデルを使う製品・サービスを第三者へ配布・提供する場合は、ライセンスの提供、NOTICEの保持、関連UIや文書等での `Built with Fish Audio` 表示などが必要。
- モデル・派生物・生成結果にはFish Audio Acceptable Use Policyも適用され、基盤生成AIモデルの作成・改善への利用には制限がある。
- Fish Audioとの関係では、適用法が認める範囲で生成物は利用者に帰属するとライセンスに記載されている。
- 公式: https://huggingface.co/fishaudio/s2-pro/blob/main/LICENSE.md

### IndexTTS 2.5

- ライセンス: **bilibili Model Use License Agreement**。
- 条件に従い、世界的・非独占・譲渡不可・ロイヤリティフリーの限定ライセンスが付与される。
- 自社または関連会社の製品・サービスが前月 **1億MAU超**、または前年売上が **10億人民元超** の場合は、bilibiliから別途書面ライセンスを得るまで本ライセンス上の権利を行使できない。
- 再配布時は元の著作権表示とライセンスを保持し、下流利用者にも条件を課す必要がある。派生物の配布には元権利者が変更内容を保証しない旨の表示も必要。
- 第三者データ・重みの権利、適用法、プライバシー等は利用者側で確認する。医療診断、自動運転、軍事、重要インフラ、大規模生体監視、自動与信・採用判断などの高リスク用途には追加の遵守義務がある。
- IndexTTS 2.5や派生物を他のAIモデル改善へ使うことにも制限がある。
- 公式: https://github.com/index-tts/index-tts/blob/main/LICENSE

第三者の声を本人の同意なく複製・なりすまし用途へ使用しない。モデルのライセンスだけで、参照音声・人物の声・生成物に含まれる第三者権利が自動的に許諾されるわけではない。

## 任意導入

```powershell
.\scripts\setup-wsl-tts-models.ps1 -Model indextts_2_5
.\scripts\setup-wsl-tts-models.ps1 -Model fish_s2_pro
```

現環境を壊さず追加し、通常の `-Model all` では上記の大容量モデルを取得しない。生成時も1モデルずつ実行し、他のGPU使用中の作業と同時に実行しない。

## 実生成の確認

```powershell
.\scripts\check-wsl-tts.ps1 -Model indextts_2_5
.\scripts\check-wsl-tts.ps1 -Model fish_s2_pro
.\scripts\verify-wsl-tts-models.ps1 -Model indextts_2_5,fish_s2_pro
# 複数GPU環境で空いているGPUを選ぶ場合（例: CUDA番号1）
.\scripts\verify-wsl-tts-models.ps1 -Model indextts_2_5 -VoiceId sakura_01 -CudaVisibleDevices 1
```

既存の `reference/voices/<id>/voice.wav` を選択して `/v1/speak` を呼ぶ。Fishのみ `voice.txt` が必須。実生成は新規WAVの生成時間、長さ、チャンネル、RMS、無音率、SHA-256を `runtime/audio/model-smoke/manifest.json` に記録する。可能なら音声を実際に聴くかASRで本文の一致も確認する。WAVができただけでは品質保証としない。

## 既存モデルを守る

Fish S1-miniの公式コードrevision、venv、重みを上書きしない。既存の登録済み参照音声、通常生成、モデル比較、履歴、RVC、Irodori既定値はそのまま維持する。
