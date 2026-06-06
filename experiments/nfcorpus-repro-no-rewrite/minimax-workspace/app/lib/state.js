'use strict';

const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');

/**
 * In-memory application state. Lives for the lifetime of the Node process and
 * is rebuilt at every startup. The state is intentionally simple: callers
 * fetch the latest snapshot via `getSnapshot()` and trigger work via the
 * methods exposed on this object.
 */
class AppState {
  constructor() {
    this.phase = 'initializing';
    this.startedAt = new Date();
    this.lastUpdatedAt = new Date();
    this.errors = [];
    this.warnings = [];
    this.java = null;
    this.fatjar = { path: null, exists: false, sizeBytes: null };
    this.reproduction = {
      configs: null,
      beirCore: null,
      nfcorpus: null,
      rawShowPath: null,
    };
    this.prebuiltIndex = {
      name: 'beir-v1.0.0-nfcorpus.flat',
      entry: null,
      path: null,
      downloadRequired: false,
    };
    this.topics = {
      set: 'beir-nfcorpus',
      count: null,
      raw: null,
    };
    this.search = {
      lastCommand: null,
      lastResultCount: null,
      lastDurationMs: null,
    };
    this.eval = {
      status: 'pending',
      runFile: null,
      evalFile: null,
      observed: [],
      expected: {},
      metricDefinitions: {},
      lastDurationMs: null,
      lastRunAt: null,
      cached: false,
      messages: [],
    };
    this.commands = [];
    this.ports = { http: null, rest: null };
    this.restServer = { running: false, pid: null, port: null, lastError: null };
  }

  addError(err) {
    this.errors.push({ at: new Date().toISOString(), message: String(err && err.message ? err.message : err) });
    if (this.errors.length > 50) this.errors.shift();
  }

  addWarning(msg) {
    this.warnings.push({ at: new Date().toISOString(), message: String(msg) });
    if (this.warnings.length > 50) this.warnings.shift();
  }

  recordCommand(record) {
    this.commands.push(record);
    if (this.commands.length > 200) this.commands.shift();
  }

  markUpdated() {
    this.lastUpdatedAt = new Date();
  }
}

/**
 * Load cached eval/run files from disk if they exist. Used to populate the
 * state during a cold start when a previous run already produced artifacts.
 */
async function loadCachedArtifacts(state, dirs) {
  const { dataDir, logsDir } = dirs;
  const runPath = path.join(dataDir, 'run.nfcorpus.bm25.txt');
  const evalPath = path.join(dataDir, 'eval.nfcorpus.bm25.txt');
  const result = { runFile: null, evalFile: null };
  if (fs.existsSync(runPath)) {
    result.runFile = runPath;
    const stat = await fsp.stat(runPath);
    state.eval.runFile = { path: runPath, sizeBytes: stat.size, mtime: stat.mtime.toISOString() };
  }
  if (fs.existsSync(evalPath)) {
    result.evalFile = evalPath;
    const stat = await fsp.stat(evalPath);
    state.eval.evalFile = { path: evalPath, sizeBytes: stat.size, mtime: stat.mtime.toISOString() };
    const raw = await fsp.readFile(evalPath, 'utf8');
    const { parseTrecEval } = require('./anserini');
    state.eval.observed = parseTrecEval(raw);
    state.eval.status = 'cached';
    state.eval.cached = true;
  }
  // Move existing log files into the snapshot.
  if (fs.existsSync(logsDir)) {
    const entries = await fsp.readdir(logsDir);
    for (const e of entries) {
      state.eval.messages.push({ at: new Date().toISOString(), kind: 'cache', text: `Found log ${e}` });
    }
  }
  return result;
}

module.exports = { AppState, loadCachedArtifacts };
