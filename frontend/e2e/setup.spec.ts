// S01 Setup (DEV_SPEC §12.7, host_script S01): the shipped PDFs are indexed, the Brief Agent runs for
// each product, and confirming the glossary creates the next glossary version.
import { expect, test } from "@playwright/test";

test("S01 setup: documents, Brief Agent, glossary confirmation", async ({ page, request }) => {
  const before = (await (await request.get("/api/setup/glossary")).json()).version as number;

  await page.goto("/setup");
  const docs = page.getByTestId("setup-documents");
  for (const name of ["DAON_LAB_Hydra_Barrier_Cream.pdf", "DAON_LAB_Deep_Hydration_Ampoule.pdf"]) {
    const row = docs.locator("tr").filter({ hasText: name });
    await expect(row).toBeVisible();
    await expect(row).toContainText("Indexed locally");
  }

  for (const pid of ["cream_hydra_barrier", "ampoule_deep_hydration"]) {
    const card = page.getByTestId(`setup-product-${pid}`);
    await card.getByRole("button", { name: "Run Brief Agent" }).click();
    const glossary = page.getByTestId(`setup-glossary-${pid}`);
    await expect(glossary).toBeVisible({ timeout: 90_000 });
    expect(await glossary.locator("tbody tr").count()).toBeGreaterThan(5);
    await expect(glossary).toContainText("DAON LAB");
    await expect(glossary.locator("tbody tr").first()).toContainText(/Product overview|Key ingredients|Key facts|Approved/);
  }

  // Prompter point drafts stay unapplied (S01): every draft select is left on "Not used".
  for (const select of await page.getByRole("combobox", { name: /Use draft/ }).all()) {
    await expect(select).toHaveValue("");
  }

  await page.getByRole("button", { name: "Confirm glossary" }).click();
  await expect(page.getByTestId("setup-confirmed")).toHaveText(`Confirmed · version ${before + 1}`);
  await expect(page.getByTestId("setup-glossary-version")).toContainText(`version ${before + 1}`);
  const after = (await (await request.get("/api/setup/glossary")).json()).version as number;
  expect(after).toBe(before + 1);
});
