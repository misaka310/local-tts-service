# README動画の再制作ソース

2026年10月、GitHub添付URLが404になり、元動画とGit管理対象外だった制作フォルダを復元できなかったため、既知の構成を基に説明動画を再制作しました。

- `storyboard.json`: 新たに書いた14シーン・日本語台本（計123秒）
- `render_demo.py`: Pillow + FFmpegによるUIイメージ動画生成（Linux / Noto CJKフォント環境）
- `synthesize_narration.ps1`: Windows SAPI「Microsoft Haruka Desktop」による日本語ナレーション
- `combine_narration.py`: 14本のWAVをシーン時刻へ配置

## 再生成

1. Linux（またはWSL）でPillow・NumPy・FFmpeg・Noto CJKフォントを用意する
2. このディレクトリで `python render_demo.py` を実行し、字幕入り仮版MP4を生成
3. Windowsで `powershell -NoProfile -File synthesize_narration.ps1` を実行
4. Windowsで `python combine_narration.py` を実行（標準ライブラリのみ）
5. FFmpegで映像と日本語ナレーションを合成する：

```bash
ffmpeg -y -i local-tts-qwen3-1.7b-cat-rebuilt-preview.mp4 -i narration_timeline.wav \
  -filter_complex "[0:a]volume=0.18[bed];[1:a]volume=1.0[voice];[bed][voice]amix=inputs=2:duration=first:dropout_transition=0[a]" \
  -map 0:v:0 -map "[a]" -c:v copy -c:a aac -b:a 80k -movflags +faststart \
  local-tts-qwen3-1.7b-cat-rebuilt-narrated.mp4
```

音声の生成ではインストール済みの日本語音声が必要で、読み上げ速度はSAPIのRate=-1です。

## 再現できない部分

元のナレーターWAV、参照音声、実機キャプチャ、猫の元画像と台本全文は回収できていません。今回のUIは**操作を説明する再現イメージ**で、ソフトウェアを実際に操作した記録ではありません。音声モデルの性能実測として扱わないでください。
