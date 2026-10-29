/* Página de estouros: mostra só os campos do modo de tamanho escolhido,
   desenha a prévia da folha com o estouro e acompanha o processamento. */
(() => {
  const form = document.querySelector("[data-estouro-form]");
  if (form) iniciarFormulario(form);
  const lote = document.querySelector("[data-lote]");
  if (lote?.dataset.emAndamento === "1") acompanhar(lote);
  posicionarLinhasDeCorte();

  // Linha de corte sobre cada prévia, em frações da folha (vêm do PDF).
  function posicionarLinhasDeCorte() {
    document.querySelectorAll("[data-corte]").forEach((linha) => {
      const [c0, c1, c2, c3] = linha.dataset.corte.split(" ").map(Number);
      if ([c0, c1, c2, c3].some((v) => !Number.isFinite(v))) return;
      linha.style.left = `${c0 * 100}%`;
      linha.style.top = `${c1 * 100}%`;
      linha.style.right = `${(1 - c2) * 100}%`;
      linha.style.bottom = `${(1 - c3) * 100}%`;
      linha.hidden = false;
    });
  }

  function valor(nome) {
    const campo = form.elements[nome];
    if (!campo) return 0;
    const numero = Number.parseFloat(String(campo.value || "0").replace(",", "."));
    return Number.isFinite(numero) && numero > 0 ? numero : 0;
  }

  function escolhido(nome) {
    const marcado = form.querySelector(`input[name="${nome}"]:checked`);
    return marcado ? marcado.value : "";
  }

  function lados() {
    const modo = escolhido("modo_tamanho");
    if (modo === "eixos") {
      const h = valor("horizontal"), v = valor("vertical");
      return { topo: v, direita: h, base: v, esquerda: h };
    }
    if (modo === "lados") {
      return { topo: valor("topo"), direita: valor("direita"), base: valor("base"), esquerda: valor("esquerda") };
    }
    const t = valor("todos");
    return { topo: t, direita: t, base: t, esquerda: t };
  }

  function formatar(n) {
    return String(Math.round(n * 100) / 100).replace(".", ",");
  }

  function atualizar() {
    const modo = escolhido("modo_tamanho") || "igual";
    form.querySelectorAll(".estouro-medidas").forEach((bloco) => {
      bloco.hidden = bloco.dataset.modo !== modo;
    });
    const unidade = form.elements.unidade.value;
    form.querySelectorAll("[data-rotulo-unidade]").forEach((el) => { el.textContent = unidade; });
    const preenchimento = escolhido("preenchimento");
    const cor = form.querySelector("[data-so-cor]");
    if (cor) cor.hidden = preenchimento !== "cor";
    const hex = form.querySelector("[data-cor-hex]");
    if (hex) hex.textContent = form.elements.cor.value.toUpperCase();

    const l = lados();
    const valores = [l.topo, l.direita, l.base, l.esquerda];
    const texto = form.querySelector("[data-resumo-texto]");
    const nomesPreenchimento = { espelhar: "arte espelhada", esticar: "borda esticada", cor: "cor sólida", branco: "sem preenchimento" };
    let tamanho;
    if (valores.every((v) => v === valores[0])) {
      tamanho = valores[0] ? `${formatar(valores[0])} ${unidade} em todos os lados` : "sem estouro";
    } else {
      tamanho = `topo ${formatar(l.topo)}, direita ${formatar(l.direita)}, base ${formatar(l.base)}, esquerda ${formatar(l.esquerda)} ${unidade}`;
    }
    texto.textContent = `Estouro de ${tamanho}, ${nomesPreenchimento[preenchimento] || ""}.`;

    // Prévia proporcional: arte de referência 182 × 74 cm (testeira padrão).
    const folha = form.querySelector("[data-folha]");
    const fator = { cm: 1, mm: 0.1, pol: 2.54 }[unidade] || 1;
    const arteL = 182, arteA = 74;
    const totalL = arteL + (l.esquerda + l.direita) * fator;
    const totalA = arteA + (l.topo + l.base) * fator;
    const exagero = 3; // estouro é pequeno perto da arte: exagera para ser visível
    const pct = (v, total) => Math.min(30, (v * fator * exagero / total) * 100);
    folha.style.setProperty("--e-topo", `${pct(l.topo, totalA)}%`);
    folha.style.setProperty("--e-base", `${pct(l.base, totalA)}%`);
    folha.style.setProperty("--e-esq", `${pct(l.esquerda, totalL)}%`);
    folha.style.setProperty("--e-dir", `${pct(l.direita, totalL)}%`);
    folha.dataset.preenchimento = preenchimento;
    folha.style.setProperty("--e-cor", form.elements.cor.value);
  }

  function listarArquivos(input) {
    const lista = form.querySelector("[data-lista-envio]");
    lista.replaceChildren();
    [...input.files].forEach((arquivo) => {
      const item = document.createElement("li");
      const mb = (arquivo.size / 1024 / 1024).toFixed(1).replace(".", ",");
      item.textContent = `${arquivo.name} · ${mb} MB`;
      lista.append(item);
    });
    lista.hidden = input.files.length === 0;
  }

  function iniciarFormulario(alvo) {
    alvo.addEventListener("input", atualizar);
    alvo.addEventListener("change", atualizar);
    alvo.querySelectorAll("[data-atalho]").forEach((botao) => {
      botao.addEventListener("click", () => {
        const cm = Number.parseFloat(botao.dataset.atalho);
        const unidade = alvo.elements.unidade.value;
        const convertido = { cm: cm, mm: cm * 10, pol: cm / 2.54 }[unidade];
        alvo.querySelector('input[name="modo_tamanho"][value="igual"]').checked = true;
        alvo.elements.todos.value = formatar(convertido);
        atualizar();
      });
    });
    const input = alvo.elements.arquivos;
    input.addEventListener("change", () => listarArquivos(input));
    const drop = alvo.querySelector("[data-drop]");
    ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.add("is-sobre");
    }));
    ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("is-sobre")));
    drop.addEventListener("drop", (e) => {
      e.preventDefault();
      if (e.dataTransfer?.files.length) {
        input.files = e.dataTransfer.files;
        listarArquivos(input);
      }
    });
    alvo.addEventListener("submit", () => {
      const botao = alvo.querySelector("[data-enviar]");
      botao.disabled = true;
      botao.textContent = "Enviando…";
    });
    atualizar();
  }

  function acompanhar(secao) {
    const url = secao.dataset.statusUrl;
    const tick = async () => {
      try {
        const resposta = await fetch(url, { headers: { Accept: "application/json" } });
        if (!resposta.ok) return;
        const dados = await resposta.json();
        if (!dados.em_andamento) {
          window.location.reload();
          return;
        }
      } catch {
        // rede instável: tenta de novo no próximo ciclo
      }
      window.setTimeout(() => { void tick(); }, 1500);
    };
    window.setTimeout(() => { void tick(); }, 1200);
  }
})();
