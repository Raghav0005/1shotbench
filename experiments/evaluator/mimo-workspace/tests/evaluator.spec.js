const { test, expect } = require('@playwright/test');

test.describe('Anserini Prebuilt Index Evaluator', () => {
  test('full end-to-end workflow: browse catalog, run CACM evaluation, verify real results', async ({ page }) => {
    // Increase timeout for this test since Anserini retrieval takes time
    test.setTimeout(300000);

    // 1. Open the app
    await page.goto('/');

    // 2. Wait for the status bar to show ready state
    const statusBar = page.locator('#statusBar');
    await expect(statusBar).toHaveClass(/ready/, { timeout: 30000 });
    await expect(page.locator('#statusText')).toContainText('Environment ready');

    // 3. Wait for the index catalog to load
    await expect(page.locator('#indexCount')).not.toHaveText('0', { timeout: 60000 });

    // 4. Confirm the index catalog exposes more than a single CACM option
    //    This verifies we're getting data from the prebuilt-index registry, not a hardcoded list
    const totalCount = await page.locator('#indexCount').textContent();
    const total = parseInt(totalCount, 10);
    expect(total).toBeGreaterThan(1);

    // 5. Confirm CACM is selected by default (or selectable)
    const selectedIndexName = page.locator('#selectedIndex');
    await expect(selectedIndexName).toHaveText('cacm', { timeout: 15000 });

    // 6. Confirm CACM displays a topic/qrels or evaluation pairing
    const selectedTopics = page.locator('#selectedTopics');
    await expect(selectedTopics).toHaveText('cacm');
    const selectedQrels = page.locator('#selectedQrels');
    await expect(selectedQrels).toHaveText('cacm');

    // 7. Confirm the metric selector is enabled and has options including nDCG@10 or Recall@1000
    const metricSelect = page.locator('#metricSelect');
    await expect(metricSelect).toBeEnabled();
    const metricOptions = await metricSelect.locator('option').allTextContents();
    const hasNdcg = metricOptions.some(o => o.includes('nDCG@10'));
    const hasRecall = metricOptions.some(o => o.includes('Recall@1000'));
    // At least one modern metric should be available
    expect(hasNdcg || hasRecall).toBeTruthy();

    // Select nDCG@10 if available, otherwise Recall@1000
    if (hasNdcg) {
      await metricSelect.selectOption('ndcg_cut.10');
    } else if (hasRecall) {
      await metricSelect.selectOption('recall.1000');
    }

    // 8. Verify that at least one catalog-only or non-selected index is visible
    const catalogOnlyItems = page.locator('.index-item.catalog-only');
    await expect(catalogOnlyItems.first()).toBeVisible({ timeout: 10000 });
    const catalogOnlyCount = await catalogOnlyItems.count();
    expect(catalogOnlyCount).toBeGreaterThan(0);

    // Also verify evaluable items exist (besides CACM)
    const evaluableItems = page.locator('.index-item.evaluable');
    const evaluableCount = await evaluableItems.count();
    expect(evaluableCount).toBeGreaterThan(0);

    // 9. Click Run Evaluation
    const btnEvaluate = page.locator('#btnEvaluate');
    await expect(btnEvaluate).toBeEnabled();
    await btnEvaluate.click();

    // 10. Verify that a progress indicator appears
    await expect(page.locator('.progress-bar')).toBeVisible({ timeout: 5000 });

    // 11. Wait for the evaluation to complete and verify results
    // The result header with success class should appear
    const resultHeader = page.locator('.result-header.success');
    await expect(resultHeader).toBeVisible({ timeout: 180000 });

    // 12. Verify that a numeric score appears
    const scoreDisplay = page.locator('.score-display');
    await expect(scoreDisplay).toBeVisible({ timeout: 10000 });
    const scoreText = await scoreDisplay.textContent();
    const score = parseFloat(scoreText);
    expect(score).toBeGreaterThan(0);
    expect(score).toBeLessThan(1);
    // nDCG@10 for CACM should be around 0.45
    expect(score).toBeGreaterThan(0.3);

    // 13. Verify that run metadata appears
    const metadataGrid = page.locator('.metadata-grid');
    await expect(metadataGrid).toBeVisible();

    // Verify specific metadata fields
    const metadataText = await metadataGrid.textContent();
    expect(metadataText).toContain('cacm'); // index name
    expect(metadataText).toContain('cacm'); // topics name
    expect(metadataText).toContain('ndcg_cut'); // metric identifier
    expect(metadataText).toContain('/runs/run.'); // run file path
    expect(metadataText).toContain('/runs/eval.'); // eval file path

    // Verify elapsed time is shown and reasonable
    expect(metadataText).toMatch(/\d+ms/);

    // 14. Verify completion time is displayed
    expect(metadataText).toContain('T'); // ISO datetime contains 'T'
  });

  test('index catalog has search and filter capabilities', async ({ page }) => {
    test.setTimeout(60000);
    await page.goto('/');

    // Wait for indexes to load
    await expect(page.locator('#indexCount')).not.toHaveText('0', { timeout: 60000 });

    // Test search filter
    const filterInput = page.locator('#indexFilter');
    await filterInput.fill('cacm');
    // Should filter down to cacm-related indexes
    const filteredText = await page.locator('#resultCount').textContent();
    expect(filteredText).toMatch(/Showing \d+ of \d+ indexes/);

    // Verify the cacm index appears
    await expect(page.locator('.index-item').first()).toBeVisible();

    // Clear filter
    await filterInput.fill('');

    // Test type filter
    const typeSelect = page.locator('#typeFilter');
    await typeSelect.selectOption('inverted');
    const invertedText = await page.locator('#resultCount').textContent();
    // Should have fewer results than total
    const match = invertedText.match(/Showing (\d+) of (\d+)/);
    if (match) {
      expect(parseInt(match[1])).toBeLessThanOrEqual(parseInt(match[2]));
    }

    // Reset filter
    await typeSelect.selectOption('');
  });

  test('evaluable and catalog-only indexes are visually differentiated', async ({ page }) => {
    test.setTimeout(60000);
    await page.goto('/');

    // Wait for indexes to load
    await expect(page.locator('#indexCount')).not.toHaveText('0', { timeout: 60000 });

    // Both evaluable and catalog-only items should exist
    const evaluableItems = page.locator('.index-item.evaluable, .index-item.selected');
    const catalogOnlyItems = page.locator('.index-item.catalog-only');

    await expect(evaluableItems.first()).toBeVisible({ timeout: 10000 });
    await expect(catalogOnlyItems.first()).toBeVisible({ timeout: 10000 });

    // Evaluable badges should exist
    const evaluableBadges = page.locator('.idx-badge.evaluable');
    await expect(evaluableBadges.first()).toBeVisible();

    // Catalog-only badges should exist
    const catalogOnlyBadges = page.locator('.idx-badge.catalog-only');
    await expect(catalogOnlyBadges.first()).toBeVisible();
  });
});
