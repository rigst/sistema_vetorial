// @ts-check
const { test, expect } = require("@playwright/test");

test("acesso visitante: tela de login até o editor, com o selo de temporário", async ({
  page,
}) => {
  await page.goto("/login/");
  await page.getByRole("button", { name: /Experimentar sem criar conta/i }).click();

  await expect(page).toHaveURL(/\/legal\/aceite\//);
  await page.locator("#id_aceite_legal").check();
  await page.getByRole("button", { name: /Entrar como visitante/i }).click();

  await expect(page).toHaveURL(/\/templates\//);
  await expect(page.locator(".visitor-badge")).toBeVisible();
  await expect(page.locator(".visitor-badge")).toContainText(/temporário/i);
});
