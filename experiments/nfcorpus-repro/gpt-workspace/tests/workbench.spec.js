import { test, expect } from '@playwright/test';

test('NFCorpus Anserini diagnostics workflow is real and inspectable', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.getByTestId('readiness-panel')).toBeVisible();
  await expect(page.locator('#dataset')).toHaveText('NFCorpus');
  await expect(page.getByText('Anserini setup')).toBeVisible();

  await expect.poll(async () => {
    const h = await request.get('/health');
    const json = await h.json();
    return `${json.app}:${json.anseriniAvailable}:${json.nfcorpusReady}:${json.searchAvailable}:${json.evaluationAvailable}`;
  }, { timeout: 360000, intervals: [2000, 5000, 10000] }).toContain('true:true:true:true');

  await page.getByRole('button', { name: 'dietary fiber' }).click();
  await expect(page.locator('.result')).toHaveCount(10, { timeout: 120000 });
  await expect(page.locator('.result').first()).toContainText(/#1/);
  await expect(page.locator('.result').first()).toContainText(/MED-|score/i);
  await expect(page.locator('.result').first()).toContainText(/fiber|diet/i);

  await expect(page.getByTestId('evaluation-panel')).toContainText(/0\.\d+/);
  await expect(page.getByTestId('evaluation-panel')).toContainText(/Expected|Delta|pass|close|fail/i);

  await expect(page.getByTestId('commands-panel')).toContainText('io.anserini.cli.Search');
  await expect(page.getByTestId('commands-panel')).toContainText('io.anserini.search.SearchCollection');
  await expect(page.getByTestId('commands-panel')).toContainText('io.anserini.eval.TrecEval');
  await expect(page.getByTestId('commands-panel')).toContainText(/run\.beir\.core\.flat\.nfcorpus/);
  await expect(page.getByTestId('commands-panel')).toContainText(/\.stdout\.log|\.stderr\.log/);

  const status = await (await request.get('/api/status')).json();
  const commands = status.commands.map((c) => c.command).join('\n');
  expect(commands).toContain('io.anserini.cli.Search');
  expect(commands).toContain('io.anserini.search.SearchCollection');
  expect(commands).toContain('io.anserini.eval.TrecEval');
  expect(status.provenance.realAnseriniCommandsExecuted).toBe(true);
  expect(status.provenance.mocksUsed).toBe(false);
  expect(status.evaluation.metrics.ndcg_cut_10).toEqual(expect.any(Number));
  expect(status.evaluation.comparisons['nDCG@10'].delta).toEqual(expect.any(Number));
  expect(status.reproduction.expected.expectedScores['nDCG@10']).toEqual(expect.any(Number));

  await expect(page.getByText(/0\.0\.0\.0/)).toBeVisible();
  await expect(page.getByText(/PORT/)).toBeVisible();
});
