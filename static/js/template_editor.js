/* Editor visual de templates baseado em Fabric.js.
 *
 * Sistema de coordenadas: o "mundo" do canvas é a página do PDF em pontos,
 * com origem no topo-esquerda (mesma convenção persistida em TemplateField).
 * O zoom/enquadramento é feito só com o viewportTransform do Fabric, então
 * left/top/width/fontSize dos objetos são gravados direto no banco.
 */
(() => {
  "use strict";

  // Fator interno de altura de linha do Fabric. O lineHeight do objeto é
  // dividido por ele para que o espaçamento efetivo seja fontSize * line_height,
  // idêntico ao usado na geração do PDF (jobs/services.py).
  const FONT_MULT = 1.13;
  const HISTORY_LIMIT = 60;

  const round2 = (value) => Math.round(Number(value) * 100) / 100;
  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  const rgba = (hex, alpha) => {
    const safeAlpha = clamp(Number(alpha ?? 1), 0, 1);
    if (typeof hex === "string" && hex.startsWith("#") && hex.length === 7) {
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      return `rgba(${r}, ${g}, ${b}, ${safeAlpha})`;
    }
    return hex;
  };

  const debounce = (fn, wait) => {
    let timer = null;
    const wrapped = (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
    wrapped.flush = (...args) => {
      clearTimeout(timer);
      fn(...args);
    };
    return wrapped;
  };

  async function loadFonts(fonts) {
    const loaded = {};
    await Promise.allSettled(
      fonts.map(async (font) => {
        const key = `vetfont-${font.id}`;
        try {
          const face = new FontFace(key, `url(${font.url})`);
          await face.load();
          document.fonts.add(face);
          loaded[font.id] = key;
        } catch (err) {
          console.warn(`Fonte ${font.name} não pôde ser carregada no navegador.`, err);
        }
      })
    );
    return loaded;
  }

  function init(config) {
    const canvasEl = document.getElementById(config.canvasId || "editor-canvas");
    if (!canvasEl || typeof fabric === "undefined") return;
    bootstrap(config, canvasEl);
  }

  async function bootstrap(config, canvasEl) {
    const readOnly = Boolean(config.readOnly);
    const page = { width: Number(config.page.width) || 1, height: Number(config.page.height) || 1 };
    const fields = config.fields.map((field) => ({ ...field }));
    const fieldsById = new Map(fields.map((field) => [field.id, field]));
    const objectsById = new Map();
    const statusText = document.getElementById("editor-status-text");
    const saveState = document.getElementById("editor-save-state");
    const wrap = document.getElementById(config.wrapId || "editor-canvas-wrap");

    const setStatus = (text) => { if (statusText) statusText.textContent = text; };
    const setSaveState = (text, tone) => {
      if (!saveState) return;
      saveState.textContent = text;
      saveState.dataset.tone = tone || "";
    };

    const snapGuides = [];
    const sample = { active: false, rows: [], index: 0, total: 0 };

    const fontKeys = await loadFonts(config.fonts || []);
    const fontFamilyFor = (fontId) => fontKeys[fontId] || "sans-serif";

    const canvas = new fabric.Canvas(canvasEl, {
      selection: !readOnly,
      preserveObjectStacking: true,
      uniformScaling: true,
      stopContextMenu: true,
      fireRightClick: false,
      backgroundColor: "transparent",
    });

    // ----- fundo -----
    if (config.backgroundUrl) {
      try {
        const img = await fabric.FabricImage.fromURL(config.backgroundUrl);
        img.set({
          left: 0,
          top: 0,
          originX: "left",
          originY: "top",
          scaleX: page.width / img.width,
          scaleY: page.height / img.height,
          selectable: false,
          evented: false,
        });
        canvas.backgroundImage = img;
      } catch (err) {
        console.warn("Falha ao carregar a imagem de fundo.", err);
      }
    }

    // ----- enquadramento / zoom -----
    const resizeCanvas = () => {
      const width = Math.max(wrap.clientWidth - 2, 320);
      const height = Math.max(Math.min(window.innerHeight * 0.68, width * (page.height / page.width) + 48), 260);
      canvas.setDimensions({ width, height });
    };

    const fitToScreen = () => {
      resizeCanvas();
      const zoom = Math.min(canvas.getWidth() / page.width, canvas.getHeight() / page.height) * 0.97;
      canvas.setViewportTransform([
        zoom, 0, 0, zoom,
        (canvas.getWidth() - page.width * zoom) / 2,
        (canvas.getHeight() - page.height * zoom) / 2,
      ]);
      updateZoomLabel();
      canvas.requestRenderAll();
    };

    const zoomLabel = document.getElementById("editor-zoom-label");
    const updateZoomLabel = () => {
      if (zoomLabel) zoomLabel.textContent = `${Math.round(canvas.getZoom() * 100)}%`;
    };

    const zoomBy = (factor, point) => {
      const zoom = clamp(canvas.getZoom() * factor, 0.05, 10);
      const center = point || new fabric.Point(canvas.getWidth() / 2, canvas.getHeight() / 2);
      canvas.zoomToPoint(center, zoom);
      updateZoomLabel();
    };

    canvas.on("mouse:wheel", (opt) => {
      opt.e.preventDefault();
      opt.e.stopPropagation();
      const factor = Math.pow(0.999, opt.e.deltaY);
      zoomBy(factor, new fabric.Point(opt.e.offsetX, opt.e.offsetY));
    });

    // pan com barra de espaço ou botão do meio
    let spacePressed = false;
    let panState = null;
    canvas.on("mouse:down", (opt) => {
      if (spacePressed || opt.e.button === 1) {
        panState = { x: opt.e.clientX, y: opt.e.clientY };
        canvas.selection = false;
        canvas.setCursor("grabbing");
      }
    });
    canvas.on("mouse:move", (opt) => {
      if (!panState) return;
      const vpt = canvas.viewportTransform;
      vpt[4] += opt.e.clientX - panState.x;
      vpt[5] += opt.e.clientY - panState.y;
      panState = { x: opt.e.clientX, y: opt.e.clientY };
      canvas.setViewportTransform(vpt);
    });
    canvas.on("mouse:up", () => {
      if (panState) {
        panState = null;
        canvas.selection = !readOnly;
      }
      snapGuides.length = 0;
      canvas.requestRenderAll();
    });

    // moldura da página
    canvas.on("after:render", ({ ctx }) => {
      const vpt = canvas.viewportTransform;
      const zoom = canvas.getZoom();
      ctx.save();
      ctx.strokeStyle = "rgba(232, 244, 240, 0.55)";
      ctx.lineWidth = 1;
      ctx.strokeRect(vpt[4] - 0.5, vpt[5] - 0.5, page.width * zoom + 1, page.height * zoom + 1);
      ctx.strokeStyle = "rgba(255, 84, 174, 0.95)";
      ctx.lineWidth = 1;
      snapGuides.forEach((guide) => {
        ctx.beginPath();
        if (guide.axis === "x") {
          const sx = guide.value * zoom + vpt[4];
          ctx.moveTo(sx, vpt[5]);
          ctx.lineTo(sx, vpt[5] + page.height * zoom);
        } else {
          const sy = guide.value * zoom + vpt[5];
          ctx.moveTo(vpt[4], sy);
          ctx.lineTo(vpt[4] + page.width * zoom, sy);
        }
        ctx.stroke();
      });
      ctx.restore();
    });

    // ----- criação dos objetos -----
    const textFor = (field) => {
      if (sample.active && sample.rows.length) {
        const value = sample.rows[sample.index].values[String(field.id)];
        if (value !== undefined && value !== "") return String(value);
      }
      return String(field.preview_value || field.empty_value || field.name || "");
    };

    const strokeProps = (field) => {
      if (field.border_enabled && Number(field.border_size_ratio) > 0) {
        const blur = Number(field.border_blur) || 0;
        return {
          stroke: rgba(field.border_color || "#000000", field.border_opacity),
          strokeWidth: Number(field.border_size_ratio) * Number(field.font_size),
          paintFirst: "stroke",
          strokeLineJoin: "round",
          shadow: blur > 0
            ? new fabric.Shadow({
                color: rgba(field.border_color || "#000000", clamp(Number(field.border_opacity) * 0.6, 0, 1)),
                blur: blur * 2,
                offsetX: 0,
                offsetY: 0,
              })
            : null,
        };
      }
      return { stroke: null, strokeWidth: 0, paintFirst: "fill", shadow: null };
    };

    const applyFieldToObject = (obj, field) => {
      obj.set({
        left: Number(field.x) || 0,
        top: Number(field.y) || 0,
        width: Math.max(Number(field.width) || 40, 10),
        angle: Number(field.rotation) || 0,
        scaleX: 1,
        scaleY: 1,
        fontSize: Number(field.font_size) || 24,
        fontFamily: fontFamilyFor(field.font_id),
        fill: field.color || "#000000",
        textAlign: field.text_align || "left",
        lineHeight: (Number(field.line_height) || 1.1) / FONT_MULT,
        ...strokeProps(field),
      });
      obj.set("text", textFor(field));
      obj.setCoords();
    };

    const createObject = (field) => {
      const obj = new fabric.Textbox(textFor(field), {
        originX: "left",
        originY: "top",
        editable: !readOnly,
        selectable: !readOnly,
        evented: !readOnly,
        objectCaching: false,
        splitByGrapheme: false,
        lockScalingFlip: true,
        snapAngle: 15,
        snapThreshold: 4,
        transparentCorners: false,
        cornerStyle: "circle",
        cornerSize: 9,
        touchCornerSize: 20,
        cornerColor: "#1f7a72",
        borderColor: "#1f7a72",
        borderScaleFactor: 1.4,
        padding: 2,
      });
      obj.setControlsVisibility({ mt: false, mb: false });
      obj.vetFieldId = field.id;
      applyFieldToObject(obj, field);
      objectsById.set(field.id, obj);
      canvas.add(obj);

      if (!readOnly) {
        obj.on("editing:entered", () => {
          if (sample.active) obj.exitEditing();
        });
        obj.on("editing:exited", () => {
          const current = fieldsById.get(field.id);
          if (!current || sample.active) return;
          const text = obj.text || "";
          if (text !== current.preview_value) {
            current.empty_value = text;
            queueSave(current.id, { empty_value: text });
            pushHistory();
          }
          commitObject(obj);
          syncPanel();
        });
      }
      return obj;
    };

    fields.forEach(createObject);

    // ----- geometria absoluta (funciona dentro de multi-seleção) -----
    const absoluteGeometry = (obj) => {
      if (!obj.group) {
        return { left: obj.left, top: obj.top, angle: obj.angle || 0, scale: obj.scaleX || 1 };
      }
      const decomposed = fabric.util.qrDecompose(obj.calcTransformMatrix());
      const width = obj.width * decomposed.scaleX;
      const height = obj.height * decomposed.scaleY;
      const rad = (decomposed.angle * Math.PI) / 180;
      return {
        left: decomposed.translateX - (Math.cos(rad) * width) / 2 + (Math.sin(rad) * height) / 2,
        top: decomposed.translateY - (Math.sin(rad) * width) / 2 - (Math.cos(rad) * height) / 2,
        angle: decomposed.angle,
        scale: decomposed.scaleX,
      };
    };

    const commitObject = (obj) => {
      const field = fieldsById.get(obj.vetFieldId);
      if (!field) return;
      if (!obj.group && Math.abs((obj.scaleX || 1) - 1) > 0.001) {
        const scale = obj.scaleX;
        obj.set({
          fontSize: Math.max(round2(obj.fontSize * scale), 4),
          width: Math.max(obj.width * scale, 10),
          scaleX: 1,
          scaleY: 1,
        });
      }
      const geo = absoluteGeometry(obj);
      field.x = round2(geo.left);
      field.y = round2(geo.top);
      field.rotation = round2(((geo.angle % 360) + 360) % 360);
      field.width = round2(obj.width);
      field.height = round2(obj.height);
      field.font_size = round2(obj.fontSize);
      obj.set(strokeProps(field));
      obj.setCoords();
      queueSave(field.id, {
        x: field.x,
        y: field.y,
        width: field.width,
        height: field.height,
        rotation: field.rotation,
        font_size: field.font_size,
      });
    };

    // ----- persistência -----
    const csrfToken = config.csrfToken || document.querySelector("[name=csrfmiddlewaretoken]")?.value;
    const fieldUrl = (id) => config.urls.fieldTemplate.replace("123454321", String(id));
    const pendingSaves = new Map();
    let inflightSaves = 0;

    const request = async (url, method, body, isForm) => {
      const headers = { "X-CSRFToken": csrfToken };
      if (!isForm) headers["Content-Type"] = "application/json";
      const response = await fetch(url, {
        method,
        headers,
        body: isForm ? body : body ? JSON.stringify(body) : null,
      });
      if (!response.ok) {
        let message = `Erro ${response.status}`;
        try { message = (await response.json()).error || message; } catch (err) { /* corpo não-JSON */ }
        throw new Error(message);
      }
      return response.json();
    };

    const flushSaves = async () => {
      if (readOnly || !pendingSaves.size) return;
      const batch = [...pendingSaves.entries()];
      pendingSaves.clear();
      inflightSaves += 1;
      setSaveState("Salvando…", "busy");
      try {
        for (const [fieldId, payload] of batch) {
          if (!fieldsById.has(fieldId)) continue;
          const result = await request(fieldUrl(fieldId), "PATCH", payload);
          const field = fieldsById.get(fieldId);
          const obj = objectsById.get(fieldId);
          if (field && result.field) {
            field.preview_value = result.field.preview_value;
            if (obj && !sample.active && !obj.isEditing) {
              obj.set("text", textFor(field));
              field.height = round2(obj.height);
            }
          }
        }
        setSaveState("Salvo ✓", "ok");
      } catch (err) {
        setSaveState(`Falha ao salvar: ${err.message}`, "error");
      } finally {
        inflightSaves -= 1;
        canvas.requestRenderAll();
      }
    };

    const scheduledFlush = debounce(flushSaves, 600);
    const queueSave = (fieldId, payload) => {
      if (readOnly) return;
      pendingSaves.set(fieldId, { ...(pendingSaves.get(fieldId) || {}), ...payload });
      setSaveState("Alterações pendentes…", "busy");
      scheduledFlush();
    };

    const saveAll = async () => {
      fields.forEach((field) => {
        queueSave(field.id, {
          x: field.x, y: field.y, width: field.width, height: field.height,
          rotation: field.rotation, font_size: field.font_size,
        });
      });
      await flushSaves();
      setStatus("Todas as posições foram salvas.");
    };

    window.addEventListener("beforeunload", (event) => {
      if (pendingSaves.size || inflightSaves > 0) {
        flushSaves();
        event.preventDefault();
        event.returnValue = "";
      }
    });

    // ----- histórico (undo/redo de propriedades; criar/excluir zera) -----
    const snapshot = () => JSON.parse(JSON.stringify(fields));
    let history = [snapshot()];
    let historyIndex = 0;

    const pushHistory = () => {
      history = history.slice(0, historyIndex + 1);
      history.push(snapshot());
      if (history.length > HISTORY_LIMIT) history.shift();
      historyIndex = history.length - 1;
    };

    const resetHistory = () => {
      history = [snapshot()];
      historyIndex = 0;
    };

    const restoreSnapshot = (snap) => {
      snap.forEach((stored) => {
        const field = fieldsById.get(stored.id);
        const obj = objectsById.get(stored.id);
        if (!field || !obj) return;
        const changed = JSON.stringify(field) !== JSON.stringify(stored);
        Object.assign(field, JSON.parse(JSON.stringify(stored)));
        applyFieldToObject(obj, field);
        if (changed) {
          queueSave(field.id, {
            x: field.x, y: field.y, width: field.width, height: field.height,
            rotation: field.rotation, font_size: field.font_size, color: field.color,
            text_align: field.text_align, line_height: field.line_height,
            empty_value: field.empty_value,
            border_enabled: field.border_enabled, border_color: field.border_color,
            border_size_ratio: field.border_size_ratio, border_opacity: field.border_opacity,
            border_blur: field.border_blur,
          });
        }
      });
      canvas.discardActiveObject();
      canvas.requestRenderAll();
      syncPanel();
    };

    const undo = () => {
      if (historyIndex <= 0) { setStatus("Nada para desfazer."); return; }
      historyIndex -= 1;
      restoreSnapshot(history[historyIndex]);
      setStatus("Desfeito.");
    };

    const redo = () => {
      if (historyIndex >= history.length - 1) { setStatus("Nada para refazer."); return; }
      historyIndex += 1;
      restoreSnapshot(history[historyIndex]);
      setStatus("Refeito.");
    };

    // ----- snapping com guias -----
    const computeSnapTargets = (activeObj) => {
      const xs = [0, page.width / 2, page.width];
      const ys = [0, page.height / 2, page.height];
      canvas.getObjects().forEach((other) => {
        if (other === activeObj || !other.vetFieldId) return;
        if (canvas.getActiveObjects().includes(other)) return;
        other.setCoords();
        const rect = other.getBoundingRect();
        xs.push(rect.left, rect.left + rect.width / 2, rect.left + rect.width);
        ys.push(rect.top, rect.top + rect.height / 2, rect.top + rect.height);
      });
      return { xs, ys };
    };

    canvas.on("object:moving", (opt) => {
      const obj = opt.target;
      snapGuides.length = 0;
      if (opt.e && opt.e.altKey) return;
      obj.setCoords();
      const rect = obj.getBoundingRect();
      const tolerance = 6 / canvas.getZoom();
      const targets = computeSnapTargets(obj);
      const candidatesX = [rect.left, rect.left + rect.width / 2, rect.left + rect.width];
      const candidatesY = [rect.top, rect.top + rect.height / 2, rect.top + rect.height];

      let best = { dist: tolerance, delta: 0, value: null };
      targets.xs.forEach((target) => {
        candidatesX.forEach((candidate) => {
          const dist = Math.abs(target - candidate);
          if (dist < best.dist) best = { dist, delta: target - candidate, value: target };
        });
      });
      if (best.value !== null) {
        obj.set("left", obj.left + best.delta);
        snapGuides.push({ axis: "x", value: best.value });
      }

      best = { dist: tolerance, delta: 0, value: null };
      targets.ys.forEach((target) => {
        candidatesY.forEach((candidate) => {
          const dist = Math.abs(target - candidate);
          if (dist < best.dist) best = { dist, delta: target - candidate, value: target };
        });
      });
      if (best.value !== null) {
        obj.set("top", obj.top + best.delta);
        snapGuides.push({ axis: "y", value: best.value });
      }
      obj.setCoords();
      const geo = absoluteGeometry(obj);
      setStatus(`x ${round2(geo.left)} · y ${round2(geo.top)}`);
    });

    canvas.on("object:rotating", (opt) => {
      setStatus(`Rotação: ${Math.round(opt.target.angle)}°`);
    });
    canvas.on("object:scaling", (opt) => {
      const obj = opt.target;
      setStatus(`Fonte: ${round2(obj.fontSize * (obj.scaleX || 1))} pt`);
    });

    if (!readOnly) {
      canvas.on("object:modified", (opt) => {
        const target = opt.target;
        if (!target) return;
        const objs = target instanceof fabric.ActiveSelection ? target.getObjects() : [target];
        objs.forEach((obj) => { if (obj.vetFieldId) commitObject(obj); });
        pushHistory();
        syncPanel();
      });

      // multi-seleção: só mover (escala/rotação de grupo não é persistível com fidelidade)
      canvas.on("selection:created", handleSelection);
      canvas.on("selection:updated", handleSelection);
      canvas.on("selection:cleared", () => syncPanel());
    }

    function handleSelection() {
      const active = canvas.getActiveObject();
      if (active && active instanceof fabric.ActiveSelection) {
        active.setControlsVisibility({
          tl: false, tr: false, bl: false, br: false,
          ml: false, mr: false, mt: false, mb: false, mtr: false,
        });
      }
      syncPanel();
    }

    // ----- amostra de Excel -----
    const sampleLabel = document.getElementById("sample-row-label");
    const sampleControls = document.getElementById("sample-controls");

    const refreshTexts = () => {
      fields.forEach((field) => {
        const obj = objectsById.get(field.id);
        if (obj && !obj.isEditing) obj.set("text", textFor(field));
      });
      canvas.requestRenderAll();
    };

    const updateSampleUi = () => {
      if (sampleControls) sampleControls.classList.toggle("is-active", sample.active);
      if (wrap) wrap.classList.toggle("is-sample", sample.active);
      if (sampleLabel) {
        sampleLabel.textContent = sample.active
          ? `linha ${sample.rows[sample.index].row_number} (${sample.index + 1}/${sample.rows.length}${sample.total > sample.rows.length ? ` de ${sample.total}` : ""})`
          : "";
      }
    };

    const setSampleIndex = (index) => {
      if (!sample.active) return;
      sample.index = ((index % sample.rows.length) + sample.rows.length) % sample.rows.length;
      refreshTexts();
      updateSampleUi();
    };

    const exitSample = () => {
      sample.active = false;
      sample.rows = [];
      refreshTexts();
      updateSampleUi();
      setStatus("Amostra desativada; mostrando textos base.");
    };

    const sampleInput = document.getElementById("sample-file-input");
    if (sampleInput) {
      sampleInput.addEventListener("change", async () => {
        const [file] = sampleInput.files || [];
        if (!file) return;
        const data = new FormData();
        data.append("excel", file);
        setStatus("Lendo o Excel de amostra…");
        try {
          const result = await request(config.urls.sample, "POST", data, true);
          sample.rows = result.rows;
          sample.total = result.total;
          sample.index = 0;
          sample.active = true;
          canvas.discardActiveObject();
          refreshTexts();
          updateSampleUi();
          setStatus(`Amostra carregada: ${result.total} linha(s).`);
        } catch (err) {
          setStatus(err.message);
        } finally {
          sampleInput.value = "";
        }
      });
    }
    document.getElementById("sample-prev")?.addEventListener("click", () => setSampleIndex(sample.index - 1));
    document.getElementById("sample-next")?.addEventListener("click", () => setSampleIndex(sample.index + 1));
    document.getElementById("sample-exit")?.addEventListener("click", exitSample);

    // ----- painel lateral -----
    const formEl = document.getElementById("field-form");
    const panelInputs = {};
    const PANEL_KEYS = [
      "name", "excel_column", "font_id", "color", "font_size", "rotation", "width",
      "text_align", "text_transform", "value_type", "line_height", "max_lines",
      "overflow_mode", "empty_value", "transform_exceptions", "border_enabled",
      "border_color", "border_size_ratio", "border_opacity", "border_blur",
    ];
    PANEL_KEYS.forEach((key) => {
      panelInputs[key] = document.getElementById(`field-${key.replaceAll("_", "-")}`);
    });
    const colorPicker = document.getElementById("field-color-picker");
    const borderColorPicker = document.getElementById("field-border-color-picker");
    const rangeInputs = {
      border_size_ratio: document.getElementById("field-border-size-ratio-range"),
      border_opacity: document.getElementById("field-border-opacity-range"),
      border_blur: document.getElementById("field-border-blur-range"),
    };
    const GEOMETRY_KEYS = new Set(["font_size", "rotation", "width"]);

    const selectedFields = () =>
      canvas.getActiveObjects().map((obj) => fieldsById.get(obj.vetFieldId)).filter(Boolean);

    const panelEl = document.getElementById("field-panel");
    const panelNameEl = document.getElementById("field-panel-name");

    function syncPanel() {
      if (readOnly || !formEl) return;
      const selected = selectedFields();
      const field = selected[0];
      if (panelEl) panelEl.classList.toggle("is-empty", !field);
      if (panelNameEl) {
        panelNameEl.textContent = !field
          ? ""
          : selected.length > 1
            ? `— ${selected.length} selecionados`
            : `— ${field.name}`;
      }
      if (!field) {
        formEl.reset();
        setStatus("Crie ou selecione um campo.");
        return;
      }
      PANEL_KEYS.forEach((key) => {
        const input = panelInputs[key];
        if (!input) return;
        if (input.type === "checkbox") input.checked = Boolean(field[key]);
        else input.value = field[key] ?? "";
      });
      if (colorPicker) colorPicker.value = field.color || "#000000";
      if (borderColorPicker) borderColorPicker.value = field.border_color || "#000000";
      Object.entries(rangeInputs).forEach(([key, input]) => {
        if (input) input.value = field[key] ?? input.min ?? 0;
      });
      setStatus(selected.length > 1 ? `${selected.length} campos selecionados` : `${field.name} selecionado`);
    }

    const applyPanelChange = (key, rawValue) => {
      const selected = selectedFields();
      if (!selected.length) return;
      selected.forEach((field) => {
        let value = rawValue;
        if (typeof value === "string" && ["font_size", "rotation", "width", "line_height", "border_size_ratio", "border_opacity", "border_blur"].includes(key)) {
          value = Number(String(value).replace(",", "."));
          if (!Number.isFinite(value)) return;
        }
        if (key === "font_id") value = Number(value);
        field[key] = value;
        const obj = objectsById.get(field.id);
        if (obj) applyFieldToObject(obj, field);
        const payload = {};
        payload[key] = value;
        if (GEOMETRY_KEYS.has(key)) {
          payload.x = field.x; payload.y = field.y;
          payload.width = field.width; payload.height = field.height;
        }
        queueSave(field.id, payload);
      });
      canvas.requestRenderAll();
      pushHistoryDebounced();
    };

    const pushHistoryDebounced = debounce(pushHistory, 700);

    if (formEl && !readOnly) {
      formEl.addEventListener("input", (event) => {
        const target = event.target;
        if (target === colorPicker) {
          panelInputs.color.value = colorPicker.value;
          applyPanelChange("color", colorPicker.value);
          return;
        }
        if (target === borderColorPicker) {
          panelInputs.border_color.value = borderColorPicker.value;
          applyPanelChange("border_color", borderColorPicker.value);
          return;
        }
        const rangeEntry = Object.entries(rangeInputs).find(([, input]) => input === target);
        if (rangeEntry) {
          const [key] = rangeEntry;
          if (panelInputs[key]) panelInputs[key].value = target.value;
          applyPanelChange(key, target.value);
          return;
        }
        if (!target.name) return;
        if (rangeInputs[target.name]) rangeInputs[target.name].value = String(target.value).replace(",", ".");
        applyPanelChange(target.name, target.type === "checkbox" ? target.checked : target.value);
      });
    }

    // ----- criação / duplicação / exclusão -----
    const fullPayload = (field) => ({
      name: field.name,
      excel_column: field.excel_column,
      value_type: field.value_type,
      font_id: field.font_id,
      font_size: field.font_size,
      text_align: field.text_align,
      text_transform: field.text_transform,
      transform_exceptions: field.transform_exceptions,
      color: field.color,
      border_enabled: field.border_enabled,
      border_color: field.border_color,
      border_size_ratio: field.border_size_ratio,
      border_opacity: field.border_opacity,
      border_blur: field.border_blur,
      line_height: field.line_height,
      max_lines: field.max_lines,
      empty_value: field.empty_value,
      overflow_mode: field.overflow_mode,
    });

    const registerField = (fieldData, select) => {
      fields.push(fieldData);
      fieldsById.set(fieldData.id, fieldData);
      const obj = createObject(fieldData);
      if (select) {
        canvas.setActiveObject(obj);
        canvas.requestRenderAll();
        syncPanel();
      }
      resetHistory();
      return obj;
    };

    document.getElementById("new-field-button")?.addEventListener("click", async () => {
      try {
        const fontId = (config.fonts[0] || {}).id;
        const result = await request(config.urls.fields, "POST", {
          name: `Campo ${fields.length + 1}`,
          font_id: Number(panelInputs.font_id?.value || fontId),
        });
        registerField(result.field, true);
        setStatus(`${result.field.name} criado.`);
      } catch (err) {
        setStatus(`Não foi possível criar o campo: ${err.message}`);
      }
    });

    const duplicateSelected = async () => {
      const selected = selectedFields();
      if (!selected.length) { setStatus("Selecione um campo para duplicar."); return; }
      for (const field of selected) {
        try {
          const created = await request(config.urls.fields, "POST", {
            ...fullPayload(field),
            name: `${field.name} cópia`,
          });
          const patched = await request(fieldUrl(created.field.id), "PATCH", {
            x: round2(field.x + 14),
            y: round2(field.y + 14),
            width: field.width,
            height: field.height,
            rotation: field.rotation,
            max_lines: field.max_lines,
          });
          registerField(patched.field, selected.length === 1);
        } catch (err) {
          setStatus(`Falha ao duplicar: ${err.message}`);
          return;
        }
      }
      setStatus("Campo(s) duplicado(s).");
    };
    document.getElementById("duplicate-field-button")?.addEventListener("click", duplicateSelected);

    const deleteSelected = async () => {
      const selected = selectedFields();
      if (!selected.length) { setStatus("Selecione um campo para excluir."); return; }
      if (!window.confirm(`Excluir ${selected.length} campo(s)? Essa ação não pode ser desfeita.`)) return;
      for (const field of selected) {
        try {
          await fetch(fieldUrl(field.id), { method: "DELETE", headers: { "X-CSRFToken": csrfToken } });
        } catch (err) {
          setStatus(`Falha ao excluir: ${err.message}`);
          return;
        }
        pendingSaves.delete(field.id);
        const obj = objectsById.get(field.id);
        if (obj) canvas.remove(obj);
        objectsById.delete(field.id);
        fieldsById.delete(field.id);
        const index = fields.findIndex((item) => item.id === field.id);
        if (index >= 0) fields.splice(index, 1);
      }
      canvas.discardActiveObject();
      canvas.requestRenderAll();
      resetHistory();
      syncPanel();
      setStatus("Campo(s) excluído(s).");
    };
    document.getElementById("delete-field-button")?.addEventListener("click", deleteSelected);

    // ----- centralizar na página -----
    const centerSelected = (axis) => {
      const objs = canvas.getActiveObjects().filter((obj) => obj.vetFieldId);
      if (!objs.length) { setStatus("Selecione um campo para centralizar."); return; }
      objs.forEach((obj) => {
        obj.setCoords();
        const rect = obj.getBoundingRect();
        if (axis === "h") obj.set("left", obj.left + (page.width / 2 - (rect.left + rect.width / 2)));
        else obj.set("top", obj.top + (page.height / 2 - (rect.top + rect.height / 2)));
        obj.setCoords();
        commitObject(obj);
      });
      canvas.requestRenderAll();
      pushHistory();
      syncPanel();
    };
    document.getElementById("align-center-h")?.addEventListener("click", () => centerSelected("h"));
    document.getElementById("align-center-v")?.addEventListener("click", () => centerSelected("v"));

    // ----- toolbar restante -----
    document.getElementById("zoom-in-button")?.addEventListener("click", () => zoomBy(1.2));
    document.getElementById("zoom-out-button")?.addEventListener("click", () => zoomBy(1 / 1.2));
    document.getElementById("zoom-fit-button")?.addEventListener("click", fitToScreen);
    document.getElementById("undo-button")?.addEventListener("click", undo);
    document.getElementById("redo-button")?.addEventListener("click", redo);
    document.getElementById("save-layout-button")?.addEventListener("click", saveAll);

    // ----- teclado -----
    if (!readOnly) {
      document.addEventListener("keydown", (event) => {
        const tag = (event.target.tagName || "").toLowerCase();
        if (["input", "textarea", "select"].includes(tag)) return;
        const active = canvas.getActiveObject();
        if (active && active.isEditing) return;

        if (event.code === "Space") {
          spacePressed = true;
          canvas.setCursor("grab");
          event.preventDefault();
          return;
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
          event.preventDefault();
          event.shiftKey ? redo() : undo();
          return;
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
          event.preventDefault();
          redo();
          return;
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
          event.preventDefault();
          saveAll();
          return;
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d") {
          event.preventDefault();
          duplicateSelected();
          return;
        }
        if (event.key === "Delete") {
          event.preventDefault();
          deleteSelected();
          return;
        }
        if (event.key === "Escape") {
          canvas.discardActiveObject();
          canvas.requestRenderAll();
          syncPanel();
          return;
        }
        const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
        if (arrows[event.key]) {
          const objs = canvas.getActiveObjects();
          if (!objs.length) return;
          event.preventDefault();
          const step = event.shiftKey ? 10 : 1;
          const [dx, dy] = arrows[event.key];
          objs.forEach((obj) => {
            if (!obj.vetFieldId) return;
            obj.set({ left: obj.left + dx * step, top: obj.top + dy * step });
            obj.setCoords();
            commitObject(obj);
          });
          canvas.requestRenderAll();
          pushHistoryDebounced();
          syncPanel();
        }
      });
      document.addEventListener("keyup", (event) => {
        if (event.code === "Space") {
          spacePressed = false;
          canvas.setCursor("default");
        }
      });
    }

    // ----- inicialização final -----
    window.addEventListener("resize", debounce(fitToScreen, 150));
    fitToScreen();
    window.__vetorialEditor = { canvas, fields, sample };
    if (!readOnly) {
      setStatus(fields.length ? "Selecione um campo para editar." : "Crie o primeiro campo com “Novo campo”.");
      setSaveState("Salvo ✓", "ok");
      syncPanel();
    }
  }

  window.VetorialTemplateEditor = { init };
})();
