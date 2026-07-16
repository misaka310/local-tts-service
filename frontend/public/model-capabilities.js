(() => {
  function requiresReference(model) {
    return Boolean(model && model.requiresReferenceAudio);
  }

  function supportsReference(model) {
    return Boolean(model && (model.supportsReferenceVoice || model.requiresReferenceAudio));
  }

  function requiresInstruction(model) {
    return Boolean(model && model.supportsVoiceDesign && !model.supportsReferenceVoice);
  }

  function supportsInstruction(model) {
    return Boolean(model && (model.supportsInstruction || model.supportsVoiceDesign));
  }

  function supportsSpeedControl(model) {
    return Boolean(model && model.supportsSpeedControl);
  }

  function supportsStyleStrength(model) {
    return Boolean(model && model.supportsStyleStrength);
  }

  window.LocalTtsModelCapabilities = Object.freeze({
    requiresReference,
    supportsReference,
    requiresInstruction,
    supportsInstruction,
    supportsSpeedControl,
    supportsStyleStrength,
  });
})();
