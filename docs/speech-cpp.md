# speech.cpp / audio.cpp backend

`speech_cpp` runtimeは、Irodori-TTS v3のGGUF版を`audiocpp_cli.exe`から実行するローカルbackendです。通常生成・参照音声・seed・話速を既存UI/APIからそのまま使えます。caption/VoiceDesign用途は従来の`irodori_voicedesign_direct`を使います。

## このPCでの採用判定

2026-10-12に、同じ文章・seed 1234・8-step・同じ参照音声で比較しました。

| backend | 生成条件 | 実生成時間 | 出力長 | 話者類似度(WavLM cosine) |
| --- | --- | ---: | ---: | ---: |
| 従来 `irodori_voicedesign_direct` | BF16 / reference latent cache hit | 19.58 s | 6.52 s | 0.898691 |
| `speech_cpp` | GGUF Q8_0 / CUDA / 8-step | 1.24 s | 6.36 s | 0.901168 |

`speech_cpp`のプロセス起動・モデル読込まで含めた1回のAPI実測は約6秒でした。従来backendは常駐workerのモデル読込後でも、今回の参照音声あり生成で約19.6秒でした。このPCの既定参照音声を使う通常用途では`speech_cpp`の方が速く、話者類似度も同等以上だったため、ローカル設定の`irodori_v3_low_latency`を`speech_cpp`へ切り替えています。

参照音声なしでは従来常駐workerが有利な場合があります。`irodori_v3`自体は従来backendのまま残してあるため、参照音声なしの最短レイテンシを優先する場合はそちらを選択できます。

## ローカル設定

```json
{
  "models": {
    "irodori_v3_low_latency": {
      "runtime": "speech_cpp",
      "runtimeOptions": {
        "numInferenceSteps": 8
      }
    }
  },
  "runtimes": {
    "speech_cpp": {
      "executable": "../_tools/speech.cpp/prebuilt/windows-cuda13.3/audiocpp_cli.exe",
      "modelPath": "../_tools/speech.cpp/models/Irodori-TTS-500M-v3-GGUF/irodori-tts-500m-v3-q8_0.gguf",
      "backend": "cuda",
      "device": 0,
      "timeoutSec": 1800
    }
  }
}
```

必要ファイルが見つからない場合、`/v1/models`ではモデルを削除せず`available=false`と不足パスを表示します。
