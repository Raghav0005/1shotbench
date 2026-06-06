const { test, expect } = require('@playwright/test');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const PORT = process.env.TEST_PORT || '10123';
const BASE = `http://127.0.0.1:${PORT}`;
const cacheDir = path.resolve('.runtime-playwright');
let server;

async function getJson(url) {
  const res = await fetch(url);
  return { status: res.status, body: await res.json() };
}

test.beforeAll(async () => {
  fs.mkdirSync(cacheDir, { recursive: true });
  server = spawn('python3', ['app/server.py'], {
    env: {
      ...process.env,
      PORT,
      NFCORPUS_CACHE_DIR: cacheDir,
      ANSERINI_JAR: process.env.ANSERINI_JAR || path.resolve('.runtime/anserini/anserini-2.1.1-fatjar.jar'),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.stdout.on('data', d => process.stdout.write(`[server] ${d}`));
  server.stderr.on('data', d => process.stderr.write(`[server] ${d}`));

  await expect.poll(async () => {
    try {
      const { body } = await getJson(`${BASE}/health`);
      if (body.status === 'error') throw new Error(JSON.stringify(body.errors));
      return body.status;
    } catch (e) {
      return 'not-listening';
    }
  }, { timeout: 10 * 60 * 1000, intervals: [1000, 2000, 5000] }).toBe('ready');
});

test.afterAll(async () => {
  if (server) server.kill('SIGTERM');
});

test('browser verifies live NFCorpus search, evaluation, commands, artifacts, and Render contract', async ({ page }) => {
  await page.goto(BASE);

  await expect(page.getByText('Readiness / Health')).toBeVisible();
  await expect(page.getByText('Active dataset: NFCorpus')).toBeVisible();
  await expect(page.getByText('Anserini setup status')).toBeVisible();
  await expect(page.getByText('PORT')).toBeVisible();
  await expect(page.getByText('0.0.0.0')).toBeVisible();

  await page.getByRole('button', { name: 'vitamin d' }).click();
  await expect(page.locator('.result').first()).toBeVisible({ timeout: 180000 });
  await expect(page.locator('.rank').first()).toContainText('#1');
  await expect(page.locator('.result .docid').first()).toContainText(/MED-|NFCORPUS|doc/i);
  await expect(page.locator('.result .score').first()).toContainText(/score\s+[0-9.]+/);
  await expect(page.locator('.result .snippet').first()).toContainText(/vitamin|health|disease|study/i);

  await expect(page.getByText('BM25 Evaluation')).toBeVisible();
  await expect(page.locator('#metrics')).toContainText(/observed/i);
  await expect(page.locator('#metrics')).toContainText(/expected/i);
  await expect(page.locator('#metrics')).toContainText(/[0-9]+\.[0-9]+/);
  await expect(page.locator('#metrics')).toContainText(/pass|close|fail|expected-unavailable/i);
  await expect(page.getByText('Run file:')).toBeVisible();
  await expect(page.getByText('Evaluation output:')).toBeVisible();

  await expect(page.getByText('Command & Artifact Drawer')).toBeVisible();
  await expect(page.locator('#commands')).toContainText('io.anserini.cli.Search');
  await expect(page.locator('#commands')).toContainText('io.anserini.search.SearchCollection');
  await expect(page.locator('#commands')).toContainText('trec_eval');
  await expect(page.locator('#artifacts')).toContainText(/run\.beir\.core\.flat\.nfcorpus\.txt|eval\.beir\.core\.flat\.nfcorpus\.txt/);

  const status = await (await fetch(`${BASE}/api/status`)).json();
  expect(status.dataset).toBe('NFCorpus');
  expect(status.search.last.backedBy).toBe('anserini-cli');
  expect(status.search.last.results.length).toBeGreaterThan(0);
  expect(status.search.last.command).toContain('io.anserini.cli.Search');
  expect(status.evaluation.last.backedBy).toContain('anserini');
  expect(Object.values(status.evaluation.last.observed).some(v => typeof v === 'number')).toBeTruthy();
  expect(status.reproduction.expected && Object.keys(status.reproduction.expected).length).toBeGreaterThan(0);
  expect(status.commands.some(c => c.stage === 'bm25-retrieval' && c.exitCode === 0)).toBeTruthy();
  expect(status.commands.some(c => c.stage.startsWith('evaluation-') && c.command.includes('trec_eval') && c.exitCode === 0)).toBeTruthy();
});
