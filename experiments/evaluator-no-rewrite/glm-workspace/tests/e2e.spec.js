const { test, expect } = require('@playwright/test');
const { spawn } = require('child_process');
const http = require('http');

const PORT = 3456;
const BASE = `http://localhost:${PORT}`;

function waitForServer(maxWait = 30000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    function check() {
      http.get(`${BASE}/api/health`, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const h = JSON.parse(data);
            if (h.ok && h.jarExists) return resolve(true);
          } catch {}
          if (Date.now() - start > maxWait) return reject(new Error('Server health check failed'));
          setTimeout(check, 1000);
        });
      }).on('error', () => {
        if (Date.now() - start > maxWait) return reject(new Error('Server not reachable'));
        setTimeout(check, 1000);
      });
    }
    check();
  });
}

test.describe('Anserini Prebuilt Index Evaluator', () => {
  let serverProcess;

  test.beforeAll(async () => {
    // Start the server if not already running
    serverProcess = spawn('node', ['server.js'], {
      cwd: __dirname + '/..',
      env: { ...process.env, ANSERINI_JAR: process.env.ANSERINI_JAR || '' },
      stdio: 'pipe'
    });

    await waitForServer();
  });

  test.afterAll(async () => {
    if (serverProcess) {
      serverProcess.kill();
    }
  });

  test('CACM is selected by default and shows evaluation pairing', async ({ page }) => {
    await page.goto(BASE);

    // Wait for catalog to load
    await page.waitForSelector('.index-item', { timeout: 60000 });

    // Verify CACM is selected (has selected class)
    const cacmItem = page.locator('.index-item.selected');
    await expect(cacmItem).toBeVisible();
    await expect(cacmItem).toContainText('cacm');

    // Verify evaluation dashboard shows CACM pairing info
    const evalCard = page.locator('#evalCard');
    await expect(evalCard).toContainText('cacm');
    await expect(evalCard).toContainText('cacm / qrels: cacm');

    // Verify metric selector has nDCG@10 and Recall@1000
    const metricSelect = page.locator('#metricSelect');
    const metricOptions = metricSelect.locator('option');
    const metricTexts = await metricOptions.allTextContents();
    expect(metricTexts).toContain('nDCG@10');
    expect(metricTexts).toContain('Recall@1000');
  });

  test('Index catalog exposes more than just CACM', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector('.index-item', { timeout: 60000 });

    // Should have many indexes in the catalog
    const items = page.locator('.index-item');
    const count = await items.count();
    expect(count).toBeGreaterThan(5);

    // Should have at least one catalog-only item
    const catalogOnly = page.locator('.index-item.catalog-only');
    const catalogOnlyCount = await catalogOnly.count();
    expect(catalogOnlyCount).toBeGreaterThan(0);
  });

  test('Run CACM evaluation with nDCG@10 and verify results', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector('.index-item', { timeout: 60000 });

    // Select nDCG@10 metric
    await page.locator('#metricSelect').selectOption({ label: 'nDCG@10' });

    // Click Run Evaluation
    await page.locator('#runBtn').click();

    // Wait for results (CACM is fast but still needs time)
    await page.waitForSelector('#resultCard', { timeout: 120000 });
    await page.waitForSelector('.score-display', { timeout: 10000 });

    // Verify score is a number
    const scoreText = await page.locator('.score-display').textContent();
    const score = parseFloat(scoreText);
    expect(score).not.toBeNaN();
    expect(score).toBeGreaterThan(0);
    expect(score).toBeLessThanOrEqual(1);

    // Verify result metadata
    const resultCard = page.locator('#resultContent');
    await expect(resultCard).toContainText('cacm');
    await expect(resultCard).toContainText('nDCG@10');

    // Verify run file path is shown
    await expect(resultCard).toContainText('anserini-eval');

    // Verify evaluation output contains the score line
    const evalOutput = page.locator('.eval-output');
    const evalText = await evalOutput.textContent();
    expect(evalText).toContain('ndcg_cut_10');
    expect(evalText).toMatch(/0\.\d+/);
  });

  test('Run CACM evaluation with Recall@1000 and verify results', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector('.index-item', { timeout: 60000 });

    // Select Recall@1000
    await page.locator('#metricSelect').selectOption({ label: 'Recall@1000' });

    await page.locator('#runBtn').click();

    await page.waitForSelector('#resultCard', { timeout: 120000 });
    await page.waitForSelector('.score-display', { timeout: 10000 });

    const scoreText = await page.locator('.score-display').textContent();
    const score = parseFloat(scoreText);
    expect(score).not.toBeNaN();
    expect(score).toBeGreaterThan(0);
    expect(score).toBeLessThanOrEqual(1);

    const resultCard = page.locator('#resultContent');
    await expect(resultCard).toContainText('Recall@1000');
  });

  test('Catalog-only indexes are visible and not clickable for evaluation', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector('.index-item', { timeout: 60000 });

    // Find a catalog-only index
    const catalogOnly = page.locator('.index-item.catalog-only').first();
    await expect(catalogOnly).toBeVisible();
    await expect(catalogOnly).toContainText('CATALOG');

    // Clicking should not change selection
    const initialSelected = await page.locator('.index-item.selected').textContent();
    await catalogOnly.click();
    const afterClick = await page.locator('.index-item.selected').textContent();
    expect(initialSelected).toBe(afterClick);
  });
});
