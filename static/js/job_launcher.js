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
    const fullHint = document.getElementById("generate-full-hint");
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
    // O lote completo só libera depois que a amostra (3 linhas) terminar com
    // sucesso NESTA planilha — evita gerar tudo sem antes conferir o
    // resultado. Escolher outro arquivo exige nova amostra.
    let samplesReady = false;

    const show = (element, visible) => {
      if (element) element.hidden = !visible;
    };

    const setError = (message) => {
      if (!errorBox) return;
      errorBox.textContent = message || "";
      show(errorBox, Boolean(message));
    };

    const syncFullButtonState = () => {
      if (fullButton) fullButton.disabled = running || !samplesReady;
      show(fullHint, !running && !samplesReady);
    };

    const setBusy = (busy) => {
      // O botão de amostra só sai do ar enquanto o job está no ar. Fora
      // disso fica clicável: clicar sem planilha responde com o motivo, que
      // é mais útil do que um botão apagado sem explicação. Já o de lote
      // completo também depende da amostra ter sido gerada (syncFullButtonState).
      running = busy;
      if (previewButton) previewButton.disabled = busy;
      if (fileInput) fileInput.disabled = busy;
      if (card) card.setAttribute("aria-busy", busy ? "true" : "false");
      syncFullButtonState();
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

    const poll = async (statusUrl, kind) => {
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
        if (kind === "preview" && data.status === "completed" && Number(data.success_rows) > 0) {
          samplesReady = true;
        }
        setBusy(false);
        setError(data.status === "failed" ? data.last_error : "");
        return;
      }
      pollTimer = window.setTimeout(() => poll(statusUrl, kind), POLL_INTERVAL);
    };

    const launch = async (kind) => {
      if (!fileInput?.files?.length) {
        setError("Escolha o Excel com os dados antes de gerar.");
        return;
      }
      if (kind === "full" && !samplesReady) {
        setError("Gere a amostra (3 linhas) e confira o resultado antes do lote completo.");
        return;
      }
      // Uma nova rodada de amostra some com a garantia da anterior até que
      // esta também termine com sucesso — se ela falhar, o lote completo
      // continua bloqueado em vez de destravar com um resultado velho.
      if (kind === "preview") samplesReady = false;
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
      poll(data.status_url, kind);
    };

    fileInput?.addEventListener("change", () => {
      setError("");
      // Outra planilha ainda não passou pela amostra desta vez.
      samplesReady = false;
      syncFullButtonState();
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
    const filenamePatternUrl = card.dataset.filenamePatternUrl;
    const sampleUrl = card.dataset.sampleUrl;
    const filenamePreview = document.getElementById("filename-preview");
    const filenamePreviewName = document.getElementById("filename-preview-name");
    const filenameSaveStateEl = document.getElementById("filename-save-state");
    // Atribuída de verdade mais abaixo, perto de selectedCaseColumns —
    // declarada já aqui porque os listeners do padrão/espaços (registrados
    // antes) também precisam poder chamá-la.
    let renderFilenamePreview = () => {};

    // Um indicador só pro cartão inteiro (canto inferior direito) em vez de
    // um "Salvo" atrás de cada uma das quatro opções.
    const setFilenameSaveState = (tone, text) => {
      if (!filenameSaveStateEl) return;
      filenameSaveStateEl.textContent = text || "";
      if (tone) filenameSaveStateEl.dataset.tone = tone;
      else delete filenameSaveStateEl.dataset.tone;
    };

    if (filenamePatternInput && filenamePatternUrl) {
      let saveTimer = null;
      let lastSaved = filenamePatternInput.value;

      const saveFilenamePattern = async () => {
        const value = filenamePatternInput.value;
        if (value === lastSaved) return;
        setFilenameSaveState("busy", "Salvando\u2026");
        try {
          const response = await fetch(filenamePatternUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken, "Content-Type": "application/json" },
            body: JSON.stringify({ filename_pattern: value }),
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
          lastSaved = data.filename_pattern ?? value;
          setFilenameSaveState("ok", "Salvo");
        } catch (err) {
          setFilenameSaveState("error", err.message || "N\u00e3o foi poss\u00edvel salvar o nome dos arquivos.");
        }
      };

      filenamePatternInput.addEventListener("input", () => {
        setFilenameSaveState(null, "");
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(saveFilenamePattern, 600);
        renderFilenamePreview();
      });
      filenamePatternInput.addEventListener("blur", () => {
        window.clearTimeout(saveTimer);
        saveFilenamePattern();
      });
    }

    const spaceModeSelect = document.getElementById("filename-space-mode");
    const spaceReplacementInput = document.getElementById("filename-space-replacement");

    if (spaceModeSelect && filenamePatternUrl) {
      let spaceSaveTimer = null;

      const syncReplacementVisibility = () => {
        if (spaceReplacementInput) spaceReplacementInput.hidden = spaceModeSelect.value !== "replace";
      };

      const saveSpaceMode = async () => {
        setFilenameSaveState("busy", "Salvando\u2026");
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
          setFilenameSaveState("ok", "Salvo");
        } catch (err) {
          setFilenameSaveState("error", err.message || "N\u00e3o foi poss\u00edvel salvar.");
        }
      };

      spaceModeSelect.addEventListener("change", () => {
        syncReplacementVisibility();
        saveSpaceMode();
        renderFilenamePreview();
      });
      spaceReplacementInput?.addEventListener("input", () => {
        setFilenameSaveState(null, "");
        window.clearTimeout(spaceSaveTimer);
        spaceSaveTimer = window.setTimeout(saveSpaceMode, 600);
        renderFilenamePreview();
      });
      spaceReplacementInput?.addEventListener("blur", () => {
        window.clearTimeout(spaceSaveTimer);
        saveSpaceMode();
      });
    }

    const stripAccentsCheckbox = document.getElementById("filename-strip-accents");
    const caseSelect = document.getElementById("filename-case");
    const caseColumnsGroup = document.getElementById("filename-case-columns-group");
    const caseColumnsContainer = document.getElementById("filename-case-columns");
    const caseColumnsDataEl = document.getElementById("filename-case-columns-data");

    if (filenamePatternUrl) {
      // Colunas j\u00e1 marcadas ao carregar a p\u00e1gina (JSONField do template).
      const selectedCaseColumns = new Set(
        caseColumnsDataEl ? JSON.parse(caseColumnsDataEl.textContent || "[]") : []
      );

      const stripAccentsJs = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "");

      // Amostra ao vivo do nome do arquivo, s\u00f3 com dado real: firstRowColumns
      // (coluna_1, coluna_2...) vem da primeira linha da planilha escolhida
      // (ver readFirstRowFromFile) \u2014 sem planilha ainda, n\u00e3o h\u00e1 o que mostrar.
      let firstRowColumns = null;

      renderFilenamePreview = () => {
        if (!filenamePreview || !filenamePreviewName) return;
        if (!firstRowColumns) {
          filenamePreview.hidden = true;
          return;
        }
        const pattern = (filenamePatternInput?.value || "").trim();
        const caseValue = caseSelect?.value || "none";

        const columnText = (columnNumber) => {
          let value = String(firstRowColumns[columnNumber] ?? "");
          if (stripAccentsCheckbox?.checked) value = stripAccentsJs(value);
          const applyCase = caseValue !== "none" && (!selectedCaseColumns.size || selectedCaseColumns.has(columnNumber));
          if (applyCase) value = caseValue === "upper" ? value.toUpperCase() : value.toLowerCase();
          return value;
        };

        let base = !pattern
          ? ""
          : /^\d+$/.test(pattern)
            ? columnText(Number(pattern))
            : pattern.replace(/\{(\d+)\}/g, (_, n) => columnText(Number(n)));

        base = base.replace(/\s+/g, " ").trim();
        const spaceMode = spaceModeSelect?.value || "keep";
        if (spaceMode === "strip") {
          base = base.replace(/ /g, "");
        } else if (spaceMode === "replace") {
          const replacement = (spaceReplacementInput?.value || "-").trim() || "-";
          base = base.replace(/ /g, replacement);
        }

        filenamePreview.hidden = false;
        filenamePreviewName.textContent = `${base || "certificado-linha-1"}.pdf`;
      };

      const readFirstRowFromFile = async (file) => {
        if (!sampleUrl || !filenamePreview || !filenamePreviewName) return;
        firstRowColumns = null;
        filenamePreview.hidden = false;
        filenamePreviewName.textContent = "Lendo a planilha\u2026";
        const formData = new FormData();
        formData.append("excel", file);
        try {
          const response = await fetch(sampleUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken },
            body: formData,
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(data.error || "N\u00e3o foi poss\u00edvel ler a planilha.");
          firstRowColumns = data.first_row_columns || {};
          renderFilenamePreview();
        } catch (err) {
          filenamePreview.hidden = false;
          filenamePreviewName.textContent = err.message || "N\u00e3o foi poss\u00edvel ler a planilha.";
        }
      };

      fileInput?.addEventListener("change", () => {
        const file = fileInput.files?.[0];
        if (!file) {
          firstRowColumns = null;
          if (filenamePreview) filenamePreview.hidden = true;
          return;
        }
        readFirstRowFromFile(file);
      });

      const columnRefsFromPattern = (pattern) => {
        const trimmed = String(pattern || "").trim();
        if (!trimmed) return [];
        if (/^\d+$/.test(trimmed)) return [Number(trimmed)];
        const refs = [];
        const re = /\{(\d+)\}/g;
        let match;
        while ((match = re.exec(trimmed))) refs.push(Number(match[1]));
        return refs;
      };

      const saveCaseOptions = async () => {
        setFilenameSaveState("busy", "Salvando…");
        try {
          const response = await fetch(filenamePatternUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken, "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_case: caseSelect?.value || "none",
              filename_case_columns: Array.from(selectedCaseColumns).sort((a, b) => a - b),
            }),
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
          setFilenameSaveState("ok", "Salvo");
        } catch (err) {
          setFilenameSaveState("error", err.message || "Não foi possível salvar.");
        }
      };

      // Só mostra "aplicar a quais colunas" quando o padrão junta 2+ colunas
      // e a caixa não está desligada — igual ao painel de campos do editor.
      const syncCaseColumnsUI = () => {
        if (!caseColumnsGroup || !caseColumnsContainer || !caseSelect) return;
        const refs = Array.from(new Set(columnRefsFromPattern(filenamePatternInput?.value)));
        if (caseSelect.value === "none" || refs.length < 2) {
          caseColumnsGroup.hidden = true;
          caseColumnsContainer.innerHTML = "";
          return;
        }
        caseColumnsGroup.hidden = false;
        caseColumnsContainer.innerHTML = "";
        refs.forEach((columnNumber) => {
          const label = document.createElement("label");
          label.className = "field-transform-column-toggle";
          const input = document.createElement("input");
          input.type = "checkbox";
          input.checked = selectedCaseColumns.has(columnNumber);
          input.addEventListener("change", () => {
            if (input.checked) selectedCaseColumns.add(columnNumber);
            else selectedCaseColumns.delete(columnNumber);
            saveCaseOptions();
            renderFilenamePreview();
          });
          label.appendChild(input);
          label.append(`Coluna ${columnNumber}`);
          caseColumnsContainer.appendChild(label);
        });
      };

      const saveStripAccents = async () => {
        setFilenameSaveState("busy", "Salvando…");
        try {
          const response = await fetch(filenamePatternUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken, "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_strip_accents: Boolean(stripAccentsCheckbox?.checked),
            }),
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
          setFilenameSaveState("ok", "Salvo");
        } catch (err) {
          setFilenameSaveState("error", err.message || "Não foi possível salvar.");
        }
      };

      stripAccentsCheckbox?.addEventListener("change", () => {
        saveStripAccents();
        renderFilenamePreview();
      });
      caseSelect?.addEventListener("change", () => {
        syncCaseColumnsUI();
        saveCaseOptions();
        renderFilenamePreview();
      });
      filenamePatternInput?.addEventListener("input", () => {
        syncCaseColumnsUI();
        renderFilenamePreview();
      });

      syncCaseColumnsUI();
      renderFilenamePreview();
    }

    previewButton?.addEventListener("click", () => launch("preview"));
    fullButton?.addEventListener("click", () => launch("full"));

    syncButtons();
    syncFullButtonState();
    window.__vetorialJobLauncher = { launch, syncButtons };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
