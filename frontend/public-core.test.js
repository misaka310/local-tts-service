import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

globalThis.LocalTtsChunking = {
  clampInteger(value, fallback, min, max) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.min(max, Math.max(min, Math.round(parsed))) : fallback;
  },
};
globalThis.window = globalThis;
await import("./public/model-catalog.js");
await import("./public/generation-core.js");
await import("./public/store.js");
await import("./public/rvc/rvc-form.js");
await import("./public/rvc/rvc-mic-recorder.js");
await import("./public/rvc/rvc-result.js");
await import("./public/audio-controller.js");
await import("./public/normal-controller.js");
await import("./public/compare-controller.js");
await import("./public/rvc/rvc-controller.js");

const core = globalThis.LocalTts.generationCore;
const modelCatalog = globalThis.LocalTtsModelCatalog;
const capabilities = {
  requiresReference: (model) => Boolean(model.requiresReferenceAudio),
  supportsReference: (model) => Boolean(model.supportsReferenceVoice || model.requiresReferenceAudio),
  requiresInstruction: (model) => Boolean(model.supportsVoiceDesign && !model.supportsReferenceVoice),
  supportsInstruction: (model) => Boolean(model.supportsInstruction || model.supportsVoiceDesign),
  supportsSpeedControl: (model) => Boolean(model.supportsSpeedControl),
  supportsStyleStrength: (model) => Boolean(model.supportsStyleStrength),
};

function fakeElement() {
  const listeners = new Map();
  return {
    checked: false,
    value: "",
    disabled: false,
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(listener);
    },
    dispatch(type, event = {}) {
      for (const listener of listeners.get(type) || []) listener({ target: this, ...event });
    },
    listenerCount(type) {
      return (listeners.get(type) || []).length;
    },
  };
}

test("model lists keep available models first without scrambling their configured order", async () => {
  const models = [
    { id: "unavailable-a", available: false, enabled: true },
    { id: "available-a", available: true, enabled: true },
    { id: "disabled-a", available: true, enabled: false },
    { id: "available-b", available: true, enabled: true },
  ];
  assert.deepEqual(
    modelCatalog.sortModelsAvailableFirst(models).map((model) => model.id),
    ["available-a", "available-b", "unavailable-a", "disabled-a"],
  );

  const appSource = await readFile(new URL("./public/app.js", import.meta.url), "utf-8");
  const compareSource = await readFile(new URL("./public/compare-page.js", import.meta.url), "utf-8");
  assert.match(appSource, /sortModelsAvailableFirst\(prioritizedModels\)/);
  assert.match(compareSource, /sortModelsAvailableFirst\(desiredModels\)/);
});

test("audio autoplay waits for readiness and retries one interrupted play", async () => {
  const listeners = new Map();
  let playCalls = 0;
  const audio = {
    src: "http://127.0.0.1/audio/test.wav",
    currentSrc: "http://127.0.0.1/audio/test.wav",
    readyState: 0,
    error: null,
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(listener);
    },
    removeEventListener(type, listener) {
      listeners.get(type)?.delete(listener);
    },
    async play() {
      playCalls += 1;
      if (playCalls === 1) {
        const error = new Error("The play() request was interrupted by a call to pause().");
        error.name = "AbortError";
        throw error;
      }
    },
  };
  const playback = globalThis.LocalTts.audioController.playWhenReady(audio, { timeoutMs: 1000 });
  setTimeout(() => {
    audio.readyState = 4;
    for (const listener of listeners.get("canplay") || []) listener({ target: audio });
  }, 0);
  assert.equal(await playback, true);
  assert.equal(playCalls, 2);
});

test("normalizes seed and auto increment deterministically", () => {
  assert.equal(core.normalizeSeed("12"), 12);
  assert.equal(core.normalizeSeed("invalid"), 1);
  assert.deepEqual(core.incrementSeed("12", true), { value: 13, changed: true });
});

test("normalizes long-text chunk settings", () => {
  assert.deepEqual(core.normalizeChunkSettings({ targetChars: 200, hardMaxChars: 400 }), {
    targetChars: 200,
    hardMaxChars: 400,
    chunking: { softChunkChars: 200, maxChunkChars: 270, hardLimitChars: 400, pauseBetweenChunksMs: 250 },
  });
});

test("validates required, optional, and unsupported reference voice capability", () => {
  const required = { available: true, requiresReferenceAudio: true };
  assert.equal(core.validateRequest({ model: required, text: "hello" }, capabilities), "reference voice is required");
  assert.equal(core.validateRequest({ model: required, voice: { voiceId: "v" }, text: "hello" }, capabilities), "");
  assert.equal(core.validateRequest({ model: { available: true }, text: "hello" }, capabilities), "");
});

test("builds request body from advertised model capabilities", () => {
  const model = { id: "model", supportsReferenceVoice: true, supportsInstruction: true, supportsSpeedControl: true };
  assert.deepEqual(core.buildRequestBody({ model, voice: { voiceId: "voice" }, text: " hi ", instruction: " calm ", seed: "3", controls: { speedScale: 1.1 } }, capabilities, (item) => item.id), {
    text: "hi", model: "model", format: "wav", voiceId: "voice", instruction: "calm", seed: 3, speedScale: 1.1,
  });
});

test("tracks compare generation state transitions", () => {
  assert.deepEqual(core.transitionCompareResult({}, { type: "start" }), { status: "loading" });
  assert.deepEqual(core.transitionCompareResult({}, { type: "success", result: { audioUrl: "/a.wav" } }), { status: "success", result: { audioUrl: "/a.wav" } });
  assert.deepEqual(core.transitionCompareResult({}, { type: "failure", message: "bad" }), { status: "error", message: "bad" });
});

test("storage adapter safely restores objects and history lists", () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const adapter = globalThis.LocalTts.store.createStorage(storage);
  adapter.save("history", [{ id: 1 }, { id: 2 }]);
  assert.deepEqual(adapter.loadList("history", 1), [{ id: 1 }]);
  values.set("settings", "invalid");
  assert.deepEqual(adapter.loadObject("settings", { safe: true }), { safe: true });
});

test("RVC input, params, microphone state, and results are normalized", () => {
  assert.equal(globalThis.LocalTts.rvcForm.normalizeInputSource("mic"), "mic");
  assert.equal(globalThis.LocalTts.rvcForm.normalizeInputSource("unknown"), "tts");
  assert.equal(globalThis.LocalTts.rvcForm.buildParams({ pitch: "2" }).pitch, 2);
  assert.equal(globalThis.LocalTts.rvcMicRecorder.transition("recording", "stop"), "processing");
  assert.equal(globalThis.LocalTts.rvcMicRecorder.transition("processing", "saved"), "ready");
  assert.deepEqual(globalThis.LocalTts.rvcResult.normalizeResult({ audioUrl: "/a.wav" }), {
    audioUrl: "/a.wav", denoisedAudioUrl: "", filename: "", diagnostics: {},
  });
});

test("generation core owns voice validation, chunk attachment, and user-facing errors", () => {
  const model = { available: true, requiresReferenceAudio: true };
  const voice = { voiceId: "voice" };
  assert.equal(core.validateRequest(
    { model, voice, text: "hello" },
    capabilities,
    {},
    { validateVoice: () => "voice duration is invalid" },
  ), "voice duration is invalid");
  assert.deepEqual(core.attachChunking({ text: "hello" }, { softChunkChars: 120 }), {
    text: "hello",
    chunking: { softChunkChars: 120 },
  });
  assert.match(core.humanizeError({ message: "CUDA out of memory" }), /GPUメモリ不足/);
});

test("normal controller owns page event binding and binds only once", () => {
  const calls = [];
  const elements = {
    text: fakeElement(), instruction: fakeElement(), model: fakeElement(), voice: fakeElement(), language: fakeElement(), seed: fakeElement(),
    useReference: fakeElement(), seedAutoIncrement: fakeElement(), saveHistory: fakeElement(), autoPlay: fakeElement(),
    speedScale: fakeElement(), styleStrength: fakeElement(), referencePreview: fakeElement(), generate: fakeElement(), regenerate: fakeElement(),
    history: fakeElement(), clearHistory: fakeElement(),
  };
  const normal = globalThis.LocalTts.normalController.createNormalController({
    elements,
    actions: {
      refreshText: () => calls.push("refreshText"), saveSettings: () => calls.push("saveSettings"), updateModel: () => calls.push("updateModel"),
      updateReference: () => calls.push("updateReference"), updateSynthesis: () => calls.push("updateSynthesis"), previewReference: () => calls.push("previewReference"),
      generate: () => calls.push("generate"), regenerate: () => calls.push("regenerate"), restoreHistory: (index) => calls.push(`restore:${index}`),
      clearHistory: () => calls.push("clearHistory"),
    },
  });
  normal.bind();
  normal.bind();
  assert.equal(elements.generate.listenerCount("click"), 1);
  elements.text.dispatch("input");
  elements.useReference.dispatch("change");
  elements.generate.dispatch("click");
  elements.history.dispatch("click", { target: { closest: () => ({ dataset: { restoreNormalHistory: "3" } }) } });
  assert.deepEqual(calls, ["refreshText", "updateModel", "saveSettings", "updateReference", "updateModel", "generate", "restore:3"]);
});

test("normal generation result hides internal-only memo and runtime metadata", async () => {
  const html = await readFile(new URL("./public/index.html", import.meta.url), "utf-8");
  const normalPage = await readFile(new URL("./public/normal-page.js", import.meta.url), "utf-8");
  assert.doesNotMatch(html, /評価メモ/);
  assert.doesNotMatch(normalPage, /runtime：/);
  assert.doesNotMatch(normalPage, /normalResultMemo/);
});

test("advanced voice controls and primary seed controls follow the cross-screen hierarchy", async () => {
  const html = await readFile(new URL("./public/index.html", import.meta.url), "utf-8");
  for (const scope of ["normal", "compare", "rvc"]) {
    const detailsStart = html.indexOf(`id="${scope}AdvancedSettings"`);
    const guidance = html.indexOf(`id="${scope}AdvancedGuidance"`);
    const instruction = html.indexOf(`id="${scope}InstructionInput"`);
    const emojiSlot = html.indexOf(`id="irodoriEmojiSlot-${scope}"`);
    const detailsEnd = html.indexOf("</details>", detailsStart);
    assert.ok(detailsStart >= 0, `${scope} advanced settings must exist`);
    assert.ok(guidance > detailsStart && guidance < detailsEnd, `${scope} advanced guidance must be inside advanced settings`);
    assert.ok(instruction > detailsStart && instruction < detailsEnd, `${scope} instruction must be inside advanced settings`);
    assert.ok(emojiSlot > detailsStart && emojiSlot < detailsEnd, `${scope} emoji controls must be inside advanced settings`);
  }
  const compareReference = html.indexOf('id="compareReferenceVoiceSelect"');
  const compareSeed = html.indexOf('id="compareSeedInput"');
  const compareSeedIncrement = html.indexOf('id="compareSeedAutoIncrementInput"');
  const compareAdvanced = html.indexOf('id="compareAdvancedSettings"');
  assert.ok(compareReference >= 0 && compareReference < compareAdvanced, "comparison reference voice must remain a normal visible control");
  assert.ok(compareSeed >= 0 && compareSeed < compareAdvanced, "comparison seed must be a primary control like normal generation");
  assert.ok(compareSeedIncrement > compareSeed && compareSeedIncrement < compareAdvanced, "comparison seed increment must stay compact beside its seed");
  const rvcSeed = html.indexOf('id="rvcSeedInput"');
  const rvcSeedIncrement = html.indexOf('id="rvcSeedAutoIncrementInput"');
  assert.ok(rvcSeed >= 0 && rvcSeedIncrement > rvcSeed, "RVC seed increment must stay in the same compact seed field");
  assert.doesNotMatch(html, />Demucs</);
});

test("new generation keeps existing audio controls available until replacement is ready", async () => {
  const normalPage = await readFile(new URL("./public/normal-page.js", import.meta.url), "utf-8");
  const comparePage = await readFile(new URL("./public/compare-page.js", import.meta.url), "utf-8");
  const rvcPage = await readFile(new URL("./public/rvc-page.js", import.meta.url), "utf-8");
  assert.doesNotMatch(normalPage, /setNormalGenerationActive\(true\);\s*els\.normalResultCard\.hidden = true/);
  assert.doesNotMatch(comparePage, /state: "pending", message: "再生成中です。", result: \{\}/);
  assert.doesNotMatch(rvcPage, /setRvcGenerationActive\(true\);\s*resetRvcResult\(\)/);
});

test("guide starts from the already-open app and RVC has a recent history panel", async () => {
  const html = await readFile(new URL("./public/index.html", import.meta.url), "utf-8");
  assert.match(html, /この画面が開いていれば起動は完了しています/);
  assert.doesNotMatch(html, /初めて使う人へ/);
  assert.match(html, /id="rvcHistoryList"/);
  assert.match(html, /id="rvcClearHistoryButton"/);
});

test("RVC model onboarding and reference voice ID rename controls are present", async () => {
  const html = await readFile(new URL("./public/index.html", import.meta.url), "utf-8");
  const guide = await readFile(new URL("./public/rvc-model-guide.html", import.meta.url), "utf-8");
  const referenceVoices = await readFile(new URL("./public/reference-voices.js", import.meta.url), "utf-8");
  assert.match(html, /id="rvcMissingModelPanel"/);
  assert.match(html, /id="rvcVoiceModelSelect"/);
  assert.match(html, /id="rvcModelDirectoryPath"/);
  assert.match(guide, /models\\rvc\\my_voice/);
  assert.match(referenceVoices, /voiceExistingIdRenameButton/);
  assert.match(referenceVoices, /reference-voice-renamed/);
});

test("compare and RVC controllers bind delegated and device events through injected dependencies", () => {
  const compareCalls = [];
  const compareElements = {
    text: fakeElement(), instruction: fakeElement(), seed: fakeElement(), voice: fakeElement(), seedAutoIncrement: fakeElement(), autoPlay: fakeElement(),
    referencePreview: fakeElement(), generate: fakeElement(), selectAll: fakeElement(), clear: fakeElement(), results: fakeElement(), history: fakeElement(), clearHistory: fakeElement(),
  };
  const compare = globalThis.LocalTts.compareController.createCompareController({
    elements: compareElements,
    actions: {
      refreshText: () => compareCalls.push("refreshText"), saveSettings: () => compareCalls.push("saveSettings"), updateSelection: () => compareCalls.push("updateSelection"),
      previewReference: () => compareCalls.push("previewReference"), generate: () => compareCalls.push("generate"), selectAll: () => compareCalls.push("selectAll"),
      clearSelection: () => compareCalls.push("clearSelection"), regenerateModel: (id) => compareCalls.push(`regenerate:${id}`), adoptModel: (id) => compareCalls.push(`adopt:${id}`),
      restoreHistory: (index) => compareCalls.push(`restore:${index}`), clearHistory: () => compareCalls.push("clearHistory"),
    },
  });
  compare.bind();
  compareElements.results.dispatch("click", { target: { closest: (selector) => selector.includes("regenerate") ? { dataset: { regenerateModel: "m1" } } : null } });
  assert.deepEqual(compareCalls, ["regenerate:m1"]);

  const rvcCalls = [];
  const deviceEvents = fakeElement();
  const rvcElements = {
    inputSources: [fakeElement()], text: fakeElement(), instruction: fakeElement(), micScript: fakeElement(), model: fakeElement(), voiceModel: fakeElement(), reloadModels: fakeElement(), voice: fakeElement(), language: fakeElement(), seed: fakeElement(),
    seedAutoIncrement: fakeElement(), autoPlay: fakeElement(), externalAudioPath: fakeElement(), externalAudioPathHistory: fakeElement(), demucsModel: fakeElement(), indexRatePreset: fakeElement(),
    f0UpKeyPreset: fakeElement(), protectPreset: fakeElement(), micDevice: fakeElement(), referencePreview: fakeElement(), convert: fakeElement(), denoise: fakeElement(),
    micStart: fakeElement(), micStop: fakeElement(), micRerecord: fakeElement(), micUse: fakeElement(), micHistory: fakeElement(), history: fakeElement(), clearHistory: fakeElement(),
  };
  const rvc = globalThis.LocalTts.rvcController.createRvcController({
    elements: rvcElements,
    deviceEvents,
    actions: {
      refreshText: () => rvcCalls.push("refreshText"), saveInputSource: () => rvcCalls.push("saveInputSource"), saveSettings: () => rvcCalls.push("saveSettings"),
      updateModel: () => rvcCalls.push("updateModel"), selectVoiceModel: () => rvcCalls.push("selectVoiceModel"), reloadModels: () => rvcCalls.push("reloadModels"), rememberFilePath: () => rvcCalls.push("rememberFilePath"), selectFilePath: (value) => rvcCalls.push(`selectFilePath:${value}`), saveMicDevice: () => rvcCalls.push("saveMicDevice"),
      loadMicDevices: () => rvcCalls.push("loadMicDevices"), previewReference: () => rvcCalls.push("previewReference"), convert: () => rvcCalls.push("convert"),
      denoise: () => rvcCalls.push("denoise"), startRecording: () => rvcCalls.push("startRecording"), stopRecording: () => rvcCalls.push("stopRecording"),
      useRecording: () => rvcCalls.push("useRecording"), selectRecording: () => rvcCalls.push("selectRecording"), restoreHistory: (index) => rvcCalls.push(`restore:${index}`), clearHistory: () => rvcCalls.push("clearHistory"),
    },
  });
  rvc.bind();
  deviceEvents.dispatch("devicechange");
  rvcElements.voiceModel.dispatch("change");
  rvcElements.reloadModels.dispatch("click");
  rvcElements.externalAudioPathHistory.value = "C:\\audio\\saved.wav";
  rvcElements.externalAudioPathHistory.dispatch("change");
  rvcElements.convert.dispatch("click");
  rvcElements.history.dispatch("click", { target: { closest: () => ({ dataset: { restoreRvcHistory: "2" } }) } });
  rvcElements.clearHistory.dispatch("click");
  assert.deepEqual(rvcCalls, ["loadMicDevices", "selectVoiceModel", "reloadModels", "selectFilePath:C:\\audio\\saved.wav", "convert", "restore:2", "clearHistory"]);
});
