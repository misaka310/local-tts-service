(() => {
  function requiresReference(model) {
    return Boolean(model && model.requiresReferenceAudio);
  }

  function supportsReference(model) {
    return Boolean(model && (model.supportsReferenceVoice || model.requiresReferenceAudio));
  }

  function requiresInstruction(model, voice = null) {
    if (!model || !model.supportsVoiceDesign) return false;
    const hasUsableReference = Boolean(voice && supportsReference(model));
    return !hasUsableReference;
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

  function requiresPromptForStyleStrength(model) {
    return Boolean(model && (model.supportsCaption || model.supportsInstruction || model.supportsVoiceDesign));
  }

  window.LocalTtsModelCapabilities = Object.freeze({
    requiresReference,
    supportsReference,
    requiresInstruction,
    supportsInstruction,
    supportsSpeedControl,
    supportsStyleStrength,
    requiresPromptForStyleStrength,
  });
})();
