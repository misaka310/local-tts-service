(function bootstrapRvcForm(global) {
  "use strict";

  const INPUT_SOURCES = Object.freeze(["tts", "file", "mic"]);
  function normalizeInputSource(value) { return INPUT_SOURCES.includes(value) ? value : "tts"; }
  function buildParams(fields = {}) {
    const number = (value, fallback) => Number.isFinite(Number(value)) ? Number(value) : fallback;
    return {
      modelPath: String(fields.modelPath || "").trim(),
      indexPath: String(fields.indexPath || "").trim(),
      f0Method: String(fields.f0Method || "rmvpe").trim(),
      pitch: number(fields.pitch, 0),
      indexRate: number(fields.indexRate, 0.75),
      filterRadius: number(fields.filterRadius, 3),
      resampleSr: number(fields.resampleSr, 0),
      rmsMixRate: number(fields.rmsMixRate, 0.25),
      protect: number(fields.protect, 0.33),
    };
  }
  global.LocalTts = global.LocalTts || {};
  global.LocalTts.rvcForm = Object.freeze({ INPUT_SOURCES, normalizeInputSource, buildParams });
})(globalThis);
