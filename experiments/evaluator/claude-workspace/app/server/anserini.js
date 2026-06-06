// Wrapper around the Anserini fatjar CLI.
// All commands here invoke real Anserini Java classes. No mocking.

import { spawn } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..", "..");

/**
 * Locate the Anserini fatjar.
 * Order: ANSERINI_JAR env var -> any anserini-*-fatjar.jar in repo root or one level up.
 */
export function findFatjar() {
  if (process.env.ANSERINI_JAR && existsSync(process.env.ANSERINI_JAR)) {
    return resolve(process.env.ANSERINI_JAR);
  }
  const candidates = [REPO_ROOT, resolve(REPO_ROOT, "..")];
  for (const dir of candidates) {
    try {
      for (const f of readdirSync(dir)) {
        if (/^anserini-.*-fatjar\.jar$/.test(f)) {
          return join(dir, f);
        }
      }
    } catch {
      // ignore
    }
  }
  return null;
}

function runJava({ jar, mainClass, args, timeoutMs = 10 * 60 * 1000 }) {
  return new Promise((resolveP, rejectP) => {
    const child = spawn(
      "java",
      ["-cp", jar, mainClass, ...args],
      { stdio: ["ignore", "pipe", "pipe"] }
    );
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      rejectP(new Error(`Anserini command timed out: ${mainClass}`));
    }, timeoutMs);
    child.stdout.on("data", (d) => {
      stdout += d.toString();
    });
    child.stderr.on("data", (d) => {
      stderr += d.toString();
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      rejectP(err);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        const err = new Error(
          `Anserini ${mainClass} exited with code ${code}: ${stderr.slice(-2000)}`
        );
        err.stdout = stdout;
        err.stderr = stderr;
        err.exitCode = code;
        rejectP(err);
        return;
      }
      resolveP({ stdout, stderr });
    });
  });
}

/**
 * List prebuilt indexes of the given type (default: inverted).
 * Returns parsed JSON array.
 */
export async function listPrebuiltIndexes(jar, type = "inverted") {
  const { stdout } = await runJava({
    jar,
    mainClass: "io.anserini.cli.PrebuiltIndexRegistry",
    args: ["--type", type, "--list"],
    timeoutMs: 60_000,
  });
  // Strip any non-JSON preamble that the launcher may emit.
  const start = stdout.indexOf("[");
  if (start === -1) {
    throw new Error("PrebuiltIndexRegistry returned no JSON");
  }
  return JSON.parse(stdout.slice(start));
}

/**
 * List all topic symbols (returns array of strings).
 */
export async function listTopics(jar) {
  const { stdout } = await runJava({
    jar,
    mainClass: "io.anserini.cli.TopicsRegistry",
    args: ["--list"],
    timeoutMs: 60_000,
  });
  const start = stdout.indexOf("[");
  if (start === -1) {
    throw new Error("TopicsRegistry returned no JSON");
  }
  return JSON.parse(stdout.slice(start));
}

/**
 * Run SearchCollection (batch retrieval) using BM25.
 * Writes a TREC-format run file at outputPath.
 */
export async function searchCollection({
  jar,
  index,
  topics,
  outputPath,
  hits = 1000,
  threads = 1,
}) {
  return runJava({
    jar,
    mainClass: "io.anserini.search.SearchCollection",
    args: [
      "-threads",
      String(threads),
      "-index",
      index,
      "-topics",
      topics,
      "-output",
      outputPath,
      "-hits",
      String(hits),
      "-bm25",
    ],
    timeoutMs: 30 * 60 * 1000,
  });
}

/**
 * Run TrecEval. Returns stdout (typically: "<metric>\tall\t<score>" lines).
 */
export async function trecEval({ jar, qrels, runPath, metrics }) {
  const args = ["-c"];
  for (const m of metrics) {
    args.push("-m", m);
  }
  args.push(qrels, runPath);
  return runJava({
    jar,
    mainClass: "io.anserini.eval.TrecEval",
    args,
    timeoutMs: 5 * 60 * 1000,
  });
}

/**
 * Parse TrecEval stdout lines like:
 *   "map                   \tall\t0.3123"
 * Returns: { [metric_key]: score_number }
 */
export function parseTrecEval(stdout) {
  const out = {};
  for (const raw of stdout.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    // Split on whitespace.
    const parts = line.split(/\s+/);
    if (parts.length !== 3) continue;
    const [metric, scope, scoreStr] = parts;
    if (scope !== "all") continue;
    const score = Number(scoreStr);
    if (!Number.isFinite(score)) continue;
    out[metric] = score;
  }
  return out;
}
