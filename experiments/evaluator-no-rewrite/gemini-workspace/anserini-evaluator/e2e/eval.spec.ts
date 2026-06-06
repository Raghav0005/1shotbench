import { test, expect } from '@playwright/test';

import fs from 'fs';
import path from 'path';

test('evaluation dashboard workflow', async ({ page }) => {
  await page.goto('/');

  // Confirm CACM is selected or selectable
  await expect(page.locator('span:has-text("Selected Index:") + span')).toHaveText('cacm', { timeout: 10000 });

  // Confirm index catalog exposes more than a single CACM option
  // It should be visible from the registry
  const indexEntries = page.locator('.p-3.border.rounded');
  const count = await indexEntries.count();
  expect(count).toBeGreaterThan(1);

  // Check that at least one non-evaluable is present
  await expect(page.locator('text=Catalog Only').first()).toBeVisible();

  // Ensure topic/qrels pairing is cacm
  const topicSelect = page.locator('select').first();
  await expect(topicSelect).toHaveValue('cacm');

  // Select metric
  const metricSelect = page.locator('select').nth(1);
  await metricSelect.selectOption('ndcg_cut.10');

  // Click Run Evaluation
  await page.click('button:has-text("Run Evaluation")');

  // Verify that score appears
  await expect(page.locator('text=Score for ndcg_cut.10')).toBeVisible({ timeout: 60000 });
  
  // Verify a numeric score (e.g. 0.3123)
  const scoreLocator = page.locator('.text-4xl.font-bold');
  const scoreText = await scoreLocator.textContent();
  expect(Number(scoreText)).toBeGreaterThan(0);

  // Verify run metadata
  await expect(page.locator('text=run.cacm.cacm.txt')).toBeVisible();
  
  // Output preview
  await expect(page.locator('text=trec_eval Output Preview')).toBeVisible();

  // Verify that the run file actually exists on disk (proving it wasn't mocked)
  const runFilePath = path.join(process.cwd(), 'run.cacm.cacm.txt');
  expect(fs.existsSync(runFilePath)).toBe(true);
});
