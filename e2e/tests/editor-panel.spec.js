// @ts-check
const { test, expect } = require("@playwright/test");

const USER = "e2e";
const PASSWORD = "e2e-senha-123";

test.use({ viewport: { width: 1440, height: 900 } });

async function login(page) {
  await page.goto("/login/");
  await page.getByLabel(/usuário/i).fill(USER);
  await page.getByLabel(/senha/i).fill(PASSWORD);
  await page.getByRole("button", { name: /entrar/i }).click();
  await expect(page).not.toHaveURL(/\/login\//);
}

// Clica no centro do campo pela posição real dele (mundo -> tela via
// viewportTransform/zoom), não por uma porcentagem fixa da caixa do canvas:
// a régua ao redor da bancada (Photoshop-style) reduz a área do canvas, e um
// x/y fixo que "caía" num campo antes passa a cair fora dele ou no vizinho.
async function clickField(page, fieldName) {
  const canvas = page.locator("#editor-canvas");
  // Marcar um checkbox dentro do painel lateral (sticky) faz o Playwright
  // rolar a página para trazê-lo à vista, o que empurra o canvas para fora
  // do topo da viewport — sem isto, a caixa do canvas fica com y negativo e
  // o clique computado cai fora da tela.
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

async function openBancadaAndSelectField(page) {
  await login(page);
  await page.goto("/templates/");
  await page.getByRole("link", { name: /Certificado E2E/i }).first().click();
  await expect(page.locator("#generate-card")).toBeVisible();

  // O canvas Fabric.js só fica clicável depois do init(); sem esperar o
  // texto de status mudar, o clique early pode cair antes dos campos
  // existirem no canvas.
  await expect(page.locator("#editor-status-text")).not.toHaveText(/Carregando/);
  await clickField(page, "Nome");
  await expect(page.locator("#field-panel-name")).toContainText("Nome");
}

test.describe("Painel do campo: organização e estados", () => {
  test("o canvas continua visível com as duas seções avançadas abertas", async ({ page }) => {
    await openBancadaAndSelectField(page);

    await page.locator("#field-panel .field-advanced summary").first().click();
    await page.locator("#field-outline-details summary").click();

    // O bug original: abrir as seções empurrava a página até o canvas sumir.
    // Hoje a edição é um popover flutuante (posição absoluta dentro do
    // canvas, com scroll próprio) em vez de uma coluna no fluxo normal da
    // página — crescer não pode mais empurrar nada ao redor, então o canvas
    // e o próprio popover continuam à vista.
    await expect(page.locator("#editor-canvas")).toBeInViewport();
    await expect(page.locator("#field-panel")).toBeInViewport();
  });

  test("os controles do contorno só ficam ativos com o contorno ligado", async ({ page }) => {
    await openBancadaAndSelectField(page);
    await page.locator("#field-outline-details summary").click();

    const opacity = page.locator("#field-border-opacity");
    const colorHex = page.locator("#field-border-color");

    await expect(opacity).toBeDisabled();
    await expect(colorHex).toBeDisabled();

    await page.locator("#field-border-enabled").check();
    await expect(opacity).toBeEnabled();
    await expect(colorHex).toBeEnabled();

    await page.locator("#field-border-enabled").uncheck();
    await expect(opacity).toBeDisabled();
    await expect(colorHex).toBeDisabled();
  });

  test("mudar de campo atualiza o estado dos controles do contorno", async ({ page }) => {
    await openBancadaAndSelectField(page);
    await page.locator("#field-outline-details summary").click();
    await page.locator("#field-border-enabled").check();
    await expect(page.locator("#field-border-opacity")).toBeEnabled();

    // Seleciona o segundo campo (Curso), que nunca teve o contorno ligado.
    await clickField(page, "Curso");
    await expect(page.locator("#field-panel-name")).toContainText("Curso");

    await expect(page.locator("#field-border-opacity")).toBeDisabled();
  });
});

test.describe("Réguas: guias de alinhamento", () => {
  test("clique na régua cria uma guia; botão direito nela apaga", async ({ page }) => {
    await login(page);
    await page.goto("/templates/");
    await page.getByRole("link", { name: /Certificado E2E/i }).first().click();
    await expect(page.locator("#generate-card")).toBeVisible();
    await expect(page.locator("#editor-status-text")).not.toHaveText(/Carregando/);

    // Clique simples (sem arrastar) na régua vertical cria uma guia
    // horizontal a essa altura.
    const rulerV = page.locator("#ruler-v");
    const rulerBox = await rulerV.boundingBox();
    const targetY = rulerBox.y + 60;
    await page.mouse.click(rulerBox.x + rulerBox.width / 2, targetY);
    await expect
      .poll(() => page.evaluate(() => window.__vetorialEditor.guides.y.length))
      .toBe(1);
    await expect(page.locator("#editor-save-state")).toHaveText(/Salvo/, { timeout: 10_000 });

    // Botão direito bem em cima da guia (na própria régua) apaga na hora.
    await page.mouse.click(rulerBox.x + rulerBox.width / 2, targetY, { button: "right" });
    await expect
      .poll(() => page.evaluate(() => window.__vetorialEditor.guides.y.length))
      .toBe(0);

    // Persiste: recarregar não traz a guia apagada de volta.
    await page.reload();
    await expect(page.locator("#editor-status-text")).not.toHaveText(/Carregando/);
    const guidesAfterReload = await page.evaluate(() => window.__vetorialEditor.guides);
    expect(guidesAfterReload.y).toEqual([]);
  });
});

test.describe("Botões de ícone: ação destrutiva não parece CTA primário", () => {
  test("excluir/editar não herdam o preenchimento sólido do botão principal", async ({ page }) => {
    await login(page);
    await page.goto("/fontes/");

    const primaryBackground = await page
      .locator("a.button", { hasText: "Nova fonte" })
      .evaluate((el) => getComputedStyle(el).backgroundColor);
    const deleteBackground = await page
      .locator("form button.icon-button-danger")
      .first()
      .evaluate((el) => getComputedStyle(el).backgroundColor);
    const editBackground = await page
      .locator("a.icon-button")
      .first()
      .evaluate((el) => getComputedStyle(el).backgroundColor);

    expect(deleteBackground).not.toBe(primaryBackground);
    expect(editBackground).not.toBe(primaryBackground);
  });
});

test.describe("Job: Reprocessar/Inativar não parecem o CTA primário", () => {
  test("botões secundários do job ficam neutros, não preenchidos", async ({ page }) => {
    await login(page);
    await page.goto("/templates/");
    await page.getByRole("link", { name: /Certificado E2E/i }).first().click();
    await expect(page.locator("#generate-card")).toBeVisible();

    await page.locator("#generate-excel-input").setInputFiles(
      require("path").join(__dirname, "..", ".tmp", "dados.xlsx")
    );
    await page.getByRole("button", { name: /Gerar amostra/i }).click();
    await expect(page.locator("#generate-progress-text")).toHaveText(/arquivos? pronto/, {
      timeout: 30_000,
    });

    await page.goto("/jobs/");
    await page.locator('a[title="Abrir"]').first().click();
    // Job de prévia: "Gerar lote completo" é o CTA primário da tela.
    await expect(page.getByRole("button", { name: "Gerar lote completo" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reprocessar" })).toBeVisible();

    const primaryBg = await page
      .getByRole("button", { name: "Gerar lote completo" })
      .evaluate((el) => getComputedStyle(el).backgroundColor);
    const reprocessarBg = await page
      .getByRole("button", { name: "Reprocessar" })
      .evaluate((el) => getComputedStyle(el).backgroundColor);
    const inativarBg = await page
      .getByRole("button", { name: "Inativar" })
      .evaluate((el) => getComputedStyle(el).backgroundColor);

    expect(reprocessarBg).not.toBe(primaryBg);
    expect(inativarBg).not.toBe(primaryBg);
  });
});

test.describe("Lista de fontes: cada linha no seu próprio tipo", () => {
  test("as linhas usam famílias de fonte diferentes entre si", async ({ page }) => {
    await login(page);
    await page.goto("/fontes/");

    const families = await page
      .locator(".font-preview-cell")
      .evaluateAll((cells) => cells.map((cell) => getComputedStyle(cell).fontFamily));

    expect(families.length).toBeGreaterThan(1);
    // Cada linha declara sua própria família (vetorial-font-<id>): duas
    // linhas quaisquer não devem ter a mesma declaração de fonte.
    expect(new Set(families).size).toBe(families.length);
  });
});
