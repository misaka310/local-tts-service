const {
  MODEL_LABELS,
  MODEL_PROFILE,
  DESIRED_MODELS,
  modelLabel,
  profileFor,
} = window.LocalTtsModelCatalog;
const { clampInteger, splitTextForChunkPreview } = window.LocalTtsChunking;
const {
  requiresReference,
  supportsReference,
  requiresInstruction,
  supportsInstruction,
  supportsSpeedControl,
  supportsStyleStrength,
} = window.LocalTtsModelCapabilities;

const NORMAL_HISTORY_KEY = "local-tts-normal-history-v3";
const NORMAL_FORM_SETTINGS_KEY = "local-tts-normal-form-settings-v1";
const COMPARE_FORM_SETTINGS_KEY = "local-tts-compare-form-settings-v1";
const RVC_FORM_SETTINGS_KEY = "local-tts-rvc-form-settings-v1";
const COMPARE_HISTORY_KEY = "local-tts-compare-history-v1";
const RVC_HISTORY_KEY = "local-tts-rvc-history-v1";
const RVC_MIC_HISTORY_KEY = "local-tts-rvc-mic-history-v1";
const RVC_MIC_DEVICE_KEY = "local-tts-rvc-mic-device-v1";
const CHUNK_SETTINGS_KEYS = Object.freeze({
  normal: "local-tts-normal-chunk-settings-v1",
  compare: "local-tts-compare-chunk-settings-v1",
  rvc: "local-tts-rvc-chunk-settings-v1",
});
const RVC_FILE_PATH_HISTORY_KEY = "local-tts-rvc-file-path-history-v1";
const RVC_INPUT_SOURCE_KEY = "local-tts-rvc-input-source-v1";
const INITIAL_DATA_TIMEOUT_MS = 10000;
const $ = (selector) => document.querySelector(selector);
const all = (selector) => Array.from(document.querySelectorAll(selector));
const sharedUi = window.LocalTtsUi;
const ttsApi = window.LocalTtsApiClient.create(sharedUi.fetchJson);
const generationCore = window.LocalTts.generationCore;
const modelCapabilities = Object.freeze({
  requiresReference,
  supportsReference,
  requiresInstruction,
  supportsInstruction,
  supportsSpeedControl,
  supportsStyleStrength,
});

const els = Object.freeze({
  ...normalEls,
  ...compareEls,
  ...rvcEls,
});

const CHUNK_SCOPES = ["normal", "compare", "rvc"];
const chunkControls = new Map(CHUNK_SCOPES.map((scope) => {
  const panel = document.querySelector(`[data-chunk-scope="${scope}"]`);
  return [scope, {
    scope,
    panel,
    target: panel?.querySelector("[data-chunk-target]") || null,
    hardMax: panel?.querySelector("[data-chunk-hard-max]") || null,
    presets: panel ? Array.from(panel.querySelectorAll("[data-chunk-preset]")) : [],
    summary: panel?.querySelector("[data-chunk-summary]") || null,
    previewToggle: panel?.querySelector("[data-chunk-preview-toggle]") || null,
    preview: panel?.nextElementSibling?.matches?.("[data-chunk-preview]") ? panel.nextElementSibling : null,
  }];
}));

const pageControllers = Object.freeze({
  normal: window.LocalTts.normalController.createNormalController({
    elements: {
      text: els.normalText,
      instruction: els.normalInstruction,
      model: els.normalModel,
      voice: els.normalVoice,
      language: els.normalLanguage,
      seed: els.normalSeed,
      useReference: els.normalUseReference,
      seedAutoIncrement: els.normalSeedAutoIncrement,
      saveHistory: els.normalSaveHistory,
      autoPlay: els.normalAutoPlay,
      speedScale: els.normalSpeedScale,
      styleStrength: els.normalStyleStrength,
      referencePreview: els.normalReferencePreview,
      generate: els.normalGenerate,
      regenerate: els.normalRegenerateButton,
      history: els.normalHistory,
      clearHistory: els.normalClearHistory,
    },
    actions: {
      refreshText: refreshTextCountsAndChunkPreview,
      saveSettings: saveNormalFormSettings,
      updateModel: (...args) => updateNormalModelInfo(...args),
      updateReference: () => updateNormalReferenceUi(selectedNormalModel()),
      updateSynthesis: () => updateNormalSynthesisControls(selectedNormalModel()),
      previewReference: () => toggleReferencePreview(els.normalVoice, els.normalReferencePreview, els.normalStatus),
      generate: (...args) => generateNormal(...args),
      regenerate: (...args) => regenerateLastNormalRequest(...args),
      restoreHistory: (...args) => restoreNormalHistoryItem(...args),
      clearHistory: () => {
        normalHistory = [];
        saveList(NORMAL_HISTORY_KEY, normalHistory);
        renderNormalHistory();
      },
    },
  }),
  compare: window.LocalTts.compareController.createCompareController({
    elements: {
      text: els.compareText,
      instruction: els.compareInstruction,
      seed: els.compareSeed,
      voice: els.compareVoice,
      seedAutoIncrement: els.compareSeedAutoIncrement,
      autoPlay: els.compareAutoPlay,
      referencePreview: els.compareReferencePreview,
      generate: els.compareGenerate,
      selectAll: els.compareSelectAll,
      clear: els.compareClear,
      results: els.compareResults,
      history: els.compareHistory,
      clearHistory: els.compareClearHistory,
    },
    actions: {
      refreshText: refreshTextCountsAndChunkPreview,
      saveSettings: saveCompareFormSettings,
      updateSelection: (...args) => updateCompareButtonState(...args),
      previewReference: () => toggleReferencePreview(els.compareVoice, els.compareReferencePreview, els.compareStatus),
      generate: (...args) => generateCompare(...args),
      selectAll: () => {
        all('[data-model-card] input:not(:disabled)').forEach((input) => { input.checked = true; });
        saveCompareFormSettings();
        updateCompareButtonState();
      },
      clearSelection: () => {
        all('[data-model-card] input').forEach((input) => { input.checked = false; });
        saveCompareFormSettings();
        updateCompareButtonState();
      },
      regenerateModel: (...args) => regenerateCompareModel(...args),
      adoptModel: (...args) => adoptCompareModel(...args),
      restoreHistory: (...args) => restoreCompareHistoryItem(...args),
      clearHistory: () => {
        compareHistory = [];
        saveList(COMPARE_HISTORY_KEY, compareHistory);
        renderCompareHistory();
      },
    },
  }),
  rvc: window.LocalTts.rvcController.createRvcController({
    elements: {
      inputSources: els.rvcInputSources,
      text: els.rvcText,
      instruction: els.rvcInstruction,
      micScript: els.rvcMicScript,
      model: els.rvcModel,
      voiceModel: els.rvcVoiceModel,
      reloadModels: els.rvcModelReload,
      voice: els.rvcVoice,
      language: els.rvcLanguage,
      seed: els.rvcSeed,
      seedAutoIncrement: els.rvcSeedAutoIncrement,
      autoPlay: els.rvcAutoPlay,
      externalAudioPath: els.rvcExternalAudioPath, externalAudioPathHistory: els.rvcExternalAudioPathHistory,
      demucsModel: els.rvcDemucsModel,
      indexRatePreset: els.rvcIndexRatePreset,
      f0UpKeyPreset: els.rvcF0UpKeyPreset,
      protectPreset: els.rvcProtectPreset,
      micDevice: els.rvcMicDevice,
      referencePreview: els.rvcReferencePreview,
      convert: els.rvcConvert,
      denoise: els.rvcDenoiseButton,
      micStart: els.rvcMicStart,
      micStop: els.rvcMicStop,
      micRerecord: els.rvcMicRerecord,
      micUse: els.rvcMicUse,
      micHistory: els.rvcMicHistory,
      history: els.rvcHistory,
      clearHistory: els.rvcClearHistory,
      helpButtons: all(".rvc-help"),
    },
    deviceEvents: navigator.mediaDevices,
    documentEvents: document,
    actions: {
      refreshText: refreshTextCountsAndChunkPreview,
      saveInputSource: saveRvcInputSource,
      saveSettings: saveRvcFormSettings,
      updateModel: (...args) => updateRvcModelInfo(...args),
      selectVoiceModel: () => {
        syncSelectedRvcModelPaths();
        saveRvcFormSettings();
        updateRvcModelInfo();
      },
      reloadModels: () => refreshRvcModelCatalog(),
      rememberFilePath: () => rememberRvcFilePath(), selectFilePath: (value) => selectSavedRvcFilePath(value),
      saveMicDevice: () => saveSelectedRvcMicDeviceId(),
      loadMicDevices: () => loadRvcMicDevices(),
      previewReference: () => toggleReferencePreview(els.rvcVoice, els.rvcReferencePreview, els.rvcStatus),
      convert: (...args) => generateRvc(...args),
      denoise: (...args) => denoiseCurrentRvcOutput(...args),
      startRecording: (...args) => startRvcMicRecording(...args),
      stopRecording: (...args) => stopRvcMicRecording(...args),
      useRecording: () => setCurrentRvcMicRecording(currentRvcMicRecording),
      selectRecording: (value) => {
        const selected = rvcMicHistory.find((item) => (item.path || item.filename) === value);
        if (selected) setCurrentRvcMicRecording(selected, { save: false });
      },
      restoreHistory: (...args) => restoreRvcHistoryItem(...args),
      clearHistory: () => {
        rvcHistory = [];
        saveList(RVC_HISTORY_KEY, rvcHistory);
        renderRvcHistory();
      },
    },
  }),
});
const audioController = window.LocalTts.audioController.createAudioController({
  onError: (error) => setPlaybackError(`再生に失敗しました: ${error?.message || error}`),
});

let modelsById = new Map();
let voicesById = new Map();
let defaultReferenceVoice = "";
let rvcDefaults = null;
let normalHistory = loadList(NORMAL_HISTORY_KEY, 8);
let compareHistory = loadList(COMPARE_HISTORY_KEY, 8);
let rvcHistory = loadList(RVC_HISTORY_KEY, 8);
let rvcMicHistory = loadList(RVC_MIC_HISTORY_KEY, 12);
let rvcFilePathHistory = loadList(RVC_FILE_PATH_HISTORY_KEY, 12);
let currentRvcMicRecording = rvcMicHistory[0] || null;
let currentRvcConvertedFilename = "";
let rvcMediaRecorder = null;
let rvcMicStream = null;
let rvcMicChunks = [];
let rvcMicTimerId = 0;
let rvcMicStartedAt = 0;
let lastNormalBody = null;
let compareResults = [];
let compareGenerationActive = false;
let referencePreviewAudio = null;
let activeReferencePreviewButton = null;
let normalHistoryAudio = null;
let lastNormalReferenceModelId = "";
let pendingReferenceVoiceRename = null;

function migrateReferenceVoiceId(value, previousVoiceId, nextVoiceId, key = "") {
  if (Array.isArray(value)) return value.map((item) => migrateReferenceVoiceId(item, previousVoiceId, nextVoiceId));
  if (!value || typeof value !== "object") {
    return ["voice", "voiceId", "referenceVoice"].includes(key) && value === previousVoiceId ? nextVoiceId : value;
  }
  return Object.fromEntries(Object.entries(value).map(([entryKey, entryValue]) => [
    entryKey,
    migrateReferenceVoiceId(entryValue, previousVoiceId, nextVoiceId, entryKey),
  ]));
}

function migrateReferenceVoiceState(previousVoiceId, nextVoiceId) {
  if (!previousVoiceId || !nextVoiceId || previousVoiceId === nextVoiceId) return;
  const settingsKeys = [NORMAL_FORM_SETTINGS_KEY, COMPARE_FORM_SETTINGS_KEY, RVC_FORM_SETTINGS_KEY];
  for (const key of settingsKeys) {
    const current = loadObject(key, {});
    saveObject(key, migrateReferenceVoiceId(current, previousVoiceId, nextVoiceId));
  }
  normalHistory = migrateReferenceVoiceId(normalHistory, previousVoiceId, nextVoiceId);
  compareHistory = migrateReferenceVoiceId(compareHistory, previousVoiceId, nextVoiceId);
  rvcHistory = migrateReferenceVoiceId(rvcHistory, previousVoiceId, nextVoiceId);
  lastNormalBody = migrateReferenceVoiceId(lastNormalBody, previousVoiceId, nextVoiceId);
  compareResults = migrateReferenceVoiceId(compareResults, previousVoiceId, nextVoiceId);
  saveList(NORMAL_HISTORY_KEY, normalHistory);
  saveList(COMPARE_HISTORY_KEY, compareHistory);
  saveList(RVC_HISTORY_KEY, rvcHistory);
  renderNormalHistory();
  renderCompareHistory();
  renderRvcHistory();
}

function loadList(key, limit) {
  return sharedUi.loadList(key, limit);
}

function saveList(key, value) {
  sharedUi.saveList(key, value);
}

function loadObject(key, fallback = {}) {
  return sharedUi.loadObject(key, fallback);
}

function saveObject(key, value) {
  sharedUi.saveObject(key, value);
}

function normalizedStoredSeed(input) {
  return generationCore.normalizeSeed(input?.value);
}

function escapeHtml(value) {
  return sharedUi.escapeHtml(value);
}

function modelId(model) {
  return String((model && (model.id || model.model)) || "");
}

function isAvailable(model) {
  return Boolean(model && model.available && model.enabled);
}

function setRequirementBadge(element, text, state) {
  if (!element) return;
  element.textContent = text;
  element.className = `requirement-badge ${state}`;
}

function isGptSovitsModel(modelOrId) {
  const id = typeof modelOrId === "string" ? modelOrId : modelId(modelOrId);
  return id.startsWith("gpt_sovits_");
}

function gptReferenceError(modelOrId, voice) {
  if (!isGptSovitsModel(modelOrId) || !voice || typeof voice.audioDurationSec !== "number") return "";
  const min = Number(voice.minReferenceDurationSec || 3);
  const max = Number(voice.maxReferenceDurationSec || 10);
  const duration = Number(voice.audioDurationSec);
  if (duration < min || duration > max) {
    return `GPT-SoVITSでは ${voice.displayName || voice.voiceId} は使えません。${duration.toFixed(2)}秒です。${min}〜${max}秒の参照音声を選んでください。`;
  }
  return "";
}

function selectedVoice(selectEl) {
  if (!selectEl) return null;
  return voicesById.get(String(selectEl.value || "").trim()) || null;
}

function setStatus(el, text, isError = false, isWarning = false) {
  sharedUi.setStatus(el, text, isError, isWarning);
}
function modelPerformanceWarning(model) { return String(model?.performanceWarning || "").trim(); }
function irodoriEmojiPresets() {
  const configured = Array.isArray(window.IRODORI_EMOJI_PRESETS) ? window.IRODORI_EMOJI_PRESETS : [];
  const fallback = [
    { emoji: "😳", label: "驚き" },
    { emoji: "😭", label: "泣き" },
    { emoji: "😱", label: "叫び" },
    { emoji: "😡", label: "怒り" },
    { emoji: "😰", label: "不安" },
    { emoji: "🥺", label: "懇願" },
    { emoji: "😌", label: "安堵" },
    { emoji: "😊", label: "嬉しい" },
    { emoji: "😴", label: "眠そう" },
    { emoji: "⏸️", label: "間" }
  ];
  return (configured.length ? configured : fallback).slice(0, 10);
}

function insertAtCursor(textarea, value) {
  sharedUi.insertAtCursor(textarea, value);
}

async function copyText(value) {
  return sharedUi.copyText(value);
}

function isIrodoriModel(modelOrId) {
  const id = typeof modelOrId === "string" ? modelOrId : modelId(modelOrId);
  return String(id || "").startsWith("irodori_");
}

function shouldShowIrodoriEmojiPalette(scope) {
  if (scope === "normal") return isIrodoriModel(selectedNormalModel());
  if (scope === "compare") return selectedCompareModels().some((id) => isIrodoriModel(id));
  if (scope === "rvc") return selectedRvcInputSource() === "tts" && isIrodoriModel(selectedRvcModel());
  return false;
}

function updateIrodoriEmojiPaletteVisibility() {
  for (const scope of ["normal", "compare", "rvc"]) {
    const palette = document.getElementById(`irodoriEmojiPalette-${scope}`);
    if (palette) palette.hidden = !shouldShowIrodoriEmojiPalette(scope);
  }
}

function renderIrodoriEmojiPalettes() {
  const targets = [
    { id: "normal", textarea: els.normalText, status: els.normalStatus },
    { id: "compare", textarea: els.compareText, status: els.compareStatus },
    { id: "rvc", textarea: els.rvcText, status: els.rvcStatus }
  ];
  const presets = irodoriEmojiPresets();
  for (const target of targets) {
    if (!target.textarea || document.getElementById(`irodoriEmojiPalette-${target.id}`)) continue;
    const palette = document.createElement("div");
    palette.className = "irodori-emoji-palette";
    palette.id = `irodoriEmojiPalette-${target.id}`;
    palette.hidden = true;
    palette.innerHTML = `
      <div class="irodori-emoji-head">
        <strong>Irodori専用の感情絵文字</strong>
        <small>クリックすると本文のカーソル位置へ挿入します。</small>
      </div>
      <div class="irodori-emoji-list">
        ${presets.map((item) => `
          <button type="button" class="irodori-emoji-chip" data-irodori-emoji="${escapeHtml(item.emoji)}" title="${escapeHtml(item.label)}">
            <span>${escapeHtml(item.emoji)}</span><small>${escapeHtml(item.label)}</small>
          </button>
        `).join("")}
      </div>`;
    const slot = document.getElementById(`irodoriEmojiSlot-${target.id}`);
    if (slot) {
      slot.appendChild(palette);
    } else {
      const field = target.textarea.closest(".textarea-field");
      const counter = field?.querySelector(":scope > small");
      (counter || target.textarea).insertAdjacentElement("afterend", palette);
    }
    palette.addEventListener("click", (event) => {
      const button = event.target.closest("[data-irodori-emoji]");
      if (!button) return;
      const emoji = button.dataset.irodoriEmoji || "";
      insertAtCursor(target.textarea, emoji);
      button.classList.add("copied");
      const previousTitle = button.title;
      button.title = "本文へ挿入しました";
      setStatus(target.status, `${emoji} を本文に入れました。`);
      window.setTimeout(() => {
        button.classList.remove("copied");
        button.title = previousTitle;
      }, 900);
    });
  }
  updateIrodoriEmojiPaletteVisibility();
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "--:--";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function voiceLabel(item) {
  const duration = typeof item.audioDurationSec === "number" ? ` / ${item.audioDurationSec.toFixed(2)}秒` : "";
  const text = item.hasReferenceText ? "" : " / voice.txtなし";
  return `${item.displayName || item.voiceId}${duration}${text}`;
}

function fillVoiceSelect(selectEl) {
  if (!selectEl) return;
  const previousValue = selectEl.value;
  selectEl.innerHTML = "";
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = "参照音声を選択してください";
  selectEl.appendChild(blank);
  for (const voice of voicesById.values()) {
    if (voice.archived) continue;
    const option = document.createElement("option");
    option.value = voice.voiceId;
    option.textContent = voice.enabled ? voiceLabel(voice) : `${voiceLabel(voice)}（利用不可: ${voice.errorReason || "設定不備"}）`;
    option.disabled = !voice.enabled;
    selectEl.appendChild(option);
  }
  if (previousValue && voicesById.has(previousValue)) selectEl.value = previousValue;
  else if (defaultReferenceVoice && voicesById.has(defaultReferenceVoice)) selectEl.value = defaultReferenceVoice;
}

async function refreshReferenceVoices() {
  const payload = await ttsApi.referenceVoices();
  const voices = Array.isArray(payload.voices) ? payload.voices : [];
  voicesById = new Map(voices.map((voice) => [voice.voiceId, voice]));
  defaultReferenceVoice = String(payload.defaultReferenceVoice || defaultReferenceVoice || "").trim();
  fillVoiceSelect(els.normalVoice);
  fillVoiceSelect(els.compareVoice);
  fillVoiceSelect(els.rvcVoice);
  updateNormalModelInfo();
  updateCompareButtonState();
  updateRvcModelInfo();
  updateReferencePreviewButtons();
  updateRvcReferencePreviewButton();
  return voices;
}

function ensureReferencePreviewAudio() {
  if (!referencePreviewAudio) {
    referencePreviewAudio = new Audio();
    referencePreviewAudio.preload = "none";
  }
  return referencePreviewAudio;
}

function resetReferencePreviewButtons() {
  [els.normalReferencePreview, els.compareReferencePreview, els.rvcReferencePreview].forEach((button) => {
    if (button) button.textContent = "▶";
  });
  activeReferencePreviewButton = null;
}

function updateReferencePreviewButtons() {
  const normalVoice = selectedVoice(els.normalVoice);
  const compareVoice = selectedVoice(els.compareVoice);
  const rvcVoice = selectedVoice(els.rvcVoice);
  if (els.normalReferencePreview) {
    els.normalReferencePreview.disabled = !normalReferenceEnabled() || !normalVoice || !normalVoice.enabled;
  }
  if (els.compareReferencePreview) {
    els.compareReferencePreview.disabled = !compareVoice || !compareVoice.enabled;
  }
}

function updateRvcReferencePreviewButton() {
  const rvcVoice = selectedVoice(els.rvcVoice);
  if (els.rvcReferencePreview) {
    els.rvcReferencePreview.disabled = !rvcVoice || !rvcVoice.enabled;
  }
}

function referencePreviewUrl(voiceId) {
  return `/api/reference-voices/${encodeURIComponent(voiceId)}/audio`;
}

async function toggleReferencePreview(selectEl, button, statusEl) {
  const voice = selectedVoice(selectEl);
  if (!voice || !voice.enabled) {
    setStatus(statusEl, "参照音声を選択してください。", true);
    return;
  }

  const audio = ensureReferencePreviewAudio();
  const nextUrl = referencePreviewUrl(voice.voiceId);
  const currentUrl = String(audio.currentSrc || audio.src || "");
  const samePreview = currentUrl.endsWith(nextUrl);

  if (samePreview && !audio.paused) {
    resetReferencePreviewButtons();
    audio.pause();
    setStatus(statusEl, `参照音声の再生を停止しました: ${voice.displayName || voice.voiceId}`);
    return;
  }

  resetReferencePreviewButtons();
  audio.pause();
  audio.src = nextUrl;
  activeReferencePreviewButton = button;
  button.textContent = "■";
  setStatus(statusEl, `参照音声の再生を開始しました: ${voice.displayName || voice.voiceId}`);
  try {
    await audio.play();
  } catch (error) {
    resetReferencePreviewButtons();
    setStatus(statusEl, `参照音声の再生に失敗しました: ${error.message || error}`, true);
  }
}

function fillModelSelect() {
  const order = ["irodori_v3", "irodori_v3_voicedesign", "gpt_sovits_zero_shot", "qwen3_tts_clone_1_7b", "f5_tts_zero_shot", "irodori_v2", "qwen3_tts_clone_0_6b", "mock"];
  const prioritizedModels = [...order.map((id) => modelsById.get(id)).filter(Boolean), ...[...modelsById.values()].filter((m) => !order.includes(modelId(m)))];
  const sorted = window.LocalTtsModelCatalog.sortModelsAvailableFirst(prioritizedModels);
  els.normalModel.innerHTML = "";
  for (const model of sorted) {
    const id = modelId(model);
    const option = document.createElement("option");
    option.value = id;
    option.textContent = isAvailable(model) ? modelLabel(id, model.label) : `${modelLabel(id, model.label)}（利用不可）`;
    option.disabled = !isAvailable(model);
    els.normalModel.appendChild(option);
  }
  const firstAvailable = sorted.find(isAvailable);
  if (firstAvailable) els.normalModel.value = modelId(firstAvailable);
  if (els.rvcModel) {
    els.rvcModel.innerHTML = els.normalModel.innerHTML;
    if (firstAvailable) els.rvcModel.value = modelId(firstAvailable);
  }
}

function updateTextCounts() {
  els.normalTextCount.textContent = `${els.normalText.value.length} / 1000`;
  els.normalInstructionCount.textContent = `${els.normalInstruction.value.length} / 300`;
  els.compareTextCount.textContent = `${els.compareText.value.length} / 1000`;
  els.compareInstructionCount.textContent = `${els.compareInstruction.value.length} / 300`;
  if (els.rvcTextCount) els.rvcTextCount.textContent = `${els.rvcText.value.length} / 1000`;
  if (els.rvcInstructionCount) els.rvcInstructionCount.textContent = `${els.rvcInstruction.value.length} / 300`;
  if (els.rvcMicScriptCount) els.rvcMicScriptCount.textContent = `${els.rvcMicScript?.value.length || 0} / 1000`;
}

function chunkTextElement(scope) {
  if (scope === "normal") return els.normalText;
  if (scope === "compare") return els.compareText;
  return els.rvcText;
}

function chunkSettingsFromForm(scope) {
  const controls = chunkControls.get(scope);
  const saved = loadObject(CHUNK_SETTINGS_KEYS[scope], {});
  return generationCore.normalizeChunkSettings({
    targetChars: controls?.target?.value ?? saved.targetChars,
    hardMaxChars: controls?.hardMax?.value ?? saved.hardMaxChars,
  });
}

function updateChunkPreview(scope) {
  const controls = chunkControls.get(scope);
  if (!controls?.summary) return;
  const settings = chunkSettingsFromForm(scope);
  const chunks = splitTextForChunkPreview(chunkTextElement(scope)?.value || "", settings.targetChars, settings.hardMaxChars);
  const lengths = chunks.map((chunk) => chunk.length);
  const max = lengths.length ? Math.max(...lengths) : 0;
  controls.summary.textContent = !chunks.length
    ? "読み上げテキストを入力してください"
    : chunks.length === 1
      ? `分割なし / ${max}文字`
      : `${chunks.length}分割 / 最大 ${max}文字`;
  if (controls.preview && !controls.preview.hidden) {
    controls.preview.innerHTML = chunks.length
      ? `<ol>${chunks.map((chunk, index) => `<li><b>${index + 1}</b> ${chunk.length}文字<br>${escapeHtml(chunk.slice(0, 140))}${chunk.length > 140 ? "…" : ""}</li>`).join("")}</ol>`
      : "読み上げテキストを入力してください。";
  }
  saveObject(CHUNK_SETTINGS_KEYS[scope], { targetChars: settings.targetChars, hardMaxChars: settings.hardMaxChars });
}

function refreshTextCountsAndChunkPreview() {
  updateTextCounts();
  CHUNK_SCOPES.forEach(updateChunkPreview);
}

function applyChunkPreset(scope, target) {
  const controls = chunkControls.get(scope);
  if (!controls?.target) return;
  controls.target.value = String(target);
  controls.presets.forEach((button) => button.classList.toggle("active", String(button.dataset.chunkPreset) === String(target)));
  updateChunkPreview(scope);
}

function applySavedChunkSettings(scope) {
  const controls = chunkControls.get(scope);
  if (!controls) return;
  const saved = loadObject(CHUNK_SETTINGS_KEYS[scope], {});
  if (controls.target && saved.targetChars) controls.target.value = String(saved.targetChars);
  if (controls.hardMax && saved.hardMaxChars) controls.hardMax.value = String(saved.hardMaxChars);
  applyChunkPreset(scope, controls.target?.value || 240);
}

function copyChunkSettings(sourceScope, targetScope) {
  const source = chunkSettingsFromForm(sourceScope);
  const targetControls = chunkControls.get(targetScope);
  if (!targetControls) return;
  if (targetControls.target) targetControls.target.value = String(source.targetChars);
  if (targetControls.hardMax) targetControls.hardMax.value = String(source.hardMaxChars);
  applyChunkPreset(targetScope, source.targetChars);
}

function normalizeSeedInput(input) {
  const normalized = generationCore.normalizeSeed(input?.value);
  if (input) input.value = String(normalized);
  return normalized;
}

function incrementSeedInputIfNeeded(input, checkbox, afterIncrement) {
  if (!checkbox?.checked) return false;
  const result = generationCore.incrementSeed(input?.value, true);
  if (input) input.value = String(result.value);
  if (result.changed) afterIncrement?.();
  return result.changed;
}

function validateRequest(model, voice, text, instruction) {
  return generationCore.validateRequest(
    { model, voice, text, instruction },
    modelCapabilities,
    {
      modelRequired: "モデルを選択してください。",
      modelUnavailable: "このモデルは現在利用できません。",
      textRequired: "読み上げテキストを入力してください。",
      referenceRequired: "参照音声を選択してください。",
      referenceTextRequired: "このモデルでは voice.wav と voice.txt の両方が必要です。",
      instructionRequired: "instruction / 話し方メモを入力してください。",
    },
    { validateVoice: gptReferenceError },
  );
}

function buildRequestBody(model, voice, text, instruction, language, seed, controls = {}) {
  return generationCore.buildRequestBody(
    { model, voice, text, instruction, language, seed, controls },
    modelCapabilities,
    modelId,
  );
}

function attachChunking(body, chunking) {
  return generationCore.attachChunking(body, chunking);
}

function humanizeError(error) {
  return generationCore.humanizeError(error);
}

function stringifyDiagnostic(value) {
  if (value == null) return "なし";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function diagnosticResolutionHints(message) {
  const hints = [];
  if (/NameError|ReferenceError|is not defined/i.test(message)) hints.push("実装上の未定義名です。Traceback末尾のファイル・行番号と変数名を確認し、importまたは定義漏れを修正してください。");
  if (/ModuleNotFoundError|No module named|import failed/i.test(message)) hints.push("実行環境の依存関係不足です。対象モデルのセットアップを再実行し、同じPython環境でimport確認してください。");
  if (/not found|missing|ENOENT|checkpoint/i.test(message)) hints.push("モデル、checkpoint、参照音声、実行ファイルのパスを確認してください。相対パスはリポジトリルート基準です。");
  if (/os error 1455|paging file|pagefile|ページング[\s　]*ファイル/i.test(message)) hints.push("Windowsのコミット領域不足です。タスクマネージャーでメモリを大量使用するプロセスを終了し、ページングファイルの空きと自動管理設定を確認してください。");
  if (/CUDA out of memory|out of memory/i.test(message)) hints.push("GPUメモリ不足です。他の生成処理を止め、短い文章または軽いモデルで再試行してください。");
  if (/timed? out|timeout/i.test(message)) hints.push("処理時間超過です。モデルプロセスの生存、GPU使用率、初回ダウンロード待ちを確認してください。");
  if (/ECONNREFUSED|connection refused|fetch failed/i.test(message)) hints.push("接続先サービスが停止しているか、ポートが異なります。health endpointと起動ログを確認してください。");
  if (/runtime failed|Traceback|status.?502/i.test(message)) hints.push("ランタイム内部で失敗しています。下の完全なError responseのTraceback末尾から原因を確認してください。");
  if (!hints.length) hints.push("RequestとError responseをそのままAIへ渡し、最初に失敗した処理と再現条件を特定してください。");
  return hints;
}

function buildAiDiagnosticLog({ screen = "unknown", error = null, request = null, model = "", extra = null } = {}) {
  const payload = error?.payload || null;
  const rawMessage = String(payload?.errorMessage || payload?.error || error?.stack || error?.message || error || "不明なエラー");
  const resolvedModel = String(model || request?.model || payload?.model || "-");
  const runtime = String(payload?.runtime || modelsById.get(resolvedModel)?.runtime || "-");
  const errorDetail = {
    name: error?.name || "Error",
    message: error?.message || rawMessage,
    stack: error?.stack || "",
    payload,
  };
  return [
    "Local TTS diagnostic log",
    `time: ${new Date().toISOString()}`,
    `screen: ${screen}`,
    `model: ${resolvedModel}`,
    `runtime: ${runtime}`,
    `frontMessage: ${humanizeError(error)}`,
    `url: ${location.href}`,
    `browser: ${navigator.userAgent}`,
    "",
    "確認ポイント:",
    ...diagnosticResolutionHints(rawMessage).map((hint) => `- ${hint}`),
    "",
    "Request:",
    stringifyDiagnostic(request),
    "",
    "Error response:",
    stringifyDiagnostic(errorDetail),
    ...(extra == null ? [] : ["", "Additional context:", stringifyDiagnostic(extra)]),
  ].join("\n");
}

function switchTab(tab, updateHash = true) {
  const normalized = tab === "compare" || tab === "rvc" || tab === "history" || tab === "voices" || tab === "guide" ? tab : "normal";
  document.querySelectorAll(".page-section").forEach((section) => section.classList.toggle("active", section.dataset.page === normalized));
  document.querySelectorAll(".top-tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === normalized));
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.tab === normalized));
  if (updateHash) {
    history.replaceState(null, "", `#${normalized}`);
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    const resetPageScroll = () => {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    };
    resetPageScroll();
    requestAnimationFrame(() => requestAnimationFrame(resetPageScroll));
  }
}

function setPlaybackError(message) {
  const text = message || "再生に失敗しました。音声URLまたはブラウザの再生許可を確認してください。";
  if (els.normalStatus) setStatus(els.normalStatus, text, true);
  if (els.compareStatus) setStatus(els.compareStatus, text, true);
}

function playAudioElement(audio) {
  if (!audio) {
    setPlaybackError("再生対象の audio 要素が見つかりません。");
    return;
  }
  if (!audio.currentSrc && !audio.src) {
    setPlaybackError("再生対象の音声URLが空です。もう一度生成してください。");
    return;
  }
  if (audio.paused) {
    audioController.play(audio);
    return;
  }
  audio.pause();
}

function attachAudioButtons() {
  if (els.normalAudio) {
    els.normalAudio.controls = true;
  }
  all('[data-audio-target]').forEach((button) => {
    button.onclick = () => playAudioElement(document.getElementById(button.dataset.audioTarget));
  });
  all('[data-dynamic-audio]').forEach((button) => {
    button.onclick = () => playAudioElement(document.getElementById(`compareAudio-${button.dataset.dynamicAudio}`));
  });
  all('[data-history-audio]').forEach((button) => {
    button.onclick = () => {
      const url = String(button.dataset.historyAudio || "").trim();
      if (!url) {
        setPlaybackError("履歴の音声URLがありません。");
        return;
      }
      const absoluteUrl = new URL(url, location.href).href;
      if (normalHistoryAudio?.src === absoluteUrl && !normalHistoryAudio.paused) {
        normalHistoryAudio.pause();
        return;
      }
      all('[data-history-audio]').forEach((item) => { item.textContent = "▶"; });
      normalHistoryAudio?.pause();
      const audio = new Audio(url);
      normalHistoryAudio = audio;
      button.textContent = "❚❚";
      const resetButton = () => { if (normalHistoryAudio === audio) button.textContent = "▶"; };
      audio.addEventListener("pause", resetButton);
      audio.addEventListener("ended", resetButton);
      audio.play().catch((error) => {
        resetButton();
        setPlaybackError(`履歴音声の再生に失敗しました: ${error.message || error}`);
      });
    };
  });
}

async function loadInitialData() {
  try {
    const initialFetchOptions = { signal: AbortSignal.timeout(INITIAL_DATA_TIMEOUT_MS) };
    const [modelsPayload, voicesPayload, rvcPayload] = await Promise.all([
      ttsApi.models(initialFetchOptions),
      ttsApi.referenceVoices(initialFetchOptions),
      ttsApi.rvcDefaults(initialFetchOptions),
    ]);
    const models = Array.isArray(modelsPayload.models) ? modelsPayload.models : [];
    const voices = Array.isArray(voicesPayload.voices) ? voicesPayload.voices : [];
    modelsById = new Map(models.map((model) => [modelId(model), model]));
    voicesById = new Map(voices.map((voice) => [voice.voiceId, voice]));
    defaultReferenceVoice = String(voicesPayload.defaultReferenceVoice || "").trim();
    rvcDefaults = rvcPayload.defaults || null;
    applyRvcModelCatalog(rvcPayload, { preserveSelection: false });
    fillModelSelect();
    fillVoiceSelect(els.normalVoice);
    fillVoiceSelect(els.compareVoice);
    fillVoiceSelect(els.rvcVoice);
    applySavedNormalFormSettings();
    applyRvcDefaults();
    renderCompareModelCards();
    applySavedCompareFormSettings();
    applySavedRvcFormSettings();
    updateNormalModelInfo();
    updateCompareButtonState();
    updateRvcModelInfo();
    updateReferencePreviewButtons();
    updateRvcReferencePreviewButton();
    sharedUi.setServiceState("running");
  } catch (error) {
    const message = error?.name === "TimeoutError"
      ? "初期化APIが10秒以内に応答しませんでした。frontendとbackendの起動状態を確認してください。"
      : humanizeError(error);
    setStatus(els.normalStatus, `初期化に失敗しました: ${message}`, true);
    setStatus(els.compareStatus, `初期化に失敗しました: ${message}`, true);
    setStatus(els.rvcStatus, `初期化に失敗しました: ${message}`, true); sharedUi.setServiceState("error");
  }
}

function bindEvents() {
  document.querySelectorAll('[data-tab]').forEach((el) => el.addEventListener("click", () => switchTab(el.dataset.tab)));
  for (const controller of Object.values(pageControllers)) controller.bind();

  for (const [scope, controls] of chunkControls) {
    [controls.target, controls.hardMax]
      .filter(Boolean)
      .forEach((input) => input.addEventListener("input", () => updateChunkPreview(scope)));
    controls.presets.forEach((button) => button.addEventListener("click", () => applyChunkPreset(scope, button.dataset.chunkPreset || 240)));
    controls.previewToggle?.addEventListener("click", () => {
      if (!controls.preview) return;
      controls.preview.hidden = !controls.preview.hidden;
      controls.previewToggle.setAttribute("aria-expanded", String(!controls.preview.hidden));
      controls.previewToggle.textContent = controls.preview.hidden ? "分割を確認" : "閉じる";
      updateChunkPreview(scope);
    });
  }

  [els.normalVoice, els.compareVoice, els.rvcVoice]
    .filter(Boolean)
    .forEach((el) => el.addEventListener("input", () => {
      updateReferencePreviewButtons();
      updateRvcReferencePreviewButton();
    }));

  [
    [els.normalLogCopy, els.normalLog, els.normalStatus],
    [els.compareLogCopy, els.compareLog, els.compareStatus],
    [els.rvcLogCopy, els.rvcLog, els.rvcStatus],
  ].forEach(([button, log, status]) => button?.addEventListener("click", async () => {
    const copied = await copyText(log?.textContent || "");
    setStatus(status, copied ? "診断ログをコピーしました。AIへの質問に貼り付けられます。" : "診断ログをコピーできませんでした。", !copied);
  }));

  window.addEventListener("local-tts:reference-voice-renamed", (event) => {
    const previousVoiceId = String(event.detail?.previousVoiceId || "").trim();
    const voiceId = String(event.detail?.voiceId || "").trim();
    if (!previousVoiceId || !voiceId) return;
    pendingReferenceVoiceRename = {
      previousVoiceId,
      voiceId,
      normalSelected: els.normalVoice?.value === previousVoiceId,
      compareSelected: els.compareVoice?.value === previousVoiceId,
      rvcSelected: els.rvcVoice?.value === previousVoiceId,
    };
    migrateReferenceVoiceState(previousVoiceId, voiceId);
  });
  window.addEventListener("local-tts:reference-voices-changed", async () => {
    try {
      await refreshReferenceVoices();
      const rename = pendingReferenceVoiceRename;
      if (!rename) return;
      if (rename.normalSelected && Array.from(els.normalVoice?.options || []).some((option) => option.value === rename.voiceId && !option.disabled)) els.normalVoice.value = rename.voiceId;
      if (rename.compareSelected && Array.from(els.compareVoice?.options || []).some((option) => option.value === rename.voiceId && !option.disabled)) els.compareVoice.value = rename.voiceId;
      if (rename.rvcSelected && Array.from(els.rvcVoice?.options || []).some((option) => option.value === rename.voiceId && !option.disabled)) els.rvcVoice.value = rename.voiceId;
      saveNormalFormSettings();
      saveCompareFormSettings();
      saveRvcFormSettings();
      updateNormalModelInfo({ preserveStatus: true });
      updateCompareButtonState();
      updateRvcModelInfo();
      pendingReferenceVoiceRename = null;
    } catch (error) {
      setStatus(els.normalStatus, `参照音声の再読込に失敗しました: ${humanizeError(error)}`, true);
    }
  });
  window.addEventListener("local-tts:use-reference-voice", async (event) => {
    const voiceId = String(event.detail?.voiceId || "").trim();
    if (!voiceId) return;
    switchTab("normal");
    try {
      await refreshReferenceVoices();
      const option = Array.from(els.normalVoice?.options || []).find((item) => item.value === voiceId && !item.disabled);
      if (!option) throw new Error("登録した参照音声を一覧から確認できませんでした。再読込してください。");
      els.normalVoice.value = voiceId;
      const model = selectedNormalModel();
      if (supportsReference(model)) {
        if (els.normalUseReference) els.normalUseReference.checked = true;
        updateNormalReferenceUi(model);
        updateNormalModelInfo({ preserveStatus: true });
        setStatus(els.normalStatus, `参照音声「${voiceId}」を選択しました。文章を入力して生成できます。`);
      } else {
        setStatus(els.normalStatus, `参照音声「${voiceId}」を選択しました。参照音声対応のモデルを選んでください。`, true);
      }
      saveNormalFormSettings();
      updateReferencePreviewButtons();
    } catch (error) {
      setStatus(els.normalStatus, `参照音声を通常生成へ設定できませんでした: ${humanizeError(error)}`, true);
    }
  });
  window.addEventListener("local-tts:history-clear-all", () => {
    normalHistory = []; compareHistory = []; rvcHistory = [];
    [[NORMAL_HISTORY_KEY, normalHistory], [COMPARE_HISTORY_KEY, compareHistory], [RVC_HISTORY_KEY, rvcHistory]].forEach(([key, value]) => saveList(key, value));
    [renderNormalHistory, renderCompareHistory, renderRvcHistory].forEach((render) => render());
  });
  attachAudioButtons();
  const previewAudio = ensureReferencePreviewAudio();
  previewAudio.addEventListener("ended", resetReferencePreviewButtons);
  previewAudio.addEventListener("pause", () => {
    if (activeReferencePreviewButton && !previewAudio.ended) return;
    resetReferencePreviewButtons();
  });
  previewAudio.addEventListener("error", () => {
    resetReferencePreviewButtons();
    setPlaybackError("参照音声の再生に失敗しました。");
  });
}

updateTextCounts();
renderNormalHistory();
renderCompareHistory();
renderRvcHistory();
renderIrodoriEmojiPalettes();
if (els.rvcText?.value) { els.normalText.value = els.rvcText.value; els.compareText.value = els.rvcText.value; }
CHUNK_SCOPES.forEach(applySavedChunkSettings);
refreshTextCountsAndChunkPreview();
bindEvents();
window.LocalTtsAvatar?.init();
const pageParam = new URLSearchParams(location.search).get("page");
const initialPage = location.hash === "#compare" || pageParam === "compare"
  ? "compare"
  : location.hash === "#rvc" || pageParam === "rvc" ? "rvc"
    : location.hash === "#history" || pageParam === "history" ? "history"
      : location.hash === "#voices" || pageParam === "voices" ? "voices"
        : location.hash === "#guide" || pageParam === "guide" ? "guide" : "normal";
for (const el of [els.normalLanguage, els.compareLanguage, els.rvcLanguage].filter(Boolean)) { const field = el.closest(".field"); if (field) field.style.display = "none"; }
switchTab(initialPage, false);
loadRvcMicDevices();
loadInitialData();
