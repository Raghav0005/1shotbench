const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');

test('runs CACM retrieval and evaluation through the browser', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Anserini Prebuilt Index Evaluator' })).toBeVisible();
  await expect(page.locator('#catalogSummary')).toContainText(/registry-derived inverted indexes/i, { timeout: 90000 });

  const catalogRows = page.locator('#catalogRows tr');
  await expect.poll(async () => catalogRows.count()).toBeGreaterThan(1);

  const cacmRow = page.locator('#catalogRows tr[data-index-name="cacm"]');
  await expect(cacmRow).toBeVisible();
  await cacmRow.click();

  await expect(page.locator('#selectedIndex')).toContainText('cacm');
  await expect(page.locator('#selectedIndex')).toContainText(/Topics:|Qrels\/eval source:/);
  await expect(page.locator('#selectedIndex')).toContainText(/Ready for evaluation/);

  const metricSelect = page.locator('#metricSelect');
  const options = await metricSelect.locator('option').evaluateAll(opts => opts.map(o => ({ value: o.value, text: o.textContent || '' })));
  const preferred = options.find(o => o.text.includes('nDCG@10'))
    || options.find(o => o.text.includes('Recall@1000'))
    || options.find(o => o.text.includes('MAP'));
  expect(preferred, `Expected nDCG@10, Recall@1000, or explicit fallback MAP in ${JSON.stringify(options)}`).toBeTruthy();
  await metricSelect.selectOption(preferred.value);

  const nonSelectedCatalogOnly = page.locator('#catalogRows tr:not([data-index-name="cacm"])', { hasText: 'Catalog-only' }).first();
  await expect(nonSelectedCatalogOnly).toBeVisible();

  await page.getByRole('button', { name: 'Run Evaluation' }).click();
  await expect(page.locator('#status')).toContainText('Evaluation completed', { timeout: 180000 });

  await expect(page.locator('#scoreValue')).toHaveText(/^\d+(\.\d+)?$/);
  await expect(page.locator('#metaIndex')).toHaveText('cacm');
  await expect(page.locator('#metaTopics')).toHaveText('cacm');
  await expect(page.locator('#metaMetric')).toContainText(preferred.value);
  await expect(page.locator('#metaRunFile')).toContainText(/^artifacts\/runs\/run\./);
  await expect(page.locator('#metaEvalFile')).toContainText(/^artifacts\/eval\/eval\./);
  await expect(page.locator('#evalPreview')).toContainText(/all\s+\d/);

  const runRel = await page.locator('#metaRunFile').innerText();
  const evalRel = await page.locator('#metaEvalFile').innerText();
  const runFile = path.join(root, runRel);
  const evalFile = path.join(root, evalRel);
  expect(fs.existsSync(runFile), `Run file should exist: ${runFile}`).toBe(true);
  expect(fs.existsSync(evalFile), `Evaluation output should exist: ${evalFile}`).toBe(true);
  expect(fs.statSync(runFile).size, 'Real retrieval must produce a non-empty run file').toBeGreaterThan(1000);
  expect(fs.statSync(evalFile).size, 'Real evaluation must produce a non-empty eval file').toBeGreaterThan(10);
});
