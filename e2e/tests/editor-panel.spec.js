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

async function openBancadaAndSelectField(page) {
  await login(page);
  await page.goto("/templates/");
  await page.getByRole("link", { name: /Certificado E2E/i }).first().click();
  await expect(page.locator("#generate-card")).toBeVisible();

  // O canvas Fabric.js só fica clicável depois do init(); sem esperar o
  // texto de status mudar, o clique early pode cair antes dos campos
  // existirem no canvas.
  await expect(page.locator("#editor-status-text")).not.toHaveText(/Carregando/);
  const canvas = page.locator("#editor-canvas");
  const box = await canvas.boundingBox();
  await page.mouse.click(box.x + box.width * 0.35, box.y + box.height * 0.42);
  await expect(page.locator("#field-panel-name")).toContainText("Nome");
}

test.describe("Painel do campo: organização e estados", () => {
  test("o canvas continua visível com as duas seções avançadas abertas", async ({ page }) => {
    await openBancadaAndSelectField(page);

    await page.locator("#field-panel .field-advanced summary").first().click();
    await page.locator("#field-outline-details summary").click();

    // O bug original: abrir as seções empurrava a página até o canvas sumir.
    // O painel agora rola por conta própria (max-height + overflow-y no
    // sticky #editor-side), então o canvas fica sempre à vista.
    await expect(page.locator("#editor-canvas")).toBeInViewport();
    await expect(page.locator("#generate-card")).toBeInViewport();
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
    const canvas = page.locator("#editor-canvas");
    const box = await canvas.boundingBox();
    await page.mouse.click(box.x + box.width * 0.35, box.y + box.height * 0.56);
    await expect(page.locator("#field-panel-name")).toContainText("Curso");

    await expect(page.locator("#field-border-opacity")).toBeDisabled();
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
