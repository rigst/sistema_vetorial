// @ts-check
const path = require("path");
const { test, expect } = require("@playwright/test");

const TMP = path.join(__dirname, "..", ".tmp");
const EXCEL = path.join(TMP, "dados.xlsx");
const EXCEL_2 = path.join(TMP, "dados_grande.xlsx");
const NOT_EXCEL = path.join(TMP, "dados.csv");

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
}

test.describe("Bancada: gerar arquivos a partir do Excel", () => {
  test("o card começa limpo, sem progresso preso na tela", async ({ page }) => {
    await openBancada(page);

    // A regressão relatada: "Preparando…" aparecia para sempre porque o
    // display:grid do CSS vencia o atributo hidden.
    await expect(page.locator("#generate-progress")).toBeHidden();
    await expect(page.locator("#generate-result")).toBeHidden();
    await expect(page.locator("#generate-error")).toBeHidden();

    // Os botões seguem clicáveis sem planilha; quem explica o que falta é a
    // própria mensagem de erro, não um botão apagado.
    await expect(page.locator("#generate-preview-button")).toBeEnabled();
    await page.getByRole("button", { name: /Gerar amostra/i }).click();
    await expect(page.locator("#generate-error")).toHaveText(/Escolha o Excel/i);
    await expect(page.locator("#generate-progress")).toBeHidden();
  });

  test("a área de envio é alcançável pelo teclado", async ({ page }) => {
    await openBancada(page);

    await page.locator("#generate-excel-input").focus();

    // hidden tiraria o input do foco; visually-hidden mantém o campo acessível.
    const focusedId = await page.evaluate(() => document.activeElement?.id);
    expect(focusedId).toBe("generate-excel-input");
  });

  test("escolher a planilha libera a amostra, mas o lote completo espera ela terminar", async ({ page }) => {
    await openBancada(page);

    await page.locator("#generate-excel-input").setInputFiles(EXCEL);

    await expect(page.locator("#generate-file-name")).toHaveText("dados.xlsx");
    await expect(page.locator("#generate-file-label")).toHaveClass(/has-file/);
    await expect(page.locator("#generate-preview-button")).toBeEnabled();
    // O lote completo é uma etapa obrigatoriamente posterior à amostra: fica
    // desabilitado, com uma dica visível, até uma amostra terminar com sucesso.
    await expect(page.locator("#generate-full-button")).toBeDisabled();
    await expect(page.locator("#generate-full-hint")).toBeVisible();

    await page.getByRole("button", { name: /Gerar amostra/i }).click();
    await expect(page.locator("#generate-progress-text")).toHaveText(
      /3 arquivos prontos/,
      { timeout: 60_000 }
    );

    await expect(page.locator("#generate-full-button")).toBeEnabled();
    await expect(page.locator("#generate-full-hint")).toBeHidden();

    // Trocar de planilha exige nova amostra: a liberação não sobrevive.
    await page.locator("#generate-excel-input").setInputFiles(EXCEL_2);
    await expect(page.locator("#generate-full-button")).toBeDisabled();
    await expect(page.locator("#generate-full-hint")).toBeVisible();
  });

  test("a barra de progresso anuncia o avanço para leitores de tela", async ({ page }) => {
    await openBancada(page);
    await page.locator("#generate-excel-input").setInputFiles(EXCEL);

    await page.getByRole("button", { name: /Gerar amostra/i }).click();

    const bar = page.getByRole("progressbar", { name: /progresso da geração/i });
    await expect(bar).toBeVisible();
    await expect(bar).toHaveAttribute("aria-valuenow", "100", { timeout: 60_000 });
  });

  test("a amostra gera três PDFs e oferece o download de cada linha", async ({ page }) => {
    await openBancada(page);
    await page.locator("#generate-excel-input").setInputFiles(EXCEL);

    await page.getByRole("button", { name: /Gerar amostra/i }).click();

    await expect(page.locator("#generate-progress")).toBeVisible();
    await expect(page.locator("#generate-progress-text")).toHaveText(
      /3 arquivos prontos/,
      { timeout: 60_000 }
    );
    await expect(page.locator("#generate-result")).toBeVisible();
    await expect(page.locator("#generate-items li")).toHaveCount(3);
    await expect(page.locator("#generate-items a")).toHaveCount(3);
    await expect(page.locator("#generate-error")).toBeHidden();
    // A amostra não fecha ZIP; o botão de download em lote fica escondido.
    await expect(page.locator("#generate-zip-link")).toBeHidden();

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.locator("#generate-items a").first().click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/\.pdf$/);
  });

  test("o lote completo processa todas as linhas e entrega o ZIP", async ({ page }) => {
    await openBancada(page);
    await page.locator("#generate-excel-input").setInputFiles(EXCEL);

    // Passo obrigatório: sem a amostra pronta, "Gerar lote completo" continua desabilitado.
    await page.getByRole("button", { name: /Gerar amostra/i }).click();
    await expect(page.locator("#generate-progress-text")).toHaveText(
      /3 arquivos prontos/,
      { timeout: 60_000 }
    );
    await expect(page.locator("#generate-full-button")).toBeEnabled();

    await page.getByRole("button", { name: /Gerar lote completo/i }).click();

    await expect(page.locator("#generate-progress-text")).toHaveText(
      /5 arquivos prontos/,
      { timeout: 60_000 }
    );
    await expect(page.locator("#generate-items li")).toHaveCount(5);
    await expect(page.locator("#generate-zip-link")).toBeVisible();

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.locator("#generate-zip-link").click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/\.zip$/);

    await page.screenshot({ path: path.join(TMP, "bancada-lote-completo.png"), fullPage: true });
  });

  test("um arquivo que não é Excel volta com o motivo na tela", async ({ page }) => {
    await openBancada(page);
    await page.locator("#generate-excel-input").setInputFiles(NOT_EXCEL);

    await page.getByRole("button", { name: /Gerar amostra/i }).click();

    await expect(page.locator("#generate-error")).toBeVisible();
    await expect(page.locator("#generate-error")).toContainText(/Excel/i);
    await expect(page.locator("#generate-progress")).toBeHidden();
    // O erro não trava o card: dá para corrigir e tentar de novo.
    await expect(page.locator("#generate-preview-button")).toBeEnabled();
  });

});
