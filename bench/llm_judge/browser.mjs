#!/usr/bin/env node
/**
 * Generic Playwright evidence collector for Pi-Bench web eval.
 * Reads a JSON job from --job <path> and writes evidence JSON to --output <path>.
 */
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const args = process.argv.slice(2);
function getArg(name) {
  const index = args.indexOf(name);
  if (index === -1 || index + 1 >= args.length) return null;
  return args[index + 1];
}

const jobPath = getArg('--job');
const outputPath = getArg('--output');
if (!jobPath || !outputPath) {
  console.error('Usage: node browser.mjs --job <job.json> --output <evidence.json>');
  process.exit(2);
}

const job = JSON.parse(fs.readFileSync(jobPath, 'utf8'));
const baseURL = job.baseURL;
const steps = job.steps || [];
const outputDir = job.outputDir;
const featureId = job.featureId;

fs.mkdirSync(outputDir, { recursive: true });
const screenshotDir = path.join(outputDir, 'screenshots');
fs.mkdirSync(screenshotDir, { recursive: true });

const evidence = {
  feature_id: featureId,
  url: null,
  page_title: null,
  visible_text: null,
  aria_snapshot: null,
  screenshot_path: null,
  interactive_elements: [],
  console_errors: [],
  network_errors: [],
  action_log: [],
  checks: {},
  error: null,
};

function truncate(text, max) {
  if (!text) return text;
  return text.length <= max ? text : `${text.slice(0, max - 3)}...`;
}

function tail(text, max) {
  if (!text) return text;
  return text.length <= max ? text : `...${text.slice(text.length - max + 3)}`;
}

function resolveURL(target) {
  if (!target || target === '/') return baseURL;
  if (target.startsWith('http://') || target.startsWith('https://')) return target;
  return new URL(target, baseURL).toString();
}

async function settle(page, ms = 500) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(ms);
  try {
    await page.waitForLoadState('networkidle', { timeout: 5000 });
  } catch {
    // SPA apps may never reach networkidle.
  }
}

async function captureState(page) {
  evidence.url = page.url();
  evidence.page_title = await page.title();
  const bodyText = await page.locator('body').innerText().catch(() => '');
  const normalizedBody = bodyText.replace(/\s+/g, ' ').trim();
  evidence.visible_text = truncate(normalizedBody, 4000);
  evidence.checks.body_text_tail = tail(normalizedBody, 4000);
  evidence.checks.result_like_text = await collectResultLikeText(page);
  evidence.checks.numeric_candidates = collectNumericCandidates(normalizedBody);
  evidence.interactive_elements = await collectInteractiveElements(page);
  try {
    const snapshot = await page.locator('body').ariaSnapshot();
    evidence.aria_snapshot = truncate(snapshot, 6000);
  } catch (err) {
    evidence.action_log.push(`aria_snapshot_failed: ${err.message}`);
  }
}

async function collectInteractiveElements(page) {
  return await page
    .locator('button, a, input, textarea, select, [role="button"], [role="link"], [role="tab"], [role="menuitem"]')
    .evaluateAll((nodes) =>
      nodes.slice(0, 120).map((node, index) => {
        const el = node;
        const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
        const attrs = {};
        for (const name of ['id', 'name', 'type', 'role', 'aria-label', 'placeholder', 'value', 'href']) {
          const value = el.getAttribute && el.getAttribute(name);
          if (value) attrs[name] = value;
        }
        return {
          index,
          tag: el.tagName ? el.tagName.toLowerCase() : '',
          text: text.slice(0, 120),
          attributes: attrs,
          disabled: Boolean(el.disabled || el.getAttribute?.('aria-disabled') === 'true'),
        };
      })
    )
    .catch(() => []);
}

async function clickByText(page, step) {
  const text = step.text;
  const exact = !!step.exact;
  const timeout = step.timeout ?? 15000;
  const roleCandidates = [
    page.getByRole('button', { name: text, exact }),
    page.getByRole('link', { name: text, exact }),
  ];
  for (const candidate of roleCandidates) {
    const first = candidate.first();
    if (await first.isVisible({ timeout: 500 }).catch(() => false)) {
      await first.click({ timeout });
      return;
    }
  }

  const matches = page.getByText(text, { exact });
  const count = Math.min(await matches.count().catch(() => 0), 50);
  for (let i = 0; i < count; i += 1) {
    const candidate = matches.nth(i);
    if (await candidate.isVisible({ timeout: 500 }).catch(() => false)) {
      await candidate.click({ timeout });
      return;
    }
  }

  await matches.first().click({ timeout });
}

async function collectResultLikeText(page) {
  const selectors = [
    '[data-testid*="score" i]',
    '[data-testid*="result" i]',
    '[data-testid*="metric" i]',
    '[data-testid*="eval" i]',
    '[id*="score" i]',
    '[id*="result" i]',
    '[id*="metric" i]',
    '[id*="meta" i]',
    '[id*="eval" i]',
    '[class*="score" i]',
    '[class*="result" i]',
    '[class*="metric" i]',
    '[class*="meta" i]',
    '[class*="eval" i]',
    '[role="status"]',
    '[aria-live]',
    'output',
    'pre',
  ].join(', ');
  return await page.locator(selectors).evaluateAll((nodes) => {
    const seen = new Set();
    const chunks = [];
    for (const node of nodes.slice(0, 160)) {
      const text = (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
      if (!text || seen.has(text)) continue;
      seen.add(text);
      const attrs = [];
      for (const name of ['id', 'class', 'data-testid', 'role', 'aria-label']) {
        const value = node.getAttribute && node.getAttribute(name);
        if (value) attrs.push(`${name}=${value}`);
      }
      chunks.push(`${node.tagName ? node.tagName.toLowerCase() : 'node'}${attrs.length ? ` [${attrs.join(' ')}]` : ''}: ${text}`);
    }
    return chunks.join('\n');
  }).then((text) => truncate(text, 6000)).catch(() => '');
}

function collectNumericCandidates(text) {
  if (!text) return [];
  const pattern = /(?:score|metric|map|ndcg|recall|precision|success|result|elapsed|latency|ms|seconds?)\D{0,80}[-+]?\d+(?:\.\d+)?|[-+]?\d+\.\d+\D{0,80}(?:score|metric|map|ndcg|recall|precision|success|result|elapsed|latency|ms|seconds?)/gi;
  const matches = [];
  const seen = new Set();
  let match;
  while ((match = pattern.exec(text)) && matches.length < 40) {
    const value = match[0].replace(/\s+/g, ' ').trim();
    if (!seen.has(value)) {
      seen.add(value);
      matches.push(value.slice(0, 220));
    }
  }
  return matches;
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();

  page.on('console', (msg) => {
    if (['error', 'warning'].includes(msg.type())) {
      evidence.console_errors.push(`${msg.type()}: ${msg.text()}`);
    }
  });
  page.on('pageerror', (err) => {
    evidence.console_errors.push(`pageerror: ${err.message}`);
  });
  page.on('requestfailed', (request) => {
    const failure = request.failure();
    evidence.network_errors.push(
      `${request.method()} ${request.url()} -> ${failure?.errorText || 'failed'}`
    );
  });

  try {
    for (const step of steps) {
      const action = step.action;
      evidence.action_log.push(`${action}${step.name ? ` (${step.name})` : ''}`);

      switch (action) {
        case 'open': {
          const target = step.url ?? step.path ?? '/';
          await page.goto(resolveURL(target), { waitUntil: 'domcontentloaded' });
          await settle(page, step.ms ?? 500);
          break;
        }
        case 'click': {
          if (Number.isInteger(step.index)) {
            await page
              .locator('button, a, input, textarea, select, [role="button"], [role="link"], [role="tab"], [role="menuitem"]')
              .nth(step.index)
              .click({ timeout: step.timeout ?? 15000 });
          } else if (step.selector) {
            await page.locator(step.selector).first().click({ timeout: step.timeout ?? 15000 });
          } else if (step.role && step.name) {
            await page.getByRole(step.role, { name: step.name }).click({ timeout: step.timeout ?? 15000 });
          } else if (step.text) {
            await clickByText(page, step);
          } else {
            throw new Error('click requires selector, role+name, or text');
          }
          await settle(page, step.ms ?? 400);
          break;
        }
        case 'fill': {
          let locator;
          if (step.selector) locator = page.locator(step.selector).first();
          else if (step.placeholder) locator = page.getByPlaceholder(step.placeholder).first();
          else if (step.label) locator = page.getByLabel(step.label).first();
          else locator = page.locator('input, textarea').first();
          await locator.fill(step.text ?? '', { timeout: step.timeout ?? 15000 });
          break;
        }
        case 'press': {
          await page.keyboard.press(step.key ?? 'Enter');
          await settle(page, step.ms ?? 400);
          break;
        }
        case 'submit': {
          if (step.selector) await page.locator(step.selector).first().press('Enter');
          else await page.keyboard.press('Enter');
          await settle(page, step.ms ?? 600);
          break;
        }
        case 'select': {
          const locator = step.selector
            ? page.locator(step.selector).first()
            : page.locator('select').first();
          await locator.selectOption(step.value ?? step.label ?? { label: step.option });
          await settle(page, step.ms ?? 400);
          break;
        }
        case 'wait_settle':
          await settle(page, step.ms ?? 800);
          break;
        case 'wait_for_text': {
          const locator = step.selector
            ? page.locator(step.selector)
            : page.getByText(step.text, { exact: !!step.exact });
          const matched = locator.first();
          await matched.waitFor({ state: 'visible', timeout: step.timeout ?? 30000 });
          evidence.checks[`wait_for_text:${step.text || step.selector}`] = true;
          evidence.checks[`wait_for_text:${step.text || step.selector}:matched_text`] = truncate(
            (await matched.innerText().catch(() => '')).replace(/\s+/g, ' ').trim(),
            1200
          );
          await captureState(page);
          break;
        }
        case 'element_exists': {
          let exists = false;
          if (step.selector) exists = (await page.locator(step.selector).count()) > 0;
          else if (step.text) exists = (await page.getByText(step.text).count()) > 0;
          evidence.checks[`element_exists:${step.key || step.text || step.selector}`] = exists;
          break;
        }
        case 'visible_text': {
          const locator = step.selector ? page.locator(step.selector).first() : page.locator('body');
          const text = await locator.innerText().catch(() => '');
          const key = step.key || 'visible_text';
          evidence.checks[key] = truncate(text.replace(/\s+/g, ' ').trim(), step.max_chars ?? 1500);
          break;
        }
        case 'get_url':
          evidence.checks.current_url = page.url();
          break;
        case 'snapshot':
          await captureState(page);
          break;
        case 'screenshot': {
          const name = step.name || `${featureId}-${evidence.action_log.length}`;
          const file = path.join(screenshotDir, `${name}.png`);
          await page.screenshot({ path: file, fullPage: !!step.fullPage });
          evidence.screenshot_path = file;
          evidence.checks[`screenshot:${name}`] = file;
          break;
        }
        default:
          throw new Error(`Unknown action: ${action}`);
      }
    }
    if (!evidence.visible_text && !evidence.aria_snapshot) {
      await captureState(page);
    }
  } catch (err) {
    evidence.error = err.message || String(err);
    try {
      const failShot = path.join(screenshotDir, `${featureId}-error.png`);
      await page.screenshot({ path: failShot, fullPage: true });
      evidence.screenshot_path = failShot;
    } catch {
      // ignore secondary screenshot errors
    }
    await captureState(page).catch(() => {});
  } finally {
    await browser.close();
  }

  fs.writeFileSync(outputPath, JSON.stringify(evidence, null, 2));
  process.exit(evidence.error ? 1 : 0);
}

run().catch((err) => {
  evidence.error = err.message || String(err);
  fs.writeFileSync(outputPath, JSON.stringify(evidence, null, 2));
  process.exit(1);
});
