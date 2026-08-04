const rvcEls = {
  rvcModel: document.querySelector("#rvcModelSelect"),
  rvcVoiceModel: document.querySelector("#rvcVoiceModelSelect"),
  rvcMissingModelPanel: document.querySelector("#rvcMissingModelPanel"),
  rvcWorkspace: document.querySelector("#rvcWorkspace"),
  rvcModelDirectoryPath: document.querySelector("#rvcModelDirectoryPath"),
  rvcModelGuideLink: document.querySelector("#rvcModelGuideLink"),
  rvcModelReload: document.querySelector("#rvcModelReloadButton"),
  rvcModelScanNote: document.querySelector("#rvcModelScanNote"),
  rvcVoice: document.querySelector("#rvcReferenceVoiceSelect"),
  rvcReferencePreview: document.querySelector("#rvcReferencePreviewButton"),
  rvcInputSources: Array.from(document.querySelectorAll('input[name="rvcInputSource"]')),
  rvcTtsControls: document.querySelector("#rvcTtsControls"),
  rvcFileSourceControls: document.querySelector("#rvcFileSourceControls"),
  rvcExternalAudioPathHistory: document.querySelector("#rvcExternalAudioPathHistory"),
  rvcMicControls: document.querySelector("#rvcMicControls"),
  rvcMicScript: document.querySelector("#rvcMicScriptInput"),
  rvcMicScriptCount: document.querySelector("#rvcMicScriptCount"),
  rvcMicDevice: document.querySelector("#rvcMicDeviceSelect"),
  rvcMicStart: document.querySelector("#rvcMicStartButton"),
  rvcMicStop: document.querySelector("#rvcMicStopButton"),
  rvcMicTimer: document.querySelector("#rvcMicTimer"),
  rvcMicBadge: document.querySelector("#rvcMicBadge"),
  rvcMicAudio: document.querySelector("#rvcMicAudio"),
  rvcMicPath: document.querySelector("#rvcMicPath"),
  rvcMicRerecord: document.querySelector("#rvcMicRerecordButton"),
  rvcMicUse: document.querySelector("#rvcMicUseButton"),
  rvcMicHistory: document.querySelector("#rvcMicHistorySelect"),
  rvcExternalAudioPath: document.querySelector("#rvcExternalAudioPathInput"),
  rvcDemucsModel: document.querySelector("#rvcDemucsModelInput"),
  rvcText: document.querySelector("#rvcTextInput"),
  rvcAdvancedGuidance: document.querySelector("#rvcAdvancedGuidance"),
  rvcAdvancedSummary: document.querySelector("#rvcAdvancedSummary"),
  rvcInstructionField: document.querySelector("#rvcInstructionField"),
  rvcInstructionRequirement: document.querySelector("#rvcInstructionRequirement"),
  rvcInstruction: document.querySelector("#rvcInstructionInput"),
  rvcLanguage: document.querySelector("#rvcLanguageInput"),
  rvcSeed: document.querySelector("#rvcSeedInput"),
  rvcSeedAutoIncrement: document.querySelector("#rvcSeedAutoIncrementInput"),
  rvcAutoPlay: document.querySelector("#rvcAutoPlayInput"),
  rvcAdvancedSettings: document.querySelector("#rvcAdvancedSettings"),
  rvcChunkPanel: document.querySelector("#rvcChunkPanel"),
  rvcChunkPreview: document.querySelector("#rvcChunkPreview"),
  rvcTextCount: document.querySelector("#rvcTextCount"),
  rvcInstructionCount: document.querySelector("#rvcInstructionCount"),
  rvcIndexRate: document.querySelector("#rvcIndexRateInput"),
  rvcIndexRatePreset: document.querySelector("#rvcIndexRatePresetSelect"),
  rvcF0Method: document.querySelector("#rvcF0MethodInput"),
  rvcF0UpKey: document.querySelector("#rvcF0UpKeyInput"),
  rvcF0UpKeyPreset: document.querySelector("#rvcF0UpKeyPresetSelect"),
  rvcFilterRadius: document.querySelector("#rvcFilterRadiusInput"),
  rvcResampleSr: document.querySelector("#rvcResampleSrInput"),
  rvcRmsMixRate: document.querySelector("#rvcRmsMixRateInput"),
  rvcProtect: document.querySelector("#rvcProtectInput"),
  rvcProtectPreset: document.querySelector("#rvcProtectPresetSelect"),
  rvcModelPath: document.querySelector("#rvcModelPathInput"),
  rvcIndexPath: document.querySelector("#rvcIndexPathInput"),
  rvcConvert: document.querySelector("#rvcConvertButton"),
  rvcStatus: document.querySelector("#rvcStatusText"),
  rvcIntermediateTitle: document.querySelector("#rvcIntermediateTitle"),
  rvcIntermediateAudio: document.querySelector("#rvcIntermediateAudio"),
  rvcConvertedAudio: document.querySelector("#rvcConvertedAudio"),
  rvcDenoiseButton: document.querySelector("#rvcDenoiseButton"),
  rvcDenoisedCard: document.querySelector("#rvcDenoisedCard"),
  rvcDenoisedAudio: document.querySelector("#rvcDenoisedAudio"),
  rvcIntermediatePath: document.querySelector("#rvcIntermediatePath"),
  rvcConvertedPath: document.querySelector("#rvcConvertedPath"),
  rvcDenoisedPath: document.querySelector("#rvcDenoisedPath"),
  rvcIntermediateDownload: document.querySelector("#rvcIntermediateDownload"),
  rvcConvertedDownload: document.querySelector("#rvcConvertedDownload"),
  rvcDenoisedDownload: document.querySelector("#rvcDenoisedDownload"),
  rvcIntermediateBadge: document.querySelector("#rvcIntermediateBadge"),
  rvcConvertedBadge: document.querySelector("#rvcConvertedBadge"),
  rvcDenoisedBadge: document.querySelector("#rvcDenoisedBadge"),
  rvcLog: document.querySelector("#rvcLogBox"),
  rvcLogCopy: document.querySelector("#rvcLogCopyButton"),
  rvcHistory: document.querySelector("#rvcHistoryList"),
  rvcClearHistory: document.querySelector("#rvcClearHistoryButton"),
};

let rvcGenerationActive = false;
let rvcVoiceModels = [];
let rvcModelRoot = "";

function selectedRvcVoiceModel() {
  return rvcVoiceModels.find((model) => model.id === els.rvcVoiceModel?.value) || null;
}

function syncSelectedRvcModelPaths() {
  const model = selectedRvcVoiceModel();
  if (els.rvcModelPath) els.rvcModelPath.value = model?.modelPath || "";
  if (els.rvcIndexPath) els.rvcIndexPath.value = model?.indexPath || "";
  return model;
}

function renderRvcModelAvailability() {
  const readyModels = rvcVoiceModels.filter((model) => model.ready);
  const hasModels = readyModels.length > 0;
  if (els.rvcMissingModelPanel) els.rvcMissingModelPanel.hidden = hasModels;
  if (els.rvcWorkspace) els.rvcWorkspace.hidden = !hasModels;
  if (els.rvcModelDirectoryPath) els.rvcModelDirectoryPath.textContent = rvcModelRoot || "models\\rvc";
  if (els.rvcModelScanNote) {
    const incomplete = rvcVoiceModels.filter((model) => !model.ready);
    els.rvcModelScanNote.innerHTML = incomplete.length
      ? `<strong>未完成のフォルダー:</strong> ${incomplete.map((model) => `${escapeHtml(model.label)}（${escapeHtml(model.errorReason)}）`).join("、")}`
      : "";
  }
  if (els.rvcConvert) els.rvcConvert.disabled = !hasModels || rvcGenerationActive;
}

function applyRvcModelCatalog(payload = {}, { preserveSelection = true } = {}) {
  const previous = preserveSelection ? String(els.rvcVoiceModel?.value || "") : "";
  rvcVoiceModels = Array.isArray(payload.models) ? payload.models : [];
  rvcModelRoot = String(payload.modelRoot || rvcModelRoot || "");
  if (els.rvcModelGuideLink && payload.guideUrl) els.rvcModelGuideLink.href = payload.guideUrl;
  const readyModels = rvcVoiceModels.filter((model) => model.ready);
  if (els.rvcVoiceModel) {
    els.rvcVoiceModel.innerHTML = readyModels.length
      ? readyModels.map((model) => `<option value="${escapeHtml(model.id)}">${escapeHtml(model.label)}</option>`).join("")
      : '<option value="">RVCモデルがありません</option>';
    const defaultByPath = readyModels.find((model) => (
      model.modelPath === rvcDefaults?.modelPath && model.indexPath === rvcDefaults?.indexPath
    ));
    const next = readyModels.find((model) => model.id === previous) || defaultByPath || readyModels[0] || null;
    els.rvcVoiceModel.value = next?.id || "";
    els.rvcVoiceModel.disabled = !next || rvcGenerationActive;
  }
  syncSelectedRvcModelPaths();
  renderRvcModelAvailability();
}

async function refreshRvcModelCatalog() {
  if (els.rvcModelReload) els.rvcModelReload.disabled = true;
  try {
    const payload = await ttsApi.rvcDefaults({ signal: AbortSignal.timeout(INITIAL_DATA_TIMEOUT_MS) });
    rvcDefaults = payload.defaults || rvcDefaults;
    applyRvcModelCatalog(payload);
    applyRvcDefaults();
    applySavedRvcFormSettings();
    updateRvcModelInfo();
  } catch (error) {
    if (els.rvcModelScanNote) els.rvcModelScanNote.textContent = `再読み込みに失敗しました: ${humanizeError(error)}`;
  } finally {
    if (els.rvcModelReload) els.rvcModelReload.disabled = false;
  }
}

function setRvcGenerationActive(active) {
  rvcGenerationActive = Boolean(active);
  if (els.rvcModel) els.rvcModel.disabled = rvcGenerationActive;
  if (els.rvcVoiceModel) els.rvcVoiceModel.disabled = rvcGenerationActive || !selectedRvcVoiceModel();
  renderRvcModelAvailability();
}

function saveRvcFormSettings() {
  saveObject(RVC_FORM_SETTINGS_KEY, {
    model: els.rvcModel?.value || "",
    rvcVoiceModel: els.rvcVoiceModel?.value || "",
    voice: els.rvcVoice?.value || "",
    seed: normalizedStoredSeed(els.rvcSeed),
    autoIncrement: Boolean(els.rvcSeedAutoIncrement?.checked),
    autoPlay: Boolean(els.rvcAutoPlay?.checked),
  });
}

function applySavedRvcFormSettings() {
  const saved = loadObject(RVC_FORM_SETTINGS_KEY, {});
  if (els.rvcSeed) els.rvcSeed.value = String(Number.isInteger(saved.seed) && saved.seed >= 0 ? saved.seed : 1);
  if (els.rvcSeedAutoIncrement && typeof saved.autoIncrement === "boolean") els.rvcSeedAutoIncrement.checked = saved.autoIncrement;
  if (els.rvcAutoPlay && typeof saved.autoPlay === "boolean") els.rvcAutoPlay.checked = saved.autoPlay;
  if (els.rvcModel && saved.model && Array.from(els.rvcModel.options).some((option) => option.value === saved.model && !option.disabled)) els.rvcModel.value = saved.model;
  if (els.rvcVoiceModel && saved.rvcVoiceModel && Array.from(els.rvcVoiceModel.options).some((option) => option.value === saved.rvcVoiceModel)) els.rvcVoiceModel.value = saved.rvcVoiceModel;
  if (els.rvcVoice && saved.voice && Array.from(els.rvcVoice.options).some((option) => option.value === saved.voice && !option.disabled)) els.rvcVoice.value = saved.voice;
  syncSelectedRvcModelPaths();
}

function selectedRvcModel() {
  return modelsById.get(String(els.rvcModel?.value || "").trim()) || null;
}

function resetRvcResult() {
  currentRvcConvertedFilename = "";
  if (els.rvcIntermediateAudio) els.rvcIntermediateAudio.removeAttribute("src");
  if (els.rvcConvertedAudio) els.rvcConvertedAudio.removeAttribute("src");
  if (els.rvcDenoisedAudio) els.rvcDenoisedAudio.removeAttribute("src");
  if (els.rvcIntermediatePath) els.rvcIntermediatePath.textContent = "-";
  if (els.rvcConvertedPath) els.rvcConvertedPath.textContent = "-";
  if (els.rvcDenoisedPath) els.rvcDenoisedPath.textContent = "-";
  if (els.rvcIntermediateDownload) els.rvcIntermediateDownload.href = "#";
  if (els.rvcConvertedDownload) els.rvcConvertedDownload.href = "#";
  if (els.rvcDenoisedDownload) els.rvcDenoisedDownload.href = "#";
  if (els.rvcDenoiseButton) { els.rvcDenoiseButton.hidden = true; els.rvcDenoiseButton.disabled = true; }
  if (els.rvcDenoisedCard) els.rvcDenoisedCard.hidden = true;
}

function setRvcResult(result) {
  const intermediate = result.intermediate || {};
  const converted = result.converted || {};
  if (intermediate.url) {
    els.rvcIntermediateAudio.src = intermediate.url;
    els.rvcIntermediateDownload.href = intermediate.url;
    els.rvcIntermediatePath.textContent = intermediate.path || intermediate.filename || "-";
    const inputSource = result.input?.source || selectedRvcInputSource();
    const inputBadgeText = inputSource === "mic" ? "入力に設定済み" : inputSource === "file" ? "入力済み" : "生成済み";
    setBadge(els.rvcIntermediateBadge, inputBadgeText, "success");
  }
  if (converted.url) {
    currentRvcConvertedFilename = converted.filename || "";
    els.rvcConvertedAudio.src = converted.url;
    els.rvcConvertedDownload.href = converted.url;
    els.rvcConvertedPath.textContent = converted.path || converted.filename || "-";
    if (els.rvcDenoiseButton) { els.rvcDenoiseButton.hidden = false; els.rvcDenoiseButton.disabled = !currentRvcConvertedFilename; }
    setBadge(els.rvcConvertedBadge, "変換済み", "success");
  }
  setRvcLog({
    id: result.id,
    intermediate: result.intermediate,
    converted: result.converted,
    rvc: result.rvc,
    tts: {
      model: result.tts?.result?.model,
      runtime: result.tts?.result?.runtime,
      voiceId: result.tts?.result?.voiceId,
      copiedFrom: result.tts?.copiedFrom
    }
  });
}

async function playRvcResultIfEnabled() {
  if (!els.rvcAutoPlay?.checked || !els.rvcConvertedAudio?.src) return false;
  try {
    els.rvcIntermediateAudio?.pause();
    els.rvcDenoisedAudio?.pause();
    await els.rvcConvertedAudio.play();
    return true;
  } catch (error) {
    setStatus(els.rvcStatus, `RVC変換は完了しましたが、自動再生できませんでした: ${error.message || error}`, true);
    return false;
  }
}

async function denoiseCurrentRvcOutput() {
  if (!currentRvcConvertedFilename) return;
  els.rvcDenoiseButton.disabled = true;
  els.rvcDenoisedCard.hidden = false;
  setBadge(els.rvcDenoisedBadge, "処理中", "pending");
  setStatus(els.rvcStatus, "RVC変換後音声の軽いノイズ除去版を作成中です。");
  try {
    const payload = await ttsApi.denoiseRvc({ filename: currentRvcConvertedFilename });
    const result = payload.result || {};
    const denoised = result.denoised || {};
    els.rvcDenoisedAudio.src = denoised.url || "";
    els.rvcDenoisedDownload.href = denoised.url || "#";
    els.rvcDenoisedPath.textContent = denoised.path || denoised.filename || "-";
    setBadge(els.rvcDenoisedBadge, "生成済み", "success");
    setStatus(els.rvcStatus, "ノイズ除去版を作成しました。元音声と聞き比べて、良い方を使ってください。");
    setRvcLog({ postDenoise: result });
  } catch (error) {
    setBadge(els.rvcDenoisedBadge, "失敗", "failed");
    setStatus(els.rvcStatus, humanizeError(error), true);
    setRvcLog({ postDenoiseError: error.message || String(error), payload: error?.payload || null });
  } finally {
    els.rvcDenoiseButton.disabled = false;
  }
}

function buildRvcTtsInputBody() {
  const model = selectedRvcModel();
  const voice = selectedVoice(els.rvcVoice);
  const error = validateRequest(model, voice, els.rvcText.value, els.rvcInstruction.value);
  if (error) return { error };
  const body = attachChunking(
    buildRequestBody(model, voice, els.rvcText.value, els.rvcInstruction.value, els.rvcLanguage.value, els.rvcSeed.value),
    chunkSettingsFromForm("rvc").chunking
  );
  return { body, modelId: modelId(model) };
}

async function generateRvc() {
  const conversionModel = syncSelectedRvcModelPaths();
  if (!conversionModel) {
    setStatus(els.rvcStatus, "RVCモデルがありません。モデルを配置して再読み込みしてください。", true);
    return;
  }
  const source = selectedRvcInputSource();
  if (source === "tts") normalizeSeedInput(els.rvcSeed);
  saveRvcFormSettings();
  let body = {};
  let ttsModelId = "";
  if (source === "tts") {
    const built = buildRvcTtsInputBody();
    if (built.error) { setStatus(els.rvcStatus, built.error, true); return; }
    ttsModelId = built.modelId;
    body = built.body;
  } else if (source === "mic") {
    if (!currentRvcMicRecording?.path) {
      setStatus(els.rvcStatus, "先にマイク録音してください。", true);
      return;
    }
  } else if (!String(els.rvcExternalAudioPath.value || "").trim()) {
    setStatus(els.rvcStatus, "入力音声のパスを入力してください。", true);
    return;
  }
  if (source === "file") rememberRvcFilePath();
  if (!body.rvc) body.rvc = rvcParamsFromForm();
  const hasExistingIntermediate = Boolean(els.rvcIntermediateAudio?.getAttribute("src"));
  const hasExistingConverted = Boolean(els.rvcConvertedAudio?.getAttribute("src"));
  setRvcGenerationActive(true);
  if (!hasExistingIntermediate) setBadge(els.rvcIntermediateBadge, "生成中", "pending");
  if (!hasExistingConverted) setBadge(els.rvcConvertedBadge, "待機中", "pending");
  const prepareMessage = source === "tts"
    ? (ttsModelId.startsWith("qwen3_tts")
      ? "TTS入力音声を生成中です。Qwenは長文・参照音声付きだと数分かかることがあります。完了後にRVC変換へ進みます。"
      : "TTS入力音声を生成中です。完了後にRVC変換へ進みます。")
    : source === "mic"
      ? "保存済みのマイク録音を入力wavとして使います。録り直すまで同じ音声で何度でも変換できます。"
      : "入力音声ファイルを準備中です。wav以外は内部でwavへ変換してからRVC変換へ進みます。";
  setStatus(els.rvcStatus, prepareMessage);
  setRvcLog({ request: body });
  try {
    const payload = await ttsApi.convertRvc(body);
    const result = payload.result || {};
    setRvcResult(result);
    setStatus(els.rvcStatus, "RVC変換が完了しました。");
    addRvcHistory(createRvcHistoryItem(source, body, result));
    window.dispatchEvent(new CustomEvent("local-tts:history-record", {
      detail: {
        type: "rvc",
        status: "success",
        createdAt: new Date().toISOString(),
        text: source === "tts" ? body.text : source === "mic" ? (currentRvcMicRecording?.scriptText || els.rvcMicScript?.value || "") : String(els.rvcExternalAudioPath?.value || ""),
        instruction: source === "tts" ? (body.instruction || "") : "",
        model: source === "tts" ? body.model : "",
        referenceVoice: source === "tts" ? (body.voiceId || "") : "",
        seed: body.seed ?? "",
        indexRate: body.rvc?.indexRate ?? "",
        f0upKey: body.rvc?.f0upKey ?? "",
        protect: body.rvc?.protect ?? "",
        inputSource: source,
        intermediateAudioUrl: result.intermediate?.url || "",
        convertedAudioUrl: result.converted?.url || "",
        filePath: result.converted?.path || result.converted?.filename || "",
        raw: { request: body, result }
      }
    }));
    incrementRvcSeedIfNeeded(source);
    await playRvcResultIfEnabled();
  } catch (error) {
    const payload = error?.payload || {};
    const errorMessage = humanizeError(error);
    if (!hasExistingIntermediate) setBadge(els.rvcIntermediateBadge, "確認必要", "warning");
    if (!hasExistingConverted) setBadge(els.rvcConvertedBadge, "失敗", "failed");
    setStatus(els.rvcStatus, errorMessage, true);
    if (payload.partialResult?.intermediate?.url) setRvcResult(payload.partialResult);
    setRvcLog({
      request: body,
      payload,
      partialResult: payload.partialResult || null,
      error: payload.errorMessage || payload.error || error.message || String(error),
      stdout: payload.stdout || "",
      stderr: payload.stderr || "",
      command: payload.command || null
    });
    addRvcHistory(createRvcHistoryItem(source, body, payload.partialResult || {}, "failed", errorMessage));
    window.dispatchEvent(new CustomEvent("local-tts:history-record", {
      detail: {
        type: "rvc",
        status: "failed",
        createdAt: new Date().toISOString(),
        text: source === "tts" ? body.text : source === "mic" ? (currentRvcMicRecording?.scriptText || els.rvcMicScript?.value || "") : String(els.rvcExternalAudioPath?.value || ""),
        instruction: source === "tts" ? (body.instruction || "") : "",
        model: source === "tts" ? body.model : "",
        referenceVoice: source === "tts" ? (body.voiceId || "") : "",
        seed: body.seed ?? "",
        indexRate: body.rvc?.indexRate ?? "",
        f0upKey: body.rvc?.f0upKey ?? "",
        protect: body.rvc?.protect ?? "",
        inputSource: source,
        intermediateAudioUrl: payload.partialResult?.intermediate?.url || "",
        convertedAudioUrl: payload.partialResult?.converted?.url || "",
        filePath: payload.partialResult?.converted?.path || payload.partialResult?.converted?.filename || "",
        error: errorMessage,
        raw: { request: body, partialResult: payload.partialResult || null, error: errorMessage, stdout: payload.stdout || "", stderr: payload.stderr || "", command: payload.command || null }
      }
    }));
  } finally {
    setRvcGenerationActive(false);
    updateRvcModelInfo();
  }
}

function createRvcHistoryItem(source, body, result = {}, status = "success", error = "") {
  const externalPath = String(body?.rvc?.externalAudioPath || els.rvcExternalAudioPath?.value || "").trim();
  return {
    createdAt: new Date().toISOString(),
    status,
    inputSource: source,
    text: source === "tts"
      ? String(body.text || "")
      : source === "mic"
        ? String(currentRvcMicRecording?.scriptText || els.rvcMicScript?.value || "")
        : externalPath,
    instruction: source === "tts" ? String(body.instruction || "") : "",
    model: source === "tts" ? String(body.model || "") : "",
    referenceVoice: source === "tts" ? String(body.voiceId || "") : "",
    rvcModelId: String(body?.rvc?.modelId || ""),
    rvcModelLabel: String(body?.rvc?.modelLabel || ""),
    seed: body.seed ?? "",
    indexRate: body?.rvc?.indexRate ?? "",
    f0upKey: body?.rvc?.f0upKey ?? "",
    protect: body?.rvc?.protect ?? "",
    externalAudioPath: externalPath,
    intermediateAudioUrl: String(result.intermediate?.url || ""),
    convertedAudioUrl: String(result.converted?.url || ""),
    filePath: String(result.converted?.path || result.converted?.filename || ""),
    error,
    request: body && typeof body === "object" ? JSON.parse(JSON.stringify(body)) : {},
  };
}

function addRvcHistory(item) {
  rvcHistory = [item, ...rvcHistory].slice(0, 8);
  saveList(RVC_HISTORY_KEY, rvcHistory);
  renderRvcHistory();
}

function restoreRvcHistoryItem(index) {
  const item = rvcHistory[index];
  if (!item) return;
  const historyRvcModelId = String(item.rvcModelId || item.request?.rvc?.modelId || "");
  if (historyRvcModelId && Array.from(els.rvcVoiceModel?.options || []).some((option) => option.value === historyRvcModelId)) {
    els.rvcVoiceModel.value = historyRvcModelId;
    syncSelectedRvcModelPaths();
  }
  let source = ["tts", "file", "mic"].includes(item.inputSource) ? item.inputSource : "tts";
  if (source === "mic" && item.externalAudioPath) {
    const recording = rvcMicHistory.find((entry) => (entry.path || entry.filename) === item.externalAudioPath);
    if (recording) setCurrentRvcMicRecording(recording, { save: false });
    else currentRvcMicRecording = { path: item.externalAudioPath, url: item.intermediateAudioUrl || "", scriptText: item.text || "" };
  }
  els.rvcInputSources.forEach((input) => { input.checked = input.value === source; });
  if (source === "tts") {
    if (item.model && Array.from(els.rvcModel.options).some((option) => option.value === item.model && !option.disabled)) els.rvcModel.value = item.model;
    if (item.referenceVoice && Array.from(els.rvcVoice.options).some((option) => option.value === item.referenceVoice && !option.disabled)) els.rvcVoice.value = item.referenceVoice;
    if (item.text) els.rvcText.value = item.text;
    if (item.instruction != null) els.rvcInstruction.value = item.instruction;
    if (item.seed !== "" && item.seed != null) els.rvcSeed.value = String(item.seed);
    if (item.request?.chunking?.softChunkChars) applyChunkPreset("rvc", item.request.chunking.softChunkChars);
  } else if (item.externalAudioPath && els.rvcExternalAudioPath) {
    els.rvcExternalAudioPath.value = item.externalAudioPath;
  }
  if (item.indexRate !== "" && item.indexRate != null) {
    els.rvcIndexRate.value = String(item.indexRate);
    if (Array.from(els.rvcIndexRatePreset.options).some((option) => option.value === String(item.indexRate))) els.rvcIndexRatePreset.value = String(item.indexRate);
  }
  if (item.f0upKey !== "" && item.f0upKey != null) {
    els.rvcF0UpKey.value = String(item.f0upKey);
    if (Array.from(els.rvcF0UpKeyPreset.options).some((option) => option.value === String(item.f0upKey))) els.rvcF0UpKeyPreset.value = String(item.f0upKey);
  }
  if (item.protect !== "" && item.protect != null) {
    els.rvcProtect.value = String(item.protect);
    if (Array.from(els.rvcProtectPreset.options).some((option) => option.value === String(item.protect))) els.rvcProtectPreset.value = String(item.protect);
  }
  saveRvcInputSource(source);
  refreshTextCountsAndChunkPreview();
  saveRvcFormSettings();
  updateRvcModelInfo();
  setStatus(els.rvcStatus, "RVC履歴の入力元と設定を戻しました。");
}

function renderRvcHistory() {
  if (!els.rvcHistory) return;
  const sourceLabel = (source) => source === "mic" ? "マイク入力" : source === "file" ? "音声ファイル" : "TTS入力";
  els.rvcHistory.innerHTML = rvcHistory.length ? rvcHistory.map((item, index) => {
    const audioUrl = item.convertedAudioUrl || "";
    const title = item.model ? `${sourceLabel(item.inputSource)} / ${modelLabel(item.model, item.model)}` : sourceLabel(item.inputSource);
    const chips = [
      item.status === "failed" ? "失敗" : "成功",
      item.rvcModelLabel ? `RVC ${item.rvcModelLabel}` : "",
      item.indexRate !== "" ? `似せ度 ${item.indexRate}` : "",
      item.f0upKey !== "" ? `音程 ${Number(item.f0upKey) >= 0 ? "+" : ""}${item.f0upKey}` : "",
    ].filter(Boolean);
    return `
      <article class="mini-history-item rich-history-item rvc-history-item">
        ${audioUrl ? `<button class="mini-history-play" type="button" data-history-audio="${escapeHtml(audioUrl)}" aria-label="RVC変換後音声を再生">▶</button>` : '<span class="mini-history-icon" aria-hidden="true">◇</span>'}
        <div class="mini-history-content">
          <div class="mini-history-title"><strong>${escapeHtml(title)}</strong><small>${escapeHtml(new Date(item.createdAt).toLocaleString("ja-JP"))}</small></div>
          <p class="mini-history-text">${escapeHtml(String(item.text || item.filePath || "入力情報なし").trim())}</p>
          <div class="mini-history-chips">${chips.map((chip) => `<span>${escapeHtml(chip)}</span>`).join("")}</div>
          <button class="link-button mini-history-restore" type="button" data-restore-rvc-history="${index}">入力元と設定を戻す</button>
        </div>
      </article>`;
  }).join("") : '<div class="empty-state">RVC変換履歴はありません。変換後は入力元、設定、生成音声をここから確認できます。</div>';
  attachAudioButtons();
}

function incrementRvcSeedIfNeeded(source) {
  if (source !== "tts") return false;
  const incremented = incrementSeedInputIfNeeded(els.rvcSeed, els.rvcSeedAutoIncrement, updateRvcModelInfo);
  saveRvcFormSettings();
  return incremented;
}

function loadSavedRvcInputSource() {
  try {
    const value = String(localStorage.getItem(RVC_INPUT_SOURCE_KEY) || "").trim();
    return value === "tts" || value === "file" || value === "mic" ? value : "";
  } catch {
    return "";
  }
}

function saveRvcInputSource(value = selectedRvcInputSource()) {
  try {
    localStorage.setItem(RVC_INPUT_SOURCE_KEY, value);
  } catch {
    // 保存できない環境でも選択自体は使える。
  }
  if (value === "file") {
    const latest = rvcFilePathHistory[0]?.path || rvcFilePathHistory[0] || "";
    if (els.rvcExternalAudioPath && latest) els.rvcExternalAudioPath.value = latest;
    renderRvcFilePathHistory();
  }
}

function selectedRvcInputSource() {
  const value = els.rvcInputSources.find((input) => input.checked)?.value;
  return value === "tts" || value === "file" || value === "mic" ? value : "tts";
}

function updateRvcInputSourceUi() {
  const source = selectedRvcInputSource();
  const isTts = source === "tts";
  const isFile = source === "file";
  const isMic = source === "mic";
  if (els.rvcTtsControls) { els.rvcTtsControls.hidden = !isTts; els.rvcTtsControls.style.display = isTts ? "grid" : "none"; }
  if (els.rvcText?.parentElement?.parentElement) { els.rvcText.parentElement.parentElement.hidden = !isTts; els.rvcText.parentElement.parentElement.style.display = isTts ? "grid" : "none"; }
  if (els.rvcAdvancedSettings) els.rvcAdvancedSettings.hidden = !isTts;
  if (els.rvcChunkPanel) { els.rvcChunkPanel.hidden = !isTts; els.rvcChunkPanel.style.display = isTts ? "flex" : "none"; }
  if (els.rvcChunkPreview) { els.rvcChunkPreview.hidden = !isTts || els.rvcChunkPreview.hidden; if (!isTts) els.rvcChunkPreview.style.display = "none"; else els.rvcChunkPreview.style.display = ""; }
  if (els.rvcFileSourceControls) { els.rvcFileSourceControls.hidden = !isFile; els.rvcFileSourceControls.style.display = isFile ? "grid" : "none"; }
  if (els.rvcMicControls) { els.rvcMicControls.hidden = !isMic; els.rvcMicControls.style.display = isMic ? "block" : "none"; }
  if (els.rvcIntermediateTitle) els.rvcIntermediateTitle.textContent = isTts ? "TTS入力音声" : isMic ? "マイク録音音声" : "ファイル入力音声";
  updateIrodoriEmojiPaletteVisibility();
}

function updateRvcInstructionUi(model, source = selectedRvcInputSource()) {
  const instructionSupported = source === "tts" && supportsInstruction(model);
  const instructionRequired = instructionSupported && requiresInstruction(model, selectedVoice(els.rvcVoice));

  if (els.rvcInstruction) els.rvcInstruction.disabled = !instructionSupported;
  if (els.rvcInstructionField) {
    els.rvcInstructionField.hidden = !instructionSupported;
    els.rvcInstructionField.style.display = instructionSupported ? "grid" : "none";
    els.rvcInstructionField.classList.remove("is-disabled");
  }
  if (instructionSupported) {
    setRequirementBadge(
      els.rvcInstructionRequirement,
      instructionRequired ? "必須" : "任意",
      instructionRequired ? "required" : "optional",
    );
  }
  const emojiVisible = shouldShowIrodoriEmojiPalette("rvc");
  if (els.rvcAdvancedGuidance) els.rvcAdvancedGuidance.hidden = !instructionSupported && !emojiVisible;
  if (els.rvcAdvancedSummary) {
    const parts = [];
    if (instructionSupported) parts.push("話し方");
    if (emojiVisible) parts.push("感情");
    parts.push("長文分割");
    els.rvcAdvancedSummary.textContent = parts.join("・");
  }
}

function updateRvcModelInfo() {
  if (!els.rvcModel) return;
  updateRvcInputSourceUi();
  const source = selectedRvcInputSource();
  const model = source === "tts" ? selectedRvcModel() : null;
  updateRvcInstructionUi(model, source);
  if (currentRvcMicRecording?.path && els.rvcMicPath?.textContent === "-") {
    if (els.rvcMicAudio && currentRvcMicRecording.url) els.rvcMicAudio.src = currentRvcMicRecording.url;
    els.rvcMicPath.textContent = currentRvcMicRecording.path;
    if (els.rvcExternalAudioPath) els.rvcExternalAudioPath.value = currentRvcMicRecording.path;
    if (els.rvcMicUse) els.rvcMicUse.disabled = false;
    setBadge(els.rvcMicBadge, "入力に設定済み", "success");
    renderRvcMicHistory();
  }
  const conversionModel = syncSelectedRvcModelPaths();
  let error = conversionModel ? "" : "RVCモデルがありません。モデルを配置して再読み込みしてください。";
  let okMessage = conversionModel ? `${conversionModel.label} でRVC変換できます。` : "";
  if (!error) {
    if (source === "tts") {
      const voice = selectedVoice(els.rvcVoice);
      error = validateRequest(model, voice, els.rvcText.value, els.rvcInstruction.value);
    } else if (source === "file" && !String(els.rvcExternalAudioPath?.value || "").trim()) {
      error = "入力音声のパスを入力してください。wav / m4a / mp3 / flac などに対応しています。";
    } else if (source === "mic") {
      if (currentRvcMicRecording?.path && els.rvcExternalAudioPath) {
        els.rvcExternalAudioPath.value = currentRvcMicRecording.path;
        okMessage = `${conversionModel.label} で現在の入力wavを何度でも変換できます。`;
      } else {
        error = "先にマイク録音してください。録音後は同じ入力wavを再利用できます。";
      }
    }
  }
  if (els.rvcModel) els.rvcModel.disabled = rvcGenerationActive;
  if (els.rvcVoiceModel) els.rvcVoiceModel.disabled = rvcGenerationActive || !conversionModel;
  els.rvcConvert.disabled = rvcGenerationActive || Boolean(error);
  const warning = source === "tts" ? modelPerformanceWarning(model) : "";
  const status = !error && warning ? `${okMessage} ${warning}` : (error || okMessage);
  setStatus(els.rvcStatus, status, Boolean(error), !error && Boolean(warning));
  updateRvcReferencePreviewButton();
}

function rvcParamsFromForm() {
  const source = selectedRvcInputSource();
  const voiceModel = syncSelectedRvcModelPaths();
  const externalAudioPath = source === "mic"
    ? String(currentRvcMicRecording?.path || "").trim()
    : String(els.rvcExternalAudioPath?.value || "").trim();
  return {
    indexRate: Number((els.rvcIndexRatePreset?.value || els.rvcIndexRate.value) || 0.35),
    f0method: String(els.rvcF0Method.value || "rmvpe").trim(),
    f0upKey: Number((els.rvcF0UpKeyPreset?.value || els.rvcF0UpKey.value) || 0),
    filterRadius: Number(els.rvcFilterRadius.value || 3),
    resampleSr: Number(els.rvcResampleSr.value || 0),
    rmsMixRate: Number(els.rvcRmsMixRate.value || 1),
    protect: Number((els.rvcProtectPreset?.value || els.rvcProtect.value) || 0.33),
    modelId: voiceModel?.id || "",
    modelLabel: voiceModel?.label || "",
    modelPath: String(els.rvcModelPath.value || "").trim(),
    indexPath: String(els.rvcIndexPath.value || "").trim(),
    inputSource: source,
    externalAudioPath,
    cleanExternalAudio: false,
    demucsModel: String(els.rvcDemucsModel?.value || "htdemucs_ft").trim()
  };
}

function applyRvcDefaults() {
  if (!rvcDefaults) return;
  if (els.rvcIndexRate) els.rvcIndexRate.value = rvcDefaults.indexRate ?? 0.35;
  if (els.rvcIndexRatePreset) els.rvcIndexRatePreset.value = String(rvcDefaults.indexRate ?? 0.35);
  if (els.rvcF0Method) els.rvcF0Method.value = rvcDefaults.f0method || "rmvpe";
  if (els.rvcF0UpKey) els.rvcF0UpKey.value = rvcDefaults.f0upKey ?? 0;
  if (els.rvcF0UpKeyPreset) els.rvcF0UpKeyPreset.value = String(rvcDefaults.f0upKey ?? 0);
  if (els.rvcFilterRadius) els.rvcFilterRadius.value = rvcDefaults.filterRadius ?? 3;
  if (els.rvcResampleSr) els.rvcResampleSr.value = rvcDefaults.resampleSr ?? 0;
  if (els.rvcRmsMixRate) els.rvcRmsMixRate.value = rvcDefaults.rmsMixRate ?? 1;
  if (els.rvcProtect) els.rvcProtect.value = rvcDefaults.protect ?? 0.33;
  if (els.rvcProtectPreset) els.rvcProtectPreset.value = String(rvcDefaults.protect ?? 0.33);
  if (selectedRvcVoiceModel()) syncSelectedRvcModelPaths();
  else {
    if (els.rvcModelPath) els.rvcModelPath.value = rvcDefaults.modelPath || "";
    if (els.rvcIndexPath) els.rvcIndexPath.value = rvcDefaults.indexPath || "";
  }
  if (els.rvcExternalAudioPath) els.rvcExternalAudioPath.value = rvcDefaults.externalAudioPath || "";
  if (els.rvcDemucsModel) els.rvcDemucsModel.value = rvcDefaults.demucsModel || "htdemucs_ft";
  const initialInputSource = loadSavedRvcInputSource() || "tts";
  if (initialInputSource) els.rvcInputSources.forEach((input) => { input.checked = input.value === initialInputSource; });
  updateRvcInputSourceUi();
  restoreRvcFilePathHistory();
  setRvcLog({ defaults: rvcDefaults });
}

function compactLogValue(value, maxLength = 220) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
}

function compactRvcLogText(value) {
  if (!value || value.defaults) return "エラーはありません。";
  if (typeof value === "string") return value || "エラーはありません。";
  if (value.converted || value.postDenoise) return "処理が完了しました。";
  const raw = value.error || value.postDenoiseError || value.stderr || value.stdout || value.partialResult;
  if (raw) {
    const detail = typeof raw === "string" ? raw : JSON.stringify(raw);
    return buildAiDiagnosticLog({
      screen: "rvc",
      model: value.request?.model || "",
      request: value.request || null,
      error: { message: detail, payload: value.payload || value },
      extra: {
        command: value.command || null,
        stdout: value.stdout || "",
        stderr: value.stderr || "",
        partialResult: value.partialResult || null,
      },
    });
  }
  if (value.request) {
    const request = value.request;
    const source = request.rvc?.inputSource || "tts";
    return [
      "RVC変換を開始",
      `入力: ${source}`,
      request.rvc?.modelPath ? `モデル: ${request.rvc.modelPath}` : "モデル: 未設定",
      request.rvc?.indexPath ? `index: ${request.rvc.indexPath}` : "index: 未設定",
    ].join("\n");
  }
  return stringifyDiagnostic(value) || "エラーはありません。";
}

function setRvcLog(value) {
  if (els.rvcLog) els.rvcLog.textContent = compactRvcLogText(value);
}

function renderRvcFilePathHistory() {
  if (!els.rvcExternalAudioPathHistory) return;
  const paths = rvcFilePathHistory.map((item) => item.path || item).filter(Boolean);
  const currentPath = String(els.rvcExternalAudioPath?.value || "").trim();
  const placeholder = paths.length ? "保存済みのパスを選択" : "保存履歴はありません";
  els.rvcExternalAudioPathHistory.innerHTML = [
    `<option value="">${placeholder}</option>`,
    ...paths.map((pathValue) => `<option value="${escapeHtml(pathValue)}">${escapeHtml(pathValue)}</option>`),
  ].join("");
  els.rvcExternalAudioPathHistory.disabled = paths.length === 0;
  els.rvcExternalAudioPathHistory.value = paths.includes(currentPath) ? currentPath : "";
}

function rememberRvcFilePath(value = els.rvcExternalAudioPath?.value) {
  const pathValue = String(value || "").trim();
  if (!pathValue) return;
  rvcFilePathHistory = [{ path: pathValue, updatedAt: new Date().toISOString() }, ...rvcFilePathHistory.filter((item) => (item.path || item) !== pathValue)].slice(0, 12);
  saveList(RVC_FILE_PATH_HISTORY_KEY, rvcFilePathHistory);
  renderRvcFilePathHistory();
}

function selectSavedRvcFilePath(value) {
  const pathValue = String(value || "").trim();
  if (!pathValue || !els.rvcExternalAudioPath) return;
  els.rvcExternalAudioPath.value = pathValue;
  rememberRvcFilePath(pathValue);
  updateRvcModelInfo();
}

function restoreRvcFilePathHistory() {
  const latest = rvcFilePathHistory[0]?.path || rvcFilePathHistory[0] || "";
  if (els.rvcExternalAudioPath && latest) els.rvcExternalAudioPath.value = latest;
  renderRvcFilePathHistory();
}

function setBadge(badge, text, state) {
  if (!badge) return;
  badge.textContent = text;
  badge.className = `status-badge ${state || "pending"}`;
}

function formatMicDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds || 0)));
  const min = Math.floor(total / 60);
  const sec = total % 60;
  return `${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function renderRvcMicHistory() {
  if (!els.rvcMicHistory) return;
  if (!rvcMicHistory.length) {
    els.rvcMicHistory.innerHTML = '<option value="">録音履歴はまだありません</option>';
    return;
  }
  els.rvcMicHistory.innerHTML = rvcMicHistory.map((item) => {
    const value = item.path || item.filename || "";
    const label = `${item.filename || "mic.wav"}  ${formatMicDuration(item.durationSec)}`;
    return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
  }).join("");
  if (currentRvcMicRecording?.path) els.rvcMicHistory.value = currentRvcMicRecording.path;
}

function setCurrentRvcMicRecording(recording, options = {}) {
  if (!recording) return;
  const item = {
    filename: recording.filename || String(recording.path || "").split(/[\\/]/).pop() || "mic.wav",
    path: recording.path || "",
    url: recording.url || "",
    durationSec: Number(recording.durationSec || 0),
    scriptText: String(recording.scriptText || ""),
    createdAt: recording.createdAt || new Date().toISOString()
  };
  currentRvcMicRecording = item;
  if (els.rvcMicAudio && item.url) els.rvcMicAudio.src = item.url;
  if (els.rvcMicScript && item.scriptText) els.rvcMicScript.value = item.scriptText;
  if (els.rvcMicPath) els.rvcMicPath.textContent = item.path || item.filename || "-";
  if (els.rvcExternalAudioPath && item.path) els.rvcExternalAudioPath.value = item.path;
  if (els.rvcMicUse) els.rvcMicUse.disabled = !item.path;
  setBadge(els.rvcMicBadge, item.path ? "入力に設定済み" : "未録音", item.path ? "success" : "pending");
  if (options.save !== false) {
    rvcMicHistory = [item, ...rvcMicHistory.filter((old) => (old.path || old.filename) !== (item.path || item.filename))].slice(0, 12);
    saveList(RVC_MIC_HISTORY_KEY, rvcMicHistory);
  }
  renderRvcMicHistory();
  updateTextCounts();
  updateRvcModelInfo();
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("録音データの読み込みに失敗しました。"));
    reader.readAsDataURL(blob);
  });
}

function stopRvcMicStream() {
  if (rvcMicStream) rvcMicStream.getTracks().forEach((track) => track.stop());
  rvcMicStream = null;
}

function updateRvcMicTimer() {
  if (!els.rvcMicTimer || !rvcMicStartedAt) return;
  els.rvcMicTimer.textContent = formatMicDuration((Date.now() - rvcMicStartedAt) / 1000);
}

function selectedRvcMicDeviceId() {
  return String(els.rvcMicDevice?.value || "").trim();
}

function saveSelectedRvcMicDeviceId(deviceId = selectedRvcMicDeviceId()) {
  try {
    localStorage.setItem(RVC_MIC_DEVICE_KEY, String(deviceId || ""));
  } catch {
    // localStorageが無効でも録音自体は続ける。
  }
}

function loadSavedRvcMicDeviceId() {
  try {
    return String(localStorage.getItem(RVC_MIC_DEVICE_KEY) || "").trim();
  } catch {
    return "";
  }
}

async function loadRvcMicDevices() {
  if (!els.rvcMicDevice || !navigator.mediaDevices?.enumerateDevices) return;
  const selectedBeforeReload = selectedRvcMicDeviceId() || loadSavedRvcMicDeviceId();
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const inputs = devices.filter((device) => device.kind === "audioinput");
    els.rvcMicDevice.innerHTML = '<option value="">既定のマイク</option>' + inputs.map((device, index) => {
      const label = device.label || `マイク ${index + 1}`;
      return `<option value="${escapeHtml(device.deviceId)}">${escapeHtml(label)}</option>`;
    }).join("");
    if (selectedBeforeReload && inputs.some((device) => device.deviceId === selectedBeforeReload)) {
      els.rvcMicDevice.value = selectedBeforeReload;
      saveSelectedRvcMicDeviceId(selectedBeforeReload);
    } else if (!selectedBeforeReload) {
      saveSelectedRvcMicDeviceId("");
    }
  } catch {
    // 権限前は取得できない場合がある。
  }
}

async function uploadRvcMicRecording(blob) {
  const dataUrl = await blobToDataUrl(blob);
  const payload = await ttsApi.saveRvcRecording({
    dataUrl,
    mimeType: blob.type || "audio/webm",
    scriptText: String(els.rvcMicScript?.value || "").trim()
  });
  setCurrentRvcMicRecording(payload.recording || {});
  setStatus(els.rvcStatus, "録音を入力wavとして保存しました。このまま何度でもRVC変換できます。");
}

async function finishRvcMicRecording() {
  clearInterval(rvcMicTimerId);
  rvcMicTimerId = 0;
  stopRvcMicStream();
  if (els.rvcMicStart) els.rvcMicStart.disabled = false;
  if (els.rvcMicStop) els.rvcMicStop.disabled = true;
  const blob = new Blob(rvcMicChunks, { type: rvcMediaRecorder?.mimeType || "audio/webm" });
  rvcMediaRecorder = null;
  rvcMicChunks = [];
  if (!blob.size) {
    setStatus(els.rvcStatus, "録音データが空です。もう一度録音してください。", true);
    setBadge(els.rvcMicBadge, "未録音", "failed");
    return;
  }
  setBadge(els.rvcMicBadge, "保存中", "pending");
  setStatus(els.rvcStatus, "録音音声をwavへ保存しています...");
  try {
    await uploadRvcMicRecording(blob);
  } catch (error) {
    setBadge(els.rvcMicBadge, "保存失敗", "failed");
    setStatus(els.rvcStatus, humanizeError(error), true);
  }
}

async function startRvcMicRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setStatus(els.rvcStatus, "このブラウザではマイク録音に対応していません。", true);
    return;
  }
  if (rvcMediaRecorder && rvcMediaRecorder.state === "recording") return;
  try {
    const deviceId = selectedRvcMicDeviceId();
    saveSelectedRvcMicDeviceId(deviceId);
    const audio = deviceId
      ? { deviceId: { exact: deviceId }, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      : { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    rvcMicStream = await navigator.mediaDevices.getUserMedia({ audio });
    await loadRvcMicDevices();
    rvcMicChunks = [];
    const preferred = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"].find((type) => MediaRecorder.isTypeSupported(type));
    rvcMediaRecorder = preferred ? new MediaRecorder(rvcMicStream, { mimeType: preferred }) : new MediaRecorder(rvcMicStream);
    rvcMediaRecorder.ondataavailable = (event) => { if (event.data?.size) rvcMicChunks.push(event.data); };
    rvcMediaRecorder.onstop = finishRvcMicRecording;
    rvcMediaRecorder.start();
    rvcMicStartedAt = Date.now();
    updateRvcMicTimer();
    clearInterval(rvcMicTimerId);
    rvcMicTimerId = setInterval(updateRvcMicTimer, 250);
    if (els.rvcMicStart) els.rvcMicStart.disabled = true;
    if (els.rvcMicStop) els.rvcMicStop.disabled = false;
    setBadge(els.rvcMicBadge, "録音中", "pending");
    setStatus(els.rvcStatus, "録音中です。停止すると入力wavとして保存します。録り直すまでは同じ録音を使います。");
  } catch (error) {
    stopRvcMicStream();
    setBadge(els.rvcMicBadge, "録音失敗", "failed");
    setStatus(els.rvcStatus, `マイク録音に失敗しました: ${error.message || error}`, true);
  }
}

function stopRvcMicRecording() {
  if (!rvcMediaRecorder || rvcMediaRecorder.state !== "recording") return;
  rvcMediaRecorder.stop();
}
