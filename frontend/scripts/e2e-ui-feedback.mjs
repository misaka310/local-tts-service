import { createServer } from "../server.js";

const CHROME_PATH = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

async function main() {
  const server = createServer({ host: "127.0.0.1", port: 0, ttsBaseUrl: "http://127.0.0.1:1" });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const frontBase = `http://127.0.0.1:${address.port}`;
  const model = {
    id: "mock",
    model: "mock",
    label: "mock",
    family: "mock_wav",
    runtime: "mock_wav",
    available: true,
    enabled: true,
    supportsReferenceVoice: false,
    requiresReferenceAudio: false,
    requiresReferenceText: false,
    supportsInstruction: false,
    supportsLanguage: false,
    supportsSeed: false,
    supportsSpeedControl: false,
    supportsStyleStrength: false,
  };

  const { chromium } = await import("playwright-core");
  const browser = await chromium.launch({
    headless: true,
    executablePath: CHROME_PATH,
    args: ["--mute-audio", "--autoplay-policy=user-gesture-required"],
  });
  const context = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: frontBase });
  const page = await context.newPage();

  await page.route("**/api/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        health: {
          ok: true,
          status: "healthy",
          defaultModel: "mock",
          availableModelInfo: [model],
        },
      }),
    });
  });
  await page.route("**/api/models", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, models: [model] }),
    });
  });
  await page.route("**/api/reference-voices", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, voices: [], defaultReferenceVoice: "" }),
    });
  });
  await page.route("**/api/rvc/defaults", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, defaults: {} }),
    });
  });
  await page.route("**/api/speak", async (route) => {
    await route.abort("connectionrefused");
  });

  try {
    await page.goto(frontBase, { waitUntil: "networkidle", timeout: 60000 });
    await page.locator("#normalTextInput").fill("接続失敗時の表示を確認します。");
    await page.locator("#normalGenerateButton").click();

    const status = page.locator("#normalStatusText");
    await status.waitFor({ state: "visible" });
    await page.waitForFunction(() => {
      return document.querySelector("#normalStatusText")?.textContent?.includes("local-tts.bat");
    });
    ensure(
      await status.textContent() === "ローカルTTSサービスに接続できません。local-tts.batを起動したまま、もう一度生成してください。",
      "raw fetch error was shown instead of the actionable message",
    );

    const diagnostic = await page.locator("#normalLogBox").textContent();
    ensure(diagnostic.includes("Failed to fetch"), "diagnostic log did not preserve the original fetch error");
    ensure(diagnostic.includes("Request:"), "diagnostic log did not preserve the request");

    await page.locator("#normalLogCopyButton").click();
    const toast = page.locator("#localTtsToast");
    await toast.waitFor({ state: "visible", timeout: 5000 });
    ensure(await toast.textContent() === "コピーしました", "copy success toast text is incorrect");
    ensure(await toast.getAttribute("role") === "status", "copy toast is missing an accessible status role");

    console.log(JSON.stringify({
      ok: true,
      checked: [
        "actionable Failed to fetch message",
        "raw request and error retained in diagnostics",
        "visible copy success toast",
      ],
    }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: error.message }, null, 2));
  process.exit(1);
});
