// @ts-check
const { test, expect } = require("@playwright/test");

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

async function clickField(page, { x, y }) {
  const canvas = page.locator("#editor-canvas");
  const box = await canvas.boundingBox();
  await page.mouse.click(box.x + box.width * x, box.y + box.height * y);
}

const NOME_FIELD = { x: 0.35, y: 0.42 };

test.use({ viewport: { width: 1440, height: 900 } });

// O checkbox por trás de cada ícone B/I/U/S fica visually-hidden (só a
// label estilizada aparece); clicar a label é como um mouse de verdade
// ativa o toggle — .check() no input falha porque ele não tem área visível.
const clickToggle = (page, id) => page.locator(`label[for="${id}"]`).click();

const currentField = (page) =>
  page.evaluate(() => window.__vetorialEditor.fields.find((f) => f.name === "Nome"));

// field.font_name é só a foto do carregamento da página — trocar o font_id
// pelo painel não reescreve esse campo. O nome de verdade sai batendo o
// font_id atual contra a lista de fontes exposta em __vetorialEditor.fonts.
const currentFontName = (page) =>
  page.evaluate(() => {
    const field = window.__vetorialEditor.fields.find((f) => f.name === "Nome");
    const font = window.__vetorialEditor.fonts.find((f) => f.id === field.font_id);
    return font ? font.name : null;
  });

const canvasObjectFor = (page, fieldId) =>
  page.evaluate(
    (id) => window.__vetorialEditor.canvas.getObjects().find((o) => o.vetFieldId === id),
    fieldId
  );

test.describe("Painel de fonte: cada variação vem do arquivo", () => {
  test("não oferece negrito ou itálico sintético", async ({ page }) => {
    await openBancada(page);
    await clickField(page, NOME_FIELD);
    await expect(page.locator("#field-panel-name")).toContainText("Nome");

    await expect(page.locator("#field-font-id")).toBeVisible();
    await expect(page.locator("#field-font-weight")).toHaveCount(0);
    await expect(page.locator("#field-style-italic")).toHaveCount(0);
  });

  test("Wix oferece todas as cinco variações oficiais", async ({ page }) => {
    await openBancada(page);
    await clickField(page, NOME_FIELD);

    const wixGroup = page.locator('#field-font-id optgroup[label="Wix Madefor Display"]');
    await expect(wixGroup.locator("option")).toHaveText([
      "Regular",
      "Medium",
      "SemiBold",
      "Bold",
      "ExtraBold",
    ]);
  });

  test("selecionar Bold usa o arquivo Bold e persiste", async ({ page }) => {
    await openBancada(page);
    await clickField(page, NOME_FIELD);

    const boldId = await page.evaluate(() => {
      const font = window.__vetorialEditor.fonts.find(
        (item) => item.family === "Wix Madefor Display" && item.variant === "Bold"
      );
      return String(font.id);
    });
    await page.locator("#field-font-id").selectOption(boldId);
    await expect.poll(() => currentFontName(page)).toBe("Wix Madefor Display Bold");
    await expect(page.locator("#editor-save-state")).toHaveText(/Salvo/, { timeout: 10_000 });

    await page.reload();
    await expect(page.locator("#editor-status-text")).not.toHaveText(/Carregando/);
    await clickField(page, NOME_FIELD);
    await expect(page.locator("#field-font-id")).toHaveValue(boldId);
  });
});

test.describe("Sublinhado e tachado no campo", () => {
  test("os ícones aplicam underline/linethrough no canvas e persistem", async ({ page }) => {
    await openBancada(page);
    await clickField(page, NOME_FIELD);

    // Garante ligado→desligado→ligado independente do que outro teste no
    // mesmo banco deixou marcado, em vez de assumir "começa desmarcado".
    if (await page.locator("#field-text-underline").isChecked()) {
      await clickToggle(page, "field-text-underline");
    }
    if (await page.locator("#field-text-strikethrough").isChecked()) {
      await clickToggle(page, "field-text-strikethrough");
    }
    const before = await currentField(page);
    const objBefore = await canvasObjectFor(page, before.id);
    expect(objBefore.underline).toBe(false);
    expect(objBefore.linethrough).toBe(false);

    await clickToggle(page, "field-text-underline");
    await clickToggle(page, "field-text-strikethrough");

    const field = await currentField(page);
    const obj = await canvasObjectFor(page, field.id);
    expect(obj.underline).toBe(true);
    expect(obj.linethrough).toBe(true);
    expect(field.text_underline).toBe(true);
    expect(field.text_strikethrough).toBe(true);

    await expect(page.locator("#editor-save-state")).toHaveText(/Salvo/, { timeout: 10_000 });
  });

  test("os toggles ficam com o fundo de destaque quando ativos", async ({ page }) => {
    await openBancada(page);
    await clickField(page, NOME_FIELD);

    // Testes anteriores no mesmo banco podem já ter deixado este campo
    // sublinhado — o que importa aqui é que a cor de fundo muda junto com o
    // estado do checkbox, não qual dos dois estados é o inicial.
    const checkbox = page.locator("#field-text-underline");
    const underlineLabel = page.locator('label[for="field-text-underline"]');
    const wasChecked = await checkbox.isChecked();
    const before = await underlineLabel.evaluate((el) => getComputedStyle(el).backgroundColor);

    await clickToggle(page, "field-text-underline");

    await expect(checkbox).toBeChecked({ checked: !wasChecked });
    // O fundo do toggle anima (transition no CSS) — espera estabilizar em
    // vez de ler um instantâneo no meio da transição.
    await expect
      .poll(() => underlineLabel.evaluate((el) => getComputedStyle(el).backgroundColor))
      .not.toBe(before);
  });
});
