(function bootstrapNormalController(global) {
  "use strict";

  function requireActions(actions, names) {
    for (const name of names) {
      if (typeof actions?.[name] !== "function") throw new TypeError(`normal controller requires ${name}`);
    }
  }

  function listen(element, type, handler) {
    element?.addEventListener?.(type, handler);
  }

  function createNormalController({ elements = {}, actions = {} } = {}) {
    requireActions(actions, [
      "refreshText",
      "saveSettings",
      "updateModel",
      "updateReference",
      "updateSynthesis",
      "previewReference",
      "generate",
      "regenerate",
      "restoreHistory",
      "clearHistory",
    ]);

    let bound = false;

    function bind() {
      if (bound) return false;
      bound = true;

      [elements.text, elements.instruction].filter(Boolean).forEach((element) => {
        listen(element, "input", () => {
          actions.refreshText();
          actions.updateModel();
        });
      });

      [elements.model, elements.voice, elements.language, elements.seed].filter(Boolean).forEach((element) => {
        listen(element, "input", () => {
          actions.saveSettings();
          actions.updateModel();
        });
      });

      [elements.seedAutoIncrement, elements.saveHistory, elements.autoPlay].filter(Boolean).forEach((element) => {
        listen(element, "change", actions.saveSettings);
      });

      listen(elements.useReference, "change", () => {
        actions.saveSettings();
        actions.updateReference();
        actions.updateModel();
      });

      [elements.speedScale, elements.styleStrength].filter(Boolean).forEach((element) => {
        listen(element, "input", () => {
          actions.updateSynthesis();
          actions.saveSettings();
        });
      });

      listen(elements.referencePreview, "click", actions.previewReference);
      listen(elements.generate, "click", actions.generate);
      listen(elements.regenerate, "click", actions.regenerate);
      listen(elements.clearHistory, "click", actions.clearHistory);
      listen(elements.history, "click", (event) => {
        const button = event?.target?.closest?.("[data-restore-normal-history]");
        if (button) actions.restoreHistory(Number(button.dataset.restoreNormalHistory));
      });
      return true;
    }

    return Object.freeze({
      bind,
      generate: (...args) => actions.generate(...args),
      regenerate: (...args) => actions.regenerate(...args),
      restoreHistory: (...args) => actions.restoreHistory(...args),
      updateModel: (...args) => actions.updateModel(...args),
    });
  }

  global.LocalTts = global.LocalTts || {};
  global.LocalTts.normalController = Object.freeze({ createNormalController });
})(globalThis);
