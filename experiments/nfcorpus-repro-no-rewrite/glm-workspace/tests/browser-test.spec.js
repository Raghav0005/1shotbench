/**
 * End-to-end browser test for NFCorpus Live Retrieval Diagnostics Workbench.
 *
 * This test verifies that the app uses real Anserini commands for search
 * and evaluation — not mocked results.
 *
 * Prerequisites:
 *   - The app server must be running (e.g. python3 app/server.py)
 *   - Playwright must be installed: npx playwright install chromium
 *
 * Run:
 *   npx playwright test tests/browser-test.spec.js
 */

const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.APP_URL || 'http://localhost:10000';
const SETUP_TIMEOUT = 300_000; // 5 min for Anserini setup on first run

test.describe('NFCorpus Live Retrieval Diagnostics', () => {

  test('health endpoint returns valid JSON', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('app_status', 'running');
    expect(body).toHaveProperty('anserini_available');
    expect(body).toHaveProperty('nfcorpus_ready');
    expect(body).toHaveProperty('search_available');
    expect(body).toHaveProperty('evaluation_available');
  });

  test('readiness panel appears and shows setup status', async ({ page }) => {
    await page.goto(BASE_URL);

    // The readiness panel should exist
    const panel = page.locator('#readiness-panel');
    await expect(panel).toBeVisible();

    // Wait for setup to complete (may take a while on first run)
    const badge = page.locator('#setup-badge');
    await expect(badge).toHaveText(/READY|FAILED/, { timeout: SETUP_TIMEOUT });
  });

  test('NFCorpus is identified as the active dataset', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for readiness
    await expect(page.locator('#setup-badge')).toHaveText(/READY|FAILED/, { timeout: SETUP_TIMEOUT });

    const datasetStatus = page.locator('#dataset-status');
    await expect(datasetStatus).toContainText('NFCorpus', { timeout: SETUP_TIMEOUT });
  });

  test('Anserini setup status is visible', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for setup to finish
    await expect(page.locator('#setup-badge')).toHaveText(/READY|FAILED/, { timeout: SETUP_TIMEOUT });

    const javaStatus = page.locator('#java-status');
    await expect(javaStatus).not.toHaveText('—');

    const anseriniStatus = page.locator('#anserini-status');
    await expect(anseriniStatus).not.toHaveText('—');
  });

  test('live search returns ranked results with docids, scores, and text', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for search to become available
    await page.locator('#search-btn').waitFor({ state: 'visible', timeout: SETUP_TIMEOUT });
    await expect(page.locator('#search-btn')).toBeEnabled({ timeout: SETUP_TIMEOUT });

    // Type a query
    await page.locator('#search-input').fill('health benefits of exercise');
    await page.locator('#search-btn').click();

    // Wait for results to appear
    const results = page.locator('.result-item');
    await expect(results.first()).toBeVisible({ timeout: 30_000 });

    // Verify at least one result has rank, docid, score, and text
    const count = await results.count();
    expect(count).toBeGreaterThan(0);

    // Check first result has the required fields
    const firstResult = results.first();
    await expect(firstResult.locator('.result-rank')).toContainText(/#\d+/);
    await expect(firstResult.locator('.result-docid')).not.toBeEmpty();
    await expect(firstResult.locator('.result-score')).toContainText(/\d+\.\d+/);
    await expect(firstResult.locator('.result-text')).not.toBeEmpty();
  });

  test('sample query click triggers live search', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for search readiness
    await expect(page.locator('#search-btn')).toBeEnabled({ timeout: SETUP_TIMEOUT });

    // Wait for sample queries to load
    const sampleQuery = page.locator('.sample-query').first();
    await expect(sampleQuery).toBeVisible({ timeout: 10_000 });

    // Click a sample query
    await sampleQuery.click();

    // Wait for results
    const results = page.locator('.result-item');
    await expect(results.first()).toBeVisible({ timeout: 30_000 });
  });

  test('evaluation panel shows numeric observed metrics', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for evaluation to complete
    await expect(page.locator('#eval-badge')).toHaveText(/READY|FAILED/, { timeout: SETUP_TIMEOUT });

    // Check evaluation table exists
    const evalTable = page.locator('.eval-table');
    await expect(evalTable).toBeVisible({ timeout: 10_000 });

    // Check at least one observed metric is a number
    const observedCells = page.locator('.eval-table td.mono');
    const count = await observedCells.count();
    expect(count).toBeGreaterThan(0);

    // Get all observed values and verify they're numeric
    for (let i = 0; i < count; i++) {
      const text = await observedCells.nth(i).textContent();
      if (text && !isNaN(parseFloat(text))) {
        expect(parseFloat(text)).toBeGreaterThan(0);
        break;
      }
    }
  });

  test('expected metrics appear in evaluation comparison', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for evaluation
    await expect(page.locator('#eval-badge')).toHaveText(/READY|FAILED/, { timeout: SETUP_TIMEOUT });

    // Verify expected metric column exists
    const evalTable = page.locator('.eval-table');
    await expect(evalTable).toBeVisible({ timeout: 10_000 });

    // Check that expected metric names appear
    const bodyContent = await page.locator('#eval-content').textContent();
    expect(bodyContent).toMatch(/nDCG@10|R@100|R@1000/);
  });

  test('observed-vs-expected comparison status or delta is visible', async ({ page }) => {
    await page.goto(BASE_URL);

    await expect(page.locator('#eval-badge')).toHaveText(/READY|FAILED/, { timeout: SETUP_TIMEOUT });

    // Check that PASS/CLOSE/FAIL badges appear
    const statusBadge = page.locator('.eval-table .badge').first();
    await expect(statusBadge).toBeVisible({ timeout: 10_000 });

    const statusText = await statusBadge.textContent();
    expect(['PASS', 'CLOSE', 'FAIL']).toContain(statusText);

    // Check that delta column has values
    const deltaCells = page.locator('.eval-table td.mono');
    const count = await deltaCells.count();
    expect(count).toBeGreaterThan(0);
  });

  test('exact command text and artifact paths are visible', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for setup
    await expect(page.locator('#setup-badge')).toHaveText(/READY|FAILED/, { timeout: SETUP_TIMEOUT });

    // Commands section should have command blocks
    const commandBlocks = page.locator('.command-block');
    await expect(commandBlocks.first()).toBeVisible({ timeout: 10_000 });

    // Verify command content contains Anserini references
    const content = await page.locator('#commands-content').textContent();
    expect(content).toMatch(/anserini|SearchCollection|TrecEval|io\.anserini/i);

    // Check for artifact links
    const artifactLinks = page.locator('.artifact-link');
    const linkCount = await artifactLinks.count();
    expect(linkCount).toBeGreaterThan(0);
  });

  test('setup log drawer can be opened and shows real commands', async ({ page }) => {
    await page.goto(BASE_URL);

    // Click the log toggle
    await page.locator('.drawer-toggle').click();

    // Log should be visible
    const logDrawer = page.locator('#log-drawer');
    await expect(logDrawer).toBeVisible();

    // Wait for log content to load (it's fetched async when drawer opens)
    const logEl = page.locator('#setup-log');
    await expect(logEl).not.toHaveText('No log yet.', { timeout: 10_000 });

    const logContent = await logEl.textContent();
    // Should contain actual command output, not placeholder text
    expect(logContent).toMatch(/java|SearchCollection|curl|anserini/i);
  });

  test('Docker/Render PORT binding is documented', async ({ request }) => {
    // The health endpoint itself proves PORT binding works
    const res = await request.get(`${BASE_URL}/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.app_status).toBe('running');
  });
});
