'use strict';

const { spawn, execFile } = require('child_process');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const yaml = require('js-yaml');

/**
 * Thin wrapper around the Anserini fatjar. Executes commands with `java -cp
 * $ANSERINI_JAR <main-class> <args>`, captures stdout/stderr, and exposes a
 * small structured surface to the rest of the app.
 */
class AnseriniRunner {
  constructor(opts) {
    this.jar = opts.jar;
    this.cacheDir = opts.cacheDir;
    this.dataDir = opts.dataDir;
    this.logsDir = opts.logsDir;
    this.commandLog = [];
    this.lastSearchTimeMs = null;
    this.lastEvalTimeMs = null;
  }

  isAvailable() {
    try {
      return Boolean(this.jar) && fs.existsSync(this.jar);
    } catch (_) {
      return false;
    }
  }

  /**
   * Run `java -version` and return { version, raw, ok, error }.
   */
  async probeJava() {
    return new Promise((resolve) => {
      const proc = spawn('java', ['-version']);
      let stdout = '';
      let stderr = '';
      proc.stdout.on('data', (d) => { stdout += d.toString(); });
      proc.stderr.on('data', (d) => { stderr += d.toString(); });
      proc.on('error', (err) => resolve({ ok: false, error: err.message }));
      proc.on('close', (code) => {
        const raw = (stdout + stderr).trim();
        const m = raw.match(/version\s+"(\d+)\.?(\d+)?\.?(\d+)?/i);
        const major = m ? Number(m[1]) : null;
        resolve({
          ok: code === 0,
          code,
          major,
          raw,
        });
      });
    });
  }

  /**
   * Run an Anserini main class via the fatjar and capture output.
   * @param {string} mainClass
   * @param {string[]} args
   * @param {object} [opts]
   * @param {string} [opts.logName] - filename under logsDir to append full output
   * @param {string} [opts.label] - human-readable command label
   * @param {object} [opts.env] - extra env vars
   */
  async runMain(mainClass, args, opts = {}) {
    if (!this.isAvailable()) {
      throw new Error(`Anserini fatjar not found at ${this.jar}`);
    }
    const label = opts.label || `${mainClass} ${args.join(' ')}`;
    const commandLine = `java -cp "${this.jar}" ${mainClass} ${args.map(quoteIfNeeded).join(' ')}`.trim();
    const startedAt = new Date();
    const child = spawn('java', ['-cp', this.jar, mainClass, ...args], {
      env: { ...process.env, ...(opts.env || {}) },
      cwd: this.dataDir,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    const exitCode = await new Promise((resolve, reject) => {
      child.on('error', reject);
      child.on('close', resolve);
    });
    const finishedAt = new Date();
    const record = {
      label,
      command: commandLine,
      mainClass,
      args,
      exitCode,
      startedAt: startedAt.toISOString(),
      finishedAt: finishedAt.toISOString(),
      durationMs: finishedAt - startedAt,
      stdoutTail: stdout.split('\n').slice(-12).join('\n'),
      stderrTail: stderr.split('\n').slice(-12).join('\n'),
    };
    this.commandLog.push(record);
    if (opts.logName) {
      const logPath = path.join(this.logsDir, opts.logName);
      const combined = [
        `# ${label}`,
        `# command: ${commandLine}`,
        `# started: ${record.startedAt}`,
        `# finished: ${record.finishedAt}`,
        `# exit: ${exitCode}`,
        '# --- stdout ---',
        stdout,
        '# --- stderr ---',
        stderr,
      ].join('\n');
      await fsp.writeFile(logPath, combined);
      record.logFile = logPath;
    }
    if (exitCode !== 0) {
      const err = new Error(`${label} exited with code ${exitCode}`);
      err.record = record;
      throw err;
    }
    return { ...record, stdout, stderr };
  }

  /**
   * Run `PrebuiltIndexRegistry --list --filter <regex>` and return the parsed
   * JSON entries. Returns `[]` if the index entry is not present.
   */
  async lookupPrebuiltIndex(filterRegex) {
    const res = await this.runMain('io.anserini.cli.PrebuiltIndexRegistry', [
      '--list',
      '--filter',
      filterRegex,
    ], { label: `PrebuiltIndexRegistry --list --filter ${filterRegex}` });
    try {
      return JSON.parse(res.stdout.trim());
    } catch (e) {
      // Fallback: try to grab the JSON line even if surrounded by other text.
      const m = res.stdout.match(/\[[\s\S]*\]/);
      if (m) {
        return JSON.parse(m[0]);
      }
      throw e;
    }
  }

  /**
   * Run `TopicsRegistry --get <set>` and return the parsed JSON object.
   */
  async getTopics(setName) {
    const res = await this.runMain('io.anserini.cli.TopicsRegistry', [
      '--get',
      setName,
    ], { label: `TopicsRegistry --get ${setName}` });
    try {
      return JSON.parse(res.stdout.trim());
    } catch (e) {
      const m = res.stdout.match(/\{[\s\S]*\}/);
      if (m) {
        return JSON.parse(m[0]);
      }
      throw e;
    }
  }

  /**
   * Run `ReproduceFromPrebuiltIndexes --list` and return the parsed JSON.
   */
  async listReproductions() {
    const res = await this.runMain('io.anserini.reproduce.ReproduceFromPrebuiltIndexes', [
      '--list',
    ], { label: 'ReproduceFromPrebuiltIndexes --list' });
    return JSON.parse(res.stdout.trim());
  }

  /**
   * Run `ReproduceFromPrebuiltIndexes --config <cfg> --show` and return the
   * parsed YAML object.
   */
  async showReproduction(config) {
    const res = await this.runMain('io.anserini.reproduce.ReproduceFromPrebuiltIndexes', [
      '--config',
      config,
      '--show',
    ], { label: `ReproduceFromPrebuiltIndexes --config ${config} --show` });
    return yaml.load(res.stdout);
  }

  /**
   * Run the configured SearchCollection command for the NFCorpus flat BM25
   * condition. Writes a TREC run file and returns the path plus metadata.
   */
  async runNfcorpusSearch({ threads = 1, outputName = 'run.nfcorpus.bm25.txt' } = {}) {
    const outputPath = path.join(this.dataDir, outputName);
    const args = [
      '-threads', String(threads),
      '-index', 'beir-v1.0.0-nfcorpus.flat',
      '-topics', 'beir-nfcorpus',
      '-output', outputPath,
      '-bm25',
      '-removeQuery',
    ];
    const res = await this.runMain('io.anserini.search.SearchCollection', args, {
      label: 'NFCorpus BM25 SearchCollection',
      logName: 'search-collection.log',
    });
    this.lastSearchTimeMs = res.durationMs;
    const stat = await fsp.stat(outputPath);
    return {
      runPath: outputPath,
      command: res.command,
      durationMs: res.durationMs,
      sizeBytes: stat.size,
    };
  }

  /**
   * Run `TrecEval` for the NFCorpus flat BM25 run with the configured metric
   * definition and return observed metrics plus raw output.
   */
  async evaluateNfcorpusRun({ runPath, metricArgs = '-c -m ndcg_cut.10' } = {}) {
    const args = [
      ...metricArgs.split(/\s+/).filter(Boolean),
      'beir-v1.0.0-nfcorpus.test',
      runPath,
    ];
    const res = await this.runMain('io.anserini.eval.TrecEval', args, {
      label: 'NFCorpus TrecEval',
      logName: 'trec-eval.log',
    });
    const observed = parseTrecEval(res.stdout);
    this.lastEvalTimeMs = res.durationMs;
    return {
      raw: res.stdout.trim(),
      observed,
      durationMs: res.durationMs,
      command: res.command,
    };
  }

  /**
   * Spawn a long-running Anserini REST server. Returns the child process and
   * the resolved port. Reuses `port` if free, otherwise picks the next free
   * high port. The server is started with `-Xmx512m` to keep the footprint
   * modest on small hosts.
   */
  async startRestServer({ port = 8081, jvmArgs = ['-Xmx512m'] } = {}) {
    const child = spawn('java', [...jvmArgs, '-cp', this.jar, 'io.anserini.api.RestServer', '--port', String(port)], {
      cwd: this.dataDir,
      env: { ...process.env },
    });
    let started = false;
    let stderrBuf = '';
    const ready = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (!started) reject(new Error(`RestServer failed to start within 60s: ${stderrBuf}`));
      }, 60000);
      child.stderr.on('data', (d) => {
        stderrBuf += d.toString();
        if (/Listening|Started|Netty|HTTP/i.test(stderrBuf) && !started) {
          started = true;
          clearTimeout(timer);
          resolve();
        }
      });
      child.stdout.on('data', (d) => {
        stderrBuf += d.toString();
        if (/Listening|Started|Netty|HTTP/i.test(stderrBuf) && !started) {
          started = true;
          clearTimeout(timer);
          resolve();
        }
      });
      child.on('error', (err) => { clearTimeout(timer); reject(err); });
      child.on('exit', (code) => {
        if (!started) {
          clearTimeout(timer);
          reject(new Error(`RestServer exited with code ${code} before becoming ready: ${stderrBuf}`));
        }
      });
    });
    await ready;
    return { child, port };
  }
}

function quoteIfNeeded(arg) {
  if (arg == null) return '';
  const s = String(arg);
  if (s === '') return '""';
  if (/[\s"'$\\]/.test(s)) {
    return '"' + s.replace(/(["\\$])/g, '\\$1') + '"';
  }
  return s;
}

/**
 * Parse the output of `io.anserini.eval.TrecEval`. Anserini prints
 * tab-separated rows of the form `<metric>\t<condition>\t<score>`. Returns a
 * list of `{ metric, condition, score }` records. The metric column may
 * contain spaces and underscores interchangeably.
 */
function parseTrecEval(stdout) {
  const out = [];
  const lines = stdout.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const parts = trimmed.split(/\s+/);
    if (parts.length < 3) continue;
    const [metric, condition, scoreStr] = parts;
    const score = Number(scoreStr);
    if (!Number.isFinite(score)) continue;
    out.push({ metric, condition, score });
  }
  return out;
}

module.exports = { AnseriniRunner, parseTrecEval };
