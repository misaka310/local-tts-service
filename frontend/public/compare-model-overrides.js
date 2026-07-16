(() => {
  "use strict";

  const MODEL_OVERRIDES = {
    f5_tts_zero_shot: {
      id: "qwen3_tts_clone_1_7b",
      label: "Qwen 1.7B",
      badges: ["高品質", "参照音声", "1.7B"],
      description: "参照音声と voice.txt を使う Qwen3-TTS 1.7B。F5-TTS の代わりに比較します。"
    },
    irodori_v2: {
      id: "irodori_v3_voicedesign",
      label: "Irodori v3 VoiceDesign",
      badges: ["VoiceDesign", "話し方指定", "感情制御"],
      description: "Irodori v3 の VoiceDesign 版。instruction / caption で話し方や感情を指定して比較します。"
    }
  };

  let modelsById = new Map();
  let patching = false;

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function modelAvailable(id) {
    const model = modelsById.get(id);
    return Boolean(model && model.available && model.enabled);
  }

  async function refreshModels() {
    try {
      const response = await fetch("/api/models", { cache: "no-store" });
      const payload = await response.json();
      const models = Array.isArray(payload.models) ? payload.models : [];
      modelsById = new Map(models.map((model) => [String(model.id || model.model || ""), model]));
    } catch {
      modelsById = new Map();
    }
  }

  function rewriteStaticHints() {
    document.querySelectorAll(".hint-panel li").forEach((item) => {
      item.innerHTML = item.innerHTML
        .replace("<strong>F5-TTS</strong>：高速で安定した読み上げを大量に作る時。", "<strong>Qwen 1.7B</strong>：参照音声寄せの高品質比較をしたい時。")
        .replace("<strong>Irodori</strong>：感情表現や自然な抑揚を見たい時。", "<strong>Irodori</strong>：v3通常版とVoiceDesign版の自然さ・話し方指定を見たい時。");
    });
  }

  function rewriteCard(oldId, override) {
    const card = document.querySelector(`[data-model-card="${oldId}"]`);
    if (!card) return false;

    const available = modelAvailable(override.id);
    const input = card.querySelector('input[type="checkbox"]');
    const title = card.querySelector("h3");
    const badgeRow = card.querySelector(".badge-row");
    const description = card.querySelector("p");

    card.dataset.modelCard = override.id;
    card.classList.toggle("disabled", !available);
    if (input) {
      input.value = override.id;
      input.disabled = !available;
      input.checked = available;
    }
    if (title) title.textContent = override.label;
    if (badgeRow) {
      badgeRow.innerHTML = override.badges.map((badge, index) => {
        const klass = index === 0 ? "green" : index === 2 ? "purple" : "";
        return `<span class="badge ${klass}">${escapeHtml(badge)}</span>`;
      }).join("");
    }
    if (description) {
      description.textContent = available ? override.description : `${override.description}（/api/models に ${override.id} がありません）`;
    }
    return true;
  }

  function rewriteLabelsInText(root = document) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const replacements = [
      ["F5-TTS Zero-shot", "Qwen 1.7B"],
      ["f5_tts_zero_shot", "qwen3_tts_clone_1_7b"],
      ["Irodori v2", "Irodori v3 VoiceDesign"],
      ["irodori v2", "Irodori v3 VoiceDesign"],
      ["irodori_v2", "irodori_v3_voicedesign"]
    ];
    let node = walker.nextNode();
    while (node) {
      let value = node.nodeValue;
      for (const [from, to] of replacements) value = value.replaceAll(from, to);
      node.nodeValue = value;
      node = walker.nextNode();
    }
  }

  function patchCompareCards() {
    if (patching) return;
    patching = true;
    try {
      Object.entries(MODEL_OVERRIDES).forEach(([oldId, override]) => rewriteCard(oldId, override));
      rewriteStaticHints();
      rewriteLabelsInText(document.querySelector("#comparePage") || document);

      const container = document.querySelector("#compareModelCards");
      const cards = Array.from(document.querySelectorAll("[data-model-card]"));
      const order = ["gpt_sovits_zero_shot", "qwen3_tts_clone_1_7b", "irodori_v3_voicedesign", "irodori_v3"];
      if (container && cards.length) {
        cards.sort((a, b) => order.indexOf(a.dataset.modelCard) - order.indexOf(b.dataset.modelCard));
        cards.forEach((card) => container.appendChild(card));
      }

      const status = document.querySelector("#compareStatusText");
      const checked = document.querySelectorAll('[data-model-card] input[type="checkbox"]:checked').length;
      if (status && checked) status.textContent = `${checked}モデルを同条件で生成します。`;
    } finally {
      patching = false;
    }
  }

  async function init() {
    await refreshModels();
    patchCompareCards();
    const observer = new MutationObserver(() => patchCompareCards());
    const target = document.querySelector("#comparePage") || document.body;
    if (target) observer.observe(target, { childList: true, subtree: true, characterData: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
