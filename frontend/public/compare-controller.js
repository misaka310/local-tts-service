(function bootstrapCompareController(global) {
  "use strict";

  function requireActions(actions, names) {
    for (const name of names) {
      if (typeof actions?.[name] !== "function") throw new TypeError(`compare controller requires ${name}`);
    }
  }

  function listen(element, type, handler) {
    element?.addEventListener?.(type, handler);
  }

  function createCompareController({ elements = {}, actions = {} } = {}) {
    requireActions(actions, [
      "refreshText",
      "saveSettings",
      "updateSelection",
      "previewReference",
      "generate",
      "selectAll",
      "clearSelection",
      "regenerateModel",
      "adoptModel",
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
          actions.updateSelection();
        });
      });

      [elements.seed, elements.voice].filter(Boolean).forEach((element) => {
        listen(element, "input", () => {
          actions.saveSettings();
          actions.updateSelection();
        });
      });

      [elements.seedAutoIncrement, elements.autoPlay].filter(Boolean).forEach((element) => {
        listen(element, "change", actions.saveSettings);
      });

      listen(elements.referencePreview, "click", actions.previewReference);
      listen(elements.generate, "click", actions.generate);
      listen(elements.selectAll, "click", actions.selectAll);
      listen(elements.clear, "click", actions.clearSelection);
      listen(elements.clearHistory, "click", actions.clearHistory);

      listen(elements.results, "click", async (event) => {
        const regenerateButton = event?.target?.closest?.("[data-regenerate-model]");
        if (regenerateButton) {
          await actions.regenerateModel(regenerateButton.dataset.regenerateModel || "");
          return;
        }
        const adoptButton = event?.target?.closest?.("[data-adopt-model]");
        if (adoptButton) actions.adoptModel(adoptButton.dataset.adoptModel || "");
      });

      listen(elements.history, "click", (event) => {
        const button = event?.target?.closest?.("[data-restore-compare-history]");
        if (button) actions.restoreHistory(Number(button.dataset.restoreCompareHistory));
      });
      return true;
    }

    return Object.freeze({
      bind,
      generate: (...args) => actions.generate(...args),
      regenerateModel: (...args) => actions.regenerateModel(...args),
      adoptModel: (...args) => actions.adoptModel(...args),
      restoreHistory: (...args) => actions.restoreHistory(...args),
      updateSelection: (...args) => actions.updateSelection(...args),
    });
  }

  global.LocalTts = global.LocalTts || {};
  global.LocalTts.compareController = Object.freeze({ createCompareController });
})(globalThis);
