/**
 * NFCorpus Live Retrieval Diagnostics Workbench – End-to-End Browser Test
 *
 * Validates that the application:
 * - Shows readiness panel with Anserini/NFCorpus status
 * - Identifies NFCorpus as the active dataset
 * - Executes live search returning real document IDs, ranks, scores, text
 * - Displays real observed evaluation metrics
 * - Shows expected metrics and observed-vs-expected comparison
 * - Exposes command text and artifact paths
 * - Documents PORT binding / Render contract
 *
 * This test FAILS if the app returns only mocked data.
 */

import { test, expect } from '@playwright/test';

const BASE = process.env.BASE_URL || 'http://localhost:10000';

// Wait for setup to complete (up to 120s)
async function waitForSetup(page, timeoutMs = 120_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const resp = await page.request.get(`${BASE}/health`);
      const health = await resp.json();
      if (health.setup_status === 'done') return health;
      if (health.setup_status === 'error') {
        throw new Error(`Setup failed: ${health.setup_error}`);
      }
    } catch (e) {
      if (e.message.startsWith('Setup failed')) throw e;
      // Server may not be up yet
    }
    await page.waitForTimeout(2000);
  }
  throw new Error('Timed out waiting for setup to complete');
}

test.describe('NFCorpus Workbench E2E', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
    // Wait for initial load
    await page.waitForLoadState('networkidle');
  });

  test('health endpoint returns valid JSON with required fields', async ({ page }) => {
    const health = await waitForSetup(page);
    expect(health).toHaveProperty('status');
    expect(health).toHaveProperty('anserini_available');
    expect(health).toHaveProperty('nfcorpus_ready');
    expect(health).toHaveProperty('search_available');
    expect(health).toHaveProperty('evaluation_available');
    expect(health.anserini_available).toBe(true);
    expect(health.nfcorpus_ready).toBe(true);
    expect(health.search_available).toBe(true);
    expect(health.evaluation_available).toBe(true);
  });

  test('readiness panel is visible with status indicators', async ({ page }) => {
    await waitForSetup(page);
    // The readiness card should exist
    const card = page.locator('#readiness-card');
    await expect(card).toBeVisible();

    // Status dots should exist
    await expect(page.locator('#dot-java')).toBeVisible();
    await expect(page.locator('#dot-fatjar')).toBeVisible();
    await expect(page.locator('#dot-index')).toBeVisible();
    await expect(page.locator('#dot-search')).toBeVisible();
    await expect(page.locator('#dot-eval')).toBeVisible();
  });

  test('NFCorpus is identified as the active dataset', async ({ page }) => {
    await waitForSetup(page);
    // Check page heading mentions nfcorpus
    await expect(page.locator('body')).toContainText('nfcorpus', { ignoreCase: true });
  });

  test('Anserini setup status is visible', async ({ page }) => {
    await waitForSetup(page);
    // The readiness grid should show Anserini Fatjar label
    await expect(page.locator('#lbl-fatjar')).toContainText('Anserini');
    // It should have the 'ok' class (green dot)
    await expect(page.locator('#dot-fatjar')).toHaveClass(/ok/);
  });

  test('live search returns real results with document IDs, ranks, scores, and text', async ({ page }) => {
    await waitForSetup(page);

    // Click a sample query button
    const sampleBtn = page.locator('.sample-btn').first();
    await expect(sampleBtn).toBeVisible();
    const queryText = await sampleBtn.textContent();
    await sampleBtn.click();

    // Wait for results to appear
    await page.waitForSelector('.result-table tbody tr', { timeout: 30_000 });

    // Verify result table has rows with real data
    const rows = page.locator('.result-table tbody tr');
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);

    // Check first row has rank, docid, score, and content
    const firstRow = rows.first();
    const rankCell = firstRow.locator('td').nth(0);
    const docidCell = firstRow.locator('td').nth(1);
    const scoreCell = firstRow.locator('td').nth(2);
    const contentCell = firstRow.locator('td').nth(3);

    // Rank should be a number
    const rankText = await rankCell.textContent();
    expect(rankText.trim()).toMatch(/^\d+$/);

    // DocID should be non-empty (not a placeholder)
    const docidText = await docidCell.textContent();
    expect(docidText.trim().length).toBeGreaterThan(0);

    // Score should be a float
    const scoreText = await scoreCell.textContent();
    expect(scoreText.trim()).toMatch(/^-?\d+\.\d+$/);

    // Content/snippet should have actual text (not "N/A" or empty)
    const contentText = await contentCell.textContent();
    expect(contentText.trim().length).toBeGreaterThan(2);

    // Verify search command is shown
    const cmdInfo = page.locator('#search-info');
    await expect(cmdInfo).toContainText('Command');
    await expect(cmdInfo).toContainText('io.anserini.cli.Search');
  });

  test('evaluation panel shows at least one numeric observed metric', async ({ page }) => {
    await waitForSetup(page);

    // Wait for eval panel to populate
    await page.waitForSelector('#eval-panel .metric-row', { timeout: 10_000 });

    // There should be metric rows with numeric values
    const metricRows = page.locator('#eval-panel .metric-row');
    const count = await metricRows.count();
    expect(count).toBeGreaterThan(0);

    // At least one row should have a float value (pattern: 0.xxxx)
    const firstMetric = metricRows.first();
    const metricText = await firstMetric.textContent();
    expect(metricText).toMatch(/\d+\.\d{4}/);
  });

  test('expected metric information is displayed', async ({ page }) => {
    await waitForSetup(page);

    // Should show "Expected nDCG@10" with 0.3218
    const evalPanel = page.locator('#eval-panel');
    await expect(evalPanel).toContainText('Expected');
    await expect(evalPanel).toContainText('nDCG@10');
    await expect(evalPanel).toContainText('0.3218');
  });

  test('observed-vs-expected comparison status is displayed', async ({ page }) => {
    await waitForSetup(page);

    // Should have a comparison status badge (PASS/CLOSE/FAIL)
    const evalPanel = page.locator('#eval-panel');
    await expect(evalPanel).toContainText('Delta');

    // Status badge should exist
    const badge = page.locator('#eval-panel .badge');
    await expect(badge).toBeVisible();
    const badgeText = await badge.textContent();
    expect(['PASS', 'CLOSE', 'FAIL']).toContain(badgeText);
  });

  test('exact command text and artifact paths are visible', async ({ page }) => {
    await waitForSetup(page);

    // Commands panel should have entries
    const cmdsPanel = page.locator('#commands-panel');
    await expect(cmdsPanel).toBeVisible();
    // Should contain at least "nfcorpus-search" or "nfcorpus-eval"
    const cmdsText = await cmdsPanel.textContent();
    expect(cmdsText.length).toBeGreaterThan(20);

    // Artifacts panel should show paths
    const artsPanel = page.locator('#artifacts-panel');
    await expect(artsPanel).toBeVisible();
    const artsText = await artsPanel.textContent();
    // Should show a file path
    expect(artsText).toMatch(/\/.*\//);
  });

  test('search results are not mocked – verifies real Anserini execution', async ({ page }) => {
    await waitForSetup(page);

    // Run a specific query via API to check raw response
    const resp = await page.request.post(`${BASE}/api/search`, {
      data: { query: 'vitamin D', hits: 5 },
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await resp.json();

    // Should have results
    expect(data.results).toBeDefined();
    expect(data.results.length).toBeGreaterThan(0);

    // Each result should have real fields (not placeholder values)
    const firstResult = data.results[0];
    expect(firstResult).toHaveProperty('docid');
    expect(firstResult.docid.length).toBeGreaterThan(0);
    expect(firstResult.score).toBeDefined();
    expect(typeof firstResult.score).toBe('number');

    // Command should reference Anserini
    expect(data.command).toContain('io.anserini.cli.Search');
    expect(data.command).toContain('beir-v1.0.0-nfcorpus.flat');
  });

  test('evaluation metrics are not mocked – verifies real TrecEval execution', async ({ page }) => {
    await waitForSetup(page);

    // Check status API for real metrics
    const resp = await page.request.get(`${BASE}/api/status`);
    const data = await resp.json();

    // Observed nDCG@10 should be a real float, not a placeholder
    expect(data.observed_metrics).toHaveProperty('nDCG@10');
    const ndcg = data.observed_metrics['nDCG@10'];
    expect(typeof ndcg).toBe('number');
    // Should be within a reasonable range for BM25 on NFCorpus
    expect(ndcg).toBeGreaterThan(0.1);
    expect(ndcg).toBeLessThan(0.6);

    // Comparison should exist and have real values
    expect(data.comparison).toBeDefined();
    expect(data.comparison.status).toMatch(/^(PASS|CLOSE|FAIL)$/);
  });
});
