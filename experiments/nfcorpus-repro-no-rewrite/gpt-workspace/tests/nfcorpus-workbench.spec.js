const { test, expect } = require('@playwright/test');

test('NFCorpus Anserini workbench runs real search and evaluation', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /NFCorpus Live Retrieval Diagnostics Workbench/i })).toBeVisible();
  await expect(page.getByText(/Active dataset/i)).toBeVisible();
  await expect(page.getByText(/Anserini setup status/i)).toBeVisible();
  await expect(page.getByText(/Docker \/ Render Readiness Contract/i)).toBeVisible();
  await expect(page.getByText(/defaulting to 10000/i)).toBeVisible();

  await expect.poll(async () => {
    const h = await request.get('/health');
    const json = await h.json();
    return `${json.status}:${json.anseriniAvailable}:${json.nfcorpusReady}:${json.searchAvailable}:${json.evaluationAvailable}`;
  }, { timeout: 420000, intervals: [1000, 2500, 5000] }).toBe('ready:true:true:true:true');

  await page.reload();
  await expect(page.getByText(/NFCorpus \(beir-v1\.0\.0-nfcorpus\.flat\)/)).toBeVisible();
  await expect(page.getByText(/Java\/fatjar:/)).toBeVisible();
  await expect(page.getByText(/nDCG@10 observed/i)).toBeVisible();
  await expect(page.locator('#metrics')).toContainText(/Expected:/);
  await expect(page.locator('#metrics')).toContainText(/Delta:/);
  await expect(page.locator('#metrics')).toContainText(/pass|close|fail|expected-unavailable/i);
  await expect(page.locator('#metrics')).toContainText(/0\.\d+/);

  await page.getByRole('button', { name: 'vitamin d cancer' }).click();
  await expect(page.locator('.result').first()).toBeVisible({ timeout: 120000 });
  await expect(page.locator('.result').first()).toContainText(/docid=/);
  await expect(page.locator('.result').first()).toContainText(/rank=1/);
  await expect(page.locator('.result').first()).toContainText(/score=/);
  await expect(page.locator('.result').first()).toContainText(/vitamin|cancer|health/i);
  await expect(page.locator('#search-command')).toContainText('io.anserini.cli.Search');

  await expect(page.getByText(/BM25 retrieval: NFCorpus SearchCollection/)).toBeVisible();
  await expect(page.getByText(/evaluation: NFCorpus TrecEval nDCG@10/)).toBeVisible();
  await expect(page.getByText(/reproduction discovery: show BEIR core config/)).toBeVisible();
  await expect(page.locator('body')).toContainText(/java -cp/);
  await expect(page.locator('body')).toContainText(/run\.beir-v1\.0\.0-nfcorpus\.flat\.bm25\.txt/);
  await expect(page.locator('body')).toContainText(/eval\.beir-v1\.0\.0-nfcorpus\.flat\.bm25\.txt/);

  const status = await (await request.get('/api/status')).json();
  expect(status.commands.some((c) => /io\.anserini\.cli\.Search/.test(c.command) && /--json/.test(c.command))).toBeTruthy();
  expect(status.commands.some((c) => /io\.anserini\.search\.SearchCollection/.test(c.command) && /beir-v1\.0\.0-nfcorpus\.flat/.test(c.command))).toBeTruthy();
  expect(status.commands.some((c) => /io\.anserini\.eval\.TrecEval/.test(c.command) && /beir-v1\.0\.0-nfcorpus\.test/.test(c.command))).toBeTruthy();
  expect(status.evaluation.observed['nDCG@10']).toEqual(expect.any(Number));
  expect(JSON.stringify(status).toLowerCase()).not.toContain('mocked search');
  expect(JSON.stringify(status).toLowerCase()).not.toContain('mocked evaluation');
});
