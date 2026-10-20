const normalEls = {
  normalModel: document.querySelector("#normalModelSelect"),
  normalReferenceField: document.querySelector("#normalReferenceField"),
  normalReferenceRequirement: document.querySelector("#normalReferenceRequirement"),
  normalUseReference: document.querySelector("#normalUseReference"),
  normalUseReferenceLabel: document.querySelector("#normalUseReferenceLabel"),
  normalUseReferenceTip: document.querySelector("#normalUseReferenceTip"),
  normalVoice: document.querySelector("#normalReferenceVoiceSelect"),
  normalText: document.querySelector("#normalTextInput"),
  normalAdvancedGuidance: document.querySelector("#normalAdvancedGuidance"),
  normalAdvancedSummary: document.querySelector("#normalAdvancedSummary"),
  normalInstructionField: document.querySelector("#normalInstructionField"),
  normalInstructionRequirement: document.querySelector("#normalInstructionRequirement"),
  normalInstruction: document.querySelector("#normalInstructionInput"),
  normalLanguage: document.querySelector("#normalLanguageInput"),
  normalSeed: document.querySelector("#normalSeedInput"),
  normalSeedAutoIncrement: document.querySelector("#normalSeedAutoIncrementInput"),
  normalSaveHistory: document.querySelector("#normalSaveHistory"),
  normalAutoPlay: document.querySelector("#normalAutoPlayInput"),
  normalSpeedControl: document.querySelector("#normalSpeedControl"),
  normalSpeedScale: document.querySelector("#normalSpeedScale"),
  normalSpeedValue: document.querySelector("#normalSpeedValue"),
  normalStyleStrengthControl: document.querySelector("#normalStyleStrengthControl"),
  normalStyleStrength: document.querySelector("#normalStyleStrength"),
  normalStyleStrengthValue: document.querySelector("#normalStyleStrengthValue"),
  normalGenerate: document.querySelector("#normalGenerateButton"),
  normalRegenerateButton: document.querySelector("#normalRegenerateButton"),
  normalReferencePreview: document.querySelector("#normalReferencePreviewButton"),
  normalStatus: document.querySelector("#normalStatusText"),
  normalResultCard: document.querySelector("#normalResultCard"),
  normalResultModel: document.querySelector("#normalResultModel"),
  normalResultMeta: document.querySelector("#normalResultMeta"),
  normalResultDuration: document.querySelector("#normalResultDuration"),
  normalAudio: document.querySelector("#normalAudioPlayer"),
  avatarVideo: document.querySelector("#avatarLoopVideo"),
  avatarStatus: document.querySelector("#avatarSyncStatus"),
  avatarToggle: document.querySelector("#avatarToggleButton"),
  normalDownloadLink: document.querySelector("#normalDownloadLink"),
  normalDownloadButton: document.querySelector("#normalDownloadButton"),
  normalLog: document.querySelector("#normalLogBox"),
  normalLogCopy: document.querySelector("#normalLogCopyButton"),
  normalHistory: document.querySelector("#normalHistoryList"),
  normalClearHistory: document.querySelector("#normalClearHistoryButton"),
  normalTextCount: document.querySelector("#normalTextCount"),
  normalInstructionCount: document.querySelector("#normalInstructionCount"),
};

let normalGenerationActive = false;

function setNormalGenerationActive(active) {
  normalGenerationActive = Boolean(active);
  if (els.normalModel) els.normalModel.disabled = normalGenerationActive;
  document.querySelector("#normalPage")?.classList.toggle("generation-locked", normalGenerationActive);
}

function setNormalDiagnostic(error = null, request = null) {
  if (!els.normalLog) return;
  els.normalLog.textContent = error
    ? buildAiDiagnosticLog({ screen: "normal", error, request, model: request?.model || selectedNormalModel()?.id || "" })
    : "エラーはありません。";
}

function saveNormalFormSettings() {
  const seed = Number.parseInt(String(els.normalSeed?.value || "1"), 10);
  saveObject(NORMAL_FORM_SETTINGS_KEY, {
    model: els.normalModel?.value || "",
    voice: els.normalVoice?.value || "",
    useReference: Boolean(els.normalUseReference?.checked),
    seed: Number.isInteger(seed) && seed >= 0 ? seed : 1,
    autoIncrement: Boolean(els.normalSeedAutoIncrement?.checked),
    saveHistory: Boolean(els.normalSaveHistory?.checked),
    autoPlay: Boolean(els.normalAutoPlay?.checked),
    speedScale: Number(els.normalSpeedScale?.value || 1),
    styleStrength: Number(els.normalStyleStrength?.value || 3),
  });
}

function applySavedNormalFormSettings() {
  const saved = loadObject(NORMAL_FORM_SETTINGS_KEY, {});
  const seed = Number.parseInt(String(saved.seed ?? els.normalSeed?.value ?? "1"), 10);
  if (els.normalSeed) els.normalSeed.value = String(Number.isInteger(seed) && seed >= 0 ? seed : 1);
  if (els.normalUseReference && typeof saved.useReference === "boolean") els.normalUseReference.checked = saved.useReference;
  if (els.normalSeedAutoIncrement && typeof saved.autoIncrement === "boolean") els.normalSeedAutoIncrement.checked = saved.autoIncrement;
  if (els.normalSaveHistory && typeof saved.saveHistory === "boolean") els.normalSaveHistory.checked = saved.saveHistory;
  if (els.normalAutoPlay && typeof saved.autoPlay === "boolean") els.normalAutoPlay.checked = saved.autoPlay;
  if (els.normalSpeedScale && Number.isFinite(Number(saved.speedScale))) els.normalSpeedScale.value = String(saved.speedScale);
  if (els.normalStyleStrength && Number.isFinite(Number(saved.styleStrength))) els.normalStyleStrength.value = String(saved.styleStrength);
  if (els.normalModel && saved.model && Array.from(els.normalModel.options).some((option) => option.value === saved.model && !option.disabled)) els.normalModel.value = saved.model;
  if (els.normalVoice && saved.voice && Array.from(els.normalVoice.options).some((option) => option.value === saved.voice && !option.disabled)) els.normalVoice.value = saved.voice;
  updateNormalSynthesisControls(selectedNormalModel());
  updateNormalReferenceUi(selectedNormalModel());
}

function normalReferenceEnabled(model = selectedNormalModel()) {
  return Boolean(supportsReference(model) && els.normalUseReference?.checked);
}

function updateNormalReferenceUi(model = selectedNormalModel()) {
  const currentModelId = modelId(model);
  const previousModel = modelsById.get(lastNormalReferenceModelId) || null;
  const supported = supportsReference(model);
  const required = requiresReference(model);
  const switchedFromUnsupported = Boolean(lastNormalReferenceModelId && currentModelId !== lastNormalReferenceModelId && !supportsReference(previousModel));
  if (!supported && els.normalUseReference) els.normalUseReference.checked = false;
  else if (supported && switchedFromUnsupported && els.normalUseReference) els.normalUseReference.checked = true;
  lastNormalReferenceModelId = currentModelId;
  const active = supported && Boolean(els.normalUseReference?.checked);
  if (els.normalUseReference) els.normalUseReference.disabled = !supported;
  if (els.normalUseReferenceLabel) els.normalUseReferenceLabel.textContent = supported ? "使用する" : "未対応";
  if (els.normalUseReferenceTip) {
    els.normalUseReferenceTip.dataset.tip = !supported
      ? "このモデルは参照音声を受け取りません。"
      : required
        ? "このモデルは生成時に参照音声が必要です。OFFにすると生成できません。"
        : "ONのときだけ選択中の参照音声をモデルへ渡します。OFFでは参照音声を使いません。";
  }
  if (els.normalVoice) els.normalVoice.disabled = !active;
  if (els.normalReferenceField) {
    els.normalReferenceField.classList.toggle("is-disabled", !active);
    els.normalReferenceField.removeAttribute("aria-disabled");
    els.normalReferenceField.querySelector(".reference-input-group")?.setAttribute("aria-disabled", String(!active));
  }
  updateReferencePreviewButtons();
}

function updateNormalRequirementLabels(model = selectedNormalModel()) {
  const voice = normalReferenceEnabled(model) ? selectedVoice(els.normalVoice) : null;
  if (requiresReference(model)) setRequirementBadge(els.normalReferenceRequirement, "必須", "required");
  else if (supportsReference(model)) setRequirementBadge(els.normalReferenceRequirement, "任意", "optional");
  else setRequirementBadge(els.normalReferenceRequirement, "未対応", "inactive");

  const instructionSupported = supportsInstruction(model);
  if (requiresInstruction(model, voice)) setRequirementBadge(els.normalInstructionRequirement, "必須", "required");
  else if (instructionSupported) setRequirementBadge(els.normalInstructionRequirement, "任意", "optional");

  if (els.normalInstruction) els.normalInstruction.disabled = !instructionSupported;
  if (els.normalInstructionField) {
    els.normalInstructionField.hidden = !instructionSupported;
    els.normalInstructionField.style.display = instructionSupported ? "grid" : "none";
    els.normalInstructionField.classList.remove("is-disabled");
  }
  if (els.normalAdvancedGuidance) {
    els.normalAdvancedGuidance.hidden = !instructionSupported && !shouldShowIrodoriEmojiPalette("normal");
  }
  if (els.normalAdvancedSummary) {
    const parts = [];
    if (instructionSupported) parts.push("話し方");
    if (shouldShowIrodoriEmojiPalette("normal")) parts.push("感情");
    parts.push("長文分割", "保存設定");
    els.normalAdvancedSummary.textContent = parts.join("・");
  }
}

function normalStyleStrengthEnabled(model) {
  if (!supportsStyleStrength(model)) return false;
  if (!window.LocalTtsModelCapabilities.requiresPromptForStyleStrength(model)) return true;
  return Boolean(String(els.normalInstruction?.value || "").trim());
}

function normalSynthesisControls(model) {
  const controls = {};
  if (supportsSpeedControl(model)) controls.speedScale = Number(els.normalSpeedScale?.value || 1);
  if (normalStyleStrengthEnabled(model)) controls.styleStrength = Number(els.normalStyleStrength?.value || 3);
  return controls;
}

function updateNormalSynthesisControls(model) {
  const showSpeed = supportsSpeedControl(model);
  const showStyle = supportsStyleStrength(model);
  const enableStyle = normalStyleStrengthEnabled(model);
  if (els.normalSpeedControl) {
    els.normalSpeedControl.hidden = !showSpeed;
    els.normalSpeedControl.style.display = showSpeed ? "grid" : "none";
  }
  if (els.normalStyleStrengthControl) {
    els.normalStyleStrengthControl.hidden = !showStyle;
    els.normalStyleStrengthControl.style.display = showStyle ? "grid" : "none";
    els.normalStyleStrengthControl.classList.toggle("is-disabled", showStyle && !enableStyle);
  }
  if (els.normalStyleStrength) els.normalStyleStrength.disabled = !enableStyle;
  if (els.normalSpeedValue) els.normalSpeedValue.textContent = `${Number(els.normalSpeedScale?.value || 1).toFixed(2)}x`;
  if (els.normalStyleStrengthValue) els.normalStyleStrengthValue.textContent = Number(els.normalStyleStrength?.value || 3).toFixed(1);
}

function selectedNormalModel() {
  return modelsById.get(String(els.normalModel.value || "").trim()) || null;
}

function updateNormalModelInfo({ preserveStatus = false } = {}) {
  const model = selectedNormalModel();
  updateNormalSynthesisControls(model);
  updateNormalReferenceUi(model);
  updateNormalRequirementLabels(model);
  updateIrodoriEmojiPaletteVisibility();
  const voice = normalReferenceEnabled(model) ? selectedVoice(els.normalVoice) : null;
  const error = requiresReference(model) && !normalReferenceEnabled(model)
    ? "このモデルには参照音声が必要です。「使用する」をONにしてください。"
    : validateRequest(model, voice, els.normalText.value, els.normalInstruction.value);
  const warning = modelPerformanceWarning(model);
  if (els.normalModel) els.normalModel.disabled = normalGenerationActive;
  els.normalGenerate.disabled = normalGenerationActive || Boolean(error);
  if (!preserveStatus || els.normalStatus.textContent === "読込中です...") {
    setStatus(els.normalStatus, error || warning || "生成できます。", Boolean(error), !error && Boolean(warning));
  }
}

function setNormalResult(result, body) {
  const id = String(result.model || body.model || "");
  const audioUrl = String(result.audioUrl || "");
  els.normalResultModel.textContent = modelLabel(id, id);
  els.normalResultDuration.textContent = result.timings?.durationSec ? formatDuration(result.timings.durationSec) : "--:--";
  els.normalAudio.pause();
  if (audioUrl) {
    els.normalAudio.src = audioUrl;
    els.normalAudio.load();
  } else {
    els.normalAudio.removeAttribute("src");
    els.normalAudio.load();
  }
  els.normalDownloadLink.href = audioUrl || "#";
  els.normalDownloadButton.href = audioUrl || "#";
  els.normalResultMeta.innerHTML = [
    `言語：${body.language || "-"}`,
    `seed：${body.seed ?? "-"}`,
    body.speedScale != null ? `話速：${Number(body.speedScale).toFixed(2)}x` : null,
    body.styleStrength != null ? `スタイル追従度：${Number(body.styleStrength).toFixed(1)}` : null,
    `参照音声：${body.voiceId || "-"}`
  ].filter(Boolean).map((item) => `<span>${escapeHtml(item)}</span>`).join("");
  els.normalResultCard.hidden = false;
  lastNormalBody = body;
  if (els.normalSaveHistory?.checked) {
    addNormalHistory({
      createdAt: new Date().toISOString(),
      model: id,
      audioUrl,
      duration: els.normalResultDuration.textContent,
      text: body.text,
      instruction: body.instruction || "",
      seed: body.seed ?? "",
      referenceVoice: body.voiceId || "",
      request: { ...body },
    });
    window.dispatchEvent(new CustomEvent("local-tts:history-record", {
      detail: {
        type: "normal",
        status: "success",
        createdAt: new Date().toISOString(),
        text: body.text,
        instruction: body.instruction || "",
        model: id,
        referenceVoice: body.voiceId || "",
        seed: body.seed ?? "",
        duration: els.normalResultDuration.textContent,
        audioUrl,
        raw: { request: body, result }
      }
    }));
  }
}

async function playNormalResultIfEnabled() {
  if (!els.normalAutoPlay?.checked || !els.normalAudio?.src) return false;
  try {
    await window.LocalTts.audioController.playWhenReady(els.normalAudio);
    return true;
  } catch (error) {
    const interrupted = window.LocalTts.audioController.isInterruptedPlayError(error);
    const message = interrupted
      ? "生成は完了しました。自動再生が中断されたため、再生ボタンを押してください。"
      : `生成は完了しましたが、自動再生できませんでした: ${error.message || error}`;
    setStatus(els.normalStatus, message, true);
    return false;
  }
}

async function generateNormal() {
  const model = selectedNormalModel();
  const voice = normalReferenceEnabled(model) ? selectedVoice(els.normalVoice) : null;
  const error = requiresReference(model) && !normalReferenceEnabled(model)
    ? "このモデルには参照音声が必要です。「使用する」をONにしてください。"
    : validateRequest(model, voice, els.normalText.value, els.normalInstruction.value);
  if (error) { setStatus(els.normalStatus, error, true); return; }
  normalizeSeedInput(els.normalSeed);
  saveNormalFormSettings();
  const body = attachChunking(
    buildRequestBody(
      model,
      voice,
      els.normalText.value,
      els.normalInstruction.value,
      els.normalLanguage.value,
      els.normalSeed.value,
      normalSynthesisControls(model)
    ),
    chunkSettingsFromForm("normal").chunking
  );
  setNormalGenerationActive(true);
  setNormalDiagnostic();
  setStatus(els.normalStatus, "音声を生成中です...");
  try {
    const payload = await ttsApi.speak(body);
    setNormalResult(payload.result || {}, body);
    incrementSeedInputIfNeeded(els.normalSeed, els.normalSeedAutoIncrement, updateNormalModelInfo);
    saveNormalFormSettings();
    setNormalDiagnostic();
    setStatus(els.normalStatus, "生成が完了しました。");
    await playNormalResultIfEnabled();
  } catch (error) {
    const errorMessage = humanizeError(error);
    setNormalDiagnostic(error, body);
    setStatus(els.normalStatus, errorMessage, true);
    if (els.normalSaveHistory?.checked) window.dispatchEvent(new CustomEvent("local-tts:history-record", {
      detail: {
        type: "normal",
        status: "failed",
        createdAt: new Date().toISOString(),
        text: body.text,
        instruction: body.instruction || "",
        model: body.model,
        referenceVoice: body.voiceId || "",
        seed: body.seed ?? "",
        error: errorMessage,
        raw: { request: body, error: errorMessage, payload: error?.payload || null }
      }
    }));
  } finally {
    setNormalGenerationActive(false);
    updateNormalModelInfo({ preserveStatus: true });
  }
}

async function regenerateLastNormalRequest() {
  if (!lastNormalBody) {
    setStatus(els.normalStatus, "再生成できる前回の結果がありません。", true);
    return;
  }
  const body = JSON.parse(JSON.stringify(lastNormalBody));
  setNormalGenerationActive(true);
  if (els.normalRegenerateButton) els.normalRegenerateButton.disabled = true;
  setNormalDiagnostic();
  setStatus(els.normalStatus, `同じ設定・seed ${body.seed ?? "-"} で再生成中です...`);
  try {
    const payload = await ttsApi.speak(body);
    setNormalResult(payload.result || {}, body);
    setNormalDiagnostic();
    setStatus(els.normalStatus, "同じ設定・seedで再生成しました。");
    await playNormalResultIfEnabled();
  } catch (error) {
    setNormalDiagnostic(error, body);
    setStatus(els.normalStatus, humanizeError(error), true);
  } finally {
    setNormalGenerationActive(false);
    if (els.normalRegenerateButton) els.normalRegenerateButton.disabled = false;
    updateNormalModelInfo({ preserveStatus: true });
  }
}

function addNormalHistory(item) {
  normalHistory = [item, ...normalHistory].slice(0, 8);
  saveList(NORMAL_HISTORY_KEY, normalHistory);
  renderNormalHistory();
}

function normalHistoryRequest(item) {
  if (item?.request && typeof item.request === "object") return item.request;
  return {
    model: item?.model || "",
    text: item?.text || "",
    instruction: item?.instruction || "",
    seed: item?.seed ?? "",
    voiceId: item?.referenceVoice || "",
  };
}

function restoreNormalHistoryItem(index) {
  const item = normalHistory[index];
  if (!item) return;
  const request = normalHistoryRequest(item);
  if (request.model && Array.from(els.normalModel.options).some((option) => option.value === request.model && !option.disabled)) els.normalModel.value = request.model;
  if (request.voiceId && Array.from(els.normalVoice.options).some((option) => option.value === request.voiceId && !option.disabled)) els.normalVoice.value = request.voiceId;
  if (els.normalUseReference) els.normalUseReference.checked = Boolean(request.voiceId);
  if (request.text) els.normalText.value = request.text;
  if (request.instruction != null) els.normalInstruction.value = request.instruction;
  if (request.seed != null && request.seed !== "") els.normalSeed.value = String(request.seed);
  if (request.speedScale != null) els.normalSpeedScale.value = String(request.speedScale);
  if (request.styleStrength != null) els.normalStyleStrength.value = String(request.styleStrength);
  if (request.chunking?.softChunkChars) applyChunkPreset("normal", request.chunking.softChunkChars);
  refreshTextCountsAndChunkPreview();
  saveNormalFormSettings();
  updateNormalModelInfo();
  setStatus(els.normalStatus, "履歴の文章と生成設定を戻しました。");
}

function renderNormalHistory() {
  els.normalHistory.innerHTML = normalHistory.length ? normalHistory.map((item, index) => {
    const request = normalHistoryRequest(item);
    const text = String(request.text || item.text || "").trim();
    const chips = [request.seed !== "" && request.seed != null ? `seed ${request.seed}` : "", request.voiceId ? `参照 ${request.voiceId}` : "参照なし", item.duration || ""].filter(Boolean);
    return `
      <article class="mini-history-item rich-history-item">
        <button class="mini-history-play" type="button" data-history-audio="${escapeHtml(item.audioUrl || "")}" aria-label="音声を再生">▶</button>
        <div class="mini-history-content">
          <div class="mini-history-title"><strong>${escapeHtml(modelLabel(item.model, item.model))}</strong><small>${escapeHtml(new Date(item.createdAt).toLocaleString("ja-JP"))}</small></div>
          <p class="mini-history-text">${escapeHtml(text || "文章情報なし")}</p>
          <div class="mini-history-chips">${chips.map((chip) => `<span>${escapeHtml(chip)}</span>`).join("")}</div>
          <button class="link-button mini-history-restore" type="button" data-restore-normal-history="${index}">文章と設定を戻す</button>
        </div>
      </article>`;
  }).join("") : '<div class="empty-state">保存した生成はありません。生成時に「履歴へ保存」をONにすると、文章と設定をここから戻せます。</div>';
  attachAudioButtons();
}

