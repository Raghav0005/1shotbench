const { test, expect } = require('@playwright/test');

test.describe('Anserini Prebuilt Index Evaluator', () => {
  test('end-to-end CACM evaluation workflow', async ({ page }) => {
    // 1. Open the application
    await page.goto('/');
    await expect(page.locator('h1')).toHaveText('Anserini Prebuilt Index Evaluator');

    // 2. Confirm that CACM is selected or selectable
    // CACM should be auto-selected as the default
    const cacmItem = page.locator('.catalog-item[data-index="cacm"]');
    await expect(cacmItem).toBeVisible();
    // Wait for catalog to load and CACM to be selected
    await expect(cacmItem).toHaveClass(/selected/, { timeout: 15_000 });

    // 3. Confirm that the index catalog surfaces more than a single hardcoded CACM entry
    const catalogItems = page.locator('.catalog-item');
    const count = await catalogItems.count();
    expect(count).toBeGreaterThan(1);

    // 4. Confirm that CACM displays a topic/qrels or evaluation pairing
    await expect(page.locator('#selectedTopics')).toHaveText('cacm');
    await expect(page.locator('#selectedQrels')).toHaveText('cacm');

    // Verify the eval form is visible
    await expect(page.locator('#evalForm')).toBeVisible();

    // 5. Select a supported metric - prefer nDCG@10, fallback to Recall@1000, then MAP
    const metricSelect = page.locator('#metricSelect');
    await expect(metricSelect).toBeVisible();
    const options = metricSelect.locator('option');
    const optTexts = await options.allTextContents();

    // Try nDCG@10 first, then Recall@1000, then MAP as fallback
    let chosenMetric = null;
    for (const candidate of ['nDCG@10', 'Recall@1000', 'MAP']) {
      if (optTexts.includes(candidate)) {
        chosenMetric = candidate;
        break;
      }
    }
    expect(chosenMetric).not.toBeNull();
    await metricSelect.selectOption({ label: chosenMetric });

    // 6. Trigger the Run Evaluation action
    const btnRun = page.locator('#btnRun');
    await expect(btnRun).toBeEnabled();
    await btnRun.click();

    // Wait for running state
    await expect(page.locator('#evalRunning')).toBeVisible();

    // 7. Assert that a numeric evaluation score appears (may take time for first download)
    const resultScore = page.locator('#resultScore');
    await expect(resultScore).toBeVisible({ timeout: 180_000 });
    const scoreText = await resultScore.textContent();
    const score = parseFloat(scoreText);
    expect(score).not.toBeNaN();
    expect(score).toBeGreaterThan(0);

    // 8. Assert that run metadata is displayed
    await expect(page.locator('#resultMeta')).toBeVisible();
    await expect(page.locator('#resultMeta')).toContainText('cacm');
    await expect(page.locator('#resultMeta')).toContainText('cacm'); // topics
    await expect(page.locator('#resultMeta')).toContainText(chosenMetric.split('@')[0]); // metric label portion
    await expect(page.locator('#resultMeta')).toContainText('s'); // elapsed time

    // Assert eval output is present
    await expect(page.locator('#evalOutputBox')).toBeVisible();
    const evalOutput = await page.locator('#evalOutputBox').textContent();
    expect(evalOutput.length).toBeGreaterThan(0);

    // Assert run preview or run file path
    await expect(page.locator('#resultMeta')).toContainText('/'); // path contains /

    // 9. Assert that at least one catalog-only or non-selected index is visible
    const catalogOnlyItems = page.locator('.catalog-item.disabled');
    const catalogOnlyCount = await catalogOnlyItems.count();
    expect(catalogOnlyCount).toBeGreaterThanOrEqual(1);
  });
});
