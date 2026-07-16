const FRONT_BASE = (process.env.TTS_FRONT_BASE_URL || "http://127.0.0.1:5177").replace(/\/+$/, "");

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

async function fetchJson(url, options, label) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { ok: false, raw: text };
  }
  if (!response.ok || payload.ok === false) {
    throw new Error(`${label}: ${payload.error || `HTTP ${response.status}`}`);
  }
  return payload;
}

function ensureHtmlIncludes(html, id) {
  ensure(html.includes(`id="${id}"`), `Frontend missing current UI element with id="${id}"`);
}

async function main() {
  console.log(`[E2E] Verifying frontend is running at: ${FRONT_BASE}`);

  const indexHtmlResponse = await fetch(`${FRONT_BASE}/`);
  ensure(indexHtmlResponse.ok, `Failed to load frontend home: HTTP ${indexHtmlResponse.status}`);
  const html = await indexHtmlResponse.text();

  const requiredIds = [
    "serviceStatus",
    "serviceStatusDetail",
    "normalModelSelect",
    "normalReferenceVoiceSelect",
    "normalTextInput",
    "normalGenerateButton",
    "normalResultCard",
    "normalAudioPlayer",
    "compareModelCards",
    "rvcMicDeviceSelect",
    "rvcConvertButton",
    "historyList",
    "historySearchInput",
    "voiceIdInput",
    "voiceReferenceTextInput",
    "voiceSaveButton",
    "voiceManageList",
    "youtubeReferenceUrlInput",
    "youtubeReferenceRightsInput",
    "youtubeReferenceAnalyzeButton",
    "youtubeReferenceCandidates",
    "guidePage",
    "guideRvcActionCard",
    "voiceFileInput",
    "voiceFileSaveButton",
    "voiceRegistrationSuccess"
  ];
  requiredIds.forEach((id) => ensureHtmlIncludes(html, id));
  ensure(html.includes('./shared-ui.js'), "Frontend missing shared-ui.js script");
  ensure(html.includes('./app.js'), "Frontend missing app.js script");
  ensure(html.includes('./history.js'), "Frontend missing history.js script");
  ensure(html.includes('./reference-voices.js'), "Frontend missing reference-voices.js script");
  ensure(html.includes('./irodori-emojis.js'), "Frontend missing irodori-emojis.js script");
  console.log("[E2E] HTML page and current critical elements verified successfully.");

  const health = await fetchJson(`${FRONT_BASE}/api/health`, undefined, "frontend health");
  const models = await fetchJson(`${FRONT_BASE}/api/models`, undefined, "frontend models");
  const voices = await fetchJson(`${FRONT_BASE}/api/reference-voices`, undefined, "frontend reference voices");
  const rvcDefaults = await fetchJson(`${FRONT_BASE}/api/rvc/defaults`, undefined, "rvc defaults");

  const items = Array.isArray(models.models) ? models.models : [];
  ensure(items.length > 0, "models is empty");
  ensure(items.some((item) => item.id || item.model), "models do not contain ids");
  ensure(Array.isArray(voices.voices), "reference voices payload missing voices array");
  ensure(rvcDefaults.defaults && typeof rvcDefaults.defaults === "object", "RVC defaults payload missing defaults");

  console.log(JSON.stringify({
    ok: true,
    frontBase: FRONT_BASE,
    ttsStatus: health.health?.status || "unknown",
    defaultModel: health.health?.defaultModel || "",
    modelCount: items.length,
    voiceCount: voices.voices.length,
    rvcInputSource: rvcDefaults.defaults.inputSource || ""
  }, null, 2));
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: error.message }, null, 2));
  process.exit(1);
});
