const { test, expect } = require('@playwright/test');

test.describe('Anserini Prebuilt Index Evaluator', () => {
  test('complete CACM evaluation workflow', async ({ page }) => {
    // Navigate to the app
    await page.goto('/');

    // Verify the page loaded
    await expect(page.locator('h1')).toHaveText('Anserini Prebuilt Index Evaluator');

    // Wait for health check
    await expect(page.locator('#statusText')).toContainText('Environment ready', { timeout: 15000 });

    // Wait for indexes to load
    await expect(page.locator('#indexCount')).not.toHaveText('Loading...', { timeout: 30000 });

    // Verify CACM is selected (auto-selected on load)
    await expect(page.locator('#selectedIndex')).toHaveValue(/cacm/i);

    // Verify topics are populated for CACM
    await expect(page.locator('#topicsSelect')).toBeEnabled();
    await expect(page.locator('#topicsSelect')).toHaveValue('cacm');

    // Verify metric selector is enabled and has nDCG@10 as default
    await expect(page.locator('#metricSelect')).toBeEnabled();
    await expect(page.locator('#metricSelect')).toHaveValue('ndcg_cut.10');

    // Verify the catalog shows more than just CACM (registry-derived data)
    const indexItems = page.locator('.index-item');
    const indexCount = await indexItems.count();
    expect(indexCount).toBeGreaterThan(1);

    // Verify CACM shows as evaluable
    const cacmItem = page.locator('.index-item[data-name="cacm"]');
    await expect(cacmItem).toBeVisible();
    await expect(cacmItem.locator('.badge')).toHaveText('Evaluable');

    // Verify at least one catalog-only index is visible
    const catalogOnlyItems = page.locator('.index-item.catalog-only');
    const catalogOnlyCount = await catalogOnlyItems.count();
    expect(catalogOnlyCount).toBeGreaterThan(0);

    // Verify run button is enabled
    await expect(page.locator('#runBtn')).toBeEnabled();

    // Click Run Evaluation
    await page.locator('#runBtn').click();

    // Wait for results (this runs actual Anserini retrieval and evaluation)
    await expect(page.locator('#resultsCard')).toBeVisible({ timeout: 300000 });

    // Verify a numeric score appears
    const scoreElement = page.locator('.result-score');
    await expect(scoreElement).toBeVisible();
    const scoreText = await scoreElement.textContent();
    const score = parseFloat(scoreText);
    expect(score).toBeGreaterThan(0);
    expect(score).toBeLessThan(1);

    // Verify run metadata appears
    const resultMeta = page.locator('.result-meta');
    await expect(resultMeta).toBeVisible();
    await expect(resultMeta).toContainText('Index:');
    await expect(resultMeta).toContainText('cacm');
    await expect(resultMeta).toContainText('Topics:');
    await expect(resultMeta).toContainText('Metric:');
    await expect(resultMeta).toContainText('Success');
    await expect(resultMeta).toContainText('Run File:');
    await expect(resultMeta).toContainText('Eval File:');

    // Verify evaluation output is shown
    const evalOutput = page.locator('.run-preview').first();
    await expect(evalOutput).toBeVisible();
    const evalText = await evalOutput.textContent();
    expect(evalText).toContain('ndcg');

    // Verify run file preview is shown and contains TREC format data
    const runPreview = page.locator('.run-preview').nth(1);
    await expect(runPreview).toBeVisible();
    const runText = await runPreview.textContent();
    // TREC run format: qid Q0 docid rank score tag
    expect(runText).toMatch(/\d+\s+Q0\s+/);
  });

  test('metric selector shows nDCG@10 and Recall@1000', async ({ page }) => {
    await page.goto('/');

    // Wait for CACM to be auto-selected
    await expect(page.locator('#selectedIndex')).toHaveValue(/cacm/i, { timeout: 30000 });

    // Check metric options
    const metricOptions = page.locator('#metricSelect option');
    const optionTexts = await metricOptions.allTextContents();
    
    // Verify modern metrics are available
    expect(optionTexts).toContain('nDCG@10');
    expect(optionTexts).toContain('Recall@1000');
    expect(optionTexts).toContain('MAP');
  });

  test('catalog search filters indexes', async ({ page }) => {
    await page.goto('/');

    // Wait for indexes to load
    await expect(page.locator('#indexCount')).not.toHaveText('Loading...', { timeout: 30000 });

    // Get initial count
    const initialCount = await page.locator('.index-item').count();
    expect(initialCount).toBeGreaterThan(1);

    // Search for 'cacm'
    await page.fill('#indexSearch', 'cacm');
    
    // Verify filtered results
    const filteredCount = await page.locator('.index-item').count();
    expect(filteredCount).toBeLessThan(initialCount);
    expect(filteredCount).toBeGreaterThanOrEqual(1);

    // Verify CACM is in filtered results
    await expect(page.locator('.index-item[data-name="cacm"]')).toBeVisible();
  });
});
