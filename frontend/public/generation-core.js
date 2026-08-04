(function bootstrapGenerationCore(global) {
  "use strict";

  function normalizeSeed(value, fallback = 1) {
    const parsed = Number.parseInt(String(value ?? "").trim(), 10);
    return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : fallback;
  }

  function incrementSeed(value, enabled) {
    const current = normalizeSeed(value);
    return { value: enabled ? current + 1 : current, changed: Boolean(enabled) };
  }

  function normalizeChunkSettings(raw = {}) {
    const clamp = global.LocalTtsChunking?.clampInteger || ((value, fallback, min, max) => {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? Math.min(max, Math.max(min, Math.round(parsed))) : fallback;
    });
    const targetChars = clamp(raw.targetChars, 240, 80, 500);
    const hardMaxChars = clamp(raw.hardMaxChars, 500, Math.max(120, targetChars), 700);
    return {
      targetChars,
      hardMaxChars,
      chunking: {
        softChunkChars: targetChars,
        maxChunkChars: Math.min(hardMaxChars, Math.max(targetChars, Math.round(targetChars * 1.35))),
        hardLimitChars: hardMaxChars,
        pauseBetweenChunksMs: 250,
      },
    };
  }

  function normalizeStoredSettings(raw, allowedKeys = []) {
    const source = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
    return Object.fromEntries(allowedKeys.filter((key) => source[key] !== undefined).map((key) => [key, source[key]]));
  }

  function validateRequest({ model, voice, text, instruction }, capabilities, messages = {}, validators = {}) {
    if (!model) return messages.modelRequired || "model is required";
    if (model.available === false || model.enabled === false) return model.unavailableReason || messages.modelUnavailable || "model is unavailable";
    if (!String(text || "").trim()) return messages.textRequired || "text is required";
    if (capabilities.requiresReference(model) && !voice) return messages.referenceRequired || "reference voice is required";
    if (voice && capabilities.requiresReference(model) && model.requiresReferenceText && !voice.hasReferenceText) {
      return messages.referenceTextRequired || "reference text is required";
    }
    if (voice && typeof validators.validateVoice === "function") {
      const voiceError = String(validators.validateVoice(model, voice) || "").trim();
      if (voiceError) return voiceError;
    }
    if (capabilities.requiresInstruction(model, voice) && !String(instruction || "").trim()) {
      return messages.instructionRequired || "instruction is required";
    }
    return "";
  }

  function buildRequestBody({ model, voice, text, instruction, language, seed, controls = {} }, capabilities, getModelId) {
    const body = { text: String(text || "").trim(), model: getModelId(model), format: "wav" };
    if (voice && capabilities.supportsReference(model)) body.voiceId = voice.voiceId;
    if (capabilities.supportsInstruction(model) && String(instruction || "").trim()) body.instruction = String(instruction).trim();
    if (String(language || "").trim()) body.language = String(language).trim();
    if (String(seed ?? "").trim()) body.seed = Number(seed);
    if (capabilities.supportsSpeedControl(model) && Number.isFinite(Number(controls.speedScale))) body.speedScale = Number(controls.speedScale);
    if (capabilities.supportsStyleStrength(model) && Number.isFinite(Number(controls.styleStrength))) body.styleStrength = Number(controls.styleStrength);
    return body;
  }

  function attachChunking(body, chunking) {
    if (!chunking || typeof chunking !== "object" || Array.isArray(chunking)) return body;
    return { ...body, chunking: { ...chunking } };
  }

  function compactMessage(value, maxLength = 240) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
  }

  function humanizeError(error) {
    const payload = error?.payload || {};
    const raw = String(payload.errorMessage || payload.error || error?.message || "音声生成に失敗しました。");
    const message = raw.replace(/\s+/g, " ").trim();
    if (message.includes("127.0.0.1:9880")) return "GPT-SoVITS APIに接続できません。APIを起動して再試行してください。";
    if (/os error 1455|paging file|pagefile|ページング[\s　]*ファイル/i.test(message)) return "Windowsのメモリまたはページングファイルが不足しています。ほかの重い処理を終了して再試行してください。";
    if (/CUDA out of memory|out of memory/i.test(message)) return "GPUメモリ不足です。ほかの生成処理を止めるか、短い文章で再試行してください。";
    if (/model_path|model path|\.pth/i.test(message) && /not found|missing|ENOENT|ありません/i.test(message)) return "RVCモデル（.pth）が見つかりません。model_pathを確認してください。";
    if (/index_path|index path|\.index/i.test(message) && /not found|missing|ENOENT|ありません/i.test(message)) return "RVCのindexが見つかりません。index_pathを確認してください。";
    if (/timed? out|timeout/i.test(message)) return "処理が時間切れになりました。サービスの稼働状態と入力内容を確認してください。";
    if (/ECONNREFUSED|connection refused|fetch failed|failed to fetch/i.test(message)) return "ローカルTTSサービスに接続できません。local-tts.batを起動したまま、もう一度生成してください。";
    const firstLine = message.split(/(?:Traceback|\bat\s+[A-Za-z]:\\)/i)[0].trim();
    return compactMessage(firstLine || message);
  }

  function transitionCompareResult(previous, event) {
    const state = { ...(previous || {}) };
    if (event.type === "start") return { status: "loading" };
    if (event.type === "success") return { status: "success", result: event.result };
    if (event.type === "failure") return { status: "error", message: String(event.message || "") };
    return state;
  }

  global.LocalTts = global.LocalTts || {};
  global.LocalTts.generationCore = Object.freeze({
    normalizeSeed,
    incrementSeed,
    normalizeChunkSettings,
    normalizeStoredSettings,
    validateRequest,
    buildRequestBody,
    attachChunking,
    humanizeError,
    transitionCompareResult,
  });
})(globalThis);
