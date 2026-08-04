(() => {
  const MODEL_LABELS = {
    irodori_v4_small: "Irodori v4 Small",
    irodori_v3: "Irodori v3",
    irodori_v3_voicedesign: "Irodori v3 VoiceDesign",
    irodori_v2: "Irodori v2",
    f5_tts_zero_shot: "F5-TTS Zero-shot",
    gpt_sovits_zero_shot: "GPT-SoVITS Zero-shot",
    gpt_sovits_finetuned: "GPT-SoVITS Fine-tuned",
    qwen3_tts_clone_0_6b: "Qwen3-TTS Clone 0.6B",
    qwen3_tts_clone_1_7b: "Qwen 1.7B",
    sarashina2_2_tts: "Sarashina2.2-TTS",
    fireredtts2: "FireRedTTS-2",
    t5gemma_tts_2b_2b: "T5Gemma-TTS 2B-2B",
    fish_s1_mini: "FishAudio S1-mini",
    chatterbox_multilingual_v3: "Chatterbox Multilingual V3",
    fun_cosyvoice3_0_5b: "Fun-CosyVoice 3.0 0.5B",
    mock: "Mock WAV",
  };

  const MODEL_PROFILE = {
    irodori_v4_small: {
      badges: ["最新版", "公式v4", "約0.8B"],
      description: "声寄せと話し方指定を1つに統合した公式Irodori v4。Smallは公式モデル名で、約7.66億パラメータの通常版です。",
      features: ["参照音声による声寄せ", "話し方メモによる感情・スタイル指定", "参照音声なしでも生成可能", "本文中の絵文字による表現調整", "最大120秒の参照音声に対応"],
      scores: { 自然さ: "高", 感情表現: "高", 安定性: "高" },
      memo: "量子化版ではない公式チェックポイントです。短い参照1本でも使えますが、声寄せは30秒程度以上のきれいな参照音声で安定しやすくなります。",
      rankReason: "声寄せと表現制御を1モデルで扱え、Irodori系の第一候補です。",
      baseScore: 98,
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
      memo: "Qwen 1.7B の出力確認用です。参照音声との近さとノイズ感を他モデルと比較してください。",
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

  const DESIRED_MODELS = [
    "irodori_v4_small",
    "chatterbox_multilingual_v3",
    "fun_cosyvoice3_0_5b",
    "gpt_sovits_zero_shot",
    "qwen3_tts_clone_1_7b",
    "irodori_v3_voicedesign",
    "irodori_v3",
    "sarashina2_2_tts",
    "fireredtts2",
    "t5gemma_tts_2b_2b",
    "fish_s1_mini",
  ];

  function modelIsAvailable(model) {
    return Boolean(model && model.available && model.enabled);
  }

  function sortModelsAvailableFirst(models, availability = modelIsAvailable) {
    return Array.from(models || [])
      .map((model, index) => ({ model, index, available: Boolean(availability(model)) }))
      .sort((a, b) => Number(b.available) - Number(a.available) || a.index - b.index)
      .map((entry) => entry.model);
  }

  function modelLabel(id, fallback = "") {
    return MODEL_LABELS[id] || fallback || id || "Unknown";
  }

  function profileFor(id) {
    return MODEL_PROFILE[id] || {
      badges: ["TTS", "生成"],
      description: "登録済みのTTSモデルです。",
      features: ["利用可能なモデル", "用途に応じて比較可能", "ローカル生成に対応"],
      scores: { 自然さ: "中", 感情表現: "中", 安定性: "中" },
      memo: "生成結果を再生して確認してください。",
      rankReason: "生成結果を聞いて判断してください。",
      baseScore: 60,
    };
  }

  window.LocalTtsModelCatalog = Object.freeze({
    MODEL_LABELS,
    MODEL_PROFILE,
    DESIRED_MODELS,
    modelIsAvailable,
    sortModelsAvailableFirst,
    modelLabel,
    profileFor,
  });
})();
