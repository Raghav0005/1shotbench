const { test, expect } = require('@playwright/test');

test.describe('Anserini Prebuilt Index Evaluator', () => {

  test('should load the app and display the index catalog', async ({ page }) => {
    await page.goto('/');

    // Verify title
    await expect(page.locator('h1')).toHaveText('Anserini Prebuilt Index Evaluator');

    // Verify JAR badge is shown (not "No JAR found")
    const jarBadge = page.locator('#jarBadge');
    await expect(jarBadge).toContainText('JAR:');

    // Verify index list loads with more than 1 index (registry-derived)
    const indexItems = page.locator('[data-testid="index-item"]');
    await expect(indexItems.first()).toBeVisible({ timeout: 30000 });
    const count = await indexItems.count();
    expect(count).toBeGreaterThanOrEqual(5);

    // Verify CACM is present and evaluable
    const cacmItem = page.locator('[data-name="cacm"]');
    await expect(cacmItem).toBeVisible();
    await expect(cacmItem).toHaveAttribute('data-evaluable', 'true');
  });

  test('should show catalog-only indexes alongside evaluable ones', async ({ page }) => {
    await page.goto('/');

    // Wait for indexes to load
    await expect(page.locator('[data-testid="index-item"]').first()).toBeVisible({ timeout: 30000 });

    // Verify there are catalog-only indexes (not just CACM)
    const catalogOnlyItems = page.locator('[data-evaluable="false"]');
    await expect(catalogOnlyItems.first()).toBeVisible({ timeout: 30000 });
    const catCount = await catalogOnlyItems.count();
    expect(catCount).toBeGreaterThanOrEqual(1);
  });

  test('should auto-select CACM and show evaluation panel', async ({ page }) => {
    await page.goto('/');

    // Wait for CACM to be auto-selected
    await expect(page.locator('[data-name="cacm"].selected')).toBeVisible({ timeout: 30000 });

    // Verify evaluation panel shows CACM info
    await expect(page.locator('#evalContent')).toContainText('cacm');
    await expect(page.locator('#evalContent')).toContainText('Topics');

    // Verify metric selector is present with expected metrics
    const metricSelect = page.locator('[data-testid="metric-select"]');
    await expect(metricSelect).toBeVisible();
    
    // Check nDCG@10 is available
    const options = metricSelect.locator('option');
    const optionTexts = await options.allTextContents();
    const hasNdcg = optionTexts.some(t => t.includes('nDCG@10') || t.includes('ndcg_cut.10'));
    const hasRecall = optionTexts.some(t => t.includes('Recall@1000') || t.includes('recall.1000'));
    expect(hasNdcg || hasRecall).toBeTruthy();

    // Verify Run Evaluation button is present
    await expect(page.locator('[data-testid="run-eval-btn"]')).toBeVisible();
  });

  test('should run CACM evaluation end-to-end and display results', async ({ page }) => {
    await page.goto('/');

    // Wait for CACM to be auto-selected
    await expect(page.locator('[data-name="cacm"].selected')).toBeVisible({ timeout: 30000 });

    // Select nDCG@10 if available, otherwise first metric
    const metricSelect = page.locator('[data-testid="metric-select"]');
    await expect(metricSelect).toBeVisible();

    const options = metricSelect.locator('option');
    const optionTexts = await options.allTextContents();
    const ndcgOption = optionTexts.find(t => t.includes('nDCG@10'));
    if (ndcgOption) {
      const ndcgValue = await options.nth(optionTexts.indexOf(ndcgOption)).getAttribute('value');
      await metricSelect.selectOption(ndcgValue);
    }

    // Click Run Evaluation
    await page.locator('[data-testid="run-eval-btn"]').click();

    // Wait for evaluation to complete (may take time for first download)
    await expect(page.locator('[data-testid="score-display"]')).toBeVisible({ timeout: 120000 });

    // Verify a numeric score is displayed
    const scoreText = await page.locator('[data-testid="score-display"]').textContent();
    const score = parseFloat(scoreText);
    expect(score).not.toBeNaN();
    expect(score).toBeGreaterThan(0);

    // Verify result metadata
    const metaTable = page.locator('[data-testid="result-meta"]');
    await expect(metaTable).toContainText('cacm');
    await expect(metaTable).toContainText('Topics');

    // Verify run file path
    const runFile = page.locator('[data-testid="run-file"]');
    const runFileText = await runFile.textContent();
    expect(runFileText).toContain('run.');
    expect(runFileText).toContain('cacm');

    // Verify evaluation output is non-empty
    const evalOutput = page.locator('[data-testid="eval-output"]');
    const evalText = await evalOutput.textContent();
    expect(evalText.length).toBeGreaterThan(0);

    // Verify run file preview
    const runPreview = page.locator('[data-testid="run-preview"]');
    const previewText = await runPreview.textContent();
    expect(previewText.length).toBeGreaterThan(0);
  });

});
