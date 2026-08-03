(() => {
  const HISTORY_KEY = "local-tts-generation-history-v1";
  const MAX_HISTORY = 120;
  const HISTORY_PAGE_SIZE = 20;
  const MAX_DIAGNOSTIC_TEXT_CHARS = 6000;
  const MODEL_LABELS_FALLBACK = {
    irodori_v4_small: "Irodori v4 Small",
    irodori_v3: "Irodori v3",
    irodori_v3_voicedesign: "Irodori v3 VoiceDesign",
    irodori_v2: "Irodori v2",
    f5_tts_zero_shot: "F5-TTS Zero-shot",
    gpt_sovits_zero_shot: "GPT-SoVITS Zero-shot",
    gpt_sovits_finetuned: "GPT-SoVITS Fine-tuned",
    qwen3_tts_clone_0_6b: "Qwen3-TTS Clone 0.6B",
    qwen3_tts_clone_1_7b: "Qwen 1.7B",
    qwen3_tts_design_1_7b: "Qwen3-TTS Design 1.7B",
    mock: "Mock WAV"
  };

  const $ = (selector) => document.querySelector(selector);
  const all = (selector) => Array.from(document.querySelectorAll(selector));
  const sharedUi = window.LocalTtsUi;

  const els = {
    list: $("#historyList"),
    detail: $("#historyDetailBody"),
    detailPanel: $("#historyDetailPanel"),
    close: $("#historyDetailClose"),
    search: $("#historySearchInput"),
    favoriteOnly: $("#historyFavoriteOnly"),
    resultSummary: $("#historyResultSummary"),
    loadMore: $("#historyLoadMoreButton"),
    clearAll: $("#historyClearAllButton")
  };

  const state = {
    type: "all",
    status: "all",
    query: "",
    favoriteOnly: false,
    selectedId: "",
    visibleCount: HISTORY_PAGE_SIZE,
    storageError: ""
  };

  let historyItems = loadHistory();

  function escapeHtml(value) {
    return sharedUi.escapeHtml(value);
  }

  function compactDiagnosticText(value) {
    if (value === undefined || value === null || value === "") return "";
    let text;
    try {
      text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    } catch {
      text = String(value);
    }
    if (text.length <= MAX_DIAGNOSTIC_TEXT_CHARS) return text;
    const headLength = Math.floor(MAX_DIAGNOSTIC_TEXT_CHARS * 0.72);
    const tailLength = MAX_DIAGNOSTIC_TEXT_CHARS - headLength;
    return `${text.slice(0, headLength)}\n\n… 履歴保存時に長い診断ログを省略しました …\n\n${text.slice(-tailLength)}`;
  }

  function historyNeedsCompaction(item) {
    return Boolean(item && typeof item === "object" && (
      Object.prototype.hasOwnProperty.call(item, "raw")
      || String(item.rawText || "").length > MAX_DIAGNOSTIC_TEXT_CHARS + 100
    ));
  }

  function loadHistory() {
    const stored = sharedUi.loadList(HISTORY_KEY, MAX_HISTORY);
    const loaded = stored.map((item) => normalizeRecord(item));
    if (stored.some(historyNeedsCompaction)) {
      try {
        sharedUi.saveList(HISTORY_KEY, loaded, MAX_HISTORY);
      } catch {
        state.storageError = "履歴ストレージを整理できませんでした。ブラウザの保存容量を確認してください。";
      }
    }
    return loaded;
  }

  function saveHistory() {
    try {
      sharedUi.saveList(HISTORY_KEY, historyItems, MAX_HISTORY);
      state.storageError = "";
      return true;
    } catch {
      state.storageError = "履歴を保存できませんでした。古い履歴を削除するか、ブラウザの保存容量を確認してください。";
      return false;
    }
  }

  function makeId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return `hist-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function modelLabel(value) {
    const raw = String(value || "").trim();
    return MODEL_LABELS_FALLBACK[raw] || raw || "-";
  }

  function typeLabel(type) {
    if (type === "rvc") return "RVC変換";
    if (type === "compare") return "モデル比較";
    return "通常生成";
  }

  function typeClass(type) {
    if (type === "rvc") return "rvc";
    if (type === "compare") return "compare";
    return "normal";
  }

  function statusText(status) {
    return status === "failed" ? "失敗" : "成功";
  }

  function formatDate(value) {
    const date = value ? new Date(value) : new Date();
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleString("ja-JP", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
  }

  function clip(value, max = 86) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    return text.length > max ? `${text.slice(0, max)}…` : text;
  }

  function fileNameFromUrl(url) {
    const raw = String(url || "").trim();
    if (!raw) return "";
    try {
      const parsed = new URL(raw, location.href);
      return decodeURIComponent(parsed.pathname.split("/").pop() || "");
    } catch {
      return raw.split(/[\\/]/).pop() || raw;
    }
  }

  function normalizeRecord(detail = {}) {
    const type = ["normal", "compare", "rvc"].includes(detail.type) ? detail.type : "normal";
    const status = detail.status === "failed" ? "failed" : "success";
    const primaryAudioUrl = String(detail.convertedAudioUrl || detail.audioUrl || detail.intermediateAudioUrl || "").trim();
    const fileName = String(detail.fileName || fileNameFromUrl(primaryAudioUrl) || "").trim();
    return {
      id: detail.id || makeId(),
      createdAt: detail.createdAt || new Date().toISOString(),
      type,
      status,
      favorite: Boolean(detail.favorite),
      text: String(detail.text || detail.savedText || "").trim(),
      instruction: String(detail.instruction || "").trim(),
      model: String(detail.model || "").trim(),
      models: Array.isArray(detail.models) ? detail.models.map(String) : [],
      referenceVoice: String(detail.referenceVoice || detail.voiceId || "").trim(),
      seed: detail.seed ?? "",
      indexRate: detail.indexRate ?? "",
      f0upKey: detail.f0upKey ?? "",
      protect: detail.protect ?? "",
      inputSource: String(detail.inputSource || "").trim(),
      duration: String(detail.duration || "").trim(),
      fileName,
      filePath: String(detail.filePath || "").trim(),
      audioUrl: String(detail.audioUrl || "").trim(),
      intermediateAudioUrl: String(detail.intermediateAudioUrl || "").trim(),
      convertedAudioUrl: String(detail.convertedAudioUrl || "").trim(),
      error: String(detail.error || "").trim(),
      rawText: compactDiagnosticText(detail.rawText || detail.raw || "")
    };
  }

  function historyPageActive() {
    return Boolean($("#historyPage")?.classList.contains("active"));
  }

  function recordHistory(detail) {
    const item = normalizeRecord(detail);
    const hasUsefulPayload = item.text || item.audioUrl || item.intermediateAudioUrl || item.convertedAudioUrl || item.error;
    if (!hasUsefulPayload) return;
    historyItems = [item, ...historyItems.filter((old) => old.id !== item.id)].slice(0, MAX_HISTORY);
    if (!state.selectedId) state.selectedId = item.id;
    saveHistory();
    if (historyPageActive()) renderHistory();
  }

  function replaceReferenceVoiceId(value, previousVoiceId, nextVoiceId, key = "") {
    if (Array.isArray(value)) return value.map((item) => replaceReferenceVoiceId(item, previousVoiceId, nextVoiceId));
    if (!value || typeof value !== "object") {
      return ["voice", "voiceId", "referenceVoice"].includes(key) && value === previousVoiceId ? nextVoiceId : value;
    }
    return Object.fromEntries(Object.entries(value).map(([entryKey, entryValue]) => [
      entryKey,
      replaceReferenceVoiceId(entryValue, previousVoiceId, nextVoiceId, entryKey),
    ]));
  }

  function renameReferenceVoiceInHistory(previousVoiceId, nextVoiceId) {
    if (!previousVoiceId || !nextVoiceId || previousVoiceId === nextVoiceId) return;
    historyItems = replaceReferenceVoiceId(historyItems, previousVoiceId, nextVoiceId);
    saveHistory();
    if (historyPageActive()) renderHistory();
  }

  function filteredItems() {
    const query = state.query.trim().toLowerCase();
    return historyItems.filter((item) => {
      if (state.type !== "all" && item.type !== state.type) return false;
      if (state.status !== "all" && item.status !== state.status) return false;
      if (state.favoriteOnly && !item.favorite) return false;
      if (!query) return true;
      const target = [
        item.text,
        item.instruction,
        item.model,
        modelLabel(item.model),
        item.models.join(" "),
        item.referenceVoice,
        item.fileName,
        item.error
      ].join(" ").toLowerCase();
      return target.includes(query);
    });
  }

  function metaRow(item) {
    const modelText = item.type === "compare"
      ? (item.models.length ? item.models.map(modelLabel).join(" / ") : "-")
      : modelLabel(item.model);
    const cells = [
      ["TTSモデル", modelText],
      ["参照音声", item.referenceVoice || "（なし）"],
      ["出力時間", item.duration || "—"],
      ["ファイル", item.fileName || "—"]
    ];
    return cells.map(([label, value]) => `
      <div class="history-card-meta-item">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `).join("");
  }

  function primaryAudioUrl(item) {
    return item.convertedAudioUrl || item.audioUrl || item.intermediateAudioUrl || "";
  }

  function cardHtml(item, selected) {
    const audioUrl = primaryAudioUrl(item);
    const previewText = item.text || item.instruction || item.error || "保存された読み上げ文章はありません。";
    const canPlay = Boolean(audioUrl) && item.status !== "failed";
    return `
      <article class="history-card ${selected ? "active" : ""}" data-history-id="${escapeHtml(item.id)}">
        <div class="history-card-side">
          <strong>${escapeHtml(formatDate(item.createdAt))}</strong>
          <div class="history-badge-row">
            <span class="history-type-badge ${typeClass(item.type)}">${escapeHtml(typeLabel(item.type))}</span>
            <span class="status-badge ${item.status === "failed" ? "failed" : "success"}">${escapeHtml(statusText(item.status))}</span>
          </div>
          <small>seed: ${escapeHtml(item.seed || "-")}</small>
          ${item.type === "rvc" ? `<small>似せ度: ${escapeHtml(item.indexRate || "-")} / 音程: ${escapeHtml(item.f0upKey || "0")} / 安定性: ${escapeHtml(item.protect || "-")}</small>` : ""}
        </div>
        <div class="history-card-main">
          <div class="history-card-text">
            <span>保存した読み上げ文章（プレビュー）</span>
            <p>${escapeHtml(clip(previewText, 110))}</p>
          </div>
          <div class="history-card-meta">${metaRow(item)}</div>
          <audio class="history-audio" controls preload="none" ${audioUrl ? `src="${escapeHtml(audioUrl)}"` : ""}></audio>
        </div>
        <div class="history-card-actions">
          <button class="secondary-button small history-action-play" type="button" data-history-action="play" ${canPlay ? "" : "disabled"}>▶ 再生</button>
          <button class="secondary-button small" type="button" data-history-action="restore">⚙ 設定を復元</button>
          <button class="secondary-button small" type="button" data-history-action="copy">□ 文章をコピー</button>
          <button class="secondary-button small" type="button" data-history-action="folder">▱ ファイル情報をコピー</button>
          <button class="secondary-button small save-button" type="button" data-history-action="favorite">${item.favorite ? "★ お気に入り済み" : "☆ お気に入り"}</button>
        </div>
      </article>
    `;
  }

  function emptyHtml() {
    return `
      <div class="empty-state history-empty-state">
        まだ保存された履歴はありません。通常生成・モデル比較・RVC変換を実行すると、読み上げ文章と音声結果がここに保存されます。
      </div>
    `;
  }

  function renderList(items) {
    if (!els.list) return;
    if (!items.length) {
      els.list.innerHTML = emptyHtml();
      renderDetail(null);
      return;
    }
    if (!state.selectedId || !items.some((item) => item.id === state.selectedId)) {
      state.selectedId = items[0].id;
    }
    els.list.innerHTML = items.map((item) => cardHtml(item, item.id === state.selectedId)).join("");
    renderDetail(items.find((item) => item.id === state.selectedId) || items[0]);
  }

  function audioBlock(title, url) {
    return `
      <div class="history-detail-audio-row">
        <strong>${escapeHtml(title)}</strong>
        <div class="history-detail-audio-control">
          <audio controls preload="none" ${url ? `src="${escapeHtml(url)}"` : ""}></audio>
          <a class="icon-link history-download-link" href="${escapeHtml(url || "#")}" download title="download">⇩</a>
        </div>
      </div>
    `;
  }

  function renderDetail(item) {
    if (!els.detail) return;
    if (!item) {
      els.detail.innerHTML = '<div class="empty-state">左の履歴を選択すると詳細が表示されます。</div>';
      return;
    }
    const raw = item.rawText || item.error || "-";
    const modelText = item.type === "compare"
      ? (item.models.length ? item.models.map(modelLabel).join(" / ") : "-")
      : modelLabel(item.model);
    els.detail.innerHTML = `
      <div class="history-detail-summary">
        <div><span>▣</span>${escapeHtml(formatDate(item.createdAt))}</div>
        <div><span class="history-type-badge ${typeClass(item.type)}">${escapeHtml(typeLabel(item.type))}</span><span class="status-badge ${item.status === "failed" ? "failed" : "success"}">${escapeHtml(statusText(item.status))}</span></div>
        <div>seed: ${escapeHtml(item.seed || "-")}</div>
        ${item.type === "rvc" ? `<div>似せ度: ${escapeHtml(item.indexRate || "-")} / 音程: ${escapeHtml(item.f0upKey || "0")} / 安定性: ${escapeHtml(item.protect || "-")}</div>` : ""}
        <button class="history-detail-star" type="button" data-history-action="favorite" data-history-id="${escapeHtml(item.id)}">${item.favorite ? "★" : "☆"}</button>
      </div>

      <section class="history-detail-section">
        <h3>保存した読み上げ文章</h3>
        <textarea readonly>${escapeHtml(item.text || "保存された読み上げ文章はありません。")}</textarea>
      </section>

      <section class="history-detail-section">
        <h3>instruction / 話し方メモ</h3>
        <textarea readonly>${escapeHtml(item.instruction || "-")}</textarea>
      </section>

      <section class="history-detail-section history-detail-meta-section">
        <h3>設定</h3>
        <div class="history-detail-meta-grid">
          <span>モデル</span><strong>${escapeHtml(modelText)}</strong>
          <span>参照音声</span><strong>${escapeHtml(item.referenceVoice || "（なし）")}</strong>
          <span>入力元</span><strong>${escapeHtml(item.inputSource || "-")}</strong>
          <span>ファイル</span><strong>${escapeHtml(item.filePath || item.fileName || "-")}</strong>
        </div>
      </section>

      <section class="history-detail-section">
        <h3>出力音声</h3>
        ${item.type === "rvc" ? audioBlock("元TTS / 入力音声", item.intermediateAudioUrl) + audioBlock(`RVC後（${item.referenceVoice || "converted"}）`, item.convertedAudioUrl) : audioBlock(typeLabel(item.type), primaryAudioUrl(item))}
      </section>

      <p class="status-line" id="historyActionStatus"></p>

      <details class="history-json-details">
        <summary>実行ログ / JSON</summary>
        <pre>${escapeHtml(raw)}</pre>
      </details>
    `;
  }

  function resetVisibleHistory() {
    state.visibleCount = HISTORY_PAGE_SIZE;
    state.selectedId = "";
  }

  function renderHistory() {
    const filtered = filteredItems();
    const visible = filtered.slice(0, state.visibleCount);
    renderList(visible);
    if (els.resultSummary) {
      const shown = visible.length;
      const total = filtered.length;
      const storageNote = state.storageError ? ` ${state.storageError}` : "";
      els.resultSummary.textContent = `${shown} / ${total}件を表示（保存上限 ${MAX_HISTORY}件）。${storageNote}`;
      els.resultSummary.classList.toggle("error", Boolean(state.storageError));
    }
    if (els.loadMore) {
      els.loadMore.hidden = visible.length >= filtered.length;
      const remaining = Math.max(0, filtered.length - visible.length);
      els.loadMore.textContent = remaining > HISTORY_PAGE_SIZE
        ? `さらに${HISTORY_PAGE_SIZE}件表示`
        : `残り${remaining}件を表示`;
    }
  }

  function setActivePill(kind, value) {
    all(`[data-history-filter="${kind}"]`).forEach((button) => button.classList.toggle("active", button.dataset.value === value));
  }

  function activateTab(tab, updateHash = true) {
    const normalized = ["normal", "compare", "rvc", "history", "voices"].includes(tab) ? tab : "normal";
    all(".page-section").forEach((section) => section.classList.toggle("active", section.dataset.page === normalized));
    all(".top-tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === normalized));
    all(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.tab === normalized));
    if (normalized === "history") renderHistory();
    if (updateHash) history.replaceState(null, "", `#${normalized}`);
  }

  function setValue(selector, value) {
    const el = $(selector);
    if (!el || value === undefined || value === null || value === "") return;
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function restoreItem(item) {
    if (!item) return;
    if (item.type === "compare") {
      setValue("#compareTextInput", item.text);
      setValue("#compareInstructionInput", item.instruction);
      setValue("#compareSeedInput", item.seed);
      setValue("#compareReferenceVoiceSelect", item.referenceVoice);
      activateTab("compare");
      return;
    }
    if (item.type === "rvc") {
      setValue("#rvcTextInput", item.text);
      setValue("#rvcInstructionInput", item.instruction);
      setValue("#rvcSeedInput", item.seed);
      setValue("#rvcModelSelect", item.model);
      setValue("#rvcReferenceVoiceSelect", item.referenceVoice);
      setValue("#rvcIndexRatePresetSelect", item.indexRate);
      setValue("#rvcF0UpKeyPresetSelect", item.f0upKey);
      setValue("#rvcProtectPresetSelect", item.protect);
      const source = item.inputSource || "tts";
      const radio = $(`input[name="rvcInputSource"][value="${CSS.escape(source)}"]`);
      if (radio) {
        radio.checked = true;
        radio.dispatchEvent(new Event("input", { bubbles: true }));
        radio.dispatchEvent(new Event("change", { bubbles: true }));
      }
      activateTab("rvc");
      return;
    }
    setValue("#normalTextInput", item.text);
    setValue("#normalInstructionInput", item.instruction);
    setValue("#normalSeedInput", item.seed);
    setValue("#normalModelSelect", item.model);
    setValue("#normalReferenceVoiceSelect", item.referenceVoice);
    activateTab("normal");
  }

  async function copyItemText(item) {
    if (!item) return false;
    const text = item.text || item.instruction || "";
    if (!text) return false;
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.style.position = "fixed";
      helper.style.left = "-9999px";
      document.body.appendChild(helper);
      helper.focus();
      helper.select();
      const ok = document.execCommand("copy");
      helper.remove();
      return ok;
    }
  }

  async function copyFolderHint(item) {
    const value = item?.filePath || item?.fileName || primaryAudioUrl(item || {});
    if (!value) return false;
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      return false;
    }
  }

  function actionStatus(text, isError = false) {
    const el = $("#historyActionStatus");
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("error", isError);
  }

  function itemById(id) {
    return historyItems.find((item) => item.id === id) || null;
  }

  function toggleFavorite(item) {
    if (!item) return;
    historyItems = historyItems.map((old) => old.id === item.id ? { ...old, favorite: !old.favorite } : old);
    saveHistory();
    renderHistory();
  }

  function clearAllHistory({ notifyPeers = true } = {}) {
    historyItems = [];
    resetVisibleHistory();
    saveHistory();
    if (notifyPeers) window.dispatchEvent(new CustomEvent("local-tts:history-clear-all"));
    renderHistory();
  }

  function bindEvents() {
    document.addEventListener("click", async (event) => {
      const historyTab = event.target.closest('[data-tab="history"]');
      if (historyTab) {
        window.setTimeout(() => activateTab("history"), 0);
        return;
      }

      const filter = event.target.closest("[data-history-filter]");
      if (filter) {
        const kind = filter.dataset.historyFilter;
        const value = filter.dataset.value || "all";
        if (kind === "type") state.type = value;
        if (kind === "status") state.status = value;
        resetVisibleHistory();
        setActivePill(kind, value);
        renderHistory();
        return;
      }

      const actionButton = event.target.closest("[data-history-action]");
      if (actionButton) {
        const card = actionButton.closest("[data-history-id]");
        const id = actionButton.dataset.historyId || card?.dataset.historyId || state.selectedId;
        const item = itemById(id);
        const action = actionButton.dataset.historyAction;
        if (action === "favorite") toggleFavorite(item);
        if (action === "restore") restoreItem(item);
        if (action === "copy") actionStatus(await copyItemText(item) ? "読み上げ文章をコピーしました。" : "コピーできる読み上げ文章がありません。", !item?.text);
        if (action === "folder") actionStatus(await copyFolderHint(item) ? "ブラウザからフォルダを直接開けないため、ファイル情報をコピーしました。" : "コピーできるファイル情報がありません。", !item);
        if (action === "play") {
          const audio = card?.querySelector("audio");
          if (audio) audio.paused ? audio.play().catch(() => {}) : audio.pause();
        }
        return;
      }

      const card = event.target.closest("[data-history-id]");
      if (card && !event.target.closest("button,a,audio")) {
        state.selectedId = card.dataset.historyId || "";
        renderHistory();
      }
    });

    els.search?.addEventListener("input", () => {
      state.query = els.search.value || "";
      resetVisibleHistory();
      renderHistory();
    });
    els.favoriteOnly?.addEventListener("change", () => {
      state.favoriteOnly = Boolean(els.favoriteOnly.checked);
      resetVisibleHistory();
      renderHistory();
    });
    els.close?.addEventListener("click", () => {
      state.selectedId = "";
      renderDetail(null);
    });
    els.loadMore?.addEventListener("click", () => {
      state.visibleCount += HISTORY_PAGE_SIZE;
      renderHistory();
    });
    els.clearAll?.addEventListener("click", () => {
      if (!historyItems.length) return;
      if (!window.confirm("通常生成・モデル比較・RVC変換の保存済み履歴をすべて削除しますか？")) return;
      clearAllHistory();
    });
    window.addEventListener("local-tts:history-record", (event) => recordHistory(event.detail || {}));
    window.addEventListener("local-tts:reference-voice-renamed", (event) => {
      renameReferenceVoiceInHistory(
        String(event.detail?.previousVoiceId || "").trim(),
        String(event.detail?.voiceId || "").trim(),
      );
    });
  }

  bindEvents();
  if (historyPageActive()) renderHistory();

  const pageParam = new URLSearchParams(location.search).get("page");
  if (location.hash === "#history" || pageParam === "history") {
    window.setTimeout(() => activateTab("history", false), 0);
  }

  window.localTtsHistory = {
    record: recordHistory,
    render: renderHistory,
    clear: () => clearAllHistory()
  };
})();
