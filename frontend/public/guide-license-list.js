(() => {
  const catalog = window.LocalTtsModelCatalog;
  const ui = window.LocalTtsUi;
  if (!catalog || !ui) return;

  function groupedLicenseEntries() {
    const seen = new Set();
    const entries = [];

    for (const id of catalog.MODEL_ORDER) {
      if (id === "mock") continue;
      const metadata = catalog.metadataFor(id);
      if (!metadata) continue;

      const group = String(metadata.licenseGroup || id);
      if (seen.has(group)) continue;
      seen.add(group);

      entries.push({
        group,
        label: metadata.licenseLabel || catalog.modelLabel(id),
        metadata,
      });
    }
    return entries;
  }

  function render() {
    const list = document.querySelector("#guideModelLicenseList");
    if (!list) return;

    list.innerHTML = groupedLicenseEntries()
      .map(({ group, label, metadata }) => `
        <div class="guide-license-row" data-license-group="${ui.escapeHtml(group)}">
          <strong class="guide-license-name">${ui.escapeHtml(label)}</strong>
          <span class="guide-license-commercial" title="${ui.escapeHtml(metadata.commercial)}">${ui.escapeHtml(metadata.commercialStatus)}</span>
          <span class="guide-license-nameplate" title="${ui.escapeHtml(metadata.license)}">${ui.escapeHtml(metadata.license)}</span>
          <a href="${ui.escapeHtml(metadata.termsUrl)}" target="_blank" rel="noopener noreferrer">詳細 ↗</a>
        </div>`)
      .join("");
  }

  window.LocalTtsGuideLicenses = Object.freeze({ groupedLicenseEntries, render });
  render();
})();
