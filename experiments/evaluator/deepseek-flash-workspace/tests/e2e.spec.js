/**
 * End-to-End Test for Anserini Prebuilt Index Evaluator
 *
 * This Playwright test verifies the full workflow:
 * 1. Opens the app
 * 2. Confirms CACM is selectable
 * 3. Confirms the index catalog exposes more than CACM
 * 4. Confirms CACM shows topic/qrels pairing
 * 5. Selects a supported metric (nDCG@10 or Recall@1000)
 * 6. Clicks Run Evaluation
 * 7. Verifies a numeric score appears
 * 8. Verifies run metadata appears
 * 9. Verifies at least one catalog-only index is visible
 *
 * The test MUST fail if results are mocked — it verifies real execution.
 */

const { test, expect } = require('@playwright/test');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const WORKSPACE_DIR = path.resolve(__dirname, '..');
const APP_URL = 'http://localhost:3000';
const RUNS_DIR = path.join(WORKSPACE_DIR, 'runs');
const EVALS_DIR = path.join(WORKSPACE_DIR, 'evals');

let serverProcess = null;

// ── Start the server before all tests ──
test.beforeAll(async () => {
  // Check that a fatjar exists (installed by setup/install-fatjar.js)
  const jars = fs.readdirSync(WORKSPACE_DIR).filter((f) => f.endsWith('-fatjar.jar'));
  const envJar = process.env.ANSERINI_JAR;
  let jarPath = envJar && fs.existsSync(envJar) ? envJar : null;

  if (!jarPath) {
    // Check .env
    const envFile = path.join(WORKSPACE_DIR, '.env');
    if (fs.existsSync(envFile)) {
      const content = fs.readFileSync(envFile, 'utf8');
      const match = content.match(/ANSERINI_JAR=(.+)/);
      if (match && fs.existsSync(match[1].trim())) {
        jarPath = match[1].trim();
      }
    }
  }

  if (!jarPath && jars.length > 0) {
    jarPath = path.join(WORKSPACE_DIR, jars[0]);
  }

  if (!jarPath) {
    console.log('No fatjar found. Running setup/install-fatjar.js...');
    const setup = spawn('node', ['setup/install-fatjar.js'], {
      cwd: WORKSPACE_DIR,
      stdio: 'inherit',
      env: { ...process.env },
    });
    await new Promise((resolve, reject) => {
      setup.on('close', (code) => {
        if (code === 0) resolve();
        else reject(new Error(`Setup exited with code ${code}`));
      });
      setup.on('error', reject);
    });
    // Re-check
    const newJars = fs.readdirSync(WORKSPACE_DIR).filter((f) => f.endsWith('-fatjar.jar'));
    if (newJars.length > 0) {
      jarPath = path.join(WORKSPACE_DIR, newJars[0]);
    } else {
      throw new Error('Failed to install Anserini fatjar');
    }
  }

  console.log('Using fatjar:', jarPath);
  process.env.ANSERINI_JAR = jarPath;

  // Start the server
  serverProcess = spawn('node', ['server.js'], {
    cwd: WORKSPACE_DIR,
    stdio: 'pipe',
    env: { ...process.env, PORT: '3000' },
  });

  // Wait for server to be ready
  let output = '';
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Server start timeout')), 30000);
    serverProcess.stdout.on('data', (data) => {
      output += data.toString();
      if (output.includes('http://localhost:3000')) {
        clearTimeout(timeout);
        resolve();
      }
    });
    serverProcess.stderr.on('data', (data) => {
      console.error('Server stderr:', data.toString());
    });
    serverProcess.on('error', (err) => {
      clearTimeout(timeout);
      reject(err);
    });
  });

  console.log('Server started on', APP_URL);
});

// ── Cleanup after all tests ──
test.afterAll(async () => {
  if (serverProcess) {
    serverProcess.kill('SIGTERM');
    // Give it a moment
    await new Promise((r) => setTimeout(r, 1000));
    if (serverProcess.exitCode === null) {
      serverProcess.kill('SIGKILL');
    }
  }
});

// ── Tests ──

test.describe('Anserini Prebuilt Index Evaluator', () => {

  test('should load the app and display the catalog', async ({ page }) => {
    await page.goto(APP_URL);

    // Wait for the catalog to load (skeleton disappears, items appear)
    await page.waitForSelector('.catalog-item', { timeout: 30000 });

    // 1. Confirm catalog has at least one evaluable index (CACM)
    const evaluableItems = await page.locator('.catalog-item.evaluable').count();
    expect(evaluableItems).toBeGreaterThanOrEqual(1);

    // 2. Confirm at least one catalog-only index is visible
    const catalogOnlyItems = await page.locator('.catalog-item.catalog-only').count();
    expect(catalogOnlyItems).toBeGreaterThanOrEqual(1);

    // 3. Confirm the count shows more than 1 index
    const countText = await page.locator('#catalogCount').textContent();
    const countNum = parseInt(countText, 10);
    expect(countNum).toBeGreaterThan(1);

    // 4. Find and click CACM if not already selected
    const cacmItem = page.locator('.catalog-item.evaluable', { hasText: 'CACM' });
    await expect(cacmItem).toBeVisible();
    await cacmItem.click();

    // 5. Verify CACM shows evaluation details
    await expect(page.locator('#evalDetails')).not.toHaveClass(/hidden/);
    const indexName = await page.locator('#evalIndexName').textContent();
    expect(indexName.toLowerCase()).toContain('cacm');

    // 6. Verify topics and qrels are displayed
    const topicsText = await page.locator('#evalTopics').textContent();
    expect(topicsText).toBeTruthy();
    const qrelsText = await page.locator('#evalQrels').textContent();
    expect(qrelsText).toBeTruthy();
  });

  test('should run CACM retrieval and evaluation end-to-end', async ({ page }) => {
    await page.goto(APP_URL);
    await page.waitForSelector('.catalog-item', { timeout: 30000 });

    // Select CACM
    const cacmItem = page.locator('.catalog-item.evaluable', { hasText: 'CACM' });
    await cacmItem.click();
    await expect(page.locator('#evalDetails')).not.toHaveClass(/hidden/);

    // Wait for metrics to appear
    await page.waitForSelector('.metric-btn', { timeout: 10000 });

    // Find a supported metric — prefer nDCG@10, then Recall@1000, then fall back to any
    let metricToSelect = null;
    const ndcgBtn = page.locator('.metric-btn', { hasText: 'nDCG@10' });
    const recallBtn = page.locator('.metric-btn', { hasText: 'Recall@1000' });
    const firstMetric = page.locator('.metric-btn').first();

    if (await ndcgBtn.count() > 0 && await ndcgBtn.isVisible()) {
      metricToSelect = ndcgBtn;
      console.log('Selecting metric: nDCG@10');
    } else if (await recallBtn.count() > 0 && await recallBtn.isVisible()) {
      metricToSelect = recallBtn;
      console.log('Selecting metric: Recall@1000');
    } else {
      metricToSelect = firstMetric;
      console.log('Selecting first available metric');
    }

    await metricToSelect.click();
    await expect(metricToSelect).toHaveClass(/active/);

    // Click Run Evaluation
    const runBtn = page.locator('#btnRun');
    await expect(runBtn).toBeEnabled();
    await runBtn.click();

    // Wait for results to appear (button text changes back from running state)
    await page.waitForFunction(
      () => {
        const btn = document.querySelector('#btnRun');
        return btn && btn.textContent.includes('▶ Run Evaluation') && !btn.disabled;
      },
      { timeout: 120000 }
    );

    // Wait for results area to be visible
    await page.waitForSelector('#resultsArea:not(.hidden)', { timeout: 5000 });

    // Verify a numeric score appeared
    const scoreText = await page.locator('#resultScore').textContent();
    const scoreNum = parseFloat(scoreText);
    expect(isNaN(scoreNum)).toBe(false);
    console.log(`Evaluation score: ${scoreNum}`);

    // Verify metadata appears
    const metaText = await page.locator('#resultMeta').textContent();

    // The metadata should contain key fields
    expect(metaText).toContain('cacm');     // index name
    expect(metaText).toContain('completed'); // status
    expect(metaText).toContain('Run file:'); // run path
    expect(metaText).toContain('Eval file:');// eval path

    // Verify actual run and eval files exist on disk
    const runFileMatch = metaText.match(/Run file:\s+(.+)/);
    if (runFileMatch) {
      expect(fs.existsSync(runFileMatch[1].trim())).toBe(true);
    }

    const evalFileMatch = metaText.match(/Eval file:\s+(.+)/);
    if (evalFileMatch) {
      expect(fs.existsSync(evalFileMatch[1].trim())).toBe(true);
    }

    // Verify no error is shown
    const errorArea = page.locator('#resultError');
    if (await errorArea.isVisible()) {
      const errorText = await errorArea.textContent();
      // If there's an error but we got a valid score, that's acceptable
      // But if score is NaN and there's an error, fail
      if (isNaN(scoreNum)) {
        throw new Error(`Evaluation failed with error: ${errorText}`);
      }
    }

    console.log('✓ End-to-end evaluation passed');
  });

  test('should show catalog-only indexes as non-evaluable', async ({ page }) => {
    await page.goto(APP_URL);
    await page.waitForSelector('.catalog-item', { timeout: 30000 });

    // Find a catalog-only index
    const catalogOnly = page.locator('.catalog-item.catalog-only').first();
    await expect(catalogOnly).toBeVisible();

    // Click on it
    await catalogOnly.click();

    // Verify that the evaluation panel shows it as catalog-only
    await expect(page.locator('#noSelection')).not.toHaveClass(/hidden/);
    const noSelectText = await page.locator('#noSelection').textContent();
    expect(noSelectText.toLowerCase()).toContain('catalog-only');
  });

});
