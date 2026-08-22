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
    // Atribuída de verdade mais abaixo (perto do popover de edição do
    // campo) — declarada já aqui porque after:render, registrado antes
    // disso, precisa poder chamá-la a cada render.
    let updateFieldOverlay = () => {};

    const setStatus = (text) => { if (statusText) statusText.textContent = text; };
    const setSaveState = (text, tone) => {
      if (!saveState) return;
      saveState.textContent = text;
      saveState.dataset.tone = tone || "";
    };

    const snapGuides = [];

    const fontsList = config.fonts || [];
    const fontKeys = await loadFonts(fontsList);
    const fontFamilyFor = (fontId) => fontKeys[fontId] || "sans-serif";

    const canvas = new fabric.Canvas(canvasEl, {
      // o retângulo de seleção fica desligado: arrastar área vazia move a
      // página; múltiplos campos são selecionados com Shift+clique
      selection: false,
      preserveObjectStacking: true,
      uniformScaling: true,
      stopContextMenu: true,
      fireRightClick: false,
      backgroundColor: "transparent",
      defaultCursor: "grab",
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
      const height = Math.max(Math.min(window.innerHeight * 0.82, width * (page.height / page.width) + 48), 420);
      canvas.setDimensions({ width, height });
      resizeRulers();
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

    // pan: arrastar área vazia com o botão esquerdo (ou espaço/botão do meio)
    let spacePressed = false;
    let panState = null;
    // campo sendo arrastado agora mesmo: enquanto não-nulo, after:render
    // desenha as réguas de distância até as bordas da página (ver drawMeasurements)
    let measureTarget = null;
    canvas.on("mouse:down", (opt) => {
      // Guia ganha prioridade sobre o campo por baixo dela — igual ao
      // Photoshop, onde dá pra pegar uma guia mesmo em cima de conteúdo.
      if (rulersActive && !spacePressed && opt.e.button !== 1) {
        const rect = canvasEl.getBoundingClientRect();
        const hit = guideAtScreenPoint(opt.e.clientX - rect.left, opt.e.clientY - rect.top);
        if (hit) {
          canvas.setCursor(hit.axis === "x" ? "col-resize" : "row-resize");
          trackGuideDrag(hit.axis, hit.index);
          return;
        }
      }
      if (spacePressed || opt.e.button === 1 || !opt.target) {
        panState = { x: opt.e.clientX, y: opt.e.clientY };
        canvas.setCursor("grabbing");
        return;
      }
      // Shift+clique adiciona/remove da seleção múltipla
      if (!readOnly && opt.e.shiftKey && opt.target.vetFieldId) {
        const active = canvas.getActiveObject();
        if (active && active !== opt.target) {
          if (active instanceof fabric.ActiveSelection) {
            if (active.getObjects().includes(opt.target)) {
              active.remove(opt.target);
              if (active.getObjects().length === 1) {
                const last = active.getObjects()[0];
                canvas.discardActiveObject();
                canvas.setActiveObject(last);
              }
            } else {
              active.add(opt.target);
            }
            active.setCoords();
          } else {
            canvas.setActiveObject(new fabric.ActiveSelection([active, opt.target], { canvas }));
          }
          canvas.requestRenderAll();
          syncPanel();
        }
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
        canvas.setCursor("grab");
      }
      snapGuides.length = 0;
      measureTarget = null;
      canvas.requestRenderAll();
    });

    // réguas de distância: enquanto um campo é arrastado, mostram — em cm —
    // o vão entre cada borda da caixa e a borda correspondente da página.
    const PT_TO_CM = 2.54 / 72;
    const CM_TO_PT = 72 / 2.54;
    const formatCm = (pt) => `${(pt * PT_TO_CM).toFixed(1)} cm`;

    // Pontos desenhados um a um em vez de ctx.setLineDash: um dash quase
    // zero (pra virar bolinha com lineCap round) renderiza inconsistente
    // entre navegadores — em alguns o segmento sub-pixel vira linha sólida.
    // Um círculo pequeno por vez sempre aparece igual.
    const drawDottedLine = (ctx, x1, y1, x2, y2, spacing, radius) => {
      const length = Math.hypot(x2 - x1, y2 - y1);
      const steps = Math.max(1, Math.round(length / spacing));
      const stepX = (x2 - x1) / steps;
      const stepY = (y2 - y1) / steps;
      for (let i = 0; i <= steps; i += 1) {
        ctx.beginPath();
        ctx.arc(x1 + stepX * i, y1 + stepY * i, radius, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const drawDimension = (ctx, { x1, y1, x2, y2, tickAxis, label, labelX, labelY }) => {
      // linha discreta com pequenos traços perpendiculares nas pontas, no
      // estilo de cota de desenho técnico — só a marcação, sem chamar atenção.
      ctx.fillStyle = "rgba(232, 244, 240, 0.6)";
      drawDottedLine(ctx, x1, y1, x2, y2, 6, 1);

      const tick = 4;
      ctx.strokeStyle = "rgba(232, 244, 240, 0.65)";
      [
        [x1, y1],
        [x2, y2],
      ].forEach(([x, y]) => {
        ctx.beginPath();
        if (tickAxis === "x") {
          ctx.moveTo(x, y - tick);
          ctx.lineTo(x, y + tick);
        } else {
          ctx.moveTo(x - tick, y);
          ctx.lineTo(x + tick, y);
        }
        ctx.stroke();
      });

      ctx.font = "11px 'Segoe UI', system-ui, sans-serif";
      const textWidth = ctx.measureText(label).width;
      const padX = 5;
      const padY = 3;
      ctx.fillStyle = "rgba(15, 26, 24, 0.75)";
      ctx.fillRect(
        labelX - textWidth / 2 - padX,
        labelY - 6 - padY,
        textWidth + padX * 2,
        12 + padY * 2
      );
      ctx.fillStyle = "#eaf4f0";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, labelX, labelY);
    };

    const drawMeasurements = (ctx) => {
      if (!measureTarget || !measureTarget.canvas) return;
      const vpt = canvas.viewportTransform;
      const zoom = canvas.getZoom();
      const rect = measureTarget.getBoundingRect();
      const left = rect.left;
      const top = rect.top;
      const right = rect.left + rect.width;
      const bottom = rect.top + rect.height;
      const midX = left + rect.width / 2;
      const midY = top + rect.height / 2;

      const sx = (worldX) => worldX * zoom + vpt[4];
      const sy = (worldY) => worldY * zoom + vpt[5];

      ctx.save();

      // vão até a esquerda / direita da página, numa linha na altura do
      // meio da caixa
      if (left > 0.5) {
        const y = sy(midY);
        drawDimension(ctx, {
          x1: sx(0), y1: y, x2: sx(left), y2: y,
          tickAxis: "x",
          label: formatCm(left),
          labelX: sx(left / 2), labelY: y,
        });
      }
      if (page.width - right > 0.5) {
        const y = sy(midY);
        drawDimension(ctx, {
          x1: sx(right), y1: y, x2: sx(page.width), y2: y,
          tickAxis: "x",
          label: formatCm(page.width - right),
          labelX: sx(right + (page.width - right) / 2), labelY: y,
        });
      }

      // vão até o topo / base da página, numa linha no meio da caixa
      if (top > 0.5) {
        const x = sx(midX);
        drawDimension(ctx, {
          x1: x, y1: sy(0), x2: x, y2: sy(top),
          tickAxis: "y",
          label: formatCm(top),
          labelX: x, labelY: sy(top / 2),
        });
      }
      if (page.height - bottom > 0.5) {
        const x = sx(midX);
        drawDimension(ctx, {
          x1: x, y1: sy(bottom), x2: x, y2: sy(page.height),
          tickAxis: "y",
          label: formatCm(page.height - bottom),
          labelX: x, labelY: sy(bottom + (page.height - bottom) / 2),
        });
      }

      ctx.restore();
    };

    // ----- réguas ao redor da bancada + guias de alinhamento (como no
    // Photoshop): arrastar a partir da régua cria uma guia; arrastar uma
    // guia de volta pra régua apaga; campos encostam nelas ao arrastar
    // (computeSnapTargets, mais abaixo). Só existe na tela de edição —
    // a pré-visualização somente-leitura não passa rulerHId/rulerVId. -----
    const rulerH = document.getElementById(config.rulerHId || "ruler-h");
    const rulerV = document.getElementById(config.rulerVId || "ruler-v");
    const rulersActive = Boolean(!readOnly && rulerH && rulerV);
    // Região que "segura" uma guia: régua + canvas juntos. Soltar dentro
    // dela (mesmo ainda em cima da régua, sem nunca ter entrado no canvas —
    // o caso de um clique simples) mantém a guia; só sair de tudo isso
    // apaga. Sem isso, um clique parado na régua já nascia e morria no
    // mesmo instante, porque a posição nunca tinha "entrado" no canvas.
    const rulersContainer = rulerH ? rulerH.closest(".editor-rulers") : null;

    // Posições em pontos PDF (o mesmo "mundo" dos campos): x = guias
    // verticais, y = guias horizontais.
    const guideLines = {
      x: Array.isArray(config.guides && config.guides.x) ? config.guides.x.slice() : [],
      y: Array.isArray(config.guides && config.guides.y) ? config.guides.y.slice() : [],
    };

    const saveGuides = debounce(async () => {
      if (!config.urls || !config.urls.guides) return;
      try {
        await request(config.urls.guides, "POST", { guides: guideLines });
      } catch (err) {
        setStatus(`Não foi possível salvar as guias: ${err.message}`);
      }
    }, 500);

    const GUIDE_HIT_TOLERANCE = 5;
    const guideAtScreenPoint = (sx, sy) => {
      const vpt = canvas.viewportTransform;
      const zoom = canvas.getZoom();
      const pageTop = vpt[5] - GUIDE_HIT_TOLERANCE;
      const pageBottom = vpt[5] + page.height * zoom + GUIDE_HIT_TOLERANCE;
      const pageLeft = vpt[4] - GUIDE_HIT_TOLERANCE;
      const pageRight = vpt[4] + page.width * zoom + GUIDE_HIT_TOLERANCE;
      for (let i = 0; i < guideLines.x.length; i += 1) {
        const gx = guideLines.x[i] * zoom + vpt[4];
        if (Math.abs(gx - sx) <= GUIDE_HIT_TOLERANCE && sy >= pageTop && sy <= pageBottom) {
          return { axis: "x", index: i };
        }
      }
      for (let i = 0; i < guideLines.y.length; i += 1) {
        const gy = guideLines.y[i] * zoom + vpt[5];
        if (Math.abs(gy - sy) <= GUIDE_HIT_TOLERANCE && sx >= pageLeft && sx <= pageRight) {
          return { axis: "y", index: i };
        }
      }
      return null;
    };

    // Acompanha o arrasto de uma guia (nova ou já existente) até soltar o
    // botão — sempre por listeners no document, nunca pelos eventos do
    // Fabric: o gesto de criar começa fora do canvas (na régua), e mesmo o
    // de mover uma guia existente pode terminar fora dele (arrastar de
    // volta pra régua apaga), e o mouse:up do Fabric não dispara nesse caso.
    const trackGuideDrag = (axis, index) => {
      const rect = canvasEl.getBoundingClientRect();
      const worldFromEvent = (evt) => {
        const vpt = canvas.viewportTransform;
        const zoom = canvas.getZoom();
        return axis === "x"
          ? (evt.clientX - rect.left - vpt[4]) / zoom
          : (evt.clientY - rect.top - vpt[5]) / zoom;
      };
      const onMove = (moveEvt) => {
        const value = worldFromEvent(moveEvt);
        guideLines[axis][index] = value;
        canvas.requestRenderAll();
        setStatus(`Guia ${axis === "x" ? "vertical" : "horizontal"}: ${formatCm(value)}`);
      };
      const onUp = (upEvt) => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        // "Fora dos limites" é sair da régua+canvas inteiros, não só do
        // canvas — soltar parado em cima da régua (um clique sem arrastar)
        // tem que criar a guia ali, não apagar na hora por nunca ter
        // "entrado" no canvas.
        const bounds = (rulersContainer || canvasEl).getBoundingClientRect();
        const px = upEvt.clientX - bounds.left;
        const py = upEvt.clientY - bounds.top;
        const outOfBounds = px < 0 || px > bounds.width || py < 0 || py > bounds.height;
        if (outOfBounds) {
          guideLines[axis].splice(index, 1);
          setStatus("Guia removida.");
        } else {
          guideLines[axis][index] = round2(guideLines[axis][index]);
          setStatus("Guia salva.");
        }
        canvas.setCursor("grab");
        canvas.requestRenderAll();
        saveGuides();
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    };

    // Mousedown numa régua já cria a guia (satisfaz um clique simples) e
    // entra em modo de arrasto na hora (satisfaz arrastar antes de soltar).
    const beginGuideFromRuler = (axis, downEvent) => {
      const rect = canvasEl.getBoundingClientRect();
      const vpt = canvas.viewportTransform;
      const zoom = canvas.getZoom();
      const worldValue = axis === "x"
        ? (downEvent.clientX - rect.left - vpt[4]) / zoom
        : (downEvent.clientY - rect.top - vpt[5]) / zoom;
      guideLines[axis].push(round2(worldValue));
      canvas.requestRenderAll();
      trackGuideDrag(axis, guideLines[axis].length - 1);
    };

    if (rulersActive) {
      // button !== 0 (botão direito, ou o do meio) não cria guia — sem essa
      // checagem, o mousedown do botão direito (que sempre dispara antes do
      // contextmenu) criava uma guia fantasma bem no meio do gesto de
      // apagar uma guia existente.
      rulerH.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        beginGuideFromRuler("x", e);
      });
      rulerV.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        beginGuideFromRuler("y", e);
      });

      // Botão direito em cima de uma guia (na régua ou já no canvas) apaga
      // na hora — sem isso a única forma de remover era arrastar de volta
      // pra régua, o que não é óbvio. O Fabric já suprime o menu do
      // navegador sobre o canvas (stopContextMenu); as réguas não são dele,
      // então cada uma precisa do próprio preventDefault.
      const removeGuide = (axis, index) => {
        guideLines[axis].splice(index, 1);
        canvas.requestRenderAll();
        setStatus("Guia removida.");
        saveGuides();
      };
      // O Fabric envolve o <canvas> original (canvasEl) num canvas "de
      // baixo" só de desenho — quem recebe eventos de verdade é o
      // upperCanvasEl que ele cria por cima. Um listener em canvasEl nunca
      // dispararia pra cliques reais do usuário.
      canvas.upperCanvasEl.addEventListener("contextmenu", (e) => {
        const rect = canvasEl.getBoundingClientRect();
        const hit = guideAtScreenPoint(e.clientX - rect.left, e.clientY - rect.top);
        if (hit) {
          e.preventDefault();
          removeGuide(hit.axis, hit.index);
        }
      });
      rulerH.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        const rect = canvasEl.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const vpt = canvas.viewportTransform;
        const zoom = canvas.getZoom();
        const index = guideLines.x.findIndex(
          (wx) => Math.abs(wx * zoom + vpt[4] - sx) <= GUIDE_HIT_TOLERANCE
        );
        if (index !== -1) removeGuide("x", index);
      });
      rulerV.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        const rect = canvasEl.getBoundingClientRect();
        const sy = e.clientY - rect.top;
        const vpt = canvas.viewportTransform;
        const zoom = canvas.getZoom();
        const index = guideLines.y.findIndex(
          (wy) => Math.abs(wy * zoom + vpt[5] - sy) <= GUIDE_HIT_TOLERANCE
        );
        if (index !== -1) removeGuide("y", index);
      });
    }

    const NICE_RULER_STEPS_CM = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200];
    const chooseRulerStepCm = (zoom) => {
      const targetPx = 62;
      for (const stepCm of NICE_RULER_STEPS_CM) {
        if (stepCm * CM_TO_PT * zoom >= targetPx) return stepCm;
      }
      return NICE_RULER_STEPS_CM[NICE_RULER_STEPS_CM.length - 1];
    };

    const resizeRulers = () => {
      if (!rulersActive) return;
      const dpr = window.devicePixelRatio || 1;
      [rulerH, rulerV].forEach((el) => {
        const w = Math.round(el.clientWidth * dpr);
        const h = Math.round(el.clientHeight * dpr);
        if (el.width !== w) el.width = w;
        if (el.height !== h) el.height = h;
      });
    };

    const drawRuler = (el, axis) => {
      const ctx = el.getContext("2d");
      const dpr = window.devicePixelRatio || 1;
      const widthCss = el.clientWidth;
      const heightCss = el.clientHeight;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, widthCss, heightCss);

      const vpt = canvas.viewportTransform;
      const zoom = canvas.getZoom();
      const stepCm = chooseRulerStepCm(zoom);
      const stepPt = stepCm * CM_TO_PT;
      const minorStepPt = stepPt / 5;

      ctx.strokeStyle = "rgba(232, 244, 240, 0.4)";
      ctx.fillStyle = "rgba(232, 244, 240, 0.8)";
      ctx.font = "9px ui-sans-serif, system-ui, sans-serif";
      ctx.lineWidth = 1;

      if (axis === "h") {
        const worldStart = (0 - vpt[4]) / zoom;
        const worldEnd = (widthCss - vpt[4]) / zoom;
        const first = Math.floor(worldStart / minorStepPt) * minorStepPt;
        ctx.textAlign = "left";
        ctx.textBaseline = "alphabetic";
        for (let wx = first; wx <= worldEnd; wx += minorStepPt) {
          const sx = Math.round(wx * zoom + vpt[4]) + 0.5;
          const nearestMajor = Math.round(wx / stepPt) * stepPt;
          const isMajor = Math.abs(nearestMajor - wx) < minorStepPt / 2;
          const tickLen = isMajor ? 9 : 4;
          ctx.beginPath();
          ctx.moveTo(sx, heightCss);
          ctx.lineTo(sx, heightCss - tickLen);
          ctx.stroke();
          if (isMajor) ctx.fillText(String(Math.round(nearestMajor * PT_TO_CM)), sx + 2, 9);
        }
      } else {
        const worldStart = (0 - vpt[5]) / zoom;
        const worldEnd = (heightCss - vpt[5]) / zoom;
        const first = Math.floor(worldStart / minorStepPt) * minorStepPt;
        for (let wy = first; wy <= worldEnd; wy += minorStepPt) {
          const sy = Math.round(wy * zoom + vpt[5]) + 0.5;
          const nearestMajor = Math.round(wy / stepPt) * stepPt;
          const isMajor = Math.abs(nearestMajor - wy) < minorStepPt / 2;
          const tickLen = isMajor ? 9 : 4;
          ctx.beginPath();
          ctx.moveTo(widthCss, sy);
          ctx.lineTo(widthCss - tickLen, sy);
          ctx.stroke();
          if (isMajor) {
            ctx.save();
            ctx.translate(9, sy - 2);
            ctx.rotate(-Math.PI / 2);
            ctx.textAlign = "left";
            ctx.textBaseline = "alphabetic";
            ctx.fillText(String(Math.round(nearestMajor * PT_TO_CM)), 0, 0);
            ctx.restore();
          }
        }
      }
    };

    const drawRulers = () => {
      if (!rulersActive) return;
      drawRuler(rulerH, "h");
      drawRuler(rulerV, "v");
    };

    // moldura da página
    canvas.on("after:render", ({ ctx }) => {
      const vpt = canvas.viewportTransform;
      const zoom = canvas.getZoom();
      ctx.save();
      ctx.strokeStyle = "rgba(232, 244, 240, 0.55)";
      ctx.lineWidth = 1;
      ctx.strokeRect(vpt[4] - 0.5, vpt[5] - 0.5, page.width * zoom + 1, page.height * zoom + 1);

      if (rulersActive && (guideLines.x.length || guideLines.y.length)) {
        ctx.strokeStyle = "rgba(64, 169, 255, 0.85)";
        ctx.lineWidth = 1;
        guideLines.x.forEach((wx) => {
          const sx = Math.round(wx * zoom + vpt[4]) + 0.5;
          ctx.beginPath();
          ctx.moveTo(sx, vpt[5]);
          ctx.lineTo(sx, vpt[5] + page.height * zoom);
          ctx.stroke();
        });
        guideLines.y.forEach((wy) => {
          const sy = Math.round(wy * zoom + vpt[5]) + 0.5;
          ctx.beginPath();
          ctx.moveTo(vpt[4], sy);
          ctx.lineTo(vpt[4] + page.width * zoom, sy);
          ctx.stroke();
        });
      }

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
      drawMeasurements(ctx);
      drawRulers();
      updateFieldOverlay();
    });

    // ----- criação dos objetos -----
    const textFor = (field) =>
      String(field.preview_value || field.empty_value || field.name || "");

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

    // "Quebrar linha" + crescer para cima: o Textbox do Fabric sempre ancora o
    // TOPO (originY: "top") e estica a altura para baixo ao ganhar linhas. Para
    // o oposto, a última linha tem que ficar exatamente onde a única linha de
    // uma caixa de 1 linha ficaria — o mesmo ponto fixo que jobs/services.py
    // usa em baseline_y() — e as linhas extras empurram o topo para cima. Por
    // isso o deslocamento usa font_size/line_height (a mesma conta do PDF),
    // nunca field.height: no servidor a altura salva não entra nessa posição.
    const growOffset = (obj, field) => {
      if (!field || field.overflow_mode !== "wrap" || field.grow_direction !== "up") return 0;
      const numLines = (obj._textLines && obj._textLines.length) || 1;
      const perLine = (Number(field.font_size) || 24) * (Number(field.line_height) || 1.1);
      return (numLines - 1) * perLine;
    };

    const applyGrowDirection = (obj, field) => {
      obj.set("top", Number(field.y) - growOffset(obj, field));
      obj.setCoords();
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
        underline: Boolean(field.text_underline),
        linethrough: Boolean(field.text_strikethrough),
        ...strokeProps(field),
      });
      obj.set("text", textFor(field));
      applyGrowDirection(obj, field);
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
        obj.on("changed", () => {
          // Enquanto o usuário digita, cresce para cima em tempo real (o
          // commit em "editing:exited" já sabe reverter isso para field.y).
          applyGrowDirection(obj, fieldsById.get(field.id));
          canvas.requestRenderAll();
        });
        obj.on("editing:exited", () => {
          const current = fieldsById.get(field.id);
          if (!current) return;
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
      // O "top" visível já vem deslocado por applyGrowDirection quando a
      // caixa cresce para cima; para não acumular esse deslocamento a cada
      // arrasto, field.y guarda a âncora original (soma de volta o quanto
      // applyGrowDirection subtraiu).
      field.y = round2(geo.top + growOffset(obj, field));
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
            if (obj && !obj.isEditing) {
              obj.set("text", textFor(field));
              // O servidor pode mudar o texto (transformação, valor padrão
              // etc.) sem que nenhum outro campo do painel tenha disparado
              // applyFieldToObject — sem isto, "crescer para cima" ficaria
              // parado na posição de antes da resposta chegar.
              applyGrowDirection(obj, field);
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
      const xs = [0, page.width / 2, page.width, ...guideLines.x];
      const ys = [0, page.height / 2, page.height, ...guideLines.y];
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
      measureTarget = obj;
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
        // "drag" é um simples arrasto (top já reflete a posição solta pelo
        // usuário); qualquer outra ação (resizing/scale/rotate) pode ter
        // mudado a largura e, com ela, o número de linhas do texto.
        const isPlainMove = opt.transform && opt.transform.action === "drag";
        objs.forEach((obj) => {
          if (!obj.vetFieldId) return;
          if (!isPlainMove) {
            // Redimensionar a largura pode ter feito o texto quebrar em mais
            // (ou menos) linhas durante o arrasto, sem que "top" acompanhasse o
            // crescimento para cima (só applyFieldToObject faz isso). Reencaixa
            // antes de ler a geometria para o commit não gravar uma âncora
            // errada. Não roda num arrasto puro: ali "field.y" ainda é a
            // posição ANTERIOR ao movimento, e reaplicar o offset devolveria
            // o campo pro lugar de onde ele acabou de ser arrastado.
            applyGrowDirection(obj, fieldsById.get(obj.vetFieldId));
          }
          commitObject(obj);
        });
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

    // ----- painel lateral -----
    const formEl = document.getElementById("field-form");
    const panelInputs = {};
    const PANEL_KEYS = [
      "name", "excel_column", "font_id", "color", "font_size", "rotation", "width",
      "text_align", "text_transform", "value_type", "line_height", "max_lines",
      "overflow_mode", "grow_direction", "empty_value", "transform_exceptions",
      "text_underline", "text_strikethrough",
      "border_enabled", "border_color", "border_size_ratio", "border_opacity", "border_blur",
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

    // Cor/espessura/opacidade/blur do contorno não fazem nada com o contorno
    // desligado. O CSS já esconde isso visualmente (:has() em style.css); os
    // inputs ficam de fato desabilitados aqui — teclado e leitor de tela
    // precisam do estado real, não só de uma aparência apagada.
    const outlineDependentInputs = Array.from(
      document.querySelectorAll(".field-outline-dependent input, .field-outline-dependent select")
    );
    const syncOutlineDependentInputs = () => {
      const enabled = Boolean(panelInputs.border_enabled?.checked);
      outlineDependentInputs.forEach((input) => {
        input.disabled = !enabled;
      });
    };
    panelInputs.border_enabled?.addEventListener("change", syncOutlineDependentInputs);

    // "Máx. linhas" só existe para os modos que de fato limitam a altura
    // (Reduzir fonte, Cortar); em "Quebrar linha" o texto cresce até caber
    // tudo, e o número deixaria de significar algo. "Direção de crescimento"
    // é o oposto: só faz sentido quando há mais de uma linha possível.
    const maxLinesGroup = document.getElementById("field-max-lines-group");
    const growDirectionGroup = document.getElementById("field-grow-direction-group");
    const syncOverflowDependentInputs = () => {
      const isWrap = panelInputs.overflow_mode?.value === "wrap";
      if (maxLinesGroup) maxLinesGroup.hidden = isWrap;
      if (panelInputs.max_lines) panelInputs.max_lines.disabled = isWrap;
      if (growDirectionGroup) growDirectionGroup.hidden = !isWrap;
      if (panelInputs.grow_direction) panelInputs.grow_direction.disabled = !isWrap;
    };
    panelInputs.overflow_mode?.addEventListener("change", syncOverflowDependentInputs);

    const selectedFields = () =>
      canvas.getActiveObjects().map((obj) => fieldsById.get(obj.vetFieldId)).filter(Boolean);

    const panelEl = document.getElementById("field-panel");
    const panelNameEl = document.getElementById("field-panel-name");

    // ----- popover de edição do campo: em vez de uma coluna fixa ao lado,
    // abre flutuando perto do campo selecionado (botão ✎ no canto dele) —
    // o canvas fica livre pra usar a largura inteira da bancada. -----
    const editButton = document.getElementById("field-edit-button");
    const popoverCloseButton = document.getElementById("field-popover-close");
    let popoverOpenFieldId = null;

    // Abrir/fechar anima (opacidade + leve escala) via a classe .is-open;
    // o hidden real só chega depois da transição terminar, senão o popover
    // sumiria (display:none) na hora e a animação de saída nunca apareceria.
    const POPOVER_TRANSITION_MS = 160;
    const closePopover = () => {
      if (!panelEl || panelEl.hidden) {
        popoverOpenFieldId = null;
        return;
      }
      panelEl.classList.remove("is-open");
      popoverOpenFieldId = null;
      window.setTimeout(() => {
        if (!panelEl.classList.contains("is-open")) panelEl.hidden = true;
      }, POPOVER_TRANSITION_MS);
    };

    // Caixa do campo em coordenadas de tela, relativas ao wrap (onde o botão
    // e o popover são posicionados) — mesmo padrão de conversão mundo→tela
    // usado em drawMeasurements (rect do Fabric + vpt/zoom).
    const screenBoxFor = (obj) => {
      const rect = obj.getBoundingRect();
      const vpt = canvas.viewportTransform;
      const zoom = canvas.getZoom();
      // getBoundingClientRect() (não offsetLeft/Top): o Fabric envolve o
      // <canvas> original num wrapper próprio com dois canvases internos,
      // então o offsetParent real não é necessariamente o wrap.
      const canvasRect = canvasEl.getBoundingClientRect();
      const wrapRect = wrap.getBoundingClientRect();
      const canvasOffsetX = canvasRect.left - wrapRect.left;
      const canvasOffsetY = canvasRect.top - wrapRect.top;
      return {
        left: canvasOffsetX + rect.left * zoom + vpt[4],
        top: canvasOffsetY + rect.top * zoom + vpt[5],
        right: canvasOffsetX + (rect.left + rect.width) * zoom + vpt[4],
        bottom: canvasOffsetY + (rect.top + rect.height) * zoom + vpt[5],
      };
    };

    // Tenta várias posições ao redor do campo (direita, abaixo, esquerda,
    // acima) e escolhe a primeira que não sobrepõe o próprio campo depois de
    // encaixada nos limites do wrap — um campo largo (comum em certificado)
    // deixava pouca sobra dos dois lados, e o popover "flip" antigo (só
    // direita/esquerda) acabava clampado em cima do texto do campo.
    const positionPopover = (box) => {
      if (!panelEl) return;
      const wrapW = wrap.clientWidth;
      const wrapH = wrap.clientHeight;
      const margin = 10;
      const popW = panelEl.offsetWidth || 300;
      const popH = panelEl.offsetHeight || 400;
      const maxLeft = Math.max(margin, wrapW - popW - margin);
      const maxTop = Math.max(margin, wrapH - popH - margin);

      const candidates = [
        { left: box.right + margin, top: box.top }, // direita do campo
        { left: box.left, top: box.bottom + margin }, // abaixo do campo
        { left: box.left - popW - margin, top: box.top }, // esquerda do campo
        { left: box.left, top: box.top - popH - margin }, // acima do campo
      ].map((c) => ({
        left: clamp(c.left, margin, maxLeft),
        top: clamp(c.top, margin, maxTop),
      }));

      const overlapArea = (c) => {
        const ox = Math.min(c.left + popW, box.right) - Math.max(c.left, box.left);
        const oy = Math.min(c.top + popH, box.bottom) - Math.max(c.top, box.top);
        return Math.max(0, ox) * Math.max(0, oy);
      };

      let best = candidates[0];
      let bestOverlap = overlapArea(best);
      for (const c of candidates) {
        const overlap = overlapArea(c);
        if (overlap < bestOverlap) {
          best = c;
          bestOverlap = overlap;
        }
        if (overlap === 0) break;
      }

      panelEl.style.left = `${best.left}px`;
      panelEl.style.top = `${best.top}px`;
    };

    const openPopoverFor = (obj) => {
      if (!panelEl) return;
      popoverOpenFieldId = obj.vetFieldId;
      panelEl.hidden = false;
      positionPopover(screenBoxFor(obj));
      // Próximo frame: garante que o navegador registre o estado fechado
      // (opacity 0, ver CSS) antes de ligar is-open — sem isso as duas
      // mudanças caem no mesmo frame e a transição não roda.
      requestAnimationFrame(() => panelEl.classList.add("is-open"));
    };

    // Chamado a cada after:render: mostra/reposiciona o botão ✎ sobre o
    // campo único selecionado (some com seleção múltipla ou vazia) e, se o
    // popover já estiver aberto para ele, acompanha a posição — inclusive
    // durante um arrasto, zoom ou pan.
    updateFieldOverlay = () => {
      if (readOnly || !editButton) return;
      const activeObjects = canvas.getActiveObjects();
      const single = activeObjects.length === 1 && activeObjects[0].vetFieldId ? activeObjects[0] : null;
      if (!single) {
        editButton.hidden = true;
        if (popoverOpenFieldId) closePopover();
        return;
      }
      const box = screenBoxFor(single);
      const btnSize = 26;
      const wrapW = wrap.clientWidth;
      const wrapH = wrap.clientHeight;
      editButton.style.left = `${clamp(box.right - btnSize / 2, 2, Math.max(2, wrapW - btnSize - 2))}px`;
      editButton.style.top = `${clamp(box.top - btnSize / 2, 2, Math.max(2, wrapH - btnSize - 2))}px`;
      editButton.hidden = false;

      if (popoverOpenFieldId && popoverOpenFieldId !== single.vetFieldId) {
        closePopover();
      } else if (popoverOpenFieldId === single.vetFieldId) {
        positionPopover(box);
      }
    };

    editButton?.addEventListener("click", (e) => {
      e.stopPropagation();
      const activeObjects = canvas.getActiveObjects();
      const single = activeObjects.length === 1 ? activeObjects[0] : null;
      if (!single) return;
      if (popoverOpenFieldId === single.vetFieldId) closePopover();
      else openPopoverFor(single);
    });
    popoverCloseButton?.addEventListener("click", () => closePopover());

    // ----- Transformação por coluna (só quando o campo junta 2+ colunas) -----
    const transformColumnsGroup = document.getElementById("field-transform-columns-group");
    const transformColumnsContainer = document.getElementById("field-transform-columns");
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

    const toggleTransformColumn = (columnNumber, checked) => {
      const selected = selectedFields();
      if (!selected.length) return;
      selected.forEach((field) => {
        const columns = new Set(field.transform_columns || []);
        if (checked) columns.add(columnNumber);
        else columns.delete(columnNumber);
        field.transform_columns = Array.from(columns).sort((a, b) => a - b);
        queueSave(field.id, { transform_columns: field.transform_columns });
      });
      pushHistoryDebounced();
    };

    const syncTransformColumnsUI = (field) => {
      if (!transformColumnsGroup || !transformColumnsContainer) return;
      const refs = field ? Array.from(new Set(columnRefsFromPattern(field.excel_column))) : [];
      if (refs.length < 2) {
        transformColumnsGroup.hidden = true;
        transformColumnsContainer.innerHTML = "";
        return;
      }
      transformColumnsGroup.hidden = false;
      const selectedColumns = new Set(field.transform_columns || []);
      transformColumnsContainer.innerHTML = "";
      refs.forEach((columnNumber) => {
        const label = document.createElement("label");
        label.className = "field-transform-column-toggle";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = selectedColumns.has(columnNumber);
        input.addEventListener("change", () => toggleTransformColumn(columnNumber, input.checked));
        label.appendChild(input);
        label.append(`Coluna ${columnNumber}`);
        transformColumnsContainer.appendChild(label);
      });
    };

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
        syncOutlineDependentInputs();
        syncOverflowDependentInputs();
        syncTransformColumnsUI(null);
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
      syncOutlineDependentInputs();
      syncOverflowDependentInputs();
      syncTransformColumnsUI(field);
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
        if (target.name === "excel_column") syncTransformColumnsUI(selectedFields()[0]);
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
      transform_columns: field.transform_columns,
      color: field.color,
      text_underline: field.text_underline,
      text_strikethrough: field.text_strikethrough,
      border_enabled: field.border_enabled,
      border_color: field.border_color,
      border_size_ratio: field.border_size_ratio,
      border_opacity: field.border_opacity,
      border_blur: field.border_blur,
      line_height: field.line_height,
      max_lines: field.max_lines,
      grow_direction: field.grow_direction,
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
    window.__vetorialEditor = { canvas, fields, fonts: fontsList, guides: guideLines };
    if (!readOnly) {
      setStatus(fields.length ? "Selecione um campo para editar." : "Crie o primeiro campo com “Novo campo”.");
      setSaveState("Salvo ✓", "ok");
      syncPanel();
    }
  }

  window.VetorialTemplateEditor = { init };
})();
