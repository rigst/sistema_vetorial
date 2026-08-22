// @ts-check
const path = require("path");
const { test, expect } = require("@playwright/test");

const TMP = path.join(__dirname, "..", ".tmp");
const EXCEL = path.join(TMP, "dados.xlsx");

const USER = "e2e";
const PASSWORD = "e2e-senha-123";

async function login(page) {
  await page.goto("/login/");
  await page.getByLabel(/usuário/i).fill(USER);
  await page.getByLabel(/senha/i).fill(PASSWORD);
  await page.getByRole("button", { name: /entrar/i }).click();
  await expect(page).not.toHaveURL(/\/login\//);
}

async function openBancada(page) {
  await login(page);
  await page.goto("/templates/");
  await page.getByRole("link", { name: /Certificado E2E/i }).first().click();
  await expect(page.locator("#generate-card")).toBeVisible();
  await expect(page.locator("#editor-status-text")).not.toHaveText(/Carregando/);
}

// Clica no centro do campo pela posição real dele (mundo -> tela via
// viewportTransform/zoom), não por uma porcentagem fixa da caixa do canvas:
// a régua ao redor da bancada (Photoshop-style) reduz a área do canvas, e um
// x/y fixo que "caía" num campo antes passa a cair fora dele ou no vizinho.
async function clickField(page, fieldName) {
  const canvas = page.locator("#editor-canvas");
  // Marcar/mexer em controles do painel lateral (sticky) pode fazer o
  // Playwright rolar a página para trazê-los à vista, o que empurra o
  // canvas para fora do topo da viewport — sem isto, a caixa do canvas
  // fica com y negativo e o clique computado cai fora da tela.
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  const point = await page.evaluate((name) => {
    const ed = window.__vetorialEditor;
    const field = ed.fields.find((f) => f.name === name);
    const vpt = ed.canvas.viewportTransform;
    const zoom = ed.canvas.getZoom();
    return {
      x: (field.x + field.width / 2) * zoom + vpt[4],
      y: (field.y + field.height / 2) * zoom + vpt[5],
    };
  }, fieldName);
  await page.mouse.click(box.x + point.x, box.y + point.y);
  // A edição do campo agora é um popover que só abre pelo botão ✎ do campo
  // selecionado — clicar no campo sozinho não deixa o painel visível.
  await page.locator("#field-edit-button").click();
}

// O card "Nome dos arquivos" só salva quando o valor muda (evita repetir a
// mesma chamada a cada tecla); como os testes de um mesmo arquivo rodam
// contra o mesmo banco (sem reseed entre eles), passar direto pro valor que
// o teste quer verificar pode ser um no-op se um teste anterior já deixou o
// campo exatamente nesse valor. Um valor-sentinela garante uma mudança real
// antes do valor final, então a espera pelo "Salvo" nunca fica presa.
async function setFilenamePattern(page, value) {
  const input = page.locator("#filename-pattern-input");
  const saveState = page.locator("#filename-pattern-save-state");
  await input.fill("__reset__");
  await input.blur();
  await expect(saveState).toHaveText(/Salvo/, { timeout: 10_000 });
  await input.fill(value);
  await input.blur();
  await expect(saveState).toHaveText(/Salvo/, { timeout: 10_000 });
}

// Os dois campos do template "Certificado E2E" (seed.py).
const NOME_FIELD = "Nome";
const CURSO_FIELD = "Curso";

test.use({ viewport: { width: 1440, height: 900 } });

test.describe("Barra de ferramentas: ícones numa linha, sem quadrado", () => {
  test("os botões óbvios viram ícone com aria-label, sem caixa ao redor da barra", async ({
    page,
  }) => {
    await openBancada(page);

    const newButton = page.locator("#new-field-button");
    const duplicateButton = page.locator("#duplicate-field-button");
    const deleteButton = page.locator("#delete-field-button");

    await expect(newButton).toHaveText("+");
    await expect(newButton).toHaveAttribute("aria-label", "Novo campo");
    await expect(duplicateButton).toHaveText("⧉");
    await expect(duplicateButton).toHaveAttribute("aria-label", "Duplicar seleção");
    await expect(deleteButton).toHaveText("🗑");
    await expect(deleteButton).toHaveAttribute("aria-label", "Excluir seleção");

    // O "quadrado em volta" era uma borda nos 4 lados do #editor-toolbar; a
    // barra virou o topo do quadro escuro da bancada (barra + régua + canvas
    // como uma peça só), com só um traço embaixo separando-a da régua —
    // não uma caixa fechada nos 4 lados.
    const toolbarBorders = await page.locator("#editor-toolbar").evaluate((el) => {
      const style = getComputedStyle(el);
      return {
        top: style.borderTopStyle,
        left: style.borderLeftStyle,
        right: style.borderRightStyle,
      };
    });
    expect(toolbarBorders).toEqual({ top: "none", left: "none", right: "none" });
  });
});

test.describe("Card \"Gerar arquivos\" é uma seção separada", () => {
  test("fica fora do painel de edição do campo, com o nome dos arquivos junto", async ({
    page,
  }) => {
    await openBancada(page);

    const isInsideFieldPanel = await page.evaluate(() => {
      const panel = document.querySelector("#field-panel");
      const generateCard = document.querySelector("#generate-card");
      return Boolean(panel && generateCard && panel.contains(generateCard));
    });
    expect(isInsideFieldPanel).toBe(false);

    // O card de gerar arquivos carrega tanto a configuração do nome quanto o
    // envio do Excel — é a mesma seção, só que fora da edição do template.
    await expect(page.locator("#generate-card #filename-pattern-input")).toBeVisible();
    await expect(page.locator("#generate-card #generate-excel-input")).toBeAttached();
  });

  test("avisa que a primeira linha da planilha é o cabeçalho", async ({ page }) => {
    await openBancada(page);
    await expect(page.locator("#generate-card")).toContainText(/primeira linha.*cabeçalho/i);
  });
});

test.describe("Nome dos arquivos: padrão com colunas e espaços", () => {
  test("salva o padrão {N} e explica a sintaxe", async ({ page }) => {
    await openBancada(page);

    await expect(page.locator(".filename-pattern-config")).toContainText("{1}");
    await expect(page.locator(".filename-pattern-config")).toContainText(".pdf");

    await setFilenamePattern(page, "{1}_{2}");
  });

  test("o campo de separador só aparece no modo substituir", async ({ page }) => {
    await openBancada(page);

    const spaceMode = page.locator("#filename-space-mode");
    const replacement = page.locator("#filename-space-replacement");
    await expect(replacement).toBeHidden();

    await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("/nome-arquivo/") && res.request().method() === "POST"
      ),
      spaceMode.selectOption("replace"),
    ]);
    await expect(replacement).toBeVisible();
    await expect(page.locator("#filename-space-save-state")).toHaveText(/Salvo/);

    await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("/nome-arquivo/") && res.request().method() === "POST"
      ),
      spaceMode.selectOption("keep"),
    ]);
    await expect(replacement).toBeHidden();
  });

  test("gera PDFs nomeados pelo padrão, com o espaço tratado como escolhido", async ({
    page,
  }) => {
    await openBancada(page);

    await setFilenamePattern(page, "{1}_{2}");

    const spaceMode = page.locator("#filename-space-mode");
    const replacement = page.locator("#filename-space-replacement");
    await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("/nome-arquivo/") && res.request().method() === "POST"
      ),
      spaceMode.selectOption("replace"),
    ]);
    await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("/nome-arquivo/") && res.request().method() === "POST"
      ),
      replacement.fill("."),
    ]);
    await replacement.blur();

    await page.locator("#generate-excel-input").setInputFiles(EXCEL);
    await page.getByRole("button", { name: /Gerar amostra/i }).click();
    await expect(page.locator("#generate-progress-text")).toHaveText(/arquivos? pronto/, {
      timeout: 30_000,
    });

    // Linha 1: colunas cruas da planilha (o padrão do nome do arquivo não
    // passa pela transformação do campo, só pelo texto da célula) — "ana
    // paula de souza" + "_" + "Design" => "ana.paula.de.souza_Design.pdf"
    // com o separador "." escolhido no lugar dos espaços do texto.
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.locator("#generate-items a").first().click(),
    ]);
    expect(download.suggestedFilename()).toBe("ana.paula.de.souza_Design.pdf");
  });
});

test.describe("Concatenar colunas com conector num só campo", () => {
  // A pré-visualização "Ver com meus dados" foi removida do editor (o card
  // "Gerar arquivos" já mostra o resultado real); a sintaxe {N} de
  // concatenação em si é coberta a fundo no lado servidor
  // (jobs/tests.py::ColumnTemplateTests e
  // editor/tests.py::test_sample_endpoint_resolves_multi_column_concatenation).
  // Aqui só interessa que o painel salve e mantenha o padrão digitado.
  test("{1}-{2} digitado no painel é salvo e sobrevive a um recarregamento", async ({
    page,
  }) => {
    await openBancada(page);
    await clickField(page, CURSO_FIELD);
    await expect(page.locator("#field-panel-name")).toContainText("Curso");

    const excelColumnInput = page.locator("#field-excel-column");
    await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("/campos/") && res.request().method() === "PATCH"
      ),
      excelColumnInput.fill("{1}-{2}"),
    ]);
    await excelColumnInput.blur();
    await expect(page.locator("#editor-save-state")).toHaveText(/Salvo/, { timeout: 10_000 });

    await page.reload();
    await expect(page.locator("#editor-status-text")).not.toHaveText(/Carregando/);
    await clickField(page, CURSO_FIELD);
    await expect(page.locator("#field-excel-column")).toHaveValue("{1}-{2}");
  });
});

test.describe("Quebrar linha: cresce em vez de cortar, e respeita a direção", () => {
  test("modo cima mantém a base fixa enquanto o texto ganha linhas", async ({ page }) => {
    await openBancada(page);
    await clickField(page, NOME_FIELD);
    await expect(page.locator("#field-panel-name")).toContainText("Nome");

    // "Quando o texto não couber" e "Texto base" vivem dentro do <details>
    // avançado "Texto", fechado por padrão.
    await page.locator("#field-panel .field-advanced summary").first().click();

    await page.locator("#field-overflow-mode").selectOption("wrap");
    await expect(page.locator("#field-grow-direction-group")).toBeVisible();
    await expect(page.locator("#field-max-lines-group")).toBeHidden();
    await page.locator("#field-grow-direction").selectOption("up");
    await page.locator("#field-width").fill("120");

    const setTextAndReadGeometry = async (text) => {
      const emptyValueInput = page.locator("#field-empty-value");
      // Diferente de largura/direção (que reaplicam o texto já conhecido na
      // hora), o canvas só troca de texto quando o servidor responde com o
      // novo preview_value — textFor() prioriza esse campo sobre o local.
      await Promise.all([
        page.waitForResponse(
          (res) => res.url().includes("/campos/") && res.request().method() === "PATCH"
        ),
        emptyValueInput.fill(text),
      ]);
      await emptyValueInput.blur();
      await page.waitForFunction(
        (expected) => {
          const field = window.__vetorialEditor.fields.find((f) => f.name === "Nome");
          const obj = window.__vetorialEditor.canvas
            .getObjects()
            .find((o) => o.vetFieldId === field.id);
          return obj.text === expected;
        },
        text
      );
      return page.evaluate(() => {
        const field = window.__vetorialEditor.fields.find((f) => f.name === "Nome");
        const obj = window.__vetorialEditor.canvas
          .getObjects()
          .find((o) => o.vetFieldId === field.id);
        return { top: obj.top, height: obj.height, lines: obj._textLines.length };
      });
    };

    // Uma linha só (texto curto) é a referência: é onde a base da caixa fica
    // quando ela nunca precisou crescer.
    const short = await setTextAndReadGeometry("Ana");
    expect(short.lines).toBe(1);

    const long = await setTextAndReadGeometry("Maria Aparecida do Nascimento Oliveira");
    expect(long.lines).toBeGreaterThan(1);

    // Modo "cima": a base (top + height) não se move quando ganha linhas —
    // só o topo sobe, porque as linhas extras crescem para cima.
    expect(Math.abs(long.top + long.height - (short.top + short.height))).toBeLessThan(3);
    expect(long.top).toBeLessThan(short.top - 5);
  });
});
