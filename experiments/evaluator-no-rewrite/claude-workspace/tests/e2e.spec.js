/**
 * End-to-end Playwright test that drives the Anserini Prebuilt Index
 * Evaluator UI through a real retrieval + evaluation flow on CACM.
 *
 * Per the PRD, the test verifies:
 *   - CACM is selected (or selectable) by default.
 *   - The index catalog exposes more than just a hardcoded CACM option.
 *   - CACM shows a topic/qrels pairing.
 *   - A supported modern metric (nDCG@10 or Recall@1000) is selectable, with
 *     a clear fallback to whatever metrics CACM does expose.
 *   - Clicking Run Evaluation produces a numeric score.
 *   - Run metadata (index, topics, metric, artifact paths) is shown.
 *   - At least one catalog-only or non-selected index is visible.
 *
 * The test fails if the app displays mocked catalog data or mocked evaluation
 * results: it verifies that the displayed retrieval/evaluation commands
 * reference the real Anserini fatjar and that the evaluator output contains
 * real `trec_eval`-style rows for the chosen metric.
 */

const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const ARTIFACTS_DIR = path.join(__dirname, '..', 'artifacts');

test('CACM end-to-end retrieval and evaluation through the browser', async ({ page }) => {
  // -------- Load the app --------
  await page.goto('/');
  await expect(page.locator('h1')).toHaveText(/Anserini Prebuilt Index Evaluator/);

  // Health check should be green (Java + fatjar resolved on the server).
  const health = page.getByTestId('health');
  await expect(health).toHaveClass(/ok/, { timeout: 30 * 1000 });

  // -------- Catalog should populate from the live registry --------
  const stats = page.getByTestId('catalog-stats');
  // Wait until catalog has been loaded (warmup + 1 JVM per config).
  await expect(stats).toContainText(/inverted indexes/i, { timeout: 120 * 1000 });
  const statsText = await stats.textContent();

  // Expect *many* indexes — not just one hardcoded CACM entry.
  const indexCount = Number((statsText.match(/(\d+)\s+inverted/) || [])[1]);
  expect(indexCount).toBeGreaterThan(10);

  const items = page.getByTestId('catalog-item');
  await expect(items.first()).toBeVisible();
  const itemCount = await items.count();
  expect(itemCount).toBeGreaterThan(10);

  // -------- Confirm CACM is selectable / selected --------
  // The app auto-selects CACM on load when present.
  const cacmItem = page.locator('[data-testid="catalog-item"][data-index-name="cacm"]');
  await expect(cacmItem).toBeVisible();
  await expect(cacmItem).toHaveClass(/selected/);
  await expect(cacmItem).toHaveAttribute('data-evaluable', 'true');

  // -------- Confirm at least one non-CACM and at least one catalog-only entry --------
  const otherEvaluable = page.locator(
    '[data-testid="catalog-item"][data-evaluable="true"]:not([data-index-name="cacm"])'
  );
  expect(await otherEvaluable.count()).toBeGreaterThan(0);

  const catalogOnly = page.locator('[data-testid="catalog-item"][data-evaluable="false"]');
  // We assert >= 1 catalog-only entry from the registry-derived catalog.
  expect(await catalogOnly.count()).toBeGreaterThanOrEqual(1);

  // -------- Confirm CACM shows a topic/qrels pairing --------
  await expect(page.locator('#pairing-section')).toBeVisible();
  const pairingSelect = page.getByTestId('pairing-select');
  await expect(pairingSelect).toBeVisible();
  // CACM has exactly one pairing in the shipped reproduce config (topics=cacm,
  // qrels=cacm). The displayed option should reflect that.
  const pairingText = await pairingSelect.locator('option').first().textContent();
  expect(pairingText).toMatch(/cacm/i);
  expect(pairingText).toMatch(/qrels:cacm/i);

  // -------- Pick a supported metric: prefer nDCG@10 or Recall@1000, fall back otherwise --------
  const metricSelect = page.getByTestId('metric-select');
  await expect(metricSelect).toBeVisible();
  const metricOptionTexts = await metricSelect.locator('option').allTextContents();
  expect(metricOptionTexts.length).toBeGreaterThan(0);
  let chosenMetric = null;
  for (const candidate of ['nDCG@10', 'Recall@1000']) {
    if (metricOptionTexts.some((t) => t.startsWith(candidate))) {
      chosenMetric = candidate;
      break;
    }
  }
  if (!chosenMetric) {
    // Clear fallback: just pick whatever the first option is.
    chosenMetric = (metricOptionTexts[0] || '').split(/\s+/)[0];
  }
  expect(chosenMetric).toBeTruthy();
  await metricSelect.selectOption(chosenMetric);

  // -------- Click Run Evaluation --------
  const runButton = page.getByTestId('run-button');
  await expect(runButton).toBeEnabled();
  const artifactsBefore = listArtifacts();
  await runButton.click();

  // The status pill should report progress.
  const status = page.getByTestId('run-status');
  await expect(status).toHaveClass(/running/, { timeout: 5 * 1000 });

  // CACM retrieval + eval finishes in seconds, but be generous on first run
  // since the prebuilt index may need to be downloaded.
  await expect(status).toHaveClass(/ok/, { timeout: 5 * 60 * 1000 });

  // -------- Verify a numeric score appears --------
  const scoreText = (await page.getByTestId('score-value').textContent()).trim();
  // Should parse as a finite number in [0, 1] for the metrics we expose.
  const scoreNum = Number(scoreText);
  expect(Number.isFinite(scoreNum)).toBe(true);
  expect(scoreNum).toBeGreaterThanOrEqual(0);
  expect(scoreNum).toBeLessThanOrEqual(1);
  await expect(page.getByTestId('score-label')).toHaveText(chosenMetric);

  // -------- Verify run metadata is displayed --------
  await expect(page.getByTestId('result-index')).toHaveText('cacm');
  await expect(page.getByTestId('result-topics')).toHaveText('cacm');
  await expect(page.getByTestId('result-qrels-eval-key')).toHaveText('cacm');
  await expect(page.getByTestId('result-metric')).toContainText(chosenMetric);
  await expect(page.getByTestId('result-run-file')).toContainText('artifacts/run.');
  await expect(page.getByTestId('result-evaluation-file')).toContainText('artifacts/eval.');

  // -------- Anti-mock checks: evaluator output and commands must look real --------
  const evalOutput = await page.getByTestId('eval-output').textContent();
  // trec_eval output for the "all" aggregate row should be present.
  expect(evalOutput).toMatch(/\tall\t\d+\.\d+/);

  const commands = await page.getByTestId('commands').textContent();
  expect(commands).toContain('io.anserini.search.SearchCollection');
  expect(commands).toContain('io.anserini.eval.TrecEval');
  expect(commands).toContain('anserini-');
  expect(commands).toContain('-fatjar.jar');

  const runPreview = await page.getByTestId('run-preview').textContent();
  // TREC run line: qid Q0 docid rank score tag
  expect(runPreview).toMatch(/\bQ0\b/);

  // -------- The server should have produced real artifact files on disk --------
  const artifactsAfter = listArtifacts();
  const newArtifacts = artifactsAfter.filter((a) => !artifactsBefore.includes(a));
  expect(newArtifacts.some((n) => n.startsWith('run.cacm.'))).toBe(true);
  expect(newArtifacts.some((n) => n.startsWith('eval.cacm.'))).toBe(true);
});

function listArtifacts() {
  if (!fs.existsSync(ARTIFACTS_DIR)) return [];
  return fs.readdirSync(ARTIFACTS_DIR);
}
