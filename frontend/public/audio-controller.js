(function bootstrapAudioController(global) {
  "use strict";

  function currentSource(audio) {
    return String(audio?.src || audio?.currentSrc || "");
  }

  function isInterruptedPlayError(error) {
    const message = String(error?.message || error || "");
    return error?.name === "AbortError" || /play\(\) request was interrupted|interrupted by a call to pause/i.test(message);
  }

  function waitForPlayable(audio, { timeoutMs = 15000 } = {}) {
    if (!audio) return Promise.reject(new Error("audio element is required"));
    if (audio.error) return Promise.reject(new Error(audio.error.message || `audio error ${audio.error.code || "unknown"}`));
    if (Number(audio.readyState || 0) >= 2) return Promise.resolve(true);

    return new Promise((resolve, reject) => {
      let timer = 0;
      const cleanup = () => {
        if (timer) global.clearTimeout(timer);
        audio.removeEventListener?.("loadeddata", onReady);
        audio.removeEventListener?.("canplay", onReady);
        audio.removeEventListener?.("error", onError);
      };
      const onReady = () => {
        if (Number(audio.readyState || 0) < 2) return;
        cleanup();
        resolve(true);
      };
      const onError = () => {
        cleanup();
        reject(new Error(audio.error?.message || `audio error ${audio.error?.code || "unknown"}`));
      };
      audio.addEventListener?.("loadeddata", onReady);
      audio.addEventListener?.("canplay", onReady);
      audio.addEventListener?.("error", onError);
      timer = global.setTimeout(() => {
        cleanup();
        reject(new Error("音声の読み込みが完了しませんでした。"));
      }, Math.max(1000, Number(timeoutMs) || 15000));
    });
  }

  async function playWhenReady(audio, options = {}) {
    const expectedSource = currentSource(audio);
    if (!expectedSource) throw new Error("再生対象の音声URLが空です。");
    await waitForPlayable(audio, options);
    try {
      await audio.play();
      return true;
    } catch (error) {
      if (!isInterruptedPlayError(error) || currentSource(audio) !== expectedSource) throw error;
      await new Promise((resolve) => global.setTimeout(resolve, 80));
      if (currentSource(audio) !== expectedSource) throw error;
      await waitForPlayable(audio, options);
      await audio.play();
      return true;
    }
  }

  function createAudioController({ onError = () => {} } = {}) {
    let activeAudio = null;
    return Object.freeze({
      async play(audio) {
        if (!audio) return false;
        if (activeAudio && activeAudio !== audio) activeAudio.pause();
        activeAudio = audio;
        try {
          await audio.play();
          return true;
        } catch (error) {
          onError(error);
          return false;
        }
      },
      stop() {
        activeAudio?.pause();
        activeAudio = null;
      },
      current: () => activeAudio,
    });
  }

  global.LocalTts = global.LocalTts || {};
  global.LocalTts.audioController = Object.freeze({
    createAudioController,
    isInterruptedPlayError,
    playWhenReady,
    waitForPlayable,
  });
})(globalThis);
