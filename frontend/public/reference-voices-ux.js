(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));
  const SUPPORTED_EXTENSIONS = new Set(["wav", "mp3", "m4a", "flac", "ogg", "aac"]);

  let selectedFile = null;
  let objectUrl = "";
  let registeredVoiceId = "";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function selectView(view) {
    const normalized = view === "manage" ? "manage" : "register";
    $$('[data-voice-view]').forEach((button) => {
      const active = button.dataset.voiceView === normalized;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    $$('[data-voice-view-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.voiceViewPanel !== normalized;
    });
  }

  function selectMethod(method) {
    const normalized = ["mic", "file", "youtube"].includes(method) ? method : "mic";
    $$('[data-voice-method]').forEach((button) => {
      const active = button.dataset.voiceMethod === normalized;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    $$('[data-voice-method-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.voiceMethodPanel !== normalized;
    });
    if (normalized === "youtube") {
      requestAnimationFrame(() => $$('[data-youtube-candidate-text]').forEach(autoGrow));
    }
  }

  function autoGrow(textarea) {
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.max(148, textarea.scrollHeight + 2)}px`;
  }

  function selectedExtension() {
    return String(selectedFile?.name || "").split(".").pop()?.toLowerCase() || "";
  }

  function existingVoiceIds() {
    return new Set($$('[data-voice-manage-id]').map((item) => String(item.dataset.voiceManageId || "")));
  }

  function fileValidationMessage() {
    const voiceId = $("#voiceFileIdInput")?.value.trim() || "";
    const referenceText = $("#voiceFileTextInput")?.value.trim() || "";
    if (!selectedFile) return "音声ファイルを選択してください。";
    if (!SUPPORTED_EXTENSIONS.has(selectedExtension())) return "対応形式は wav・mp3・m4a・flac・ogg・aac です。ファイルを選び直してください。";
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(voiceId)) return "参照音声名は半角英数字・_・-のみ、80文字以内で入力してください。";
    if (existingVoiceIds().has(voiceId)) return "同じ参照音声名が既にあります。別の名前を入力してください。";
    if (!referenceText) return "音声内で実際に話している文章を入力してください。";
    return "";
  }

  function updateFileState({ showMessage = false } = {}) {
    const message = fileValidationMessage();
    const button = $("#voiceFileSaveButton");
    if (button) button.disabled = Boolean(message);
    if (showMessage && message) {
      const status = $("#voiceFileStatus");
      if (status) status.textContent = message;
    }
  }

  function releaseSelectedFile() {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = "";
    selectedFile = null;
    const input = $("#voiceFileInput");
    if (input) input.value = "";
    const audio = $("#voiceFilePreview");
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    const badge = $("#voiceFileBadge");
    if (badge) {
      badge.textContent = "未選択";
      badge.className = "status-badge pending";
    }
    const duration = $("#voiceFileDuration");
    if (duration) duration.textContent = "音声時間: 未選択";
    updateFileState();
  }

  function showSuccess(voiceId) {
    const normalized = String(voiceId || "").trim();
    const panel = $("#voiceRegistrationSuccess");
    if (!panel || !normalized) return;
    registeredVoiceId = normalized;
    panel.dataset.registeredVoiceId = normalized;
    panel.hidden = false;
    panel.innerHTML = `
      <h2>登録できました</h2>
      <p>参照音声「${escapeHtml(normalized)}」を登録しました。音声クローン対応モデルで使用できます。</p>
      <div class="voice-success-actions">
        <button class="primary-button" type="button" data-success="normal">通常生成で使う</button>
        <button class="secondary-button" type="button" data-success="manage">登録済み音声を見る</button>
        <button class="secondary-button" type="button" data-success="again">別の音声を登録する</button>
      </div>`;
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("ファイルを読み込めませんでした"));
      reader.readAsDataURL(file);
    });
  }

  async function saveFileVoice() {
    const button = $("#voiceFileSaveButton");
    const status = $("#voiceFileStatus");
    const validationMessage = fileValidationMessage();
    if (validationMessage) {
      if (status) status.textContent = validationMessage;
      updateFileState();
      return;
    }

    const file = selectedFile;
    const voiceId = $("#voiceFileIdInput")?.value.trim() || "";
    const referenceText = $("#voiceFileTextInput")?.value.trim() || "";
    if (button) button.disabled = true;
    if (status) status.textContent = "音声を確認し、WAVへ変換して保存しています...";
    try {
      const dataUrl = await fileToDataUrl(file);
      const response = await fetch("/api/reference-voices/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          voiceId,
          referenceText,
          fileName: file.name,
          mimeType: file.type,
          dataUrl,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || "音声ファイルを登録できませんでした。入力内容を確認してください。");
      }
      if (status) status.textContent = `参照音声「${voiceId}」を登録しました。`;
      window.dispatchEvent(new CustomEvent("local-tts:reference-voices-changed"));
      window.dispatchEvent(new CustomEvent("local-tts:reference-voice-registered", {
        detail: { voiceId, source: "file" },
      }));
    } catch (error) {
      if (status) status.textContent = `登録できませんでした: ${error.message || error}`;
      updateFileState();
    }
  }

  $$('[data-voice-view]').forEach((button) => button.addEventListener("click", () => selectView(button.dataset.voiceView)));
  $$('[data-voice-method]').forEach((button) => button.addEventListener("click", () => selectMethod(button.dataset.voiceMethod)));

  document.addEventListener("click", (event) => {
    const openButton = event.target.closest("[data-voice-open]");
    if (openButton) {
      selectView(openButton.dataset.voiceOpen);
      if (openButton.dataset.voiceOpen === "register") selectMethod("mic");
    }
  });

  document.addEventListener("input", (event) => {
    if (event.target.matches('[data-youtube-candidate-text]')) autoGrow(event.target);
    if (event.target.matches("#voiceFileIdInput, #voiceFileTextInput")) updateFileState({ showMessage: true });
  });

  const candidates = $("#youtubeReferenceCandidates");
  if (candidates) {
    new MutationObserver(() => {
      requestAnimationFrame(() => $$('[data-youtube-candidate-text]').forEach(autoGrow));
    }).observe(candidates, { childList: true, subtree: true });
  }

  $("#voiceFileInput")?.addEventListener("change", (event) => {
    const nextFile = event.target.files?.[0] || null;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = "";
    selectedFile = nextFile;
    const status = $("#voiceFileStatus");
    if (!selectedFile) {
      if (status) status.textContent = "音声ファイルを選択してください。";
      return;
    }
    if (!SUPPORTED_EXTENSIONS.has(selectedExtension())) {
      if (status) status.textContent = "対応形式は wav・mp3・m4a・flac・ogg・aac です。ファイルを選び直してください。";
      updateFileState();
      return;
    }
    objectUrl = URL.createObjectURL(selectedFile);
    const audio = $("#voiceFilePreview");
    if (audio) audio.src = objectUrl;
    const badge = $("#voiceFileBadge");
    if (badge) {
      badge.textContent = "選択済み";
      badge.className = "status-badge success";
    }
    if (status) status.textContent = "プレビューを確認し、音声内で実際に話している文章を入力してください。";
    updateFileState();
  });

  $("#voiceFilePreview")?.addEventListener("loadedmetadata", (event) => {
    const duration = Number(event.target.duration);
    const target = $("#voiceFileDuration");
    if (!target) return;
    const warning = Number.isFinite(duration) && (duration < 3 || duration > 10)
      ? "（GPT-SoVITSの推奨3〜10秒の範囲外です。ほかのモデルでは使える場合があります）"
      : "";
    target.textContent = `音声時間: ${Number.isFinite(duration) ? `${duration.toFixed(2)}秒` : "取得できません"}${warning}`;
  });

  $("#voiceFilePreview")?.addEventListener("error", () => {
    const target = $("#voiceFileDuration");
    if (target) target.textContent = "音声時間: ブラウザで確認できません。登録時にサーバー側で音声を検証します。";
  });

  $("#voiceFileSaveButton")?.addEventListener("click", saveFileVoice);

  $("#voiceRegistrationSuccess")?.addEventListener("click", (event) => {
    const action = event.target.closest("[data-success]")?.dataset.success;
    if (!action) return;
    if (action === "manage") selectView("manage");
    if (action === "again") {
      event.currentTarget.hidden = true;
      selectView("register");
      selectMethod("mic");
      releaseSelectedFile();
    }
    if (action === "normal" && registeredVoiceId) {
      window.dispatchEvent(new CustomEvent("local-tts:use-reference-voice", {
        detail: { voiceId: registeredVoiceId },
      }));
    }
  });

  window.addEventListener("local-tts:reference-voice-registered", (event) => {
    const voiceId = String(event.detail?.voiceId || "").trim();
    if (voiceId) showSuccess(voiceId);
  });
  window.addEventListener("local-tts:reference-voices-changed", () => updateFileState());

  selectView("register");
  selectMethod("mic");
  updateFileState();
})();
