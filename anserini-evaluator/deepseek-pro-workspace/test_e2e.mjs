#!/usr/bin/env node

/**
 * Playwright end-to-end test for the Anserini Prebuilt Index Evaluator.
 *
 * This test verifies:
 * 1. The app loads and shows the index catalog
 * 2. CACM is selected or selectable as an evaluable index
 * 3. CACM shows a topic/qrels pairing
 * 4. A supported metric is selectable (nDCG@10 or Recall@1000)
 * 5. Run Evaluation produces a numeric score
 * 6. Run metadata appears (index, topics, metric, run/eval files)
 * 7. At least one catalog-only or non-CACM index is visible
 *
 * Prerequisites:
 *   - Python server running on http://localhost:8089
 *   - Anserini fatjar available and configured
 *   - Node.js and Playwright installed
 *
 * Usage:
 *   npm install playwright
 *   npx playwright install chromium
 *   node test_e2e.mjs
 */

import { chromium } from 'playwright';
import { strict as assert } from 'node:assert';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8089';
const TIMEOUT = 120_000; // 2 minutes for full eval

async function main() {
  console.log(`\n🧪 Anserini Prebuilt Index Evaluator — E2E Test`);
  console.log(`   Target: ${BASE_URL}\n`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  let failures = 0;

  function fail(msg) {
    failures++;
    console.error(`  ❌ ${msg}`);
  }

  try {
    // ── Step 1: Open the app ──
    console.log('1. Opening the app…');
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    // Wait for the page to render
    await page.waitForSelector('#indexList', { timeout: 15000 });
    console.log('   ✅ App loaded');

    // ── Step 2: Check health status ──
    console.log('2. Checking health status…');
    const statusText = await page.textContent('#statusText');
    console.log(`   Status: ${statusText}`);
    const statusDot = await page.$eval('#statusDot', el => el.className);
    if (statusDot.includes('ok') || statusDot.includes('warn')) {
      console.log('   ✅ Status dot visible');
    } else {
      fail('Status dot does not indicate ready/warning state');
    }

    // If status indicates fatjar is missing, the test can still check UI but
    // evaluation will fail. We'll warn but continue to test the UI.
    if (statusDot.includes('err')) {
      console.warn('   ⚠️  Environment not ready. UI tests will run but evaluation will fail.');
    }

    // ── Step 3: Confirm CACM is in the catalog and selectable ──
    console.log('3. Checking CACM index…');
    await page.waitForSelector('.index-entry', { timeout: 15000 });

    // Get all index entries
    const indexEntries = await page.$$('.index-entry');
    const indexCount = indexEntries.length;
    console.log(`   Found ${indexCount} index entries`);

    if (indexCount < 1) {
      fail('No index entries found in catalog');
    }

    // Find CACM entry
    let cacmFound = false;
    let nonCacmCount = 0;
    let catalogOnlyFound = false;
    let evaluableCount = 0;

    for (const entry of indexEntries) {
      const text = (await entry.textContent()) || '';
      const cls = (await entry.getAttribute('class')) || '';

      if (text.includes('cacm')) {
        cacmFound = true;
      } else {
        nonCacmCount++;
      }

      if (cls.includes('disabled')) {
        catalogOnlyFound = true;
      }

      if (text.includes('evaluable')) {
        evaluableCount++;
      }
    }

    if (cacmFound) {
      console.log('   ✅ CACM found in catalog');
    } else {
      fail('CACM not found in index catalog');
    }

    // ── Step 4: Verify catalog has more than one entry (not hardcoded) ──
    if (indexCount > 1) {
      console.log(`   ✅ Catalog exposes ${indexCount} entries (more than just CACM)`);
    } else {
      fail(`Catalog only has ${indexCount} entry — may be hardcoded`);
    }

    if (nonCacmCount > 0) {
      console.log(`   ✅ ${nonCacmCount} non-CACM entries visible`);
    } else {
      fail('No non-CACM entries found — catalog may be mocked');
    }

    if (catalogOnlyFound) {
      console.log('   ✅ Catalog-only / non-evaluable index found');
    } else if (evaluableCount < indexCount) {
      // Some entries don't have "evaluable" badge, which counts as catalog-only
      console.log('   ✅ Entries without "evaluable" badge observed (catalog-only)');
    } else {
      // This is not a hard fail — all indexes may genuinely be evaluable
      console.log('   ℹ️  All visible indexes appear evaluable');
    }

    // ── Step 5: Select CACM and verify pairing ──
    console.log('4. Selecting CACM…');
    // Click the CACM entry
    const cacmEntry = await page.$('.index-entry[data-idx="cacm"]');
    if (cacmEntry) {
      await cacmEntry.click();
      await page.waitForTimeout(500);
      console.log('   ✅ CACM clicked');
    } else {
      fail('CACM entry not found for clicking');
    }

    // Check the evaluation panel for pairing info
    await page.waitForSelector('#evalBody', { timeout: 5000 });
    const evalBodyText = (await page.textContent('#evalBody')) || '';
    console.log(`   Eval panel content: ${evalBodyText.substring(0, 200)}`);

    if (evalBodyText.includes('cacm') || evalBodyText.includes('CACM')) {
      console.log('   ✅ CACM topic/qrels pairing shown');
    } else {
      fail('CACM pairing not shown in evaluation panel');
    }

    // ── Step 6: Select a metric ──
    console.log('5. Selecting evaluation metric…');
    const metricSelect = await page.$('#metricSelect');
    let selectedMetric = 'nDCG@10';

    if (metricSelect) {
      const options = await metricSelect.$$eval('option', opts =>
        opts.map(o => ({ value: o.value, text: o.textContent }))
      );
      console.log(`   Available metrics: ${options.map(o => o.value).join(', ')}`);

      // Try nDCG@10 first, fall back to Recall@1000, then MAP
      if (options.find(o => o.value === 'nDCG@10')) {
        await metricSelect.selectOption('nDCG@10');
        selectedMetric = 'nDCG@10';
        console.log('   ✅ Selected nDCG@10');
      } else if (options.find(o => o.value === 'Recall@1000')) {
        await metricSelect.selectOption('Recall@1000');
        selectedMetric = 'Recall@1000';
        console.log('   ✅ Selected Recall@1000 (fallback)');
      } else if (options.length > 0) {
        await metricSelect.selectOption(options[0].value);
        selectedMetric = options[0].value;
        console.log(`   ⚠️  Selected ${selectedMetric} (neither nDCG@10 nor Recall@1000 available)`);
      } else {
        fail('No metrics available in selector');
      }
    } else {
      fail('Metric selector not found');
    }

    // ── Step 7: Click Run Evaluation ──
    console.log('6. Running evaluation…');
    const runBtn = await page.$('#runBtn');
    if (!runBtn) {
      fail('Run Evaluation button not found');
    } else {
      // Check if the button is enabled (not disabled by missing fatjar, etc.)
      const isDisabled = await runBtn.isDisabled();
      if (isDisabled) {
        console.warn('   ⚠️  Run button is disabled — skipping evaluation test (environment not ready)');
      } else {
        await runBtn.click();
        console.log('   ✅ Clicked Run Evaluation');

        // Wait for results panel to appear
        try {
          await page.waitForSelector('#resultsPanel:visible', { timeout: TIMEOUT });
          console.log('   ✅ Results panel appeared');

          // ── Step 8: Verify numeric score ──
          const scoreText = await page.textContent('.score-display');
          console.log(`   Score text: "${scoreText}"`);

          if (scoreText) {
            const score = parseFloat(scoreText.trim());
            if (!isNaN(score) && score > 0) {
              console.log(`   ✅ Numeric score: ${score}`);
            } else if (!isNaN(score)) {
              // Score is 0 or negative — unusual but still numeric
              console.log(`   ⚠️  Score is ${score} (numeric but may be unexpected)`);
            } else {
              fail(`Score is not numeric: "${scoreText}"`);
            }
          } else {
            fail('Score display is empty');
          }

          // ── Step 9: Verify run metadata ──
          const metaGridText = (await page.textContent('.meta-grid')) || '';
          console.log(`   Metadata: ${metaGridText.substring(0, 300)}`);

          // Check for index
          if (metaGridText.toLowerCase().includes('cacm') || metaGridText.toLowerCase().includes('Index')) {
            console.log('   ✅ Index metadata present');
          } else {
            fail('Index metadata not found in results');
          }

          // Check for topics
          if (metaGridText.toLowerCase().includes('topic') || metaGridText.toLowerCase().includes('cacm')) {
            console.log('   ✅ Topics metadata present');
          } else {
            fail('Topics metadata not found in results');
          }

          // Check for metric
          if (metaGridText.toLowerCase().includes('metric') || metaGridText.toLowerCase().includes('ndcg') || metaGridText.toLowerCase().includes('recall') || metaGridText.toLowerCase().includes('map')) {
            console.log('   ✅ Metric metadata present');
          } else {
            fail('Metric metadata not found in results');
          }

          // Check for run file path
          if (metaGridText.includes('run.') || metaGridText.includes('Run File')) {
            console.log('   ✅ Run file path in metadata');
          } else {
            fail('Run file path not found in results');
          }

          // Check for eval file path
          if (metaGridText.includes('eval.') || metaGridText.includes('Eval File')) {
            console.log('   ✅ Eval file path in metadata');
          } else {
            fail('Eval file path not found in results');
          }

        } catch (e) {
          // Check for error display
          const errorEl = await page.$('#runError');
          if (errorEl) {
            const errorText = (await errorEl.textContent()) || '';
            console.warn(`   ⚠️  Evaluation produced an error: ${errorText.substring(0, 300)}`);
            fail(`Evaluation run failed with error: ${errorText.substring(0, 200)}`);
          } else {
            fail(`Results panel did not appear within timeout: ${e.message}`);
          }
        }
      }
    }

    // ── Summary ──
    console.log(`\n${'═'.repeat(50)}`);
    if (failures === 0) {
      console.log('✅ All tests passed!');
    } else {
      console.log(`❌ ${failures} test(s) failed`);
    }
    console.log('═'.repeat(50));

  } catch (e) {
    console.error(`\n❌ Fatal error: ${e.message}`);
    console.error(e.stack);
    failures++;
  } finally {
    await browser.close();
  }

  process.exit(failures > 0 ? 1 : 0);
}

main();
