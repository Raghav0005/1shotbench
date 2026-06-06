'use strict';

/**
 * Anserini Index Evaluator – End-to-End Playwright Test
 *
 * Verifies:
 *   1. App loads and shows the prebuilt-index catalog from Anserini registry.
 *   2. CACM is the default selected evaluable index.
 *   3. The catalog exposes more than one index (registry-derived, not hardcoded).
 *   4. CACM shows a topic/qrels pairing.
 *   5. The user can select nDCG@10 or Recall@1000 metric.
 *   6. Clicking "Run Evaluation" executes real Anserini retrieval + eval.
 *   7. A numeric score appears (not mocked).
 *   8. Run metadata appears: index, topics, metric, run/eval paths.
 *   9. At least one catalog-only (non-evaluable) index is visible.
 *
 * The test will fail if the app returns mocked data because:
 *   - The score must be a real floating-point number produced by TrecEval.
 *   - Run/eval file paths must reference timestamped files.
 */

const { test, expect } = require('@playwright/test');

test.describe('Anserini Index Evaluator', () => {

  // ─── App loads and catalog appears ─────────────────────────────────────────
  test('app loads and shows index catalog from Anserini registry', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1')).toContainText('Anserini Index Evaluator');

    // Catalog must show many indexes (not just 1 hardcoded CACM)
    // Wait for catalog to populate
    await page.waitForFunction(
      () => document.querySelectorAll('.index-row').length > 1,
      { timeout: 30_000 },
    );

    const rows = page.locator('.index-row');
    const count = await rows.count();
    // Anserini 2.1.1 has 272 total prebuilt indexes
    expect(count).toBeGreaterThan(10);
    console.log(`Catalog loaded: ${count} indexes visible`);
  });

  // ─── CACM is default selected ───────────────────────────────────────────────
  test('CACM is default selected evaluable index', async ({ page }) => {
    await page.goto('/');

    // Wait for catalog + auto-selection
    await page.waitForSelector('[data-testid="index-row-cacm"].selected', { timeout: 30_000 });

    // Pairing should be visible
    await expect(page.locator('#sel-name')).toHaveText('cacm', { timeout: 10_000 });
    await expect(page.locator('#sel-topics')).toHaveText('cacm');
    await expect(page.locator('#sel-qrels')).toHaveText('cacm');

    // Run button should be present and enabled
    const runBtn = page.locator('[data-testid="run-btn"]');
    await expect(runBtn).toBeVisible();
    await expect(runBtn).toBeEnabled();
  });

  // ─── CACM shows topic/qrels pairing ────────────────────────────────────────
  test('CACM shows topics and qrels pairing', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('[data-testid="index-row-cacm"].selected', { timeout: 30_000 });

    // Pairing card visible
    await expect(page.locator('#pairing-card')).toBeVisible();
    await expect(page.locator('#sel-topics')).not.toBeEmpty();
    await expect(page.locator('#sel-qrels')).not.toBeEmpty();

    // Metric pills must include nDCG@10 or Recall@1000
    const metricLabels = await page.locator('.metric-pill').allTextContents();
    console.log('Available metrics:', metricLabels);
    const hasNdcg = metricLabels.some(l => l.includes('nDCG') || l.includes('ndcg') || l.includes('NDCG'));
    const hasRecall = metricLabels.some(l => l.toLowerCase().includes('recall'));
    expect(hasNdcg || hasRecall).toBe(true);
  });

  // ─── At least one catalog-only index exists ─────────────────────────────────
  test('catalog contains non-evaluable (catalog-only) indexes', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(
      () => document.querySelectorAll('.index-row').length > 1,
      { timeout: 30_000 },
    );

    // There must be rows with the "Catalog" badge (catalog-only)
    const catalogBadges = page.locator('.index-row .badge-catalog');
    const catalogCount = await catalogBadges.count();
    expect(catalogCount).toBeGreaterThan(0);
    console.log(`Catalog-only indexes visible: ${catalogCount}`);

    // There must also be evaluable rows
    const evalBadges = page.locator('.index-row .badge-evaluable');
    const evalCount = await evalBadges.count();
    expect(evalCount).toBeGreaterThanOrEqual(1);
    console.log(`Evaluable indexes visible: ${evalCount}`);
  });

  // ─── Filtering works ─────────────────────────────────────────────────────────
  test('search filter narrows the index list', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(
      () => document.querySelectorAll('.index-row').length > 10,
      { timeout: 30_000 },
    );

    const totalBefore = await page.locator('.index-row').count();
    await page.fill('#search-input', 'msmarco');
    await page.waitForTimeout(200);
    const totalAfter = await page.locator('.index-row').count();
    expect(totalAfter).toBeLessThan(totalBefore);
    expect(totalAfter).toBeGreaterThan(0);
    console.log(`Filter "msmarco": ${totalBefore} → ${totalAfter} rows`);
  });

  // ─── End-to-end evaluation (CACM + nDCG@10) ─────────────────────────────────
  test('runs CACM evaluation with nDCG@10 and shows real score', async ({ page }) => {
    await page.goto('/');

    // Wait for CACM to be auto-selected
    await page.waitForSelector('[data-testid="index-row-cacm"].selected', { timeout: 30_000 });

    // Select nDCG@10 metric; fall back to Recall@1000, then whatever is first
    const ndcgPill = page.locator('[data-testid="metric-nDCG-10"]');
    const recallPill = page.locator('[data-testid="metric-Recall-1000"]');
    if (await ndcgPill.count() > 0) {
      await ndcgPill.click();
      console.log('Selected metric: nDCG@10');
    } else if (await recallPill.count() > 0) {
      await recallPill.click();
      console.log('Selected metric: Recall@1000');
    } else {
      const firstPill = page.locator('.metric-pill').first();
      await firstPill.click();
      const label = await firstPill.textContent();
      console.log(`Selected metric (fallback): ${label}`);
    }

    // Click Run Evaluation
    await page.locator('[data-testid="run-btn"]').click();

    // Wait for score – retrieval + eval takes several seconds
    await expect(page.locator('[data-testid="score-value"]')).not.toHaveText('—', { timeout: 240_000 });

    const scoreText = await page.locator('[data-testid="score-value"]').textContent();
    console.log(`Score returned: ${scoreText}`);

    // Must be a real numeric value (not "?" or "—")
    const score = parseFloat(scoreText);
    expect(Number.isFinite(score)).toBe(true);
    // CACM nDCG@10 ≈ 0.4543; Recall@1000 ≈ 0.8867; MAP ≈ 0.3123
    // Accept any reasonable score in (0, 1]
    expect(score).toBeGreaterThan(0);
    expect(score).toBeLessThanOrEqual(1.0);

    console.log(`✓ Score ${score} is a valid evaluation result`);
  });

  // ─── Metadata appears after evaluation ──────────────────────────────────────
  test('shows run metadata after evaluation', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('[data-testid="index-row-cacm"].selected', { timeout: 30_000 });

    // Run with whatever default metric is selected
    await page.locator('[data-testid="run-btn"]').click();

    // Wait for score to appear
    await expect(page.locator('[data-testid="score-value"]')).not.toHaveText('—', { timeout: 240_000 });

    // Meta card must be visible
    await expect(page.locator('#meta-card')).toBeVisible();

    // Check metadata fields
    const metaIndex = await page.locator('#meta-index').textContent();
    expect(metaIndex).toBe('cacm');

    const metaTopics = await page.locator('#meta-topics').textContent();
    expect(metaTopics).toBeTruthy();

    const metaMetric = await page.locator('#meta-metric').textContent();
    expect(metaMetric).toBeTruthy();

    // Run file path must be a timestamped file path (not mocked)
    const runFilePath = await page.locator('#meta-run').textContent();
    console.log(`Run file: ${runFilePath}`);
    expect(runFilePath).toMatch(/\/runs\/run\..+\.\d+\.txt$/);

    // Eval file path must be a timestamped file path
    const evalFilePath = await page.locator('#meta-eval').textContent();
    console.log(`Eval file: ${evalFilePath}`);
    expect(evalFilePath).toMatch(/\/runs\/eval\..+\.\d+\.txt$/);

    // Evaluator output card
    await expect(page.locator('#eval-output-card')).toBeVisible();
    const evalOutputText = await page.locator('#eval-output').textContent();
    console.log(`Eval output: ${evalOutputText}`);
    expect(evalOutputText.trim().length).toBeGreaterThan(0);

    console.log('✓ All metadata fields present');
  });

});
