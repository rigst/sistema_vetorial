/* Card "Gerar arquivos" da bancada.
 *
 * Fluxo: escolher o Excel -> lançar o job (jobs:launch) -> acompanhar o
 * progresso pelo status JSON (jobs:status) -> listar os PDFs prontos.
 * O card vive fora do editor Fabric, então não depende de template_editor.js.
 */
(() => {
  "use strict";

  const POLL_INTERVAL = 1200;
  const TERMINAL_STATUS = new Set(["completed", "failed"]);
  // Acima disso a lista por linha vira resumo + link para a página do job:
  // essa coluna estreita da bancada não é lugar para 100 linhas.
  const INLINE_ITEM_LIMIT = 12;

  const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`;

  function init() {
    const card = document.getElementById("generate-card");
    if (!card) return;

    const launchUrl = card.dataset.launchUrl;
    const templateId = card.dataset.templateId;
    const csrfToken = card.querySelector("[name=csrfmiddlewaretoken]")?.value;

    const fileInput = document.getElementById("generate-excel-input");
    const fileLabel = document.getElementById("generate-file-label");
    const fileLabelText = document.getElementById("generate-file-name");
    const previewButton = document.getElementById("generate-preview-button");
    const fullButton = document.getElementById("generate-full-button");
    const progressBox = document.getElementById("generate-progress");
    const progressText = document.getElementById("generate-progress-text");
    const progressTrack = document.getElementById("generate-progress-track");
    const progressFill = document.getElementById("generate-progress-fill");
    const errorBox = document.getElementById("generate-error");
    const resultBox = document.getElementById("generate-result");
    const zipLink = document.getElementById("generate-zip-link");
    const itemsList = document.getElementById("generate-items");
    const detailLink = document.getElementById("generate-detail-link");

    const EMPTY_LABEL = fileLabelText ? fileLabelText.textContent : "";
    let pollTimer = null;
    let running = false;

    const show = (element, visible) => {
      if (element) element.hidden = !visible;
    };

    const setError = (message) => {
      if (!errorBox) return;
      errorBox.textContent = message || "";
      show(errorBox, Boolean(message));
    };

    const setBusy = (busy) => {
      // Os botões só saem do ar enquanto o job está no ar. Fora disso ficam
      // clicáveis: clicar sem planilha responde com o motivo, que é mais útil
      // do que um botão apagado sem explicação.
      running = busy;
      [previewButton, fullButton].forEach((button) => {
        if (button) button.disabled = busy;
      });
      if (fileInput) fileInput.disabled = busy;
      if (card) card.setAttribute("aria-busy", busy ? "true" : "false");
    };

    const syncButtons = () => {
      const hasFile = Boolean(fileInput?.files?.length);
      if (fileLabel) fileLabel.classList.toggle("has-file", hasFile);
      if (fileLabelText) {
        fileLabelText.textContent = hasFile ? fileInput.files[0].name : EMPTY_LABEL;
      }
    };

    // #generate-progress é role="status"/aria-live: fica no ar até o fim para
    // que o texto final ("N arquivos prontos") seja anunciado por leitor de
    // tela. Escondê-la no exato instante da conclusão apagaria a região viva
    // antes de qualquer anúncio chegar a acontecer.
    const setProgress = (data) => {
      const total = Number(data.total_rows) || 0;
      const processed = Number(data.processed_rows) || 0;
      const ratio = total ? Math.round((processed / total) * 100) : 0;
      if (progressFill) progressFill.style.transform = `scaleX(${ratio / 100})`;
      if (progressTrack) progressTrack.setAttribute("aria-valuenow", String(ratio));
      if (!progressText) return;
      if (data.status === "queued") {
        progressText.textContent = "Na fila…";
      } else if (TERMINAL_STATUS.has(data.status)) {
        progressText.textContent = data.success_rows
          ? `${plural(data.success_rows, "arquivo pronto", "arquivos prontos")}${data.failed_rows ? ` · ${plural(data.failed_rows, "linha com erro", "linhas com erro")}` : ""}`
          : "Nenhum arquivo foi gerado.";
      } else {
        progressText.textContent = total
          ? `Gerando ${processed} de ${plural(total, "linha", "linhas")}…`
          : "Lendo a planilha…";
      }
    };

    const itemNode = (item) => {
      const li = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = `Linha ${item.row_number}`;
      li.appendChild(label);

      if (item.output_url) {
        const link = document.createElement("a");
        link.href = item.output_url;
        link.textContent = "Baixar PDF";
        li.appendChild(link);
      } else if (item.error_message) {
        const error = document.createElement("span");
        error.className = "item-error";
        error.textContent = item.error_message;
        li.appendChild(error);
      } else {
        const pending = document.createElement("span");
        pending.className = "item-error";
        pending.textContent = item.status_display;
        li.appendChild(pending);
      }
      return li;
    };

    const renderResult = (data) => {
      const items = data.items || [];
      const total = Number(data.total_rows) || 0;
      const inline = total > 0 && total <= INLINE_ITEM_LIMIT;

      show(itemsList, inline);
      if (inline && itemsList) itemsList.replaceChildren(...items.map(itemNode));

      // A contagem já foi dita pela barra de progresso (#generate-progress-text);
      // aqui só o link para a página do job, sem repetir a mesma frase.
      if (detailLink) detailLink.href = data.detail_url || "#";
      show(detailLink, !inline && total > 0);

      if (zipLink) {
        zipLink.href = data.zip_url || "#";
        show(zipLink, Boolean(data.zip_url));
      }
      show(resultBox, total > 0 || Boolean(data.zip_url));
    };

    const poll = async (statusUrl) => {
      let data;
      try {
        const response = await fetch(statusUrl, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!response.ok) throw new Error(`Erro ${response.status}`);
        data = await response.json();
      } catch (err) {
        setBusy(false);
        setError("Perdemos o contato com o servidor. Recarregue a página para ver o andamento.");
        return;
      }

      setProgress(data);
      renderResult(data);

      if (TERMINAL_STATUS.has(data.status)) {
        setBusy(false);
        setError(data.status === "failed" ? data.last_error : "");
        return;
      }
      pollTimer = window.setTimeout(() => poll(statusUrl), POLL_INTERVAL);
    };

    const launch = async (kind) => {
      if (!fileInput?.files?.length) {
        setError("Escolha o Excel com os dados antes de gerar.");
        return;
      }
      window.clearTimeout(pollTimer);
      setError("");
      setBusy(true);
      show(progressBox, true);
      show(resultBox, false);
      if (itemsList) itemsList.replaceChildren();
      show(detailLink, false);
      if (progressFill) progressFill.style.transform = "scaleX(0)";
      if (progressTrack) progressTrack.setAttribute("aria-valuenow", "0");
      if (progressText) progressText.textContent = "Enviando a planilha…";

      const payload = new FormData();
      payload.append("template", templateId);
      payload.append("kind", kind);
      payload.append("source_excel", fileInput.files[0]);

      let data;
      try {
        const response = await fetch(launchUrl, {
          method: "POST",
          headers: { "X-CSRFToken": csrfToken },
          body: payload,
        });
        data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
      } catch (err) {
        setBusy(false);
        show(progressBox, false);
        setError(err.message || "Não foi possível enviar a planilha.");
        return;
      }

      if (progressText) progressText.textContent = "Na fila…";
      poll(data.status_url);
    };

    fileInput?.addEventListener("change", () => {
      setError("");
      syncButtons();
    });

    if (fileLabel && fileInput) {
      const stop = (event) => {
        event.preventDefault();
        event.stopPropagation();
      };
      ["dragenter", "dragover"].forEach((name) =>
        fileLabel.addEventListener(name, (event) => {
          stop(event);
          fileLabel.classList.add("is-dragging");
        })
      );
      ["dragleave", "dragend"].forEach((name) =>
        fileLabel.addEventListener(name, (event) => {
          stop(event);
          fileLabel.classList.remove("is-dragging");
        })
      );
      fileLabel.addEventListener("drop", (event) => {
        stop(event);
        fileLabel.classList.remove("is-dragging");
        const [file] = event.dataTransfer?.files || [];
        if (!file) return;
        const transfer = new DataTransfer();
        transfer.items.add(file);
        fileInput.files = transfer.files;
        fileInput.dispatchEvent(new Event("change"));
      });
    }

    const filenamePatternInput = document.getElementById("filename-pattern-input");
    const filenamePatternSaveState = document.getElementById("filename-pattern-save-state");
    const filenamePatternUrl = card.dataset.filenamePatternUrl;

    if (filenamePatternInput && filenamePatternUrl) {
      let saveTimer = null;
      let lastSaved = filenamePatternInput.value;

      const setSaveState = (tone, text) => {
        if (!filenamePatternSaveState) return;
        filenamePatternSaveState.textContent = text || "";
        if (tone) filenamePatternSaveState.dataset.tone = tone;
        else delete filenamePatternSaveState.dataset.tone;
      };

      const saveFilenamePattern = async () => {
        const value = filenamePatternInput.value;
        if (value === lastSaved) return;
        setSaveState("busy", "Salvando…");
        try {
          const response = await fetch(filenamePatternUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken, "Content-Type": "application/json" },
            body: JSON.stringify({ filename_pattern: value }),
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
          lastSaved = data.filename_pattern ?? value;
          setSaveState("ok", "Salvo");
        } catch (err) {
          setSaveState("error", err.message || "Não foi possível salvar o nome dos arquivos.");
        }
      };

      filenamePatternInput.addEventListener("input", () => {
        setSaveState(null, "");
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(saveFilenamePattern, 600);
      });
      filenamePatternInput.addEventListener("blur", () => {
        window.clearTimeout(saveTimer);
        saveFilenamePattern();
      });
    }

    const spaceModeSelect = document.getElementById("filename-space-mode");
    const spaceReplacementInput = document.getElementById("filename-space-replacement");
    const spaceSaveState = document.getElementById("filename-space-save-state");

    if (spaceModeSelect && filenamePatternUrl) {
      let spaceSaveTimer = null;

      const setSpaceSaveState = (tone, text) => {
        if (!spaceSaveState) return;
        spaceSaveState.textContent = text || "";
        if (tone) spaceSaveState.dataset.tone = tone;
        else delete spaceSaveState.dataset.tone;
      };

      const syncReplacementVisibility = () => {
        if (spaceReplacementInput) spaceReplacementInput.hidden = spaceModeSelect.value !== "replace";
      };

      const saveSpaceMode = async () => {
        setSpaceSaveState("busy", "Salvando…");
        try {
          const response = await fetch(filenamePatternUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken, "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_space_mode: spaceModeSelect.value,
              filename_space_replacement: spaceReplacementInput?.value || "",
            }),
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
          setSpaceSaveState("ok", "Salvo");
        } catch (err) {
          setSpaceSaveState("error", err.message || "Não foi possível salvar.");
        }
      };

      spaceModeSelect.addEventListener("change", () => {
        syncReplacementVisibility();
        saveSpaceMode();
      });
      spaceReplacementInput?.addEventListener("input", () => {
        setSpaceSaveState(null, "");
        window.clearTimeout(spaceSaveTimer);
        spaceSaveTimer = window.setTimeout(saveSpaceMode, 600);
      });
      spaceReplacementInput?.addEventListener("blur", () => {
        window.clearTimeout(spaceSaveTimer);
        saveSpaceMode();
      });
    }

    previewButton?.addEventListener("click", () => launch("preview"));
    fullButton?.addEventListener("click", () => launch("full"));

    syncButtons();
    window.__vetorialJobLauncher = { launch, syncButtons };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
