(function bootstrapRvcController(global) {
  "use strict";

  function requireActions(actions, names) {
    for (const name of names) {
      if (typeof actions?.[name] !== "function") throw new TypeError(`RVC controller requires ${name}`);
    }
  }

  function listen(element, type, handler) {
    element?.addEventListener?.(type, handler);
  }

  function createRvcController({ elements = {}, actions = {}, deviceEvents = null, documentEvents = null } = {}) {
    requireActions(actions, [
      "refreshText",
      "saveInputSource",
      "saveSettings",
      "updateModel",
      "selectVoiceModel",
      "reloadModels",
      "rememberFilePath",
      "saveMicDevice",
      "loadMicDevices",
      "previewReference",
      "convert",
      "denoise",
      "startRecording",
      "stopRecording",
      "useRecording",
      "selectRecording",
      "restoreHistory",
      "clearHistory",
    ]);

    let bound = false;

    function closeHelp() {
      for (const button of elements.helpButtons || []) button.classList?.remove?.("open");
    }

    function bind() {
      if (bound) return false;
      bound = true;

      for (const element of elements.inputSources || []) {
        const onSourceChange = () => {
          actions.saveInputSource();
          actions.updateModel();
        };
        listen(element, "input", onSourceChange);
        listen(element, "change", onSourceChange);
      }

      [elements.text, elements.instruction, elements.micScript].filter(Boolean).forEach((element) => {
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

      listen(elements.voiceModel, "change", actions.selectVoiceModel);
      listen(elements.reloadModels, "click", actions.reloadModels);

      [elements.seedAutoIncrement, elements.autoPlay].filter(Boolean).forEach((element) => {
        listen(element, "change", actions.saveSettings);
      });

      [elements.externalAudioPath, elements.demucsModel, elements.indexRatePreset, elements.f0UpKeyPreset, elements.protectPreset, elements.micDevice]
        .filter(Boolean)
        .forEach((element) => listen(element, "input", actions.updateModel));

      listen(elements.externalAudioPath, "change", actions.rememberFilePath);
      listen(elements.micDevice, "input", actions.saveMicDevice);
      listen(elements.micDevice, "change", () => {
        actions.saveMicDevice();
        actions.updateModel();
      });
      listen(deviceEvents, "devicechange", actions.loadMicDevices);

      listen(elements.referencePreview, "click", actions.previewReference);
      listen(elements.convert, "click", actions.convert);
      listen(elements.denoise, "click", actions.denoise);
      listen(elements.micStart, "click", actions.startRecording);
      listen(elements.micStop, "click", actions.stopRecording);
      listen(elements.micRerecord, "click", actions.startRecording);
      listen(elements.micUse, "click", actions.useRecording);
      listen(elements.micHistory, "change", () => actions.selectRecording(elements.micHistory?.value || ""));
      listen(elements.clearHistory, "click", actions.clearHistory);
      listen(elements.history, "click", (event) => {
        const button = event?.target?.closest?.("[data-restore-rvc-history]");
        if (button) actions.restoreHistory(Number(button.dataset.restoreRvcHistory));
      });

      for (const button of elements.helpButtons || []) {
        listen(button, "click", (event) => {
          event?.stopPropagation?.();
          const shouldOpen = !button.classList?.contains?.("open");
          closeHelp();
          if (shouldOpen) button.classList?.add?.("open");
        });
      }
      listen(documentEvents, "click", closeHelp);
      return true;
    }

    return Object.freeze({
      bind,
      convert: (...args) => actions.convert(...args),
      denoise: (...args) => actions.denoise(...args),
      startRecording: (...args) => actions.startRecording(...args),
      stopRecording: (...args) => actions.stopRecording(...args),
      selectRecording: (...args) => actions.selectRecording(...args),
      updateModel: (...args) => actions.updateModel(...args),
    });
  }

  global.LocalTts = global.LocalTts || {};
  global.LocalTts.rvcController = Object.freeze({ createRvcController });
})(globalThis);
