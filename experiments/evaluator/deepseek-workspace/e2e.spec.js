const { test, expect } = require('@playwright/test');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const WORKSPACE = __dirname;
const PORT = 8090;
const BASE_URL = `http://127.0.0.1:${PORT}`;

let serverProcess;

/**
 * Wait for the server to become ready by polling /api/health.
 */
function waitForServer(url, timeoutMs = 30000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const poll = () => {
      http.get(`${url}/api/health`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else if (Date.now() - start > timeoutMs) {
          reject(new Error('Server did not become healthy in time'));
        } else {
          setTimeout(poll, 500);
        }
      }).on('error', () => {
        if (Date.now() - start > timeoutMs) {
          reject(new Error('Server did not start in time'));
        } else {
          setTimeout(poll, 500);
        }
      });
    };
    poll();
  });
}

test.beforeAll(async () => {
  // Start the Flask server
  serverProcess = spawn('python3', ['app.py'], {
    cwd: WORKSPACE,
    stdio: 'pipe',
    env: { ...process.env, FLASK_ENV: 'development' },
  });

  // Log server output for debugging
  serverProcess.stdout.on('data', (d) => process.stdout.write(`[server] ${d}`));
  serverProcess.stderr.on('data', (d) => process.stderr.write(`[server-err] ${d}`));

  await waitForServer(BASE_URL, 30000);
});

test.afterAll(async () => {
  if (serverProcess) {
    serverProcess.kill('SIGTERM');
    // Give it a moment to clean up
    await new Promise(r => setTimeout(r, 2000));
  }
});

test.describe('Anserini Prebuilt Index Evaluator', () => {

  test('application loads and shows index catalog', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for the index catalog to load
    await page.waitForSelector('.index-item', { timeout: 30000 });

    // Verify we have more than one index in the catalog (not just a hardcoded CACM)
    const indexItems = page.locator('.index-item');
    const count = await indexItems.count();
    expect(count).toBeGreaterThan(1);

    // Verify CACM is present and auto-selected
    const cacmItem = page.locator('.index-item.selected');
    await expect(cacmItem).toBeVisible();
    await expect(cacmItem).toContainText('cacm');

    // Verify CACM shows the evaluable tag
    await expect(cacmItem.locator('.tag-evaluable')).toBeVisible();

    // Verify there are catalog-only (non-evaluable) indexes visible
    const catalogOnlyItems = page.locator('.index-item .tag-catalog');
    const catalogCount = await catalogOnlyItems.count();
    expect(catalogCount).toBeGreaterThan(0);
  });

  test('CACM is selected by default with topics/qrels pairing visible', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for evaluation panel to load AND auto-select CACM
    await page.waitForSelector('#eval-content', { timeout: 30000 });
    await page.waitForSelector('#eval-content[data-state="ready"]', { timeout: 60000 });

    // The eval panel should show index, topics, and qrels for CACM
    const evalContent = page.locator('#eval-content');

    // Verify pairing info is displayed - CACM is in the input values
    const idxInput = evalContent.locator('input[readonly]').first();
    await expect(idxInput).toHaveValue('cacm');

    // Check that the evaluation panel has topics and qrels displayed
    const formInputs = evalContent.locator('input[readonly]');
    const inputCount = await formInputs.count();
    expect(inputCount).toBeGreaterThanOrEqual(2); // at least index + topics (or qrels)

    // Verify metric selector is present
    const metricSelect = evalContent.locator('#metric-select');
    await expect(metricSelect).toBeVisible();

    // Verify metric options include nDCG@10 and Recall@1000
    const options = await metricSelect.locator('option').allTextContents();
    const hasNdcg10 = options.some(o => o.includes('nDCG@10'));
    const hasRecall1000 = options.some(o => o.includes('Recall@1000'));
    expect(hasNdcg10).toBeTruthy();
    expect(hasRecall1000).toBeTruthy();
  });

  test('CACM evaluation produces a numeric score', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for the page to fully load and CACM to be auto-selected
    await page.waitForSelector('#eval-content', { timeout: 30000 });
    await page.waitForSelector('#eval-content[data-state="ready"]', { timeout: 60000 });
    await expect(page.locator('#eval-content input[readonly]').first()).toHaveValue('cacm');

    // Select nDCG@10 metric
    const metricSelect = page.locator('#metric-select');
    await metricSelect.selectOption('ndcg_cut.10');

    // Click Run Evaluation
    const runButton = page.locator('#run-btn');
    await expect(runButton).toBeEnabled({ timeout: 5000 });
    await runButton.click();

    // Wait for the results to appear (should show a score)
    await page.waitForSelector('.result-score', { timeout: 120000 });

    // Verify a numeric score is displayed
    const scoreElement = page.locator('.result-score');
    const scoreText = await scoreElement.textContent();
    const scoreValue = parseFloat(scoreText);
    expect(isNaN(scoreValue)).toBeFalsy();
    expect(scoreValue).toBeGreaterThan(0);
    expect(scoreValue).toBeLessThan(1);

    // Verify run metadata is displayed
    const resultsCard = page.locator('#results-card');
    await expect(resultsCard).toBeVisible();

    // Check for key metadata fields
    const resultsText = await resultsCard.textContent();
    expect(resultsText).toContain('cacm'); // index name
    expect(resultsText).toContain('nDCG@10'); // metric
    expect(resultsText).toContain('Run file'); // run file path
    expect(resultsText).toContain('Eval file'); // eval file path

    // Verify run file preview is present (use nth to avoid strict mode on multiple matches)
    await expect(page.locator('.run-preview').first()).toBeVisible();
  });

  test('nDCG@10 and Recall@1000 metrics are available for CACM', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for eval panel and auto-select
    await page.waitForSelector('#eval-content', { timeout: 30000 });
    await page.waitForSelector('#eval-content[data-state="ready"]', { timeout: 60000 });
    await expect(page.locator('#eval-content input[readonly]').first()).toHaveValue('cacm');

    // Check all metric options
    const metricSelect = page.locator('#metric-select');
    const options = await metricSelect.locator('option').allTextContents();

    // Must include modern ranking metrics nDCG@10 and Recall@1000
    expect(options.some(o => o === 'nDCG@10')).toBeTruthy();
    expect(options.some(o => o === 'Recall@1000')).toBeTruthy();

    // Should also include classic metrics like MAP or P.30
    expect(options.some(o => o.includes('MAP'))).toBeTruthy();
  });

  test('index catalog has both evaluable and catalog-only entries', async ({ page }) => {
    await page.goto(BASE_URL);

    await page.waitForSelector('.index-item', { timeout: 30000 });

    // Verify evaluable entries exist
    const evaluableTags = page.locator('.tag-evaluable');
    const evalCount = await evaluableTags.count();
    expect(evalCount).toBeGreaterThan(0);

    // Verify catalog-only entries exist
    const catalogTags = page.locator('.tag-catalog');
    const catCount = await catalogTags.count();
    expect(catCount).toBeGreaterThan(0);
  });

  test('search filter narrows index list', async ({ page }) => {
    await page.goto(BASE_URL);

    await page.waitForSelector('.index-item', { timeout: 30000 });

    const initialCount = await page.locator('.index-item').count();
    expect(initialCount).toBeGreaterThan(10);

    // Type a filter that should narrow results
    const searchBox = page.locator('#index-search');
    await searchBox.fill('msmarco-v1-passage');

    // Wait for the list to update
    await page.waitForTimeout(500);
    const filteredCount = await page.locator('.index-item').count();
    expect(filteredCount).toBeLessThan(initialCount);
    expect(filteredCount).toBeGreaterThan(0);
  });
});
