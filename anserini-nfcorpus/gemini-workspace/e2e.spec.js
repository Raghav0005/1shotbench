const { test, expect } = require('@playwright/test');

test.describe('NFCorpus Live Retrieval Diagnostics', () => {
  test('End-to-End Workflow', async ({ page }) => {
    const port = process.env.PORT || 10000;
    await page.goto(`http://localhost:${port}`);

    // Verify readiness panel
    await expect(page.locator('#health-status')).toContainText('App:');
    await expect(page.locator('#health-status')).toContainText('Anserini:');
    await expect(page.locator('#health-status')).toContainText('NFCorpus:');
    
    // Check if the dataset is mentioned
    await expect(page.locator('body')).toContainText('NFCorpus');

    // Wait for the evaluation to load
    await expect(page.locator('#eval-content')).toContainText('nDCG@10');
    // Expected metric check
    await expect(page.locator('#eval-content')).toContainText('0.3218');
    // Status check
    await expect(page.locator('#eval-content')).toContainText('PASS');
    
    // Command check
    await expect(page.locator('#commands-content')).toContainText('java -cp anserini');
    await expect(page.locator('#commands-content')).toContainText('trec_eval');

    // Live search
    await page.click('text="treatment of breast cancer"');
    
    // Verify search results
    await expect(page.locator('.result-item').first()).toBeVisible({ timeout: 15000 });
    
    // Verify result contains ID and Score
    const firstResult = page.locator('.result-item').first();
    await expect(firstResult).toContainText('ID:');
    await expect(firstResult).toContainText('Score:');

    // Verify commands updated to search command
    await expect(page.locator('#commands-content')).toContainText('io.anserini.cli.Search');
  });
});
