import express from "express";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  findFatjar,
  listPrebuiltIndexes,
  listTopics,
  searchCollection,
  trecEval,
  parseTrecEval,
} from "./anserini.js";
import { annotateCatalog } from "./pairings.js";
import { METRICS, metricById } from "./metrics.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const APP_ROOT = resolve(__dirname, "..");
const RUNS_DIR = join(APP_ROOT, "runs");
const PUBLIC_DIR = join(APP_ROOT, "public");

function ensureRunsDir() {
  if (!existsSync(RUNS_DIR)) mkdirSync(RUNS_DIR, { recursive: true });
}

function checkJava() {
  const res = spawnSync("java", ["-version"], { encoding: "utf8" });
  return res.status === 0;
}

const app = express();
app.use(express.json({ limit: "1mb" }));
app.use(express.static(PUBLIC_DIR));

// In-memory cached catalog/topics, fetched once at startup.
let CATALOG = null;        // annotated prebuilt inverted indexes
let TOPICS = null;         // all topic symbols
let CATALOG_ERROR = null;  // if registry calls failed
let FATJAR = null;
const ANSERINI_VERSION = (() => {
  // Will be filled when FATJAR is resolved.
  return null;
})();

async function loadRegistries() {
  FATJAR = findFatjar();
  if (!FATJAR) {
    CATALOG_ERROR = "Anserini fatjar not found. Set ANSERINI_JAR or place anserini-*-fatjar.jar in the workspace root.";
    return;
  }
  if (!checkJava()) {
    CATALOG_ERROR = "Java is not available on PATH. Install Java 21 to run Anserini.";
    return;
  }
  try {
    const [indexes, topics] = await Promise.all([
      listPrebuiltIndexes(FATJAR, "inverted"),
      listTopics(FATJAR),
    ]);
    TOPICS = topics;
    const annotated = annotateCatalog(indexes, topics);
    // Sort: CACM first, then evaluable, then alphabetical.
    annotated.sort((a, b) => {
      if (a.name === "cacm") return -1;
      if (b.name === "cacm") return 1;
      if (a.evaluable !== b.evaluable) return a.evaluable ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    CATALOG = annotated;
    console.log(
      `Loaded catalog: ${CATALOG.length} prebuilt inverted indexes ` +
        `(${CATALOG.filter((e) => e.evaluable).length} evaluable), ` +
        `${TOPICS.length} topic symbols.`
    );
  } catch (e) {
    CATALOG_ERROR = `Failed to load Anserini registries: ${e.message}`;
    console.error(CATALOG_ERROR);
  }
}

app.get("/api/health", (req, res) => {
  res.json({
    javaAvailable: checkJava(),
    fatjar: FATJAR,
    catalogLoaded: CATALOG !== null,
    catalogError: CATALOG_ERROR,
    catalogSize: CATALOG ? CATALOG.length : 0,
    evaluableCount: CATALOG ? CATALOG.filter((e) => e.evaluable).length : 0,
    topicsCount: TOPICS ? TOPICS.length : 0,
  });
});

app.get("/api/catalog", (req, res) => {
  if (CATALOG_ERROR) {
    return res.status(503).json({ error: CATALOG_ERROR });
  }
  if (!CATALOG) {
    return res.status(503).json({ error: "Catalog still loading. Try again in a moment." });
  }
  res.json({
    fatjar: FATJAR,
    defaultIndex: "cacm",
    indexes: CATALOG,
    metrics: METRICS,
  });
});

app.get("/api/metrics", (req, res) => {
  res.json({ metrics: METRICS });
});

app.post("/api/evaluate", async (req, res) => {
  if (CATALOG_ERROR) {
    return res.status(503).json({ error: CATALOG_ERROR });
  }
  if (!FATJAR) {
    return res.status(503).json({ error: "Anserini fatjar not available." });
  }
  ensureRunsDir();

  const { index, metricId } = req.body || {};
  if (!index) {
    return res.status(400).json({ error: "Missing `index`." });
  }
  const entry = CATALOG.find((e) => e.name === index);
  if (!entry) {
    return res.status(404).json({ error: `Index not found in catalog: ${index}` });
  }
  if (!entry.evaluable || !entry.pairing) {
    return res.status(400).json({
      error: `Index "${index}" is catalog-only: no compatible topics/qrels pairing was derived.`,
    });
  }

  const metric = metricById(metricId || "ndcg_cut_10");
  if (!metric) {
    return res.status(400).json({ error: `Unknown metric: ${metricId}` });
  }

  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const safeName = index.replace(/[^A-Za-z0-9._-]/g, "_");
  const runPath = join(RUNS_DIR, `run.${safeName}.bm25.${ts}.txt`);
  const evalPath = join(RUNS_DIR, `eval.${safeName}.bm25.${ts}.txt`);

  const started = Date.now();
  try {
    await searchCollection({
      jar: FATJAR,
      index: entry.name,
      topics: entry.pairing.topics,
      outputPath: runPath,
      hits: 1000,
      threads: 1,
    });
  } catch (e) {
    return res.status(500).json({
      stage: "retrieval",
      error: `Anserini SearchCollection failed: ${e.message}`,
      runPath,
    });
  }

  if (!existsSync(runPath)) {
    return res.status(500).json({
      stage: "retrieval",
      error: "Retrieval completed but no run file was produced.",
      runPath,
    });
  }

  let evalOut;
  try {
    evalOut = await trecEval({
      jar: FATJAR,
      qrels: entry.pairing.qrels,
      runPath,
      metrics: [metric.trecEvalArg],
    });
  } catch (e) {
    return res.status(500).json({
      stage: "evaluation",
      error: `Anserini TrecEval failed: ${e.message}`,
      runPath,
    });
  }

  // Persist eval output for inspection.
  try {
    const { writeFileSync } = await import("node:fs");
    writeFileSync(evalPath, evalOut.stdout);
  } catch {
    // non-fatal
  }

  const parsed = parseTrecEval(evalOut.stdout);
  const score = parsed[metric.resultKey];
  if (score === undefined) {
    return res.status(500).json({
      stage: "evaluation",
      error: `TrecEval did not report metric ${metric.resultKey}. Raw output: ${evalOut.stdout.slice(0, 500)}`,
      runPath,
      evalPath,
    });
  }

  const elapsedMs = Date.now() - started;
  res.json({
    status: "ok",
    index: entry.name,
    indexDescription: entry.description,
    topics: entry.pairing.topics,
    qrels: entry.pairing.qrels,
    metric: {
      id: metric.id,
      label: metric.label,
      trecEvalArg: metric.trecEvalArg,
      resultKey: metric.resultKey,
    },
    score,
    allScores: parsed,
    elapsedMs,
    runPath,
    evalPath,
    evalPreview: evalOut.stdout.trim(),
    fatjar: FATJAR,
  });
});

const PORT = Number(process.env.PORT || 5173);

await loadRegistries();

app.listen(PORT, () => {
  console.log(`Anserini Prebuilt Index Evaluator listening on http://localhost:${PORT}`);
});
