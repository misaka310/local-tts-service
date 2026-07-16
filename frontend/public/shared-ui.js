(() => {
  function loadList(key, limit = 24) {
    try {
      const parsed = JSON.parse(localStorage.getItem(key) || "[]");
      return Array.isArray(parsed) ? parsed.slice(0, limit) : [];
    } catch {
      return [];
    }
  }

  function saveList(key, value, limit = 24) {
    const list = Array.isArray(value) ? value : [];
    localStorage.setItem(key, JSON.stringify(list.slice(0, limit)));
  }

  function loadObject(key, fallback = {}) {
    try {
      const parsed = JSON.parse(localStorage.getItem(key) || "null");
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : fallback;
    } catch {
      return fallback;
    }
  }

  function saveObject(key, value) {
    localStorage.setItem(key, JSON.stringify(value || {}));
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const text = await response.text();
    let payload;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = { ok: false, error: text || `HTTP ${response.status}` };
    }
    if (!response.ok || payload.ok === false) {
      const error = new Error(payload.errorMessage || payload.error || `HTTP ${response.status}`);
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function setStatus(el, text, isError = false, isWarning = false) {
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("error", isError);
    el.classList.toggle("warning", !isError && isWarning);
  }

  function setServiceState(state, detail = "") {
    const status = document.querySelector("#serviceStatus");
    const statusText = status?.querySelector("span");
    const detailText = document.querySelector("#serviceStatusDetail");
    const normalized = ["running", "error"].includes(state) ? state : "checking";
    if (status) status.dataset.state = normalized;
    if (statusText) statusText.textContent = normalized === "running" ? "稼働中" : normalized === "error" ? "確認必要" : "確認中";
    if (detailText) detailText.textContent = detail || (normalized === "running" ? "バックエンドへ接続済み" : normalized === "error" ? "画面のエラーを確認してください" : "バックエンドへ接続しています");
  }

  function insertAtCursor(textarea, value) {
    if (!textarea || !value) return;
    const start = Number.isInteger(textarea.selectionStart) ? textarea.selectionStart : textarea.value.length;
    const end = Number.isInteger(textarea.selectionEnd) ? textarea.selectionEnd : start;
    textarea.value = `${textarea.value.slice(0, start)}${value}${textarea.value.slice(end)}`;
    const nextCursor = start + value.length;
    textarea.focus();
    textarea.setSelectionRange(nextCursor, nextCursor);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }

  async function copyText(value) {
    if (!value) return false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch {
      return false;
    }
    return false;
  }

  window.LocalTtsUi = Object.freeze({
    loadList,
    saveList,
    loadObject,
    saveObject,
    escapeHtml,
    fetchJson,
    setStatus,
    setServiceState,
    insertAtCursor,
    copyText
  });
})();
