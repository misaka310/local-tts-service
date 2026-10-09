(function bootstrapRvcResult(global) {
  "use strict";
  function normalizeResult(result = {}) {
    return {
      audioUrl: String(result.audioUrl || ""),
      denoisedAudioUrl: String(result.denoisedAudioUrl || ""),
      filename: String(result.filename || ""),
      diagnostics: result.diagnostics && typeof result.diagnostics === "object" ? result.diagnostics : {},
    };
  }
  global.LocalTts = global.LocalTts || {};
  global.LocalTts.rvcResult = Object.freeze({ normalizeResult });
})(globalThis);
