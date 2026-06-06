import { test, expect } from '@playwright/test';

test.describe('NFCorpus Live Retrieval Diagnostics Workbench', () => {
  test('primary workflow validates Anserini setup, search, and evaluation', async ({ page }) => {
    // 1. Access the web application
    await page.goto('http://localhost:10000');

    // 2. Confirm the visibility of the health and readiness panel
    await expect(page.locator('h2:has-text("Readiness Status")')).toBeVisible();

    // 3. Confirm that NFCorpus is recognized as the active dataset
    await expect(page.locator('text=Dataset: NFCorpus')).toBeVisible();

    // 4. Confirm the Anserini setup status is displayed
    await expect(page.locator('text=Anserini Fatjar:')).toBeVisible();

    // 5. Execute or select a live query against NFCorpus
    await page.click('button:has-text("Live Search")');
    await page.fill('input[placeholder*="query"]', 'cancer');
    await page.click('button[type="submit"]');

    // 6. Confirm that the ranked search results populate with document IDs, ranks, scores, and text/snippets
    await expect(page.locator('.result-card').first()).toBeVisible({ timeout: 15000 });
    const firstResult = page.locator('.result-card').first();
    await expect(firstResult.locator('.docid')).toBeVisible();
    await expect(firstResult.locator('.rank')).toBeVisible();
    await expect(firstResult.locator('.score')).toBeVisible();
    await expect(firstResult.locator('p')).toBeVisible();

    // 7. Confirm the exact CLI commands are visible in the UI
    await expect(page.locator('.command-drawer:has-text("Exact Command Executed")')).toBeVisible();

    // 8. Go to Evaluation Metrics tab
    await page.click('button:has-text("Evaluation Metrics")');

    // 9. Confirm that the evaluation panel renders at least one numeric observed metric
    await expect(page.locator('.metric-card:has-text("Observed") .value')).not.toHaveText('N/A', { timeout: 15000 });
    
    // 10. Confirm that expected metric data is displayed
    const expectedValue = await page.locator('.metric-card:has-text("Expected") .value').innerText();
    expect(parseFloat(expectedValue)).toBeGreaterThan(0);

    // 11. Confirm the visibility of the observed-versus-expected comparison status or delta
    await expect(page.locator('.metric-card:has-text("Status")')).toBeVisible();
    await expect(page.locator('.metric-card:has-text("Delta")')).toBeVisible();

    // 12. Confirm exact commands and artifact paths are visible in the UI
    await expect(page.locator('.command-drawer:has-text("Evaluation Commands")')).toBeVisible();
    await expect(page.locator('.command-drawer:has-text("Generated Artifacts")')).toBeVisible();

    // 13. Confirm the Docker and Render readiness requirements are documented explicitly noting the PORT binding behavior
    await expect(page.locator('text=Port Binding: Uses $PORT env var (default: 10000) for Render compatibility')).toBeVisible();
  });
});
