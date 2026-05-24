const { test, expect } = require('@playwright/test');

test('E2E: Anserini Prebuilt Index Evaluator workflow', async ({ page }) => {
  // Open the app
  await page.goto('/');
  
  // Confirm CACM is selected or selectable
  await expect(page.locator('text=Anserini Prebuilt Index Evaluator')).toBeVisible();
  
  // Wait for catalog to load
  await expect(page.locator('#index-list')).toContainText('cacm', { timeout: 15000 });
  
  // Verify that the index catalog exposes more than a single hardcoded option
  // Check that there is at least one catalog-only or non-selected index visible
  const listItems = page.locator('#index-list li');
  const count = await listItems.count();
  expect(count).toBeGreaterThan(1);
  
  // Confirm CACM is the selected index
  await expect(page.locator('#sel-index')).toHaveText('cacm');
  
  // Confirm CACM shows a topic/qrels or evaluation pairing
  await expect(page.locator('#sel-topic')).toHaveText('cacm');
  
  // Select a supported metric such as nDCG@10 or Recall@1000
  await page.locator('#metric').selectOption('MAP'); // Using MAP or ndcg
  await page.locator('#metric').selectOption('nDCG@10');
  
  // Click Run Evaluation
  await page.locator('#run-btn').click();
  
  // Wait for evaluation to complete (can take a moment for search and eval)
  await expect(page.locator('#status-msg')).toHaveText('Evaluation complete!', { timeout: 30000 });
  
  // Verify that a numeric score appears
  const scoreText = await page.locator('#res-score').textContent();
  expect(parseFloat(scoreText)).toBeGreaterThan(0);
  
  // Verify that run metadata appears, including index, topics, metric, and run/evaluation artifacts
  await expect(page.locator('#res-runfile')).toContainText('run.cacm.cacm.txt');
  const outputText = await page.locator('#res-output').textContent();
  expect(outputText).toContain('ndcg_cut_10');
  expect(outputText).toContain('all');
});