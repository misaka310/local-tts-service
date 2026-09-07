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

test("model selectors keep a stable latest-to-oldest Irodori group", () => {
  assert.deepEqual(catalog.DESIRED_MODELS.slice(0, 7), [
    "irodori_v4_1_small",
    "irodori_v4_1_anime",
    "irodori_v4_small",
    "irodori_v3",
    "irodori_v3_low_latency",
    "irodori_v3_voicedesign",
    "irodori_v2",
  ]);

  const mixedAvailability = [
    { id: "irodori_v2", available: true, enabled: true },
    { id: "irodori_v4_1_small", available: false, enabled: false },
    { id: "irodori_v3", available: true, enabled: true },
  ];
  assert.deepEqual(
    catalog.sortModelsAvailableFirst(mixedAvailability).map((model) => model.id),
    ["irodori_v4_1_small", "irodori_v3", "irodori_v2"],
  );
});
