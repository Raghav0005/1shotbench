const { test, expect } = require('@playwright/test');

test.describe('NFCorpus Diagnostics Workbench', () => {
    test.beforeEach(async ({ page }) => {
        const port = process.env.PORT || 10000;
        await page.goto(`http://localhost:${port}`);
    });

    test('verifies readiness panel and setup status', async ({ page }) => {
        // Wait for setup to complete
        await expect(page.locator('.status-item', { hasText: 'Java 21: OK' })).toBeVisible({ timeout: 15000 });
        await expect(page.locator('.status-item', { hasText: 'Fatjar: OK' })).toBeVisible();
        await expect(page.locator('.status-item', { hasText: 'NFCorpus Index: Ready' })).toBeVisible();
        await expect(page.locator('.status-item', { hasText: 'Search Ready: Yes' })).toBeVisible();
    });

    test('runs live NFCorpus query', async ({ page }) => {
        await expect(page.locator('.status-item', { hasText: 'Search Ready: Yes' })).toBeVisible({ timeout: 15000 });

        // Search
        await page.fill('#query-input', 'breast cancer treatment');
        await page.click('button:has-text("Search")');

        // Verify results
        await expect(page.locator('.result-item').first()).toBeVisible({ timeout: 10000 });
        
        const firstResult = page.locator('.result-item').first();
        await expect(firstResult.locator('.rank')).toBeVisible();
        await expect(firstResult.locator('.docid')).toBeVisible();
        await expect(firstResult.locator('.score')).toBeVisible();
        await expect(firstResult.locator('.snippet')).toBeVisible();

        // Verify exact command text is in drawer
        await expect(page.locator('#command-drawer')).toContainText('io.anserini.cli.Search --index beir-v1.0.0-nfcorpus.flat');
    });

    test('runs or verifies evaluation', async ({ page }) => {
        await expect(page.locator('.status-item', { hasText: 'Search Ready: Yes' })).toBeVisible({ timeout: 15000 });

        // Run evaluation
        await page.click('button:has-text("Verify / Rerun Evaluation")');
        
        // Wait for loading to finish
        await expect(page.locator('#eval-loading')).toBeHidden({ timeout: 20000 });

        // Check observed metric is a number
        const observed = await page.locator('#eval-observed').innerText();
        expect(Number.isNaN(parseFloat(observed))).toBe(false);

        // Check expected metric is populated
        const expected = await page.locator('#eval-expected').innerText();
        expect(Number.isNaN(parseFloat(expected))).toBe(false);

        // Check delta or status
        await expect(page.locator('#eval-status')).toBeVisible();
        const statusText = await page.locator('#eval-status').innerText();
        expect(['PASS', 'CLOSE', 'FAIL']).toContain(statusText);

        // Verify commands in drawer
        await expect(page.locator('#command-drawer')).toContainText('io.anserini.search.SearchCollection -index beir-v1.0.0-nfcorpus.flat');
        await expect(page.locator('#command-drawer')).toContainText('io.anserini.eval.TrecEval -c -m ndcg_cut.10');
        await expect(page.locator('#command-drawer')).toContainText('run.beir.nfcorpus.txt');
    });

    test('verifies Docker/Render readiness contract is documented', async () => {
        const fs = require('fs');
        const readme = fs.readFileSync('./README.md', 'utf8');
        expect(readme).toContain('PORT');
        expect(readme).toContain('0.0.0.0');
        expect(readme).toContain('/health');
    });
});
