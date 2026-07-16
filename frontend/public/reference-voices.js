(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const els = {
    page: $("#voicesPage"),
    voiceId: $("#voiceIdInput"),
    referenceText: $("#voiceReferenceTextInput"),
    referenceTextCount: $("#voiceReferenceTextCount"),
    micDevice: $("#voiceMicDeviceSelect"),
    recordStart: $("#voiceRecordStartButton"),
    recordStop: $("#voiceRecordStopButton"),
    recordTimer: $("#voiceRecordTimer"),
    recordingBadge: $("#voiceRecordingBadge"),
    recordedAudio: $("#voiceRecordedAudio"),
    save: $("#voiceSaveButton"),
    status: $("#voiceManagerStatus"),
    reload: $("#voiceListReloadButton"),
    list: $("#voiceManageList"),
    detail: $("#voiceManageDetail"),
    youtubeUrl: $("#youtubeReferenceUrlInput"),
    youtubeName: $("#youtubeReferenceNameInput"),
    youtubeDemucs: $("#youtubeReferenceDemucsInput"),
    youtubeRights: $("#youtubeReferenceRightsInput"),
    youtubeAnalyze: $("#youtubeReferenceAnalyzeButton"),
    youtubeStatus: $("#youtubeReferenceStatus"),
    youtubeBadge: $("#youtubeReferenceBadge"),
    youtubeCandidates: $("#youtubeReferenceCandidates"),
    youtubeMore: $("#youtubeReferenceMoreButton")
  };

  if (!els.page) return;

  let voices = [];
  let selectedVoiceId = "";
  let mediaStream = null;
  let mediaRecorder = null;
  let recordedChunks = [];
  let recordedBlob = null;
  let recordedObjectUrl = "";
  let recordingStartedAt = 0;
  let recordingTimerId = 0;
  let youtubeJob = null;
  let youtubeAdditionalRequested = false;
  let voiceListFilter = "all";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const raw = await response.text();
    let payload = {};
    try {
      payload = raw ? JSON.parse(raw) : {};
    } catch {
      payload = { error: raw || `HTTP ${response.status}` };
    }
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || payload.errorMessage || `HTTP ${response.status}`);
    }
    return payload;
  }

  function setStatus(message, isError = false) {
    if (!els.status) return;
    els.status.textContent = message;
    els.status.classList.toggle("error", Boolean(isError));
  }

  function setRecordingBadge(text, state = "pending") {
    if (!els.recordingBadge) return;
    els.recordingBadge.textContent = text;
    els.recordingBadge.className = `status-badge ${state}`;
  }

  function announceRegistration(voiceId, source) {
    window.dispatchEvent(new CustomEvent("local-tts:reference-voices-changed"));
    window.dispatchEvent(new CustomEvent("local-tts:reference-voice-registered", {
      detail: { voiceId, source },
    }));
  }

  function formatDuration(seconds) {
    if (!Number.isFinite(Number(seconds)) || Number(seconds) <= 0) return "長さ不明";
    return `${Number(seconds).toFixed(2)}秒`;
  }

  function formatTimer(seconds) {
    const total = Math.max(0, Math.floor(seconds));
    return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
  }

  function updateTextCount() {
    if (els.referenceTextCount) els.referenceTextCount.textContent = `${els.referenceText?.value.length || 0} / 5000`;
    updateSaveState();
  }

  function validVoiceId() {
    return /^[A-Za-z0-9_-]{1,80}$/.test(String(els.voiceId?.value || "").trim());
  }

  function voiceNameExists() {
    const value = String(els.voiceId?.value || "").trim();
    return Boolean(value) && voices.some((voice) => voice.voiceId === value);
  }

  function updateSaveState() {
    if (!els.save) return;
    els.save.disabled = !recordedBlob || !validVoiceId() || voiceNameExists() || !String(els.referenceText?.value || "").trim();
  }

  function handleVoiceNameInput() {
    updateSaveState();
    if (voiceNameExists()) setStatus("同じ参照音声名が既にあります。別の名前を指定してください。", true);
  }

  function stopStream() {
    mediaStream?.getTracks?.().forEach((track) => track.stop());
    mediaStream = null;
  }

  function clearRecordingTimer() {
    clearInterval(recordingTimerId);
    recordingTimerId = 0;
  }

  function resetRecordedPreview() {
    if (recordedObjectUrl) URL.revokeObjectURL(recordedObjectUrl);
    recordedObjectUrl = "";
    recordedBlob = null;
    if (els.recordedAudio) {
      els.recordedAudio.pause();
      els.recordedAudio.removeAttribute("src");
      els.recordedAudio.load();
    }
    updateSaveState();
  }

  async function loadDevices() {
    if (!els.micDevice || !navigator.mediaDevices?.enumerateDevices) return;
    const previous = els.micDevice.value;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const inputs = devices.filter((device) => device.kind === "audioinput");
      els.micDevice.innerHTML = '<option value="">既定のマイク</option>' + inputs.map((device, index) => {
        const label = device.label || `マイク ${index + 1}`;
        return `<option value="${escapeHtml(device.deviceId)}">${escapeHtml(label)}</option>`;
      }).join("");
      if (previous && inputs.some((device) => device.deviceId === previous)) els.micDevice.value = previous;
    } catch (error) {
      setStatus(`マイク一覧を取得できませんでした: ${error.message || error}`, true);
    }
  }

  function renderVoiceList() {
    if (!els.list) return;
    const filteredVoices = voices.filter((voice) => {
      if (voiceListFilter === "active") return !voice.archived;
      if (voiceListFilter === "archived") return Boolean(voice.archived);
      return true;
    });
    if (!filteredVoices.length) {
      const emptyMessage = !voices.length
        ? "参照音声はまだ登録されていません。"
        : voiceListFilter === "archived"
          ? "アーカイブ済みの参照音声はありません。"
          : "この条件に一致する参照音声はありません。";
      els.list.innerHTML = `<div class="empty-state">${emptyMessage}</div>`;
      renderVoiceDetail(null);
      return;
    }
    if (!selectedVoiceId || !filteredVoices.some((voice) => voice.voiceId === selectedVoiceId)) selectedVoiceId = filteredVoices[0].voiceId;
    els.list.innerHTML = filteredVoices.map((voice) => `
      <button class="voice-list-button ${voice.voiceId === selectedVoiceId ? "active" : ""} ${voice.archived ? "archived" : ""}" type="button" data-voice-manage-id="${escapeHtml(voice.voiceId)}">
        <strong>${escapeHtml(voice.displayName || voice.voiceId)}</strong>
        <small>${escapeHtml(formatDuration(voice.audioDurationSec))} / ${voice.hasReferenceText ? "文章あり" : "文章なし"}${voice.archived ? " / アーカイブ中" : ""}</small>
      </button>
    `).join("");
    renderVoiceDetail(voices.find((voice) => voice.voiceId === selectedVoiceId) || null);
  }

  function renderVoiceDetail(voice) {
    if (!els.detail) return;
    if (!voice) {
      els.detail.innerHTML = '<div class="empty-state">左の参照音声を選択してください。</div>';
      return;
    }
    els.detail.innerHTML = `
      <div class="voice-detail-card" data-selected-voice-id="${escapeHtml(voice.voiceId)}">
        <div class="panel-head compact">
          <h3>${escapeHtml(voice.displayName || voice.voiceId)}</h3>
          <span class="status-badge ${voice.archived ? "pending" : voice.enabled ? "success" : "failed"}">${voice.archived ? "アーカイブ中" : voice.enabled ? "利用可能" : "利用不可"}</span>
        </div>
        <audio controls preload="none" src="/api/reference-voices/${encodeURIComponent(voice.voiceId)}/audio?v=${Date.now()}"></audio>
        <div class="voice-detail-meta">
          <span>登録ID: ${escapeHtml(voice.voiceId)}</span>
          <span>${escapeHtml(formatDuration(voice.audioDurationSec))}</span>
          <span>${voice.hasReferenceText ? "voice.txtあり" : "voice.txtなし"}</span>
        </div>
        <div class="voice-id-rename-row">
          <label class="field">
            <span>登録ID名</span>
            <input id="voiceExistingIdInput" type="text" maxlength="80" value="${escapeHtml(voice.voiceId)}" autocomplete="off">
          </label>
          <button class="secondary-button" type="button" id="voiceExistingIdRenameButton">ID名を変更</button>
        </div>
        <small class="voice-field-note">半角英数字・_・-のみ。変更後は通常生成・モデル比較・RVCの選択肢も更新されます。</small>
        <label class="field textarea-field">
          <span>録音時に読んだ文章</span>
          <textarea id="voiceExistingTextInput" rows="7" maxlength="5000" placeholder="録音で読んだ文章を入力してください。">${escapeHtml(voice.referenceText || "")}</textarea>
        </label>
        <div class="voice-detail-actions">
          <button class="primary-button" type="button" id="voiceExistingTextSaveButton">文章を保存</button>
          <button class="secondary-button" type="button" id="voiceArchiveButton" data-archive-next="${voice.archived ? "false" : "true"}">${voice.archived ? "アーカイブから戻す" : "アーカイブする"}</button>
        </div>
        <p class="status-line" id="voiceDetailStatus"></p>
      </div>
    `;
  }

  async function loadVoices(preferredVoiceId = selectedVoiceId) {
    if (els.reload) els.reload.disabled = true;
    try {
      const payload = await fetchJson("/api/reference-voices");
      voices = Array.isArray(payload.voices) ? payload.voices : [];
      updateSaveState();
      selectedVoiceId = preferredVoiceId && voices.some((voice) => voice.voiceId === preferredVoiceId)
        ? preferredVoiceId
        : voices[0]?.voiceId || "";
      renderVoiceList();
      setStatus(payload.backendAvailable === false
        ? "TTS APIは停止中ですが、ローカルの参照音声は編集できます。"
        : "参照音声を読み込みました。");
      return voices;
    } catch (error) {
      voices = [];
      renderVoiceList();
      setStatus(`参照音声の読込に失敗しました: ${error.message || error}`, true);
      return [];
    } finally {
      if (els.reload) els.reload.disabled = false;
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setStatus("このブラウザではマイク録音に対応していません。", true);
      return;
    }
    if (mediaRecorder?.state === "recording") return;
    resetRecordedPreview();
    try {
      const deviceId = String(els.micDevice?.value || "").trim();
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: deviceId
          ? { deviceId: { exact: deviceId }, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
          : { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      await loadDevices();
      recordedChunks = [];
      const preferredType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"]
        .find((type) => MediaRecorder.isTypeSupported?.(type));
      mediaRecorder = preferredType ? new MediaRecorder(mediaStream, { mimeType: preferredType }) : new MediaRecorder(mediaStream);
      mediaRecorder.ondataavailable = (event) => { if (event.data?.size) recordedChunks.push(event.data); };
      mediaRecorder.onstop = finishRecording;
      mediaRecorder.start();
      recordingStartedAt = Date.now();
      clearRecordingTimer();
      recordingTimerId = window.setInterval(() => {
        if (els.recordTimer) els.recordTimer.textContent = formatTimer((Date.now() - recordingStartedAt) / 1000);
      }, 250);
      if (els.recordStart) els.recordStart.disabled = true;
      if (els.recordStop) els.recordStop.disabled = false;
      setRecordingBadge("録音中", "pending");
      setStatus("録音中です。入力した文章をそのまま読んでください。");
    } catch (error) {
      stopStream();
      setRecordingBadge("録音失敗", "failed");
      setStatus(`マイク録音に失敗しました: ${error.message || error}`, true);
    }
  }

  function stopRecording() {
    if (!mediaRecorder || mediaRecorder.state !== "recording") return;
    mediaRecorder.stop();
  }

  function finishRecording() {
    clearRecordingTimer();
    stopStream();
    if (els.recordStart) els.recordStart.disabled = false;
    if (els.recordStop) els.recordStop.disabled = true;
    recordedBlob = new Blob(recordedChunks, { type: mediaRecorder?.mimeType || "audio/webm" });
    mediaRecorder = null;
    recordedChunks = [];
    if (!recordedBlob.size) {
      recordedBlob = null;
      setRecordingBadge("未録音", "failed");
      setStatus("録音データが空です。もう一度録音してください。", true);
      updateSaveState();
      return;
    }
    recordedObjectUrl = URL.createObjectURL(recordedBlob);
    if (els.recordedAudio) els.recordedAudio.src = recordedObjectUrl;
    setRecordingBadge("録音済み", "success");
    setStatus("録音できました。参照音声名と文章を確認して保存してください。");
    updateSaveState();
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("録音データを読み込めませんでした"));
      reader.readAsDataURL(blob);
    });
  }

  async function saveRecording() {
    const voiceId = String(els.voiceId?.value || "").trim();
    const referenceText = String(els.referenceText?.value || "").trim();
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(voiceId)) {
      setStatus("参照音声名は半角英数字・_・-で入力してください。", true);
      return;
    }
    if (voices.some((voice) => voice.voiceId === voiceId)) {
      setStatus("同じ参照音声名が既にあります。別の名前を指定してください。", true);
      return;
    }
    if (!referenceText) {
      setStatus("録音時に読んだ文章を入力してください。", true);
      return;
    }
    if (!recordedBlob) {
      setStatus("先にマイク録音してください。", true);
      return;
    }
    els.save.disabled = true;
    setRecordingBadge("保存中", "pending");
    setStatus("参照音声をWAVへ変換して保存しています...");
    try {
      const dataUrl = await blobToDataUrl(recordedBlob);
      const payload = await fetchJson("/api/reference-voices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voiceId, referenceText, dataUrl, mimeType: recordedBlob.type || "audio/webm" })
      });
      selectedVoiceId = payload.voice?.voiceId || voiceId;
      setRecordingBadge("保存済み", "success");
      setStatus(`${selectedVoiceId} を参照音声として保存しました。`);
      resetRecordedPreview();
      await loadVoices(selectedVoiceId);
      announceRegistration(selectedVoiceId, "mic");
    } catch (error) {
      setRecordingBadge("保存失敗", "failed");
      setStatus(`参照音声の保存に失敗しました: ${error.message || error}`, true);
      updateSaveState();
    }
  }

  async function saveExistingText() {
    const voice = voices.find((item) => item.voiceId === selectedVoiceId);
    const textarea = $("#voiceExistingTextInput");
    const status = $("#voiceDetailStatus");
    if (!voice || !textarea) return;
    const referenceText = textarea.value.trim();
    if (!referenceText) {
      if (status) status.textContent = "文章を入力してください。";
      return;
    }
    const button = $("#voiceExistingTextSaveButton");
    if (button) button.disabled = true;
    try {
      await fetchJson(`/api/reference-voices/${encodeURIComponent(voice.voiceId)}/text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ referenceText })
      });
      if (status) status.textContent = "文章を保存しました。";
      await loadVoices(voice.voiceId);
      window.dispatchEvent(new CustomEvent("local-tts:reference-voices-changed"));
    } catch (error) {
      if (status) status.textContent = `保存に失敗しました: ${error.message || error}`;
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function renameExistingVoice() {
    const voice = voices.find((item) => item.voiceId === selectedVoiceId);
    const input = $("#voiceExistingIdInput");
    const button = $("#voiceExistingIdRenameButton");
    const status = $("#voiceDetailStatus");
    if (!voice || !input || !button) return;
    const newVoiceId = String(input.value || "").trim();
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(newVoiceId)) {
      if (status) status.textContent = "登録ID名は半角英数字・_・-のみ、80文字以内で入力してください。";
      return;
    }
    if (newVoiceId === voice.voiceId) {
      if (status) status.textContent = "登録ID名は変更されていません。";
      return;
    }
    if (voices.some((item) => item.voiceId === newVoiceId)) {
      if (status) status.textContent = "同じ登録ID名が既にあります。別の名前を指定してください。";
      return;
    }
    button.disabled = true;
    try {
      const result = await fetchJson(`/api/reference-voices/${encodeURIComponent(voice.voiceId)}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ newVoiceId })
      });
      const previousVoiceId = String(result.previousVoiceId || voice.voiceId);
      selectedVoiceId = String(result.voiceId || newVoiceId);
      await loadVoices(selectedVoiceId);
      const currentStatus = $("#voiceDetailStatus");
      if (currentStatus) currentStatus.textContent = `${previousVoiceId} から ${selectedVoiceId} へ登録ID名を変更しました。`;
      window.dispatchEvent(new CustomEvent("local-tts:reference-voice-renamed", {
        detail: { previousVoiceId, voiceId: selectedVoiceId },
      }));
      window.dispatchEvent(new CustomEvent("local-tts:reference-voices-changed"));
    } catch (error) {
      if (status) status.textContent = `登録ID名の変更に失敗しました: ${error.message || error}`;
    } finally {
      const currentButton = $("#voiceExistingIdRenameButton");
      if (currentButton) currentButton.disabled = false;
    }
  }

  async function setArchivedFromDetail() {
    const voice = voices.find((item) => item.voiceId === selectedVoiceId);
    const button = $("#voiceArchiveButton");
    const status = $("#voiceDetailStatus");
    if (!voice || !button) return;
    const archived = button.dataset.archiveNext === "true";
    button.disabled = true;
    try {
      await fetchJson(`/api/reference-voices/${encodeURIComponent(voice.voiceId)}/archive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived })
      });
      if (status) status.textContent = archived
        ? "アーカイブしました。通常生成・モデル比較・RVCの選択肢には表示されません。"
        : "アーカイブから戻しました。各画面の参照音声一覧へ再表示されます。";
      await loadVoices(voice.voiceId);
      window.dispatchEvent(new CustomEvent("local-tts:reference-voices-changed"));
    } catch (error) {
      if (status) status.textContent = `アーカイブ状態の変更に失敗しました: ${error.message || error}`;
    } finally {
      const currentButton = $("#voiceArchiveButton");
      if (currentButton) currentButton.disabled = false;
    }
  }

  function setYoutubeBadge(text, state = "pending") {
    if (!els.youtubeBadge) return;
    els.youtubeBadge.textContent = text;
    els.youtubeBadge.className = `status-badge ${state}`;
  }

  function youtubeNameIsValid() {
    const value = String(els.youtubeName?.value || "").trim();
    return /^[A-Za-z0-9_-]{1,80}$/.test(value) && !voices.some((voice) => voice.voiceId === value);
  }

  function updateYoutubeAnalyzeState() {
    if (!els.youtubeAnalyze) return;
    const hasUrl = /^https?:\/\//i.test(String(els.youtubeUrl?.value || "").trim());
    els.youtubeAnalyze.disabled = !hasUrl || !els.youtubeRights?.checked;
  }

  function formatYoutubeTime(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(value / 60);
    const remain = value - minutes * 60;
    return `${String(minutes).padStart(2, "0")}:${remain.toFixed(1).padStart(4, "0")}`;
  }

  function decorateYoutubeCandidates(result) {
    const jobId = String(result?.jobId || "");
    return (Array.isArray(result?.candidates) ? result.candidates : []).map((candidate) => ({
      ...candidate,
      _jobId: jobId,
      _clientKey: `${jobId}:${String(candidate.candidate_id || "")}`,
    }));
  }

  function youtubeExcludeRanges() {
    return (Array.isArray(youtubeJob?.candidates) ? youtubeJob.candidates : [])
      .map((candidate) => ({ startSec: Number(candidate.start_sec), endSec: Number(candidate.end_sec) }))
      .filter((item) => Number.isFinite(item.startSec) && Number.isFinite(item.endSec) && item.endSec > item.startSec);
  }

  function updateYoutubeMoreState() {
    if (!els.youtubeMore) return;
    const hasCandidates = Boolean(youtubeJob?.candidates?.length);
    els.youtubeMore.hidden = !hasCandidates || youtubeAdditionalRequested;
    els.youtubeMore.disabled = false;
  }

  function userFacingSeparationMessage(value) {
    return String(value || "").replace(/Demucs/gi, "BGM・伴奏除去");
  }

  function renderYoutubeCandidates() {
    if (!els.youtubeCandidates) return;
    const candidates = Array.isArray(youtubeJob?.candidates) ? youtubeJob.candidates : [];
    if (!candidates.length) {
      els.youtubeCandidates.innerHTML = '<div class="empty-state">候補を取得すると、音声・時間・文字起こしがここに表示されます。</div>';
      updateYoutubeMoreState();
      return;
    }
    els.youtubeCandidates.innerHTML = candidates.map((candidate, index) => {
      const candidateKey = String(candidate._clientKey || candidate.candidate_id || "");
      const cleanedAudio = candidate.cleanedAudioUrl
        ? `<div><strong>BGM・伴奏除去後</strong><audio controls preload="none" src="${escapeHtml(candidate.cleanedAudioUrl)}"></audio></div>`
        : "";
      const originalLabel = candidate.cleanedAudioUrl ? "元音声" : "候補音声";
      const demucsFlag = candidate.demucsApplied ? "BGM除去済み" : candidate.demucsError ? "BGM・伴奏除去に失敗・元音声を使用" : "元音声";
      return `
        <article class="youtube-candidate-card" data-youtube-candidate-id="${escapeHtml(candidateKey)}">
          <div class="youtube-candidate-head">
            <strong>候補 ${index + 1}</strong>
            <span class="youtube-candidate-time">${escapeHtml(formatYoutubeTime(candidate.start_sec))}〜${escapeHtml(formatYoutubeTime(candidate.end_sec))} / ${escapeHtml(String(candidate.duration_sec || ""))}秒</span>
          </div>
          <div class="youtube-candidate-flags">
            <span>${escapeHtml(demucsFlag)}</span>
            <span>評価 ${escapeHtml(String(Math.round(Number(candidate.score || 0))))}</span>
          </div>
          ${cleanedAudio}
          <div><strong>${originalLabel}</strong><audio controls preload="none" src="${escapeHtml(candidate.originalAudioUrl || candidate.audioUrl || "")}"></audio></div>
          <label class="field textarea-field">
            <span>文字起こし（登録前に修正可能）</span>
            <textarea data-youtube-candidate-text maxlength="5000">${escapeHtml(candidate.text || "")}</textarea>
          </label>
          ${candidate.demucsError ? `<p class="youtube-candidate-warning">${escapeHtml(userFacingSeparationMessage(candidate.demucsError))}</p>` : ""}
          <button class="primary-button" type="button" data-youtube-register="${escapeHtml(candidateKey)}">この候補を参照音声に登録</button>
          <p class="status-line" data-youtube-candidate-status></p>
        </article>
      `;
    }).join("");
    updateYoutubeMoreState();
  }

  function youtubeCandidateRequestBody(excludeRanges = []) {
    return {
      url: String(els.youtubeUrl?.value || "").trim(),
      rightsConfirmed: Boolean(els.youtubeRights?.checked),
      useDemucs: Boolean(els.youtubeDemucs?.checked),
      language: "ja",
      whisperModel: "small",
      maxCandidates: 5,
      excludeRanges,
    };
  }

  async function analyzeYoutubeReference() {
    if (!els.youtubeAnalyze || els.youtubeAnalyze.disabled) return;
    els.youtubeAnalyze.disabled = true;
    youtubeAdditionalRequested = false;
    if (els.youtubeMore) els.youtubeMore.hidden = true;
    setYoutubeBadge("処理中", "pending");
    if (els.youtubeStatus) els.youtubeStatus.textContent = "動画から音声と文字起こしの候補を取得しています。BGM・伴奏除去を使う場合は時間がかかることがあります。";
    try {
      const result = await fetchJson("/api/reference-voices/youtube/candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(youtubeCandidateRequestBody())
      });
      youtubeJob = { ...result, candidates: decorateYoutubeCandidates(result) };
      renderYoutubeCandidates();
      setYoutubeBadge("候補あり", "success");
      if (els.youtubeStatus) {
        const source = String(youtubeJob.transcriptSource || "").startsWith("subtitle:") ? "字幕" : "音声認識";
        const fallbackUsed = Boolean(String(youtubeJob.subtitleWarning || "").trim()) && source === "音声認識";
        els.youtubeStatus.textContent = fallbackUsed
          ? `字幕を取得できなかったため音声認識を使用し、${youtubeJob.title || "動画"}から${youtubeJob.candidates?.length || 0}件を抽出しました。`
          : `${youtubeJob.title || "動画"}から${youtubeJob.candidates?.length || 0}件を抽出しました。文字起こし: ${source}`;
      }
    } catch (error) {
      youtubeJob = null;
      renderYoutubeCandidates();
      setYoutubeBadge("失敗", "failed");
      const message = String(error?.message || error || "");
      if (els.youtubeStatus) els.youtubeStatus.textContent = message === "このURLには対応していません"
        ? message
        : `候補取得に失敗しました: ${message}`;
    } finally {
      updateYoutubeAnalyzeState();
    }
  }

  async function loadMoreYoutubeCandidates() {
    if (!youtubeJob?.candidates?.length || youtubeAdditionalRequested) return;
    youtubeAdditionalRequested = true;
    if (els.youtubeMore) {
      els.youtubeMore.hidden = true;
      els.youtubeMore.disabled = true;
    }
    if (els.youtubeStatus) els.youtubeStatus.textContent = "同じ動画から、表示済みと重ならない候補を追加で探しています。";
    try {
      const result = await fetchJson("/api/reference-voices/youtube/candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(youtubeCandidateRequestBody(youtubeExcludeRanges()))
      });
      const additions = decorateYoutubeCandidates(result);
      youtubeJob = { ...youtubeJob, candidates: [...youtubeJob.candidates, ...additions] };
      renderYoutubeCandidates();
      setYoutubeBadge("候補追加済み", "success");
      if (els.youtubeStatus) els.youtubeStatus.textContent = `別の時間帯から${additions.length}件を追加しました。合計${youtubeJob.candidates.length}件です。`;
    } catch (error) {
      setYoutubeBadge("追加候補なし", "pending");
      if (els.youtubeStatus) els.youtubeStatus.textContent = `追加候補を取得できませんでした: ${error.message || error}`;
    } finally {
      if (els.youtubeMore) els.youtubeMore.hidden = true;
      updateYoutubeAnalyzeState();
    }
  }

  async function registerYoutubeCandidate(candidateKey, card) {
    const candidate = youtubeJob?.candidates?.find((item) => item._clientKey === candidateKey);
    const status = card?.querySelector("[data-youtube-candidate-status]");
    const button = card?.querySelector("[data-youtube-register]");
    const referenceText = card?.querySelector("[data-youtube-candidate-text]")?.value.trim() || "";
    const voiceId = String(els.youtubeName?.value || "").trim();
    if (!candidate || !candidate._jobId || !candidate.candidate_id) return;
    if (!youtubeNameIsValid()) {
      if (status) status.textContent = "未使用の参照音声名を入力してください。";
      return;
    }
    if (!referenceText) {
      if (status) status.textContent = "文字起こしを入力してください。";
      return;
    }
    if (button) button.disabled = true;
    if (status) status.textContent = "参照音声として保存しています...";
    try {
      await fetchJson("/api/reference-voices/youtube/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jobId: candidate._jobId,
          candidateId: candidate.candidate_id,
          voiceId,
          referenceText,
          useCleaned: Boolean(candidate.demucsApplied),
          rightsConfirmed: Boolean(els.youtubeRights?.checked)
        })
      });
      if (status) status.textContent = `${voiceId} として登録しました。`;
      selectedVoiceId = voiceId;
      await loadVoices(voiceId);
      announceRegistration(voiceId, "youtube");
      updateYoutubeAnalyzeState();
    } catch (error) {
      if (status) status.textContent = `登録に失敗しました: ${error.message || error}`;
      if (button) button.disabled = false;
    }
  }

  els.referenceText?.addEventListener("input", updateTextCount);
  els.voiceId?.addEventListener("input", handleVoiceNameInput);
  els.recordStart?.addEventListener("click", startRecording);
  els.recordStop?.addEventListener("click", stopRecording);
  els.save?.addEventListener("click", saveRecording);
  els.reload?.addEventListener("click", () => loadVoices());
  document.querySelectorAll("[data-voice-filter]").forEach((button) => button.addEventListener("click", () => {
    voiceListFilter = String(button.dataset.voiceFilter || "all");
    document.querySelectorAll("[data-voice-filter]").forEach((item) => item.classList.toggle("active", item === button));
    renderVoiceList();
  }));
  els.list?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-voice-manage-id]");
    if (!button) return;
    selectedVoiceId = String(button.dataset.voiceManageId || "");
    renderVoiceList();
  });
  els.detail?.addEventListener("click", (event) => {
    if (event.target.closest("#voiceExistingIdRenameButton")) renameExistingVoice();
    if (event.target.closest("#voiceExistingTextSaveButton")) saveExistingText();
    if (event.target.closest("#voiceArchiveButton")) setArchivedFromDetail();
  });
  [els.youtubeUrl, els.youtubeName].filter(Boolean).forEach((element) => element.addEventListener("input", updateYoutubeAnalyzeState));
  els.youtubeRights?.addEventListener("change", updateYoutubeAnalyzeState);
  els.youtubeAnalyze?.addEventListener("click", analyzeYoutubeReference);
  els.youtubeMore?.addEventListener("click", loadMoreYoutubeCandidates);
  els.youtubeCandidates?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-youtube-register]");
    if (!button) return;
    registerYoutubeCandidate(String(button.dataset.youtubeRegister || ""), button.closest("[data-youtube-candidate-id]"));
  });
  navigator.mediaDevices?.addEventListener?.("devicechange", loadDevices);

  updateTextCount();
  updateYoutubeAnalyzeState();
  loadDevices();
  loadVoices();
})();
