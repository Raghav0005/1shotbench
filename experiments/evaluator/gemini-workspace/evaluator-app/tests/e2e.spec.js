const { test, expect } = require('@playwright/test');

test.describe('Anserini Evaluator E2E', () => {
  test('Completes an end-to-end evaluation workflow', async ({ page }) => {
    // 1. App opens successfully
    await page.goto('http://localhost:3000');
    await expect(page.locator('h1')).toHaveText('Anserini Evaluator Dashboard');

    // 2. Wait for catalog to load and ensure multiple options are sourced
    await page.waitForSelector('.index-item');
    const catalogItems = await page.locator('.index-item').count();
    expect(catalogItems).toBeGreaterThan(1); // Not just a single hardcoded CACM

    // 3. Ensure at least one catalog-only index is visible
    const catalogOnlyCount = await page.locator('.badge.catalog-only').count();
    expect(catalogOnlyCount).toBeGreaterThan(0);

    // 4. CACM is default or can be selected, displays associated topic/qrels
    const cacmDetails = page.locator('#details-pane');
    await expect(cacmDetails).toContainText('cacm');
    await expect(cacmDetails).toContainText('Topics: cacm');
    await expect(cacmDetails).toContainText('Qrels: cacm');

    // 5. Select a metric
    const metricSelect = page.locator('#metric-select');
    await metricSelect.selectOption('ndcg_cut.10');

    // 6. Run Evaluation
    await page.click('#run-btn');

    // Wait for the status indicator to appear then disappear
    await expect(page.locator('.loader')).toBeVisible();
    await expect(page.locator('.loader')).toBeHidden({ timeout: 60000 }); // give it 60s max

    // 7. A numeric evaluation score is rendered on the screen
    const scoreText = await page.locator('#eval-score').textContent();
    expect(parseFloat(scoreText)).toBeGreaterThan(0); // Score should be a positive number

    // 8. Run metadata is present
    await expect(page.locator('#eval-metadata')).toContainText('Index: cacm');
    await expect(page.locator('#eval-metadata')).toContainText('Topics: cacm');
    await expect(page.locator('#eval-metadata')).toContainText('Metric: ndcg_cut.10');
    await expect(page.locator('#eval-metadata')).toContainText('Status: success');
    await expect(page.locator('#eval-metadata')).toContainText('Elapsed Time:');
    await expect(page.locator('#eval-metadata')).toContainText('Run File Path:');
    
    // Preview is present
    const previewText = await page.locator('#eval-preview').textContent();
    expect(previewText).toContain('ndcg_cut_10');
  });
});
