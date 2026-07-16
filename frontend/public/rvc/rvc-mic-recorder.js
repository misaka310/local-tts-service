(function bootstrapRvcMicRecorder(global) {
  "use strict";
  function transition(state = "idle", event) {
    const transitions = {
      idle: { start: "recording" },
      recording: { stop: "processing", fail: "error" },
      processing: { saved: "ready", fail: "error" },
      ready: { start: "recording", clear: "idle" },
      error: { start: "recording", clear: "idle" },
    };
    return transitions[state]?.[event] || state;
  }
  global.LocalTts = global.LocalTts || {};
  global.LocalTts.rvcMicRecorder = Object.freeze({ transition });
})(globalThis);
