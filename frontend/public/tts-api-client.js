(() => {
  function jsonOptions(method, body, options = {}) {
    return {
      ...options,
      method,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      body: JSON.stringify(body),
    };
  }

  function create(fetchJson) {
    if (typeof fetchJson !== "function") throw new TypeError("fetchJson is required");
    return Object.freeze({
      models(options) {
        return fetchJson("/api/models", options);
      },
      referenceVoices(options) {
        return fetchJson("/api/reference-voices", options);
      },
      rvcDefaults(options) {
        return fetchJson("/api/rvc/defaults", options);
      },
      speak(body, options) {
        return fetchJson("/api/speak", jsonOptions("POST", body, options));
      },
      saveRvcRecording(body, options) {
        return fetchJson("/api/rvc/recording", jsonOptions("POST", body, options));
      },
      convertRvc(body, options) {
        return fetchJson("/api/rvc/convert", jsonOptions("POST", body, options));
      },
      denoiseRvc(body, options) {
        return fetchJson("/api/rvc/denoise", jsonOptions("POST", body, options));
      },
    });
  }

  window.LocalTtsApiClient = Object.freeze({ create });
})();
