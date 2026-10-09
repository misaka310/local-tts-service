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
    args: ["--mute-audio"],
  });
  const context = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
  const page = await context.newPage();

  await page.route("**/api/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        health: { ok: true, status: "healthy", defaultModel: "mock", availableModelInfo: [model] },
      }),
    });
  });
  await page.route("**/api/models", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, models: [model] }) });
  });
  await page.route("**/api/reference-voices", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, voices: [], defaultReferenceVoice: "" }) });
  });
  await page.route("**/api/rvc/defaults", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, defaults: {} }) });
  });

  try {
    await page.goto(frontBase, { waitUntil: "networkidle", timeout: 60000 });

    ensure(await page.locator("#normalModelInfo").count() === 0, "license UI leaked into normal generation");

    await page.locator('.top-tab[data-tab="compare"]').click();
    ensure(await page.locator(".usage-terms").count() === 0, "license UI leaked into comparison");

    await page.locator('.top-tab[data-tab="guide"]').click();
    const licenseSection = page.locator('[aria-labelledby="guideModelLicenseTitle"]');
    await licenseSection.waitFor({ state: "visible" });
    const expectedRows = await page.evaluate(() => {
      const catalog = window.LocalTtsModelCatalog;
      return new Set(
        catalog.MODEL_ORDER
          .filter((id) => id !== "mock")
          .map((id) => catalog.metadataFor(id)?.licenseGroup)
          .filter(Boolean),
      ).size;
    });
    const actualRows = await licenseSection.locator(".guide-license-row").count();
    ensure(actualRows === expectedRows, `guide license list has ${actualRows} rows, expected ${expectedRows}`);
    const text = await licenseSection.textContent();

    ensure(await licenseSection.locator('[data-license-group="irodori_v3"]').count() === 1, "Irodori v3 must have one license row");
    ensure(!text.includes("Irodori v3 低遅延 (8-step)"), "low latency runtime profile leaked into license rows");
    ensure(await licenseSection.locator('[data-license-group="gpt_sovits"]').count() === 1, "GPT-SoVITS variants must share one license row");
    ensure(text.includes("GPT-SoVITS"), "GPT-SoVITS grouped label is missing");

    for (const group of ["irodori_v2", "fireredtts2", "ming_omni_tts_0_5b", "fun_cosyvoice3_0_5b"]) {
      ensure(
        (await licenseSection.locator(`[data-license-group="${group}"] .guide-license-commercial`).textContent()) === "商用可",
        `${group} commercial label must be explicit 商用可`,
      );
    }

    ensure(text.includes("Fish Audio S2 Pro"), "Fish S2 Pro is missing from the guide license section");
    ensure(text.includes("Fish Audio Research License"), "Fish license is missing from the guide license section");
    ensure(text.includes("IndexTTS 2.5"), "IndexTTS 2.5 is missing from the guide license section");

    const fishRow = licenseSection.locator('[data-license-group="fish_s2_pro"]');
    const indexRow = licenseSection.locator('[data-license-group="indextts_2_5"]');
    ensure((await fishRow.locator(".guide-license-commercial").textContent()) === "要別契約", "Fish commercial label must be 要別契約");
    ensure((await indexRow.locator(".guide-license-commercial").textContent()) === "条件付き", "IndexTTS commercial label must be 条件付き");
    ensure((await fishRow.locator(".guide-license-commercial").getAttribute("title") || "").includes("別途書面ライセンス"), "Fish full commercial condition is missing from title");
    ensure((await indexRow.locator(".guide-license-commercial").getAttribute("title") || "").includes("1億MAU"), "IndexTTS full commercial condition is missing from title");
    ensure(await fishRow.locator('a[href*="fishaudio/s2-pro/blob/main/LICENSE.md"]').count() === 1, "Fish official license link is missing");
    ensure(await indexRow.locator('a[href*="index-tts/index-tts/blob/main/LICENSE"]').count() === 1, "IndexTTS official license link is missing");

    console.log(JSON.stringify({
      ok: true,
      checked: [
        "no license block in normal generation",
        "no license block in model comparison",
        "all license groups rendered in compact guide rows",
        "shared-checkpoint runtime profiles grouped into one license row",
        "Fish S2 Pro license row in guide",
        "IndexTTS 2.5 license row in guide",
        "official license links",
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
