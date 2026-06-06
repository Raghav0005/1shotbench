const { test, expect } = require('@playwright/test');

test('Anserini Prebuilt Index Evaluator end-to-end', async ({ page }) => {
  // Open the app
  await page.goto('/');
  await expect(page.locator('h1')).toHaveText('Anserini Prebuilt Index Evaluator');

  // Wait for catalog to load (registry discovery may take a while)
  await page.waitForSelector('.index-item', { timeout: 90000 });

  // Confirm catalog exposes more than a hardcoded single CACM option
  const items = await page.locator('.index-item').count();
  expect(items).toBeGreaterThan(1);

  // Confirm at least one catalog-only index is visible
  const catalogOnly = page.locator('.index-badge.badge-catalog');
  await expect(catalogOnly.first()).toBeVisible();

  // Confirm CACM is selected or selectable
  const cacmItem = page.locator('.index-item', { hasText: 'cacm' });
  if (await cacmItem.locator('.selected').count() === 0) {
    await cacmItem.first().click();
  }
  await expect(cacmItem.first()).toHaveClass(/selected/);

  // Confirm CACM shows a topic/qrels or evaluation pairing
  await expect(page.locator('select#pairingSelect')).toBeVisible({ timeout: 5000 });
  const pairingOptions = await page.locator('select#pairingSelect option').allTextContents();
  expect(pairingOptions.length).toBeGreaterThan(0);
  expect(pairingOptions.some(t => t.includes('cacm'))).toBe(true);

  // Select a supported metric such as nDCG@10 or Recall@1000, with fallback for CACM
  const metricSelect = page.locator('select#metricSelect');
  await expect(metricSelect).toBeVisible();
  const metrics = await metricSelect.locator('option').allTextContents();
  expect(metrics.length).toBeGreaterThan(0);

  // Prefer nDCG@10 or Recall@1000 if available, otherwise use first available
  let chosenMetric = metrics[0];
  for (const m of metrics) {
    if (m.toLowerCase().includes('ndcg') || m.toLowerCase().includes('recall') || m.toLowerCase().includes('r@')) {
      chosenMetric = m;
      break;
    }
  }
  await metricSelect.selectOption({ label: chosenMetric });

  // Click Run Evaluation
  const runBtn = page.locator('button:has-text("Run Evaluation")');
  await expect(runBtn).toBeVisible();
  await runBtn.click();

  // Wait for result
  await expect(page.locator('.score')).toBeVisible({ timeout: 120000 });

  // Verify that a numeric score appears
  const scoreText = await page.locator('.score').textContent();
  const score = parseFloat(scoreText);
  expect(!isNaN(score)).toBe(true);

  // Verify that run metadata appears
  await expect(page.locator('.meta-key', { hasText: 'Index' }).first()).toBeVisible();
  await expect(page.locator('.meta-key', { hasText: 'Topics' }).first()).toBeVisible();
  await expect(page.locator('.meta-key', { hasText: 'Qrels' }).first()).toBeVisible();
  await expect(page.locator('.meta-key', { hasText: 'Run File' }).first()).toBeVisible();
  await expect(page.locator('.meta-key', { hasText: 'Eval File' }).first()).toBeVisible();

  // Verify eval output contains numeric results from real Anserini execution
  const evalDetails = page.locator('details summary:has-text("Evaluation output")');
  if (await evalDetails.count() > 0) {
    await evalDetails.first().click();
    const pre = page.locator('details pre');
    await expect(pre).toBeVisible();
    const evalText = await pre.textContent();
    expect(evalText).toMatch(/\d+\.\d+/);
  }
});
