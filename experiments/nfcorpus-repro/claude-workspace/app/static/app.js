"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const PHASE_GROUPS = {
  ready: "ready",
  failed: "failed",
};
function phaseState(phase) {
  if (phase === "ready") return "ready";
  if (phase === "failed") return "failed";
  return "working";
}

function setText(testid, text) {
  const el = document.querySelector(`[data-testid="${testid}"]`);
  if (el) el.textContent = text == null ? "" : String(text);
}

function setCardState(testid, value, detail, stateClass) {
  const card = document.querySelector(`[data-testid="${testid}"]`);
  if (!card) return;
  card.setAttribute("data-state", stateClass);
  card.querySelector(`[data-testid="${testid}-value"]`).textContent = value;
  const det = card.querySelector(`[data-testid="${testid}-detail"]`);
  if (det) det.textContent = detail || "";
}

function escapeHtml(s) {
  return (s == null ? "" : String(s))
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtFloat(n, places = 4) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(places);
}

async function fetchStatus() {
  const resp = await fetch("/api/status", { cache: "no-store" });
  if (!resp.ok) throw new Error("status failed");
  return resp.json();
}

function renderReadiness(status) {
  const phase = status.phase;
  const phasePill = $("[data-testid=phase-pill]");
  phasePill.setAttribute("data-state", phaseState(phase));
  setText("phase-label", phase);

  // Java
  if (status.java && status.java.available) {
    setCardState("status-java", `Java ${status.java.major ?? "?"}`, "Anserini requires major 21", "ok");
  } else {
    setCardState("status-java", "missing", "Install Java 21 (Temurin/OpenJDK).", "bad");
  }

  // Fatjar
  const f = status.fatjar || {};
  if (f.verified) {
    setCardState("status-fatjar", "verified", `${f.path}`, "ok");
  } else if (f.exists) {
    setCardState("status-fatjar", "found, verifying…", f.path, "warn");
  } else {
    setCardState("status-fatjar", "missing", f.path || "ANSERINI_JAR not set", "bad");
  }

  // NFCorpus
  const nfc = status.nfcorpus || {};
  const entry = nfc.registry_entry;
  if (nfc.ready) {
    setCardState(
      "status-nfcorpus",
      "ready",
      entry ? `${entry.documents} docs, ${entry.unique_terms} unique terms, ~${Math.round((entry.size || 0) / 1024 / 1024)} MB` : "",
      "ok",
    );
  } else if (entry) {
    setCardState(
      "status-nfcorpus",
      "registered, downloading…",
      `${entry.filename}`,
      "warn",
    );
  } else {
    setCardState("status-nfcorpus", "pending", `index=${nfc.index}`, "warn");
  }

  // Reproduction
  const repro = status.reproduction || {};
  if (repro.target) {
    const exp = Object.entries(repro.target.expected_scores || {}).map(([k, v]) => `${k}=${v}`).join(", ");
    setCardState(
      "status-reproduction",
      "found",
      `config=${repro.config}, condition=${repro.target.condition_name}, expected ${exp || "(none)"}`,
      "ok",
    );
  } else if (repro.available === false && (status.errors || []).some((e) => e.includes("Reproduction"))) {
    setCardState("status-reproduction", "missing", "ReproduceFromPrebuiltIndexes did not expose nfcorpus", "bad");
  } else {
    setCardState("status-reproduction", "discovering…", `config=${repro.config || ""}`, "warn");
  }

  // Search
  const rest = status.rest_server || {};
  if (rest.ready) {
    setCardState("status-search", "available", `RestServer at ${rest.base_url}`, "ok");
  } else if (rest.running) {
    setCardState("status-search", "starting…", rest.base_url || "", "warn");
  } else if (rest.error) {
    setCardState("status-search", "failed", rest.error, "bad");
  } else {
    setCardState("status-search", "pending", "", "warn");
  }

  // Evaluation
  const ev = status.evaluation || {};
  if (ev.ran) {
    const label = ev.overall_status || "ran";
    const state = ev.overall_status === "match" ? "ok" : (ev.overall_status === "fail" ? "bad" : "warn");
    setCardState("status-evaluation", label, ev.fresh ? "fresh rerun" : "cached setup pass", state);
  } else {
    setCardState("status-evaluation", "pending", "Setup will run BM25 + TrecEval", "warn");
  }

  // Setup log
  const log = (status.log || []).map((l) => `[${new Date(l.ts * 1000).toLocaleTimeString()}] ${l.msg}`).join("\n");
  setText("setup-log", log);

  // Errors
  const errEl = $("[data-testid=errors]");
  if ((status.errors || []).length) {
    errEl.hidden = false;
    errEl.innerHTML = `<strong>Errors:</strong><ul>${status.errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("")}</ul>`;
  } else {
    errEl.hidden = true;
  }

  // Deployment info
  if (status.deployment) {
    setText("deployment-port", `PORT (${status.deployment.port})`);
    setText("deployment-cache", status.deployment.cache_dir);
  }
}

function renderEvaluation(status) {
  const ev = status.evaluation || {};
  setText("eval-status", ev.overall_status || "pending");
  setText("eval-elapsed", ev.elapsed_seconds != null ? `${ev.elapsed_seconds.toFixed(2)} s` : "—");
  setText("eval-source", ev.fresh ? "fresh rerun" : (ev.ran ? "cached startup pass" : "—"));
  setText("eval-rerun-count", String(ev.rerun_count || 0));
  setText("eval-run-path", ev.run_path || "—");
  setText("eval-eval-path", ev.eval_path || "—");

  const tbody = $("[data-testid=metrics-table-body]");
  const target = (status.reproduction && status.reproduction.target) || {};
  const comparison = ev.comparison || [];

  let rows = [];
  if (comparison.length) {
    rows = comparison.map((row) => `
      <tr>
        <td>${escapeHtml(row.metric)}</td>
        <td><code>${escapeHtml(row.trec_eval_key)}</code></td>
        <td data-testid="metric-expected-${escapeHtml(row.trec_eval_key)}">${fmtFloat(row.expected)}</td>
        <td data-testid="metric-observed-${escapeHtml(row.trec_eval_key)}">${fmtFloat(row.observed)}</td>
        <td data-testid="metric-delta-${escapeHtml(row.trec_eval_key)}">${row.delta == null ? "—" : (row.delta >= 0 ? "+" : "") + Number(row.delta).toFixed(4)}</td>
        <td class="status-${escapeHtml(row.status)}" data-testid="metric-status-${escapeHtml(row.trec_eval_key)}">${escapeHtml(row.status)}</td>
      </tr>
    `);
  } else if (Object.keys(ev.metrics || {}).length) {
    rows = Object.entries(ev.metrics).map(([k, v]) => `
      <tr>
        <td>${escapeHtml(k)}</td>
        <td><code>${escapeHtml(k)}</code></td>
        <td>—</td>
        <td data-testid="metric-observed-${escapeHtml(k)}">${fmtFloat(v)}</td>
        <td>—</td>
        <td class="status-missing">observed-only</td>
      </tr>
    `);
  } else {
    rows = [`<tr><td colspan="6" style="color:#475569">No evaluation metrics available yet.</td></tr>`];
  }
  tbody.innerHTML = rows.join("");
}

function renderCommands(status) {
  const list = $("[data-testid=commands-list]");
  const commands = status.commands || {};
  const order = [
    "java_version",
    "verify_fatjar_registry",
    "reproduce_show",
    "reproduce_dry_run",
    "search_collection",
    "trec_eval",
  ];
  const labels = {
    java_version: "Java runtime check",
    verify_fatjar_registry: "Verify NFCorpus prebuilt index entry",
    reproduce_show: "Discover reproduction target (--show)",
    reproduce_dry_run: "Reproduction dry-run (exact commands)",
    search_collection: "Run BM25 SearchCollection over NFCorpus",
    trec_eval: "Evaluate run file with TrecEval",
  };
  const blocks = [];
  // Live search REST command first.
  const rest = status.rest_server || {};
  if (rest.cmd) {
    blocks.push(`
      <div class="command-block" data-testid="cmd-restserver">
        <h3>Live search backend (Anserini RestServer)</h3>
        <div class="command-meta">base url: <code>${escapeHtml(rest.base_url || "")}</code> &middot; ready: ${rest.ready ? "yes" : "no"}</div>
        <pre>${escapeHtml(rest.cmd)}</pre>
        <div class="command-meta">log: <code>${escapeHtml(rest.log_path || "")}</code></div>
      </div>
    `);
  }
  for (const key of order) {
    const c = commands[key];
    if (!c) continue;
    blocks.push(`
      <div class="command-block" data-testid="cmd-${key}">
        <h3>${escapeHtml(labels[key] || key)}</h3>
        <div class="command-meta">exit=${c.returncode} &middot; elapsed=${(c.elapsed_seconds ?? 0).toFixed(3)}s</div>
        <pre>${escapeHtml(c.cmd || "")}</pre>
        ${c.stdout ? `<details><summary>stdout (${c.stdout.length} bytes)</summary><pre>${escapeHtml(c.stdout)}</pre></details>` : ""}
        ${c.stderr ? `<details><summary>stderr</summary><pre>${escapeHtml(c.stderr)}</pre></details>` : ""}
      </div>
    `);
  }
  list.innerHTML = blocks.join("");
}

function renderSamples(status) {
  const samples = (status && status.sample_queries) || [];
  const container = $("[data-testid=sample-queries]");
  container.innerHTML = samples
    .map(
      (s) => `<span class="sample" data-testid="sample-${escapeHtml(s.id)}" data-query="${escapeHtml(s.title)}">${escapeHtml(s.title)}</span>`,
    )
    .join("");
  container.querySelectorAll(".sample").forEach((el) => {
    el.addEventListener("click", () => {
      const q = el.getAttribute("data-query");
      $("#search-input").value = q;
      runSearch();
    });
  });
}

async function runSearch() {
  const input = $("#search-input");
  const q = input.value.trim();
  const hits = $("#hits-input").value || 10;
  if (!q) return;
  const meta = $("[data-testid=search-meta]");
  const list = $("[data-testid=search-results]");
  meta.textContent = `Searching for "${q}"…`;
  list.innerHTML = "";
  try {
    const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}&hits=${encodeURIComponent(hits)}`);
    const body = await resp.json();
    if (!body.ok) {
      meta.textContent = `Error: ${body.error || resp.statusText}`;
      return;
    }
    meta.innerHTML = `Returned <strong data-testid="result-count">${body.result_count}</strong> hits in ${body.elapsed_seconds.toFixed(3)}s &middot; index <code>${escapeHtml(body.index)}</code> &middot; backend <code>${escapeHtml(body.backend)}</code>`;
    list.innerHTML = body.results
      .map(
        (r) => `
          <li data-testid="result-${escapeHtml(String(r.rank))}">
            <div>
              <span class="docid" data-testid="result-docid-${escapeHtml(String(r.rank))}">${escapeHtml(r.docid)}</span>
              <span class="score" data-testid="result-score-${escapeHtml(String(r.rank))}">score ${fmtFloat(r.score, 4)}</span>
            </div>
            <div class="title" data-testid="result-title-${escapeHtml(String(r.rank))}">${escapeHtml(r.title || "(no title)")}</div>
            <div class="snippet" data-testid="result-snippet-${escapeHtml(String(r.rank))}">${escapeHtml((r.text || "").slice(0, 500))}${(r.text || "").length > 500 ? "…" : ""}</div>
          </li>
        `,
      )
      .join("");
  } catch (e) {
    meta.textContent = `Request failed: ${e}`;
  }
}

async function rerunEvaluation() {
  const btn = $("#rerun-btn");
  btn.disabled = true;
  btn.textContent = "Rerunning…";
  try {
    const resp = await fetch("/api/evaluation/rerun", { method: "POST" });
    const body = await resp.json();
    if (!body.ok) {
      alert("Rerun failed: " + (body.error || body.errors?.join(", ") || "unknown"));
    }
  } catch (e) {
    alert("Rerun failed: " + e);
  } finally {
    btn.disabled = false;
    btn.textContent = "Rerun evaluation (fresh)";
    refresh();
  }
}

async function refresh() {
  try {
    const status = await fetchStatus();
    renderReadiness(status);
    renderEvaluation(status);
    renderCommands(status);
    renderSamples(status);
  } catch (e) {
    console.error(e);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  $("#search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    runSearch();
  });
  $("#rerun-btn").addEventListener("click", rerunEvaluation);
  refresh();
  setInterval(refresh, 4000);
});
