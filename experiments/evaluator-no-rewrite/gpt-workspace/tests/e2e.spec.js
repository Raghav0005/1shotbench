import { test, expect } from '@playwright/test';
import fs from 'node:fs';

function numericText(value) {
  return Number(String(value).trim());
}

test('runs real CACM retrieval and evaluation from the browser', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByTestId('catalog-status')).toContainText('registry indexes shown', { timeout: 120_000 });

  const catalogItems = page.getByTestId('catalog-index');
  await expect(catalogItems.first()).toBeVisible();
  expect(await catalogItems.count()).toBeGreaterThan(1);

  const cacm = page.locator('[data-testid="catalog-index"][data-index-name="cacm"]');
  await expect(cacm).toBeVisible();
  await expect(cacm).toContainText('Ready for evaluation');
  await cacm.click();

  await expect(page.getByTestId('selected-topics')).toHaveText('cacm');
  await expect(page.getByTestId('selected-qrels')).toHaveText('cacm');

  const catalogOnlyCount = await page.locator('[data-testid="catalog-index"][data-evaluable="false"]').count();
  expect(catalogOnlyCount).toBeGreaterThan(0);

  const metric = page.getByTestId('metric');
  const labels = await metric.locator('option').allTextContents();
  if (labels.some((label) => label.includes('nDCG@10'))) {
    await metric.selectOption('ndcg_cut.10');
  } else if (labels.some((label) => label.includes('Recall@1000'))) {
    await metric.selectOption('recall.1000');
  } else {
    await metric.selectOption({ index: 0 });
  }

  await page.getByTestId('run-evaluation').click();
  await expect(page.getByTestId('run-status')).toContainText('Evaluation completed', { timeout: 10 * 60 * 1000 });

  const score = numericText(await page.getByTestId('score').textContent());
  expect(Number.isFinite(score)).toBeTruthy();

  await expect(page.getByTestId('meta-index')).toHaveText('cacm');
  await expect(page.getByTestId('meta-topics')).toHaveText('cacm');
  await expect(page.getByTestId('meta-metric')).not.toHaveText('');
  await expect(page.getByTestId('meta-run-path')).not.toHaveText('');
  await expect(page.getByTestId('meta-eval-path')).not.toHaveText('');
  await expect(page.getByTestId('eval-preview')).toContainText(/\d+\.\d+/);

  const runPath = (await page.getByTestId('meta-run-path').textContent()).trim();
  const evalPath = (await page.getByTestId('meta-eval-path').textContent()).trim();
  expect(fs.existsSync(runPath)).toBeTruthy();
  expect(fs.existsSync(evalPath)).toBeTruthy();
  expect(fs.statSync(runPath).size).toBeGreaterThan(1000);
  expect(fs.readFileSync(evalPath, 'utf8')).toMatch(/(ndcg_cut_10|recall_1000|map|P_30)\s+all\s+\d+\.\d+/);
});
