// @ts-check
const path = require("path");
const { test, expect } = require("@playwright/test");

const TMP = path.join(__dirname, "..", ".tmp");
const EXCEL_GRANDE = path.join(TMP, "dados_grande.xlsx");

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

// "Gerar lote completo" só libera depois de uma amostra pronta — passo
// obrigatório em toda planilha nova, mesmo nestes testes de lote grande.
async function runSampleThenFullBatch(page) {
  await page.getByRole("button", { name: /Gerar amostra/i }).click();
  await expect(page.locator("#generate-progress-text")).toHaveText(/3 arquivos prontos/, {
    timeout: 60_000,
  });
  await expect(page.locator("#generate-full-button")).toBeEnabled();
  await page.getByRole("button", { name: /Gerar lote completo/i }).click();
}

test.describe("Lote grande: a bancada aponta para a página do job", () => {
  test("30 linhas viram resumo + link, não uma lista de 30 itens na coluna", async ({ page }) => {
    await openBancada(page);
    await page.locator("#generate-excel-input").setInputFiles(EXCEL_GRANDE);

    await runSampleThenFullBatch(page);

    // A contagem final é anunciada pela barra de progresso (role=status),
    // que fica no ar até o fim; o link é o único elemento novo em #generate-result.
    await expect(page.locator("#generate-progress-text")).toHaveText(
      /30 arquivos prontos/,
      { timeout: 60_000 }
    );
    await expect(page.locator("#generate-detail-link")).toBeVisible();
    // A lista por item não deve aparecer para um lote deste tamanho.
    await expect(page.locator("#generate-items")).toBeHidden();
    await expect(page.locator("#generate-items li")).toHaveCount(0);

    await page.screenshot({ path: path.join(TMP, "bancada-lote-grande.png"), fullPage: true });
  });

  test("o link leva à página do job com estatísticas, chips e paginação", async ({ page }) => {
    await openBancada(page);
    await page.locator("#generate-excel-input").setInputFiles(EXCEL_GRANDE);
    await runSampleThenFullBatch(page);
    await expect(page.locator("#generate-detail-link")).toBeVisible({ timeout: 60_000 });

    await page.locator("#generate-detail-link").click();
    await expect(page).toHaveURL(/\/jobs\/\d+\/$/);

    await expect(page.locator("#job-stat-total")).toHaveText("30");
    await expect(page.locator("#job-stat-success")).toHaveText("30");
    await expect(page.locator("#job-stat-failed")).toHaveText("0");

    // 30 linhas com página de 25: duas páginas.
    await expect(page.locator("#job-items-page-label")).toContainText("Página 1 de 2");
    await expect(page.locator("#job-items-body tr")).toHaveCount(25);

    await page.getByRole("link", { name: "Próxima" }).click();
    await expect(page).toHaveURL(/page=2/);
    await expect(page.locator("#job-items-body tr")).toHaveCount(5);

    // Nenhum comentário do Django deve ter vazado como texto na página.
    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toContain("{#");
    expect(bodyText).not.toContain("A tabela é sempre renderizada");

    await page.screenshot({ path: path.join(TMP, "job-detail-pagina-2.png"), fullPage: true });
  });

  test("os chips filtram a tabela por estado", async ({ page }) => {
    await openBancada(page);
    await page.locator("#generate-excel-input").setInputFiles(EXCEL_GRANDE);
    await runSampleThenFullBatch(page);
    await expect(page.locator("#generate-detail-link")).toBeVisible({ timeout: 60_000 });
    await page.locator("#generate-detail-link").click();
    await expect(page).toHaveURL(/\/jobs\/\d+\/$/);

    await page.getByRole("link", { name: /Prontas/i }).click();
    await expect(page).toHaveURL(/estado=completed/);
    await expect(page.locator("#job-items-body tr")).toHaveCount(25);

    await page.getByRole("link", { name: /Falhas/i }).click();
    await expect(page).toHaveURL(/estado=failed/);
    await expect(page.locator("#job-items-body")).toContainText("Nenhuma linha com erro.");

    await page.getByRole("link", { name: /^Todos/i }).click();
    await expect(page.locator("#job-items-body tr")).toHaveCount(25);
  });
});
