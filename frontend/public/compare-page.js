const compareEls = {
  compareText: document.querySelector("#compareTextInput"),
  compareAdvancedGuidance: document.querySelector("#compareAdvancedGuidance"),
  compareAdvancedSummary: document.querySelector("#compareAdvancedSummary"),
  compareInstructionField: document.querySelector("#compareInstructionField"),
  compareInstructionRequirement: document.querySelector("#compareInstructionRequirement"),
  compareInstruction: document.querySelector("#compareInstructionInput"),
  compareLanguage: document.querySelector("#compareLanguageInput"),
  compareVoice: document.querySelector("#compareReferenceVoiceSelect"),
  compareSeed: document.querySelector("#compareSeedInput"),
  compareSeedAutoIncrement: document.querySelector("#compareSeedAutoIncrementInput"),
  compareAutoPlay: document.querySelector("#compareAutoPlayInput"),
  compareReferencePreview: document.querySelector("#compareReferencePreviewButton"),
  compareCards: document.querySelector("#compareModelCards"),
  compareGenerate: document.querySelector("#compareGenerateButton"),
  compareStatus: document.querySelector("#compareStatusText"),
  compareResults: document.querySelector("#compareResultsGrid"),
  compareResultCount: document.querySelector("#compareResultCount"),
  compareLog: document.querySelector("#compareLogBox"),
  compareLogCopy: document.querySelector("#compareLogCopyButton"),
  compareHistory: document.querySelector("#compareHistoryList"),
  compareClearHistory: document.querySelector("#compareClearHistoryButton"),
  compareSelectAll: document.querySelector("#compareSelectAllButton"),
  compareClear: document.querySelector("#compareClearButton"),
  compareTextCount: document.querySelector("#compareTextCount"),
  compareInstructionCount: document.querySelector("#compareInstructionCount"),
};

let compareDiagnosticEntries = [];
let activeCompareModelIds = new Set();

function setCompareGenerationActive(active) {
  compareGenerationActive = Boolean(active);
  all('[data-model-card] input').forEach((input) => {
    const model = modelsById.get(input.value);
    input.disabled = compareGenerationActive || !isAvailable(model);
  });
  if (els.compareSelectAll) els.compareSelectAll.disabled = compareGenerationActive;
  if (els.compareClear) els.compareClear.disabled = compareGenerationActive;
  els.compareCards?.classList.toggle("generation-locked", compareGenerationActive);
}

function resetCompareDiagnostics() {
  compareDiagnosticEntries = [];
  if (els.compareLog) els.compareLog.textContent = "エラーはありません。";
}

function appendCompareDiagnostic(model, error, request = null) {
  compareDiagnosticEntries.push(buildAiDiagnosticLog({ screen: "compare", model, error, request }));
  if (els.compareLog) els.compareLog.textContent = compareDiagnosticEntries.join("\n\n====================\n\n");
}

function saveCompareFormSettings() {
  saveObject(COMPARE_FORM_SETTINGS_KEY, {
    voice: els.compareVoice?.value || "",
    seed: normalizedStoredSeed(els.compareSeed),
    autoIncrement: Boolean(els.compareSeedAutoIncrement?.checked),
    autoPlay: Boolean(els.compareAutoPlay?.checked),
    selectedModels: selectedCompareModels(),
  });
}

function applySavedCompareFormSettings() {
  const saved = loadObject(COMPARE_FORM_SETTINGS_KEY, {});
  if (els.compareSeed) els.compareSeed.value = String(Number.isInteger(saved.seed) && saved.seed >= 0 ? saved.seed : 1);
  if (els.compareSeedAutoIncrement && typeof saved.autoIncrement === "boolean") els.compareSeedAutoIncrement.checked = saved.autoIncrement;
  if (els.compareAutoPlay && typeof saved.autoPlay === "boolean") els.compareAutoPlay.checked = saved.autoPlay;
  if (els.compareVoice && saved.voice && Array.from(els.compareVoice.options).some((option) => option.value === saved.voice && !option.disabled)) els.compareVoice.value = saved.voice;
  if (Array.isArray(saved.selectedModels)) {
    const selected = new Set(saved.selectedModels);
    all('[data-model-card] input:not(:disabled)').forEach((input) => { input.checked = selected.has(input.value); });
  }
  updateCompareButtonState();
}

function renderCompareModelCards() {
  const desiredModels = DESIRED_MODELS.filter((id) => modelsById.has(id)).map((id) => modelsById.get(id));
  const ids = window.LocalTtsModelCatalog.sortModelsAvailableFirst(desiredModels).map(modelId);
  els.compareCards.innerHTML = ids.map((id) => {
    const model = modelsById.get(id);
    const profile = profileFor(id);
    const disabled = !isAvailable(model);
    const badges = profile.badges.map((badge, index) => `<span class="badge ${index === 0 ? "green" : index === 2 ? "purple" : ""}">${escapeHtml(badge)}</span>`).join("");
    return `
      <article class="model-card ${disabled ? "disabled" : ""}" data-model-card="${escapeHtml(id)}">
        <div class="model-card-head">
          <input type="checkbox" value="${escapeHtml(id)}" ${disabled ? "disabled" : "checked"}>
          <h3>${escapeHtml(modelLabel(id, model?.label))}</h3>
        </div>
        <div class="badge-row">${badges}</div>
        <p class="model-card-description">${escapeHtml(profile.description)}</p>
        ${disabled ? `<p class="model-unavailable-reason">利用不可: ${escapeHtml(model?.unavailableReason || "セットアップが完了していません。")}</p>` : ""}
      </article>`;
  }).join("") || '<div class="empty-state">比較できるモデルがありません。</div>';
  all('[data-model-card] input').forEach((input) => input.addEventListener("change", () => { saveCompareFormSettings(); updateCompareButtonState(); }));
  updateCompareButtonState();
}

function updateCompareResultProgress(id, state, message) {
  const item = compareResults.find((result) => result.model === id);
  const card = els.compareResults.querySelector(`[data-result-model="${CSS.escape(id)}"]`);
  if (!item) return;
  if (!card) {
    els.compareResults.querySelector(".empty-state")?.remove();
    els.compareResults.insertAdjacentHTML("beforeend", resultCardHtml(item.model, item.state, item.result, item.message));
    attachAudioButtons();
    return;
  }
  const badge = card.querySelector(".status-badge");
  if (badge) {
    badge.className = `status-badge ${state === "stale" ? "warning" : "pending"}`;
    badge.textContent = state === "stale" ? "前回結果" : state === "queued" ? "待機中" : "生成中";
  }
  const memo = card.querySelector(".memo-box p");
  if (memo) memo.textContent = message;
  const regenerate = card.querySelector("[data-regenerate-model]");
  if (regenerate) regenerate.disabled = state !== "stale";
}

async function generateCompareModel(id, bodyBase) {
  const model = modelsById.get(id);
  const voice = selectedVoice(els.compareVoice);
  const previousAudioUrl = compareResults.find((item) => item.model === id)?.result?.audioUrl || "";
  const validation = validateRequest(model, voice, bodyBase.text, bodyBase.instruction || "");
  if (validation) {
    const message = previousAudioUrl ? `新しい生成に失敗しました。前回の音声を残しています。${validation}` : validation;
    compareResults = compareResults.map((item) => item.model === id ? { ...item, state: previousAudioUrl ? "stale" : "failed", message, score: 0 } : item);
    appendCompareDiagnostic(id, new Error(validation), { ...bodyBase, model: id });
    if (previousAudioUrl) updateCompareResultProgress(id, "stale", message);
    else renderCompareResultModel(id);
    return;
  }
  const body = attachChunking(
    buildRequestBody(model, voice, bodyBase.text, bodyBase.instruction, bodyBase.language, bodyBase.seed),
    bodyBase.chunking
  );
  try {
    const payload = await ttsApi.speak(body);
    const result = payload.result || {};
    const score = profileFor(id).baseScore + (result.audioUrl ? 2 : 0);
    const duration = formatDuration(Number(result.timings?.durationSec ?? result.durationSec));
    compareResults = compareResults.map((item) => item.model === id ? { ...item, state: "success", result: { ...result, duration }, message: profileFor(id).memo, score } : item);
  } catch (error) {
    const errorMessage = humanizeError(error);
    const message = previousAudioUrl ? `新しい生成に失敗しました。前回の音声を残しています。${errorMessage}` : errorMessage;
    compareResults = compareResults.map((item) => item.model === id ? { ...item, state: previousAudioUrl ? "stale" : "failed", message, score: 0 } : item);
    appendCompareDiagnostic(id, error, body);
  }
  const best = compareResults.filter((item) => activeCompareModelIds.has(item.model) && item.state === "success").sort((a, b) => b.score - a.score)[0];
  compareResults = compareResults.map((item) => ({ ...item, recommended: Boolean(best && item.model === best.model) }));
  const updated = compareResults.find((item) => item.model === id);
  if (updated?.state === "stale") updateCompareResultProgress(id, "stale", updated.message);
  else renderCompareResultModel(id);
}

async function generateCompare() {
  const ids = selectedCompareModels();
  if (!ids.length) { setStatus(els.compareStatus, "比較するモデルを選択してください。", true); return; }
  if (!els.compareText.value.trim()) { setStatus(els.compareStatus, "読み上げテキストを入力してください。", true); return; }
  normalizeSeedInput(els.compareSeed);
  saveCompareFormSettings();
  const seedRaw = els.compareSeed.value.trim();
  if (seedRaw && !Number.isInteger(Number(seedRaw))) { setStatus(els.compareStatus, "seed は整数で入力してください。", true); return; }
  activeCompareModelIds = new Set(ids);
  compareResults = compareResults.map((item) => ({
    ...item,
    state: activeCompareModelIds.has(item.model) ? "queued" : "stale",
    message: activeCompareModelIds.has(item.model) ? "新しい音声を生成待ちです。前回の音声は再生できます。" : "前回の比較結果です。",
    recommended: false,
  }));
  for (const id of ids) {
    if (!compareResults.some((item) => item.model === id)) {
      compareResults.push({ model: id, state: "queued", result: {}, message: "順番待ちです。", score: 0, recommended: false });
    }
  }
  resetCompareDiagnostics();
  for (const item of compareResults) updateCompareResultProgress(item.model, item.state, item.message);
  els.compareResultCount.textContent = `（${compareResults.length}件）`;
  setCompareGenerationActive(true);
  updateCompareButtonState();
  setStatus(els.compareStatus, `${ids.length}モデルを順番に生成します。完了した音声から再生できます。`);
  const bodyBase = {
    text: els.compareText.value,
    instruction: els.compareInstruction.value,
    language: els.compareLanguage.value,
    seed: seedRaw || undefined,
    chunking: chunkSettingsFromForm("compare").chunking
  };
  for (const [index, id] of ids.entries()) {
    const hadPreviousAudio = Boolean(compareResults.find((item) => item.model === id)?.result?.audioUrl);
    const pendingMessage = hadPreviousAudio ? "新しい音声を生成中です。前回の音声はそのまま再生できます。" : "生成中です。";
    compareResults = compareResults.map((item) => item.model === id ? { ...item, state: "pending", message: pendingMessage } : item);
    updateCompareResultProgress(id, "pending", pendingMessage);
    setStatus(els.compareStatus, `${index + 1}/${ids.length} ${modelLabel(id, id)} を生成中です。完了済みの音声は再生できます。`);
    await generateCompareModel(id, bodyBase);
    if (index + 1 < ids.length) {
      const successCount = compareResults.filter((item) => item.state === "success").length;
      setStatus(els.compareStatus, `${index + 1}/${ids.length} 完了（成功 ${successCount}件）。完了済みの音声は再生できます。`);
    }
  }
  if (compareResults.some((item) => item.state === "success")) incrementSeedInputIfNeeded(els.compareSeed, els.compareSeedAutoIncrement);
  saveCompareFormSettings();
  setCompareGenerationActive(false);
  updateCompareButtonState();
  setStatus(els.compareStatus, "比較生成が完了しました。");
  await playCompareResultIfEnabled();
  const selectedResults = compareResults.filter((item) => activeCompareModelIds.has(item.model));
  const successful = selectedResults.filter((item) => item.state === "success");
  const recommended = successful.find((item) => item.recommended) || successful[0] || null;
  addCompareHistory({
    createdAt: new Date().toISOString(),
    count: ids.length,
    text: els.compareText.value,
    instruction: els.compareInstruction.value,
    seed: seedRaw,
    referenceVoice: selectedVoice(els.compareVoice)?.voiceId || "",
    models: ids,
    successCount: successful.length,
    failedCount: ids.length - successful.length,
    recommendedModel: recommended?.model || "",
    audioUrl: recommended?.result?.audioUrl || "",
    chunking: bodyBase.chunking,
  });
  window.dispatchEvent(new CustomEvent("local-tts:history-record", {
    detail: {
      type: "compare",
      status: successful.length ? "success" : "failed",
      createdAt: new Date().toISOString(),
      text: els.compareText.value,
      instruction: els.compareInstruction.value,
      models: ids,
      referenceVoice: selectedVoice(els.compareVoice)?.voiceId || "",
      seed: seedRaw || "",
      audioUrl: recommended?.result?.audioUrl || "",
      duration: recommended?.result?.duration || "",
      raw: { results: selectedResults }
    }
  }));
}

function compareBodyBaseFromForm() {
  const seedRaw = els.compareSeed.value.trim();
  return {
    text: els.compareText.value,
    instruction: els.compareInstruction.value,
    language: els.compareLanguage.value,
    seed: seedRaw || undefined,
    chunking: chunkSettingsFromForm("compare").chunking
  };
}

async function regenerateCompareModel(id) {
  if (compareGenerationActive) return;
  if (!modelsById.has(id) || !compareResults.some((item) => item.model === id)) return;
  normalizeSeedInput(els.compareSeed);
  saveCompareFormSettings();
  const seedRaw = els.compareSeed.value.trim();
  if (seedRaw && !Number.isInteger(Number(seedRaw))) {
    setStatus(els.compareStatus, "seed は整数で入力してください。", true);
    return;
  }
  resetCompareDiagnostics();
  setCompareGenerationActive(true);
  activeCompareModelIds = new Set([id]);
  const pendingMessage = compareResults.find((item) => item.model === id)?.result?.audioUrl
    ? "再生成中です。前回の音声はそのまま再生できます。"
    : "再生成中です。";
  compareResults = compareResults.map((item) => item.model === id ? { ...item, state: "pending", message: pendingMessage, score: 0, recommended: false } : item);
  updateCompareResultProgress(id, "pending", pendingMessage);
  updateCompareButtonState();
  setStatus(els.compareStatus, `${modelLabel(id, id)} を再生成しています...`);
  await generateCompareModel(id, compareBodyBaseFromForm());
  if (compareResults.some((item) => item.model === id && item.state === "success")) incrementSeedInputIfNeeded(els.compareSeed, els.compareSeedAutoIncrement);
  saveCompareFormSettings();
  setCompareGenerationActive(false);
  updateCompareButtonState();
  setStatus(els.compareStatus, `${modelLabel(id, id)} の再生成が完了しました。`);
  await playCompareResultIfEnabled(id);
}

function adoptCompareModel(id) {
  const item = compareResults.find((result) => result.model === id && result.state === "success");
  if (!item) {
    setStatus(els.compareStatus, "採用できる生成結果がありません。", true);
    return;
  }
  if (!Array.from(els.normalModel.options).some((option) => option.value === id && !option.disabled)) {
    setStatus(els.compareStatus, "このモデルは通常生成で利用できません。", true);
    return;
  }
  els.normalModel.value = id;
  els.normalText.value = els.compareText.value;
  els.normalInstruction.value = els.compareInstruction.value;
  els.normalLanguage.value = els.compareLanguage.value;
  els.normalSeed.value = els.compareSeed.value;
  copyChunkSettings("compare", "normal");
  refreshTextCountsAndChunkPreview();
  updateNormalModelInfo();
  switchTab("normal");
  setStatus(els.normalStatus, `${modelLabel(id, id)} と比較条件を通常生成へ反映しました。`);
}

function selectedCompareModels() {
  return all('[data-model-card] input:checked').map((input) => input.value).filter((id) => modelsById.has(id));
}

function updateCompareInstructionUi() {
  const selectedModels = selectedCompareModels()
    .map((id) => modelsById.get(id))
    .filter(Boolean);
  const supportedModels = selectedModels.filter((model) => supportsInstruction(model));
  const instructionSupported = supportedModels.length > 0;
  const voice = selectedVoice(els.compareVoice);
  const instructionRequired = supportedModels.some((model) => requiresInstruction(model, voice));

  if (els.compareInstruction) els.compareInstruction.disabled = !instructionSupported;
  if (els.compareInstructionField) {
    els.compareInstructionField.hidden = !instructionSupported;
    els.compareInstructionField.style.display = instructionSupported ? "grid" : "none";
    els.compareInstructionField.classList.remove("is-disabled");
  }
  if (instructionSupported) {
    setRequirementBadge(
      els.compareInstructionRequirement,
      instructionRequired ? "必須" : "任意",
      instructionRequired ? "required" : "optional",
    );
  }
  const emojiVisible = shouldShowIrodoriEmojiPalette("compare");
  if (els.compareAdvancedGuidance) els.compareAdvancedGuidance.hidden = !instructionSupported && !emojiVisible;
  if (els.compareAdvancedSummary) {
    const parts = [];
    if (instructionSupported) parts.push("話し方");
    if (emojiVisible) parts.push("感情");
    parts.push("長文分割", "再生設定");
    els.compareAdvancedSummary.textContent = parts.join("・");
  }
}

function updateCompareButtonState() {
  const selected = selectedCompareModels();
  const hasText = Boolean(els.compareText.value.trim());
  updateIrodoriEmojiPaletteVisibility();
  updateCompareInstructionUi();
  els.compareGenerate.disabled = compareGenerationActive || !selected.length || !hasText;
  if (compareGenerationActive) return;
  const warning = [...new Set(selected.map((id) => modelPerformanceWarning(modelsById.get(id))).filter(Boolean))].join(" ");
  const status = selected.length
    ? `${selected.length}\u30e2\u30c7\u30eb\u3092\u9806\u756a\u306b\u751f\u6210\u3057\u307e\u3059\u3002\u5b8c\u4e86\u3057\u305f\u97f3\u58f0\u304b\u3089\u518d\u751f\u3067\u304d\u307e\u3059\u3002`
    : "\u30e2\u30c7\u30eb\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044\u3002";
  if (!hasText) {
    setStatus(els.compareStatus, "\u8aad\u307f\u4e0a\u3052\u30c6\u30ad\u30b9\u30c8\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002");
    return;
  }
  setStatus(els.compareStatus, warning ? `${status} ${warning}` : status, false, Boolean(warning));
}

function resultCardHtml(id, state, result = {}, message = "") {
  const profile = profileFor(id);
  const statusClass = state === "success" ? "success" : state === "pending" || state === "queued" ? "pending" : state === "warning" || state === "stale" ? "warning" : "failed";
  const statusText = state === "success" ? "成功" : state === "pending" ? "生成中" : state === "queued" ? "待機中" : state === "stale" ? "前回結果" : state === "warning" ? "一部警告" : "失敗";
  const recommended = compareResults.some((item) => item.model === id && item.recommended);
  const audioUrl = result.audioUrl || "";
  const audioContent = audioUrl
    ? `<div class="audio-row">
        <button class="play-round" type="button" data-dynamic-audio="${escapeHtml(id)}">▶</button>
        <div class="waveform"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
        <span class="duration-pill">${escapeHtml(result.duration || "--:--")}</span>
        <a class="icon-link" href="${escapeHtml(audioUrl)}" download>⇩</a>
        <audio id="compareAudio-${escapeHtml(id)}" class="compare-native-audio" controls src="${escapeHtml(audioUrl)}" preload="auto"></audio>
      </div>`
    : `<div class="compare-audio-pending">${state === "pending" ? "生成中です" : state === "queued" ? "順番待ちです" : "音声を生成できませんでした"}</div>`;
  return `
    <article class="result-card ${recommended ? "recommended" : ""}" data-result-model="${escapeHtml(id)}">
      <div class="result-card-head">
        <div><h3>${escapeHtml(modelLabel(id, id))}</h3>${recommended ? '<span class="recommend-badge">今回の入力におすすめ</span>' : ""}</div>
        <span class="status-badge ${statusClass}">${statusText}</span>
      </div>
      <div class="rating-row">
        <span>自然さ <b class="stars">★★★★☆</b></span>
        <span>感情 <b class="stars">★★★★☆</b></span>
        <span>安定性 <b class="stars">★★★★☆</b></span>
        <span>速度 <b class="stars">★★★★☆</b></span>
      </div>
      ${audioContent}
      <div class="memo-box"><p>${escapeHtml(message || profile.memo)}</p></div>
      <div class="result-actions">
        <button class="secondary-button" type="button" data-regenerate-model="${escapeHtml(id)}" ${state === "pending" || state === "queued" ? "disabled" : ""}>単独で再生成</button>
        <button class="primary-button" type="button" data-adopt-model="${escapeHtml(id)}" ${audioUrl ? "" : "disabled"}>このモデルを採用</button>
      </div>
    </article>`;
}

function renderCompareResults() {
  if (!compareResults.length) {
    els.compareResults.innerHTML = '<div class="empty-state">同じ文章で複数モデルを生成すると、ここに横並びで結果が表示されます。</div>';
    els.compareResultCount.textContent = "（0件）";
  } else {
    els.compareResults.innerHTML = compareResults.map((item) => resultCardHtml(item.model, item.state, item.result, item.message)).join("");
    els.compareResultCount.textContent = `（${compareResults.length}件）`;
  }
  attachAudioButtons();
}

function syncCompareRecommendationDom() {
  all("[data-result-model]").forEach((card) => {
    const id = card.dataset.resultModel || "";
    const recommended = compareResults.some((item) => item.model === id && item.recommended);
    card.classList.toggle("recommended", recommended);
    const heading = card.querySelector(".result-card-head > div");
    const badge = heading?.querySelector(".recommend-badge");
    if (recommended && heading && !badge) {
      const nextBadge = document.createElement("span");
      nextBadge.className = "recommend-badge";
      nextBadge.textContent = "今回の入力におすすめ";
      heading.appendChild(nextBadge);
    } else if (!recommended) badge?.remove();
  });
}

function renderCompareResultModel(id) {
  const item = compareResults.find((result) => result.model === id);
  const currentCard = els.compareResults.querySelector(`[data-result-model="${CSS.escape(id)}"]`);
  if (!item || !currentCard) {
    renderCompareResults();
    return;
  }
  const template = document.createElement("template");
  template.innerHTML = resultCardHtml(item.model, item.state, item.result, item.message).trim();
  currentCard.replaceWith(template.content.firstElementChild);
  attachAudioButtons();
  syncCompareRecommendationDom();
}

async function playCompareResultIfEnabled(preferredModel = "") {
  if (!els.compareAutoPlay?.checked) return false;
  const preferred = compareResults.find((item) => item.model === preferredModel && item.state === "success" && item.result?.audioUrl);
  const recommended = compareResults.find((item) => item.recommended && item.state === "success" && item.result?.audioUrl);
  const target = preferred || recommended || compareResults.find((item) => item.state === "success" && item.result?.audioUrl);
  if (!target) return false;
  const audio = document.querySelector(`#compareAudio-${CSS.escape(target.model)}`);
  if (!audio) return false;
  try {
    all("#compareResultsGrid audio").forEach((item) => { if (item !== audio) item.pause(); });
    await audio.play();
    return true;
  } catch (error) {
    setStatus(els.compareStatus, `比較生成は完了しましたが、自動再生できませんでした: ${error.message || error}`, true);
    return false;
  }
}

function addCompareHistory(item) {
  compareHistory = [item, ...compareHistory].slice(0, 8);
  saveList(COMPARE_HISTORY_KEY, compareHistory);
  renderCompareHistory();
}

function restoreCompareHistoryItem(index) {
  const item = compareHistory[index];
  if (!item) return;
  if (item.text) els.compareText.value = item.text;
  if (item.instruction != null) els.compareInstruction.value = item.instruction;
  if (item.seed != null && item.seed !== "") els.compareSeed.value = String(item.seed);
  if (item.referenceVoice && Array.from(els.compareVoice.options).some((option) => option.value === item.referenceVoice && !option.disabled)) els.compareVoice.value = item.referenceVoice;
  if (Array.isArray(item.models)) {
    const selected = new Set(item.models);
    all('[data-model-card] input:not(:disabled)').forEach((input) => { input.checked = selected.has(input.value); });
  }
  if (item.chunking?.softChunkChars) applyChunkPreset("compare", item.chunking.softChunkChars);
  refreshTextCountsAndChunkPreview();
  saveCompareFormSettings();
  updateCompareButtonState();
  setStatus(els.compareStatus, "比較履歴の文章・モデル・seedを戻しました。");
}

function renderCompareHistory() {
  els.compareHistory.innerHTML = compareHistory.length ? compareHistory.map((item, index) => {
    const total = Number(item.models?.length || item.count || 0);
    const success = Number.isFinite(Number(item.successCount)) ? Number(item.successCount) : 0;
    const recommended = item.recommendedModel ? modelLabel(item.recommendedModel, item.recommendedModel) : "記録なし";
    return `
      <article class="mini-history-item rich-history-item compare-history-item">
        ${item.audioUrl ? `<button class="mini-history-play" type="button" data-history-audio="${escapeHtml(item.audioUrl)}" aria-label="おすすめ結果を再生">▶</button>` : '<span class="mini-history-icon" aria-hidden="true">▦</span>'}
        <div class="mini-history-content">
          <div class="mini-history-title"><strong>${escapeHtml(`${total}モデル比較`)}</strong><small>${escapeHtml(new Date(item.createdAt).toLocaleString("ja-JP"))}</small></div>
          <p class="mini-history-text">${escapeHtml(String(item.text || "文章情報なし").trim())}</p>
          <div class="mini-history-chips"><span>成功 ${success}/${total}</span><span>推奨 ${escapeHtml(recommended)}</span>${item.seed !== "" && item.seed != null ? `<span>seed ${escapeHtml(String(item.seed))}</span>` : ""}</div>
          <button class="link-button mini-history-restore" type="button" data-restore-compare-history="${index}">比較条件を戻す</button>
        </div>
      </article>`;
  }).join("") : '<div class="empty-state">比較履歴はありません。生成後は文章、対象モデル、成功数、おすすめ結果をここで確認できます。</div>';
  attachAudioButtons();
}

