import { createServer } from "../server.js";

const CHROME_PATH = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

function makeWavBuffer(durationSec = 4, sampleRate = 16000) {
  const samples = Math.max(1, Math.floor(durationSec * sampleRate));
  const dataSize = samples * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataSize, 40);
  return buffer;
}

async function main() {
  const server = createServer({ host: "127.0.0.1", port: 0, ttsBaseUrl: "http://127.0.0.1:1" });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const frontBase = `http://127.0.0.1:${address.port}`;
  const { chromium } = await import("playwright-core");
  const browser = await chromium.launch({
    headless: true,
    executablePath: CHROME_PATH,
    args: ["--autoplay-policy=no-user-gesture-required"],
  });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  let importRequests = 0;
  let renameRequests = 0;
  let youtubeCandidateRequests = 0;
  const voices = [{
    voiceId: "sample_voice",
    displayName: "sample_voice",
    enabled: true,
    archived: false,
    hasReferenceAudio: true,
    hasReferenceText: true,
    referenceText: "既存の参照音声です。",
    audioDurationSec: 5,
    minReferenceDurationSec: 3,
    maxReferenceDurationSec: 10,
  }, {
    voiceId: "archived_voice",
    displayName: "archived_voice",
    enabled: false,
    archived: true,
    hasReferenceAudio: true,
    hasReferenceText: true,
    referenceText: "アーカイブ済みです。",
    audioDurationSec: 4,
    minReferenceDurationSec: 3,
    maxReferenceDurationSec: 10,
  }];

  await page.route("**/api/models", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        models: [{
          id: "irodori_v3",
          model: "irodori_v3",
          label: "Irodori v3",
          available: true,
          enabled: true,
          supportsReferenceVoice: true,
          requiresReferenceAudio: false,
          supportsInstruction: true,
        }, {
          id: "qwen3_tts_clone_1_7b",
          model: "qwen3_tts_clone_1_7b",
          label: "Qwen3-TTS Voice Clone 1.7B",
          available: true,
          enabled: true,
          supportsReferenceVoice: true,
          requiresReferenceAudio: true,
          requiresReferenceText: true,
          supportsInstruction: true,
        }],
      }),
    });
  });
  await page.route("**/api/rvc/defaults", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, defaults: {} }) });
  });
  await page.route("**/api/reference-voices/*/audio", async (route) => {
    await route.fulfill({ status: 200, contentType: "audio/wav", body: makeWavBuffer(4) });
  });
  await page.route("**/api/reference-voices/import", async (route) => {
    importRequests += 1;
    const body = JSON.parse(route.request().postData() || "{}");
    const voice = {
      voiceId: body.voiceId,
      displayName: body.voiceId,
      enabled: true,
      archived: false,
      hasReferenceAudio: true,
      hasReferenceText: true,
      referenceText: body.referenceText,
      audioDurationSec: 4,
      minReferenceDurationSec: 3,
      maxReferenceDurationSec: 10,
    };
    voices.push(voice);
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, voice }) });
  });
  await page.route("**/api/reference-voices/*/rename", async (route) => {
    renameRequests += 1;
    const previousVoiceId = decodeURIComponent(route.request().url().split("/").at(-2) || "");
    const body = JSON.parse(route.request().postData() || "{}");
    const voice = voices.find((item) => item.voiceId === previousVoiceId);
    ensure(Boolean(voice), "rename target voice is missing");
    ensure(!voices.some((item) => item.voiceId === body.newVoiceId), "rename target should be unique");
    voice.voiceId = body.newVoiceId;
    voice.displayName = body.newVoiceId;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, previousVoiceId, voiceId: body.newVoiceId }) });
  });
  await page.route("**/api/reference-voices/youtube/candidates", async (route) => {
    const requestBody = JSON.parse(route.request().postData() || "{}");
    if (!String(requestBody.url || "").includes("youtu")) {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ ok: false, error: "このURLには対応していません" }),
      });
      return;
    }
    youtubeCandidateRequests += 1;
    if (youtubeCandidateRequests === 2) {
      ensure(Array.isArray(requestBody.excludeRanges) && requestBody.excludeRanges.length === 1, "additional request does not exclude the first candidate range");
    }
    const suffix = youtubeCandidateRequests === 1 ? "1" : "2";
    const start = youtubeCandidateRequests === 1 ? 12 : 42;
    const end = youtubeCandidateRequests === 1 ? 19 : 49;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        jobId: `youtube-job-e2e-${suffix}`,
        title: "reference voice test",
        transcriptSource: "whisper:small",
        subtitleWarning: "字幕を取得できなかったため、Whisperで文字起こしします。",
        candidates: [{
          candidate_id: `candidate-${suffix}`,
          start_sec: start,
          end_sec: end,
          duration_sec: 7,
          text: youtubeCandidateRequests === 1
            ? "これは自動文字起こしの重複を除去した長めの候補文章です。入力欄が狭くならず、内容に合わせて高さが自動的に広がることを確認します。さらに文章を追加して、縦スクロールが発生しない状態を確認します。"
            : "追加で取得した別の時間帯の候補文章です。",
          originalAudioUrl: `/api/reference-voices/youtube/audio/youtube-job-e2e-${suffix}/candidate-${suffix}/original`,
          cleanedAudioUrl: `/api/reference-voices/youtube/audio/youtube-job-e2e-${suffix}/candidate-${suffix}/cleaned`,
          demucsApplied: true,
        }],
      }),
    });
  });
  await page.route("**/api/reference-voices/youtube/audio/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "audio/wav", body: makeWavBuffer(7) });
  });
  await page.route("**/api/reference-voices", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, defaultReferenceVoice: "sample_voice", voices }),
    });
  });

  const checked = [];
  try {
    await page.goto(frontBase, { waitUntil: "networkidle", timeout: 60000 });

    await page.locator('.top-tab[data-tab="guide"]').click();
    await page.waitForSelector("#guidePage.active");
    const guideOrder = await page.locator("#guidePage h2").allTextContents();
    ensure(guideOrder.slice(0, 5).join("|") === [
      "1. 最初の音声を作る",
      "2. やりたいことを選ぶ",
      "3. 見本の声に寄せたい場合",
      "4. 困ったとき",
      "5. 注意事項",
    ].join("|"), `guide order is wrong: ${guideOrder.join(" | ")}`);
    ensure(await page.locator("text=長文を分割して生成する理由").count() === 0, "large chunk explanation still exists in the guide");
    ensure(await page.locator("#guideMechanismTitle").isVisible(), "mechanism information is still hidden");
    ensure(await page.locator(".guide-mechanism-card").count() === 3, "three mechanism cards are not visible");
    const mechanismText = await page.locator(".guide-mechanism-section").textContent();
    ensure(mechanismText.includes("クローン対応TTSモデル"), "clone requirements are missing");
    ensure(mechanismText.includes("voice.wav") && mechanismText.includes("voice.txt"), "reference voice file requirements are missing");
    ensure(mechanismText.includes(".pth") && mechanismText.includes(".index"), "RVC model requirements are missing");
    checked.push("guide order, visible mechanism, and required inputs");

    await page.locator('[data-voice-open="register"]').click();
    await page.waitForSelector("#voicesPage.active");
    ensure(await page.locator('[data-voice-view-panel="register"]').isVisible(), "new registration view is not the initial view");
    ensure(!(await page.locator('[data-voice-view-panel="manage"]').isVisible()), "management view should not be shown with registration forms");
    ensure(await page.locator("[data-voice-method]").count() === 3, "three registration methods are not visible");
    ensure(await page.locator('[data-voice-method-panel="mic"]').isVisible(), "microphone form should be the initial method");
    ensure(!(await page.locator('[data-voice-method-panel="file"]').isVisible()), "file form should start hidden");
    ensure(!(await page.locator('[data-voice-method-panel="youtube"]').isVisible()), "YouTube form should start hidden");
    const initialLayout = await page.evaluate(() => {
      const tabs = document.querySelector(".voice-method-picker")?.getBoundingClientRect();
      const panel = document.querySelector('[data-voice-method-panel="mic"]')?.getBoundingClientRect();
      const action = document.querySelector("#voiceSaveButton")?.getBoundingClientRect();
      return { tabsWidth: tabs?.width || 0, panelWidth: panel?.width || 0, micActionHeight: action?.height || 0 };
    });
    ensure(initialLayout.panelWidth >= initialLayout.tabsWidth - 2, `method panel is narrower than tabs: ${JSON.stringify(initialLayout)}`);
    ensure(initialLayout.micActionHeight >= 47, `microphone action is too short: ${initialLayout.micActionHeight}`);
    checked.push("registration separation and full-width method panel");

    await page.locator('[data-voice-method="file"]').click();
    ensure(await page.locator('[data-voice-method-panel="file"]').isVisible(), "file registration form did not open");
    ensure(!(await page.locator('[data-voice-method-panel="mic"]').isVisible()), "microphone form stayed visible after switching methods");
    ensure(await page.locator("#voiceFileSaveButton").isDisabled(), "file save should be disabled before required fields are complete");
    const fileLayout = await page.evaluate(() => {
      const shell = document.querySelector(".voice-file-input-shell")?.getBoundingClientRect();
      const input = document.querySelector("#voiceFileInput")?.getBoundingClientRect();
      const action = document.querySelector("#voiceFileSaveButton")?.getBoundingClientRect();
      return {
        shellHeight: shell?.height || 0,
        inputTop: input?.top || 0,
        inputBottom: input?.bottom || 0,
        shellTop: shell?.top || 0,
        shellBottom: shell?.bottom || 0,
        fileActionHeight: action?.height || 0,
      };
    });
    ensure(fileLayout.shellHeight >= 47, `file picker shell is too short: ${JSON.stringify(fileLayout)}`);
    ensure(fileLayout.inputTop >= fileLayout.shellTop && fileLayout.inputBottom <= fileLayout.shellBottom, `file picker floats outside its shell: ${JSON.stringify(fileLayout)}`);
    ensure(Math.abs(fileLayout.fileActionHeight - initialLayout.micActionHeight) <= 1, `method action heights are uneven: ${JSON.stringify({ initialLayout, fileLayout })}`);

    await page.locator("#voiceFileInput").setInputFiles({ name: "sample.wav", mimeType: "audio/wav", buffer: makeWavBuffer(4) });
    await page.fill("#voiceFileIdInput", "imported_voice");
    await page.fill("#voiceFileTextInput", "音声ファイルで実際に話している文章です。");
    await page.waitForFunction(() => !document.querySelector("#voiceFileSaveButton")?.disabled);
    ensure((await page.locator("#voiceFilePreview").getAttribute("src"))?.startsWith("blob:"), "selected file is not previewable");
    await page.locator("#voiceFileSaveButton").click();
    await page.waitForSelector("#voiceRegistrationSuccess:not([hidden])");
    ensure(importRequests === 1, "file import API was not called exactly once");
    ensure((await page.locator("#voiceRegistrationSuccess").textContent()).includes("imported_voice"), "success panel does not identify the registered voice");
    checked.push("file preview, validation, import, and success state");

    await page.locator('[data-success="normal"]').click();
    await page.waitForSelector("#normalPage.active");
    await page.waitForFunction(() => document.querySelector("#normalReferenceVoiceSelect")?.value === "imported_voice");
    ensure(await page.locator("#normalUseReference").isChecked(), "registered voice is not enabled in normal generation");
    checked.push("registered voice handoff to normal generation");
    await page.selectOption("#normalReferenceVoiceSelect", "sample_voice");

    await page.locator('.top-tab[data-tab="voices"]').click();
    await page.locator('[data-voice-view="manage"]').click();
    ensure(await page.locator('[data-voice-view-panel="manage"]').isVisible(), "registered voice management view did not open");
    ensure(!(await page.locator('[data-voice-view-panel="register"]').isVisible()), "registration forms remained visible in management view");
    await page.locator('[data-voice-filter="active"]').click();
    await page.locator('[data-voice-manage-id="sample_voice"]').click();
    await page.fill("#voiceExistingIdInput", "renamed_voice");
    await page.click("#voiceExistingIdRenameButton");
    await page.waitForFunction(() => document.querySelector("#voiceManageDetail")?.textContent?.includes("renamed_voice"));
    ensure(renameRequests === 1, "reference voice rename API was not called exactly once");
    ensure(!voices.some((voice) => voice.voiceId === "sample_voice") && voices.some((voice) => voice.voiceId === "renamed_voice"), "voice list did not keep the renamed registration ID");
    await page.waitForFunction(() => document.querySelector("#normalReferenceVoiceSelect")?.value === "renamed_voice");
    ensure(await page.locator("#normalReferenceVoiceSelect").inputValue() === "renamed_voice", "normal generation selection was not migrated after the registration ID rename");
    checked.push("reference voice registration ID rename and selector migration");
    await page.locator('[data-voice-filter="archived"]').click();
    await page.waitForFunction(() => document.querySelector("#voiceManageList")?.textContent?.includes("archived_voice"));
    ensure(!(await page.locator("#voiceManageList").textContent()).includes("sample_voice"), "archived filter includes active voices");
    checked.push("registered voice filters and archive visibility");

    await page.locator('[data-voice-view="register"]').click();
    await page.locator('[data-voice-method="youtube"]').click();
    ensure((await page.locator('[data-voice-method="youtube"]').textContent()) === "動画URLから登録", "registration method must use the generic video-URL label");
    ensure(!(await page.locator('[data-voice-method-panel="youtube"]').textContent()).includes("YouTube"), "service name leaked into the user-facing video-URL panel");
    ensure(await page.locator("#youtubeReferenceUrlInput").getAttribute("placeholder") === "https://...", "video URL placeholder must not name a service");
    const youtubeActionHeight = await page.locator("#youtubeReferenceAnalyzeButton").evaluate((button) => button.getBoundingClientRect().height);
    ensure(Math.abs(youtubeActionHeight - initialLayout.micActionHeight) <= 1, `video URL action height is uneven: ${JSON.stringify({ initialLayout, youtubeActionHeight })}`);
    await page.fill("#youtubeReferenceUrlInput", "https://example.com/video");
    await page.check("#youtubeReferenceRightsInput");
    await page.locator("#youtubeReferenceAnalyzeButton").click();
    await page.waitForFunction(() => document.querySelector("#youtubeReferenceStatus")?.textContent === "このURLには対応していません");
    await page.fill("#youtubeReferenceUrlInput", "https://www.youtube.com/watch?v=dQw4w9WgXcQ");
    await page.locator("#youtubeReferenceAnalyzeButton").click();
    await page.waitForSelector('[data-youtube-candidate-text]');
    const youtubeStatus = await page.locator("#youtubeReferenceStatus").textContent();
    ensure(youtubeStatus.includes("字幕を取得できなかったため音声認識を使用"), `audio-recognition fallback is not explained: ${youtubeStatus}`);
    checked.push("equal action heights, integrated file picker, and Whisper fallback status");
    const candidateLayout = await page.locator("#youtubeReferenceCandidates").evaluate((grid) => ({
      columns: getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length,
      cardCount: grid.querySelectorAll(".youtube-candidate-card").length,
    }));
    ensure(candidateLayout.columns === 3, `YouTube candidates are not arranged in three columns: ${JSON.stringify(candidateLayout)}`);
    ensure(candidateLayout.cardCount === 1, `unexpected initial candidate count: ${JSON.stringify(candidateLayout)}`);
    const transcriptMetrics = await page.locator('[data-youtube-candidate-text]').evaluate((textarea) => ({
      width: textarea.getBoundingClientRect().width,
      clientHeight: textarea.clientHeight,
      scrollHeight: textarea.scrollHeight,
      overflowY: getComputedStyle(textarea).overflowY,
    }));
    ensure(transcriptMetrics.width >= 300, `YouTube transcript is too narrow: ${transcriptMetrics.width}`);
    ensure(transcriptMetrics.scrollHeight <= transcriptMetrics.clientHeight + 3, `YouTube transcript still requires vertical scrolling: ${JSON.stringify(transcriptMetrics)}`);
    ensure(transcriptMetrics.overflowY === "hidden", `YouTube transcript overflow is not hidden: ${transcriptMetrics.overflowY}`);
    ensure(await page.locator("#youtubeReferenceMoreButton").isVisible(), "additional five-candidate action is not visible");
    await page.locator("#youtubeReferenceMoreButton").click();
    await page.waitForFunction(() => document.querySelectorAll("#youtubeReferenceCandidates .youtube-candidate-card").length === 2);
    ensure(youtubeCandidateRequests === 2, `additional candidates were not requested exactly once: ${youtubeCandidateRequests}`);
    ensure(!(await page.locator("#youtubeReferenceMoreButton").isVisible()), "additional action should hide after the second batch");
    checked.push("three-column candidates, auto-growing transcript, and additional batch");

    await page.setViewportSize({ width: 720, height: 900 });
    ensure(await page.locator('[data-voice-method="youtube"]').isVisible(), "registration method controls are unusable on a narrow screen");
    ensure((await page.locator('[data-voice-method-panel="youtube"]').boundingBox())?.width > 300, "YouTube form collapsed on a narrow screen");
    checked.push("narrow-screen usability");

    console.log(JSON.stringify({ ok: true, frontBase, importRequests, checked }, null, 2));
  } finally {
    await browser.close().catch(() => {});
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: error.message, stack: error.stack }, null, 2));
  process.exit(1);
});
