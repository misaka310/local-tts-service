(() => {
  const MODEL_LABELS = {
    irodori_v4_1_small: "Irodori v4.1 Small",
    irodori_v4_1_anime: "Irodori v4.1 Anime",
    irodori_v4_small: "Irodori v4 Small",
    irodori_v3: "Irodori v3",
    irodori_v3_low_latency: "Irodori v3 低遅延 (8-step)",
    irodori_v3_voicedesign: "Irodori v3 VoiceDesign",
    irodori_v2: "Irodori v2",
    f5_tts_zero_shot: "F5-TTS Zero-shot",
    gpt_sovits_zero_shot: "GPT-SoVITS Zero-shot",
    gpt_sovits_finetuned: "GPT-SoVITS Fine-tuned",
    qwen3_tts_clone_0_6b: "Qwen3-TTS Clone 0.6B",
    qwen3_tts_clone_1_7b: "Qwen3-TTS Clone 1.7B",
    sarashina2_2_tts: "Sarashina2.2-TTS",
    fireredtts2: "FireRedTTS-2",
    t5gemma_tts_2b_2b: "T5Gemma-TTS 2B-2B",
    fish_s1_mini: "FishAudio S1-mini",
    fish_s2_pro: "Fish Audio S2 Pro",
    indextts_2_5: "IndexTTS 2.5",
    orpheus_3b_asmr: "Orpheus 3B ASMR",
    ming_omni_tts_0_5b: "Ming Omni TTS 0.5B",
    chatterbox_multilingual_v3: "Chatterbox Multilingual V3",
    fun_cosyvoice3_0_5b: "Fun-CosyVoice 3.0 0.5B",
    mock: "Mock WAV",
  };

  const MODEL_PROFILE = {
    irodori_v4_1_small: {
      badges: ["v4.1", "公式", "約0.8B"],
      description: "公式Irodori v4.1 Small。v4の統合型モデルを引き継ぎ、Duration Predictorが改善されています。",
      features: ["参照音声による声寄せ", "話し方メモによるスタイル指定", "参照音声なしのVoiceDesign", "本文中の絵文字による表現調整", "最大120秒の参照音声に対応"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "高" },
      memo: "公式v4.1の通常版です。声寄せと話し方指定を同じモデルで比較できます。",
      rankReason: "現行Irodoriの標準モデルとして、自然さ・声寄せ・表現制御をまとめて確認できます。",
      baseScore: 99,
    },
    irodori_v4_1_anime: {
      badges: ["v4.1", "Anime FT", "日本語"],
      description: "Irodori v4.1 Smallをアニメ調の日本語音声でfine-tuneした派生モデルです。",
      features: ["アニメ調の日本語音声", "参照音声による声寄せ", "話し方メモによるスタイル指定", "参照音声なしのVoiceDesign", "絵文字による表現調整"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "中〜高" },
      memo: "captionや絵文字の効き方は公式v4.1と異なる場合があります。同じ文章・参照音声で聞き比べてください。",
      rankReason: "公式v4.1と同じ条件で、アニメ調fine-tuneによる声質・表現の差を比較できます。",
      baseScore: 98,
    },
    irodori_v4_small: {
      badges: ["公式v4", "旧版", "約0.8B"],
      description: "声寄せと話し方指定を1つに統合した公式Irodori v4。v4.1との比較用に残しています。",
      features: ["参照音声による声寄せ", "話し方メモによる感情・スタイル指定", "参照音声なしでは話し方メモから生成", "本文中の絵文字による表現調整", "最大120秒の参照音声に対応"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "高" },
      memo: "旧v4チェックポイントです。通常利用はv4.1 Smallを優先してください。",
      rankReason: "v4.1との比較や既存生成条件の再現に利用できます。",
      baseScore: 96,
    },
    irodori_v3: {
      badges: ["感情表現強化", "自然さ向上", "長文向け"],
      description: "自然さと安定性を重視した定番モデル。本文中の絵文字で感情表現を寄せられます。",
      features: ["自然で聞き取りやすい音質", "絵文字入り本文で感情を寄せられる", "感情表現が豊かで抑揚が自然", "長文でも安定した生成品質", "参照音声の再現性が高い"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "高" },
      memo: "自然で聞き取りやすい。感情の起伏が穏やかで、全体的なバランスが良い。",
      rankReason: "自然で表現力が高く、全体のバランスが最も優れています。",
      baseScore: 96,
    },
    irodori_v3_low_latency: {
      badges: ["低遅延", "8-step", "実験"],
      description: "Irodori v3を8-step・sway・参照latentキャッシュで動かす低遅延モデルです。通常版とは別に選べます。",
      features: ["ウォーム後の短文生成を高速化", "参照音声のlatentを再利用", "Irodori v3と同じチェックポイントを使用", "通常版Irodori v3へいつでも切り替え可能"],
      scores: { 自然さ: "中〜高", 感情表現: "高", 安定性: "中" },
      memo: "文章によっては通常版より発音の安定性が下がる可能性があります。初回はモデル読込と参照キャッシュ作成の時間が加わります。",
      rankReason: "返答速度を優先する短文読み上げに向いています。音質や長文安定性を優先する場合は通常版を選んでください。",
      baseScore: 91,
    },
    gpt_sovits_zero_shot: {
      badges: ["高品質", "自然さ重視", "多言語対応"],
      description: "参照音声への寄せを重視したい時に使いやすい総合型モデル。",
      features: ["参照音声との一致度が高い", "自然さと感情表現のバランスが良い", "日本語と多言語の用途に対応", "声質確認に向いている"],
      scores: { 自然さ: "高", 感情表現: "中", 安定性: "高" },
      memo: "参照音声との一致度が高く、発音も安定している。声質の確認に向いています。",
      rankReason: "安定性と自然さのバランスが良く、汎用性が高いです。",
      baseScore: 90,
    },
    qwen3_tts_clone_1_7b: {
      badges: ["1.7B", "参照音声", "比較用"],
      description: "参照音声を使って声質を近づける1.7Bモデル。ほかのモデルと再現性や自然さを聞き比べられます。",
      features: ["参照音声を使った音声クローンに対応", "Qwen系モデルの声質を比較できる", "同一条件で他モデルと聞き比べやすい", "F5-TTSの代替比較枠"],
      scores: { 自然さ: "中", 感情表現: "中", 安定性: "中" },
      memo: "Qwen3-TTS Clone 1.7B の出力確認用です。参照音声との近さとノイズ感を他モデルと比較してください。",
      rankReason: "Qwen系の声質確認枠として、他モデルとの差を見やすいです。",
      baseScore: 82,
    },
    irodori_v3_voicedesign: {
      badges: ["VoiceDesign", "Irodori v3", "参照音声"],
      description: "参照音声と話し方メモを組み合わせ、声質と感情表現を細かく調整できるIrodoriモデルです。",
      features: ["Irodori v3系の別プロファイル", "本文中の絵文字で感情を寄せられる", "参照音声ありで比較可能", "通常のIrodori v3との差を確認しやすい", "モデル比較の固定候補"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "中" },
      memo: "Irodori v3 VoiceDesign の比較枠です。通常のIrodori v3との差を確認してください。",
      rankReason: "Irodori v3系のVoiceDesign枠として、通常v3との差分確認に向いています。",
      baseScore: 88,
    },
    f5_tts_zero_shot: {
      badges: ["高速生成", "安定性重視", "低リソース"],
      description: "非常に高速で安定した生成が可能。大量生成や比較用の基準音声に向きます。",
      features: ["生成が速い", "安定性が高い", "長文でも破綻しにくい", "比較用の基準として使いやすい"],
      scores: { 自然さ: "中", 感情表現: "中", 安定性: "高" },
      memo: "非常に高速で安定しています。表現力よりも実用性を優先したい時に向いています。",
      rankReason: "速度と安定性に優れ、実用性が非常に高いモデルです。",
      baseScore: 84,
    },
    irodori_v2: {
      badges: ["感情表現", "繊細な表現", "日本語特化"],
      description: "感情表現に優れた旧版。短い台詞や比較用途で確認しやすいモデル。",
      features: ["感情表現が強い", "短い文章で映えやすい", "日本語向け", "v3との比較に便利"],
      scores: { 自然さ: "中", 感情表現: "高", 安定性: "中" },
      memo: "感情表現は良いですが、長文では一部つなぎが不自然になる可能性があります。",
      rankReason: "表現力は優れるものの、長文での安定性に課題があります。",
      baseScore: 76,
    },
    fish_s2_pro: {
      badges: ["S2 Pro", "参照音声", "商用は別契約", "Fish Audio Research License"],
      description: "Fish Audioの高品質S2 Pro。専用環境で参照WAVと書き起こしを使います。",
      features: ["日本語の声寄せ", "参照音声と文字起こし", "S1-miniと分離した導入"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "実験" },
      memo: "公式推奨VRAMは24GB以上。足りない場合は選択できない状態で理由を表示します。",
      rankReason: "既存モデルとの実音声比較用です。",
      baseScore: 90,
    },
    indextts_2_5: {
      badges: ["日本語", "参照音声", "条件付き商用", "bilibili Model License"],
      description: "参照WAVのみで日本語の声寄せができるIndexTTS 2.5。",
      features: ["日本語・英語など5言語", "文字起こし不要", "エンジン標準の話速調整"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "実験" },
      memo: "参照音声を登録すれば、文字起こしなしで生成できます。",
      rankReason: "同じ参照WAVでの声寄せ比較用です。",
      baseScore: 89,
    },
    orpheus_3b_asmr: {
      badges: ["ASMR追加学習", "英語", "要確認", "派生元条件あり"],
      description: "ASMR音声で追加学習されたOrpheus 3B。小さく柔らかい話し方を狙う英語向けの実験モデルです。",
      features: ["ASMRデータで追加学習", "soft-spoken / gentle speech向け", "本文中の<sigh>などの表現タグ", "WSLの専用環境でローカル生成"],
      scores: { 自然さ: "中〜高", 感情表現: "高", 安定性: "実験" },
      memo: "30では上流で安定している既存voiceを使います。モデル作者も真のwhisper再現は未達と明記しているため、完全な囁き専用モデルとしては扱いません。",
      rankReason: "ASMRデータで追加学習されたモデルを直接比較したい場合の専用枠です。",
      baseScore: 80,
    },
    ming_omni_tts_0_5b: {
      badges: ["ASMR指示", "参照音声", "商用利用可", "Apache-2.0"],
      description: "話し方メモだけでASMR声を設計でき、参照音声を選べばその声へ寄せながらstyle指示も同時に使えるMing Omni TTS 0.5Bです。",
      features: ["参照音声なしのASMR voice design", "任意の参照音声によるzero-shot voice clone", "ASMR・音量・感情などのstyle指定", "WSLの専用環境でローカル生成"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "中" },
      memo: "ASMR風では「非常に小さな声、近接マイク、ゆっくり、息を多め」などを話し方メモに入れます。声を寄せたいときだけ参照音声を選んでください。",
      rankReason: "ASMR系の自然言語スタイル指示を単独でも声寄せと併用でも使えるのが強みです。",
      baseScore: 92,
    },
    chatterbox_multilingual_v3: {
      badges: ["Multilingual V3", "日本語", "MIT"],
      description: "参照音声の声質を使いながら、表現強度で感情の出方を調整できる多言語モデルです。",
      features: ["日本語を含む23言語", "短い参照音声による声寄せ", "表現強度の調整", "Windows上のCUDAで完全ローカル生成"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "高" },
      memo: "日本語の感情豊かな短い台詞を試す第一候補です。表現強度は上げすぎると誇張が強くなります。",
      rankReason: "日本語対応・感情制御・16GB VRAMでの実行可能性を両立します。",
      baseScore: 97,
    },
    fun_cosyvoice3_0_5b: {
      badges: ["日本語", "感情指示", "Apache-2.0"],
      description: "日本語の通常入力を内部でカタカナへ正規化し、参照音声と感情指示を使って生成する多言語TTSです。",
      features: ["日本語を含む9言語", "参照音声による声寄せ", "喜び・悲しみ・怒り・話速などの指示", "Windowsの分離環境で完全ローカル生成"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "高" },
      memo: "日本語本文は内部変換されます。固有名詞の読みが重要な場合はカタカナ表記にすると安定します。",
      rankReason: "日本語と感情指示に対応し、Chatterboxとは異なる制御方式で比較できます。",
      baseScore: 96,
    },
  };

  const MODEL_METADATA = {
    irodori_v4_1_small: { licenseGroup: "irodori_v4_1_small", commercialStatus: "商用可", license: "MIT + 公式Ethical Restrictions", commercial: "MIT上は商用利用可。声の無断模倣・なりすまし・誤情報用途は禁止", termsUrl: "https://huggingface.co/Aratako/Irodori-TTS-v4.1-Small/blob/main/README.md", modelUrl: "https://huggingface.co/Aratako/Irodori-TTS-v4.1-Small", codeUrl: "https://github.com/Aratako/Irodori-TTS", languages: "日本語", reference: "参照音声は任意。Voice Designにも対応" },
    irodori_v4_1_anime: { licenseGroup: "irodori_v4_1_anime", commercialStatus: "商用可", license: "MIT + Irodori Ethical Restrictions", commercial: "MIT上は商用利用可。ベースモデルと同じ倫理制限を遵守", termsUrl: "https://huggingface.co/phasefield-audio/Irodori-TTS-v4.1-Anime/blob/main/README.md", modelUrl: "https://huggingface.co/phasefield-audio/Irodori-TTS-v4.1-Anime", codeUrl: "https://github.com/Aratako/Irodori-TTS", languages: "日本語", reference: "参照音声は任意。Anime fine-tune" },
    irodori_v4_small: { licenseGroup: "irodori_v4_small", commercialStatus: "商用可", license: "MIT + 公式Ethical Restrictions", commercial: "MIT上は商用利用可。声の無断模倣・なりすまし・誤情報用途は禁止", termsUrl: "https://huggingface.co/Aratako/Irodori-TTS-v4-Small", modelUrl: "https://huggingface.co/Aratako/Irodori-TTS-v4-Small", codeUrl: "https://github.com/Aratako/Irodori-TTS", languages: "日本語", reference: "参照音声は任意。Voice Designにも対応" },
    irodori_v3: { licenseGroup: "irodori_v3", commercialStatus: "商用可", license: "MIT + 公式Ethical Restrictions", commercial: "MIT上は商用利用可。声の無断模倣・なりすまし・誤情報用途は禁止", termsUrl: "https://huggingface.co/Aratako/Irodori-TTS-500M-v3", modelUrl: "https://huggingface.co/Aratako/Irodori-TTS-500M-v3", codeUrl: "https://github.com/Aratako/Irodori-TTS", languages: "日本語", reference: "参照音声は任意" },
    irodori_v3_low_latency: { licenseGroup: "irodori_v3", commercialStatus: "商用可", license: "MIT + 公式Ethical Restrictions", commercial: "MIT上は商用利用可。声の無断模倣・なりすまし・誤情報用途は禁止", termsUrl: "https://huggingface.co/Aratako/Irodori-TTS-500M-v3", modelUrl: "https://huggingface.co/Aratako/Irodori-TTS-500M-v3", codeUrl: "https://github.com/Aratako/Irodori-TTS", languages: "日本語", reference: "参照音声は任意。30独自の8-step低遅延実行プロファイル" },
    irodori_v3_voicedesign: { licenseGroup: "irodori_v3_voicedesign", commercialStatus: "商用可", license: "MIT + 公式Ethical Restrictions", commercial: "MIT上は商用利用可。声の無断模倣・なりすまし・誤情報用途は禁止", termsUrl: "https://huggingface.co/Aratako/Irodori-TTS-600M-v3-VoiceDesign/blob/main/README.md", modelUrl: "https://huggingface.co/Aratako/Irodori-TTS-600M-v3-VoiceDesign", codeUrl: "https://github.com/Aratako/Irodori-TTS", languages: "日本語", reference: "参照音声は任意。Caption/Voice Design対応" },
    irodori_v2: { licenseGroup: "irodori_v2", commercialStatus: "商用可", license: "MIT", commercial: "MIT上は商用利用可。参照音声・生成物の第三者権利は別途確認", termsUrl: "https://huggingface.co/Aratako/Irodori-TTS-500M-v2", modelUrl: "https://huggingface.co/Aratako/Irodori-TTS-500M-v2", codeUrl: "https://github.com/Aratako/Irodori-TTS", languages: "日本語", reference: "参照音声は任意" },
    qwen3_tts_clone_0_6b: { licenseGroup: "qwen3_tts_clone_0_6b", commercialStatus: "商用可", license: "Apache-2.0", commercial: "Apache-2.0の条件で商用利用可。参照音声の権利は別途必要", termsUrl: "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base", modelUrl: "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base", codeUrl: "https://github.com/QwenLM/Qwen3-TTS", languages: "日本語を含む多言語", reference: "voice.wav + voice.txtが必須" },
    qwen3_tts_clone_1_7b: { licenseGroup: "qwen3_tts_clone_1_7b", commercialStatus: "商用可", license: "Apache-2.0", commercial: "Apache-2.0の条件で商用利用可。参照音声の権利は別途必要", termsUrl: "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base", modelUrl: "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base", codeUrl: "https://github.com/QwenLM/Qwen3-TTS", languages: "日本語を含む多言語", reference: "voice.wav + voice.txtが必須" },
    sarashina2_2_tts: { licenseGroup: "sarashina2_2_tts", commercialStatus: "非商用", license: "Sarashina Model NonCommercial License Agreement v2.0", commercial: "標準ライセンスでは商用利用不可", termsUrl: "https://huggingface.co/sbintuitions/sarashina2.2-tts/blob/main/LICENSE", modelUrl: "https://huggingface.co/sbintuitions/sarashina2.2-tts", codeUrl: "https://github.com/sbintuitions/sarashina2.2-tts", languages: "日本語・英語", reference: "voice.wav + voice.txtが必須" },
    fireredtts2: { licenseGroup: "fireredtts2", commercialStatus: "商用可", license: "Apache-2.0", commercial: "Apache-2.0の条件で商用利用可。声・入力素材の権利は別途確認", termsUrl: "https://github.com/FireRedTeam/FireRedTTS2/blob/main/LICENSE", modelUrl: "https://huggingface.co/FireRedTeam/FireRedTTS2", codeUrl: "https://github.com/FireRedTeam/FireRedTTS2", languages: "日本語・英語・中国語・韓国語・フランス語・ドイツ語・ロシア語等", reference: "voice.wav + voice.txtが必須" },
    t5gemma_tts_2b_2b: { licenseGroup: "t5gemma_tts_2b_2b", commercialStatus: "非商用", license: "Gemma Terms of Use + CC BY-NC 4.0", commercial: "非商用のみ。XCodec2もCC BY-NC条件", termsUrl: "https://huggingface.co/Aratako/T5Gemma-TTS-2b-2b/blob/main/README.md", modelUrl: "https://huggingface.co/Aratako/T5Gemma-TTS-2b-2b", codeUrl: "https://github.com/Aratako/T5Gemma-TTS", languages: "日本語", reference: "voice.wav + voice.txtが必須" },
    fish_s1_mini: { licenseGroup: "fish_s1_mini", commercialStatus: "非商用", license: "CC BY-NC-SA 4.0 + Hugging Faceゲート条件", commercial: "非商用。モデルページの追加条件・法令順守も必要", termsUrl: "https://huggingface.co/fishaudio/s1-mini", modelUrl: "https://huggingface.co/fishaudio/s1-mini", codeUrl: "https://github.com/fishaudio/fish-speech", languages: "日本語を含む13言語", reference: "voice.wav + voice.txtが必須" },
    fish_s2_pro: { licenseGroup: "fish_s2_pro", commercialStatus: "要別契約", license: "Fish Audio Research License", commercial: "商用利用はFish Audioとの別途書面ライセンスが必要", termsUrl: "https://huggingface.co/fishaudio/s2-pro/blob/main/LICENSE.md", modelUrl: "https://huggingface.co/fishaudio/s2-pro", codeUrl: "https://github.com/fishaudio/fish-speech", languages: "日本語を含む多言語", reference: "voice.wav + 内容一致のvoice.txtが必須", compute: "公式推論ガイドは24GB以上のVRAMを推奨。30ではRTX 5060 Ti 16GBで実生成確認済み", verification: "2026-09-24 参照音声付き実生成成功" },
    indextts_2_5: { licenseGroup: "indextts_2_5", commercialStatus: "条件付き", license: "bilibili Model Use License Agreement", commercial: "条件付き。1億MAU超または前年売上10億元超は別途ライセンスが必要", termsUrl: "https://github.com/index-tts/index-tts/blob/main/LICENSE", modelUrl: "https://huggingface.co/IndexTeam/IndexTTS-2.5", codeUrl: "https://github.com/index-tts/index-tts", languages: "日本語・英語・中国語・スペイン語・アラビア語", reference: "voice.wavが必須。voice.txtは不要", compute: "WSL CUDA + BF16。30ではRTX 5060 Ti 16GBで実生成確認済み", verification: "2026-09-24 参照音声付き実生成成功" },
    orpheus_3b_asmr: { licenseGroup: "orpheus_3b_asmr", commercialStatus: "要確認", license: "配布ページはApache-2.0表記 + 上流Llama 3.2系条件", commercial: "配布ページはApache-2.0表記。派生元のLlama 3.2系条件も確認が必要", termsUrl: "https://huggingface.co/nyuuzyou/Orpheus-3B-ASMR", modelUrl: "https://huggingface.co/nyuuzyou/Orpheus-3B-ASMR", codeUrl: "https://github.com/freddyaboulton/orpheus-cpp", languages: "英語", reference: "30ではpreset voiceを使用" },
    ming_omni_tts_0_5b: { licenseGroup: "ming_omni_tts_0_5b", commercialStatus: "商用可", license: "モデル Apache-2.0 / 公式コード MIT", commercial: "各ライセンス条件で商用利用可。入力音声・生成物の第三者権利は別途確認", termsUrl: "https://huggingface.co/inclusionAI/Ming-omni-tts-0.5B", modelUrl: "https://huggingface.co/inclusionAI/Ming-omni-tts-0.5B", codeUrl: "https://github.com/inclusionAI/Ming-omni-tts", languages: "中国語・英語中心", reference: "参照音声は任意。Voice Design/Clone対応" },
    chatterbox_multilingual_v3: { licenseGroup: "chatterbox_multilingual_v3", commercialStatus: "商用可", license: "MIT", commercial: "MITの条件で商用利用可。参照音声の権利は別途必要", termsUrl: "https://huggingface.co/ResembleAI/chatterbox", modelUrl: "https://huggingface.co/ResembleAI/chatterbox", codeUrl: "https://github.com/resemble-ai/chatterbox", languages: "日本語を含む23言語", reference: "voice.wavが必須" },
    fun_cosyvoice3_0_5b: { licenseGroup: "fun_cosyvoice3_0_5b", commercialStatus: "商用可", license: "Apache-2.0", commercial: "Apache-2.0の条件で商用利用可。モデルカード内のデモ素材等は別途権利確認", termsUrl: "https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512", modelUrl: "https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512", codeUrl: "https://github.com/FunAudioLLM/CosyVoice", languages: "日本語を含む9言語", reference: "voice.wavが必須。instruction対応" },
    f5_tts_zero_shot: { licenseGroup: "f5_tts_zero_shot", commercialStatus: "非商用", license: "モデル CC BY-NC 4.0 / コード MIT", commercial: "公式F5-TTS重みは非商用", termsUrl: "https://huggingface.co/SWivid/F5-TTS", modelUrl: "https://huggingface.co/SWivid/F5-TTS", codeUrl: "https://github.com/SWivid/F5-TTS", languages: "使用する重みに依存", reference: "voice.wav + voice.txtが必須" },
    gpt_sovits_zero_shot: { licenseGroup: "gpt_sovits", licenseLabel: "GPT-SoVITS", commercialStatus: "要確認", license: "コード MIT / 使用する重み・音声は個別条件", commercial: "コードはMIT。pretrained/追加重み・学習済み重み・参照音声の条件は個別確認", termsUrl: "https://github.com/RVC-Boss/GPT-SoVITS/blob/main/LICENSE", modelUrl: "https://github.com/RVC-Boss/GPT-SoVITS", codeUrl: "https://github.com/RVC-Boss/GPT-SoVITS", languages: "日本語を含む多言語", reference: "Zero-shot / Fine-tunedで参照条件が異なる" },
    gpt_sovits_finetuned: { licenseGroup: "gpt_sovits", licenseLabel: "GPT-SoVITS", commercialStatus: "要確認", license: "コード MIT / 使用する重み・音声は個別条件", commercial: "コードはMIT。pretrained/追加重み・学習済み重み・参照音声の条件は個別確認", termsUrl: "https://github.com/RVC-Boss/GPT-SoVITS/blob/main/LICENSE", modelUrl: "https://github.com/RVC-Boss/GPT-SoVITS", codeUrl: "https://github.com/RVC-Boss/GPT-SoVITS", languages: "日本語を含む多言語", reference: "Zero-shot / Fine-tunedで参照条件が異なる" },
  };

  const MODEL_ORDER = [
    "irodori_v4_1_small",
    "irodori_v4_1_anime",
    "irodori_v4_small",
    "irodori_v3",
    "irodori_v3_low_latency",
    "irodori_v3_voicedesign",
    "irodori_v2",
    "qwen3_tts_clone_1_7b",
    "qwen3_tts_clone_0_6b",
    "chatterbox_multilingual_v3",
    "fun_cosyvoice3_0_5b",
    "fireredtts2",
    "fish_s1_mini",
    "fish_s2_pro",
    "indextts_2_5",
    "ming_omni_tts_0_5b",
    "orpheus_3b_asmr",
    "sarashina2_2_tts",
    "t5gemma_tts_2b_2b",
    "gpt_sovits_zero_shot",
    "gpt_sovits_finetuned",
    "f5_tts_zero_shot",
    "mock",
  ];

  const DESIRED_MODELS = [
    "irodori_v4_1_small",
    "irodori_v4_1_anime",
    "irodori_v4_small",
    "irodori_v3",
    "irodori_v3_low_latency",
    "irodori_v3_voicedesign",
    "irodori_v2",
    "ming_omni_tts_0_5b",
    "orpheus_3b_asmr",
    "chatterbox_multilingual_v3",
    "fun_cosyvoice3_0_5b",
    "gpt_sovits_zero_shot",
    "qwen3_tts_clone_1_7b",
    "sarashina2_2_tts",
    "fireredtts2",
    "t5gemma_tts_2b_2b",
    "fish_s1_mini",
    "fish_s2_pro",
    "indextts_2_5",
  ];

  const MODEL_ORDER_INDEX = new Map(MODEL_ORDER.map((id, index) => [id, index]));

  function modelIsAvailable(model) {
    return Boolean(model && model.available && model.enabled);
  }

  function modelId(model) {
    return String((model && (model.id || model.model)) || "");
  }

  function sortModelsAvailableFirst(models, availability = modelIsAvailable) {
    return Array.from(models || [])
      .map((model, index) => ({
        model,
        index,
        id: modelId(model),
        rank: MODEL_ORDER_INDEX.get(modelId(model)),
        available: Boolean(availability(model)),
      }))
      .sort((a, b) => {
        const aKnown = Number.isInteger(a.rank);
        const bKnown = Number.isInteger(b.rank);
        if (aKnown && bKnown) return a.rank - b.rank;
        if (aKnown !== bKnown) return aKnown ? -1 : 1;
        return Number(b.available) - Number(a.available) || a.index - b.index;
      })
      .map((entry) => entry.model);
  }

  function modelLabel(id, fallback = "") {
    return MODEL_LABELS[id] || fallback || id || "Unknown";
  }

  function metadataFor(id) {
    return MODEL_METADATA[id] || null;
  }

  function profileFor(id) {
    const metadata = metadataFor(id);
    const profile = MODEL_PROFILE[id] || {
      badges: metadata ? [metadata.license] : ["TTS", "生成"],
      description: metadata ? `${metadata.languages}。 ${metadata.reference}` : "登録済みのTTSモデルです。",
      features: metadata ? [metadata.languages, metadata.reference, metadata.commercial] : ["利用可能なモデル", "用途に応じて比較可能", "ローカル生成に対応"],
      scores: { 自然さ: "中", 感情表現: "中", 安定性: "中" },
      memo: "生成結果を再生して確認してください。",
      rankReason: "生成結果を聞いて判断してください。",
      baseScore: 60,
    };
    if (!metadata) return profile;
    return { ...profile, metadata };
  }

  window.LocalTtsModelCatalog = Object.freeze({
    MODEL_LABELS,
    MODEL_PROFILE,
    MODEL_METADATA,
    MODEL_ORDER,
    DESIRED_MODELS,
    modelIsAvailable,
    sortModelsAvailableFirst,
    modelLabel,
    metadataFor,
    profileFor,
  });
})();
