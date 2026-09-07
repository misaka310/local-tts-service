import test from "node:test";
import assert from "node:assert/strict";

globalThis.window = globalThis;
await import("./public/model-catalog.js");

const catalog = globalThis.LocalTtsModelCatalog;

test("Irodori v4.1 base and anime models are selectable comparison models", () => {
  assert.equal(catalog.modelLabel("irodori_v4_1_small"), "Irodori v4.1 Small");
  assert.equal(catalog.modelLabel("irodori_v4_1_anime"), "Irodori v4.1 Anime");
  assert.ok(catalog.DESIRED_MODELS.includes("irodori_v4_1_small"));
  assert.ok(catalog.DESIRED_MODELS.includes("irodori_v4_1_anime"));
  assert.ok(catalog.profileFor("irodori_v4_1_small").badges.includes("v4.1"));
  assert.ok(catalog.profileFor("irodori_v4_1_anime").badges.includes("Anime FT"));
});
