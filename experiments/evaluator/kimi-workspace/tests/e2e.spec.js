const { test, expect } = require('@playwright/test');

test.describe('Anserini Prebuilt Index Evaluator', () => {
  test('should load, show catalog, and run CACM evaluation', async ({ page }) => {
    await page.goto('/');

    // Wait for the app to be ready
    await expect(page.locator('text=Anserini Prebuilt Index Evaluator')).toBeVisible();

    // Verify health status is OK
    await expect(page.locator('.health-status.ok')).toBeVisible();

    // Wait for the index list to finish loading
    await page.waitForFunction(() => {
      const list = document.querySelector('#index-list');
      return list && !list.textContent.includes('Loading');
    }, { timeout: 30000 });

    // Verify catalog has more than one option (not just hardcoded CACM)
    const indexCards = page.locator('.index-card');
    await expect(indexCards.first()).toBeVisible();
    const count = await indexCards.count();
    expect(count).toBeGreaterThan(1);

    // Verify at least one catalog-only index is visible
    const catalogOnly = page.locator('.index-card.catalog-only');
    await expect(catalogOnly.first()).toBeVisible();

    // Verify CACM is present and evaluable
    const cacmCard = page.locator('.index-card', { hasText: 'cacm' }).filter({ hasText: 'Evaluable' });
    await expect(cacmCard).toBeVisible();

    // Select CACM if not already selected
    const selectedCacm = page.locator('.index-card.selected', { hasText: 'cacm' });
    if (await selectedCacm.count() === 0) {
      await cacmCard.click();
    }
    await expect(page.locator('.index-card.selected', { hasText: 'cacm' })).toBeVisible();

    // Verify evaluation form is visible with CACM data
    await expect(page.locator('#evaluation-form')).not.toHaveClass(/hidden/);
    await expect(page.locator('#selected-index-name')).toHaveText('cacm');

    // Verify topic/qrels pairing is present
    const topicSelect = page.locator('#topic-select');
    await expect(topicSelect).toBeVisible();
    const topicOptions = await topicSelect.locator('option').allTextContents();
    expect(topicOptions.length).toBeGreaterThan(0);
    expect(topicOptions.some(t => t.includes('cacm'))).toBe(true);

    // Verify qrels display
    await expect(page.locator('#eval-key-display')).toContainText('cacm');

    // Choose a metric: prefer nDCG@10 or Recall@1000, fallback to MAP
    const metricSelect = page.locator('#metric-select');
    await expect(metricSelect).toBeVisible();
    const metricOptions = await metricSelect.locator('option').allTextContents();
    let chosenMetric = null;
    if (metricOptions.includes('nDCG@10')) {
      chosenMetric = 'nDCG@10';
    } else if (metricOptions.includes('Recall@1000') || metricOptions.includes('R@1K')) {
      chosenMetric = metricOptions.find(m => m.includes('Recall@1000') || m.includes('R@1K'));
    } else {
      // Fallback for CACM
      chosenMetric = metricOptions.find(m => m === 'MAP') || metricOptions[0];
    }
    expect(chosenMetric).not.toBeNull();
    await metricSelect.selectOption({ label: chosenMetric });

    // Click Run Evaluation
    await page.locator('#run-evaluation').click();

    // Wait for loading to finish and result to appear
    await page.waitForSelector('#evaluation-loading', { state: 'hidden', timeout: 120000 });

    // Confirm numeric score appears
    const scoreValue = page.locator('#result-score');
    await expect(scoreValue).toBeVisible();
    const scoreText = await scoreValue.textContent();
    expect(parseFloat(scoreText)).not.toBeNaN();

    // Confirm run metadata appears
    await expect(page.locator('#meta-index')).toHaveText('cacm');
    await expect(page.locator('#meta-topic')).toContainText('cacm');
    await expect(page.locator('#meta-qrels')).toContainText('cacm');
    await expect(page.locator('#meta-metric')).toContainText(chosenMetric);
    await expect(page.locator('#meta-status')).toContainText('Completed');

    // Confirm run and eval artifact paths appear
    await expect(page.locator('#meta-runfile')).not.toBeEmpty();
    await expect(page.locator('#meta-evalfile')).not.toBeEmpty();

    // Confirm evaluation output preview is present
    await page.locator('details summary').click();
    await expect(page.locator('#eval-preview')).not.toBeEmpty();
  });
});
