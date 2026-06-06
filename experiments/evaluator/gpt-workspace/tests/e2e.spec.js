const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { test, expect } = require('@playwright/test');

const anseriniJar = process.env.ANSERINI_JAR || path.join(__dirname, '..', 'anserini-2.1.1-fatjar.jar');

test('runs real CACM retrieval and evaluation from the browser', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Anserini Prebuilt Index Evaluator' })).toBeVisible();
  await expect(page.locator('#health')).toContainText('Ready', { timeout: 30000 });

  await expect(page.locator('#catalogSummary')).toContainText(/\d+ Lucene inverted indexes/, { timeout: 60000 });
  const summary = await page.locator('#catalogSummary').textContent();
  const count = Number(summary.match(/(\d+) Lucene inverted indexes/)?.[1]);
  expect(count).toBeGreaterThan(1);
  await expect(page.locator('#catalogSource')).toContainText('PrebuiltIndexRegistry');

  // Independently verify the UI count came from the Anserini registry, not a one-item fixture.
  const registryJson = execFileSync('java', ['-cp', anseriniJar, 'io.anserini.cli.PrebuiltIndexRegistry', '--type', 'inverted', '--list'], { encoding: 'utf8' });
  expect(JSON.parse(registryJson).length).toBe(count);

  const cacm = page.locator('[data-index-name="cacm"]');
  await expect(cacm).toBeVisible();
  await expect(cacm).toContainText('Ready for evaluation');
  const otherRegistryIndex = page.locator('[data-index-name]').nth(1);
  await expect(otherRegistryIndex).toBeVisible();
  await expect(otherRegistryIndex).toContainText('Catalog-only');

  await expect(page.locator('#selection')).toContainText('Topics: cacm');
  await expect(page.locator('#selection')).toContainText('qrels key: cacm');

  const optionTexts = await page.locator('#metric option').allTextContents();
  let metricValue;
  if (optionTexts.some((text) => text.includes('nDCG@10'))) {
    metricValue = 'ndcg_cut.10';
  } else if (optionTexts.some((text) => text.includes('Recall@1000'))) {
    metricValue = 'recall.1000';
  } else {
    metricValue = 'map';
  }
  await page.locator('#metric').selectOption(metricValue);

  await page.getByRole('button', { name: 'Run Evaluation' }).click();
  await expect(page.locator('#runStatus')).toContainText('Evaluation completed', { timeout: 180000 });
  await expect(page.locator('#score')).toHaveText(/^\d+(\.\d+)?$/);

  await expect(page.locator('#metaIndex')).toHaveText('cacm');
  await expect(page.locator('#metaTopics')).toHaveText('cacm');
  await expect(page.locator('#metaMetric')).toContainText(/nDCG@10|Recall@1000|MAP/);
  await expect(page.locator('#metaRunFile')).toContainText('artifacts/runs/run.cacm');
  await expect(page.locator('#metaEvalFile')).toContainText('artifacts/evals/eval.cacm');
  await expect(page.locator('#evalPreview')).toContainText(/ndcg_cut_10|recall_1000|map/);
  await expect(page.locator('#runPreview')).toContainText(/Q0/);

  const runRel = await page.locator('#metaRunFile').textContent();
  const evalRel = await page.locator('#metaEvalFile').textContent();
  const runPath = path.join(__dirname, '..', runRel);
  const evalPath = path.join(__dirname, '..', evalRel);
  expect(fs.existsSync(runPath)).toBeTruthy();
  expect(fs.existsSync(evalPath)).toBeTruthy();

  const runLines = fs.readFileSync(runPath, 'utf8').trim().split(/\r?\n/);
  expect(runLines.length).toBeGreaterThan(50);
  expect(runLines[0].trim().split(/\s+/).length).toBeGreaterThanOrEqual(6);

  const evalOutput = fs.readFileSync(evalPath, 'utf8');
  const scoreText = await page.locator('#score').textContent();
  expect(evalOutput).toContain(Number(scoreText).toFixed(4));

  // Independently run Anserini's evaluator over the generated run file; mocked scores should not pass.
  const independentEval = execFileSync('java', ['-cp', anseriniJar, 'io.anserini.eval.TrecEval', '-c', '-m', metricValue, 'cacm', runPath], { encoding: 'utf8' });
  expect(independentEval).toContain(Number(scoreText).toFixed(4));
});
