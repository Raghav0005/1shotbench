// NFCorpus Live Retrieval Diagnostics Workbench - frontend logic.

const $ = (sel) => document.querySelector(sel);

function statusBadge(text, cls) {
  return `<span class="status-${cls}" data-testid="status-${cls}">${text}</span>`;
}

function fmtNum(x, digits=4) {
  if (x === null || x === undefined || isNaN(x)) return "–";
  return Number(x).toFixed(digits);
}

function renderReadiness(s) {
  const r = s.readiness;
  $("#r-java").innerHTML = r.java_ok
    ? `${statusBadge("ok", "ok")} <span class="muted">${r.java_version || ""}</span>`
    : statusBadge("missing", "error");
  $("#r-jar").innerHTML = r.jar_ok
    ? `${statusBadge("ok", "ok")} <code>${r.jar_path}</code>`
    : statusBadge("missing", "error");
  $("#r-index").innerHTML = r.nfcorpus_index_ok
    ? `${statusBadge("ready", "ok")} <code>${r.nfcorpus_index_path || ""}</code>`
    : statusBadge("preparing…", "pending");
  $("#r-reproduction").innerHTML = r.reproduction_ok
    ? `${statusBadge("ok", "ok")} <code>${r.reproduction_config}/${r.reproduction_condition}</code>`
    : statusBadge("pending", "pending");
  $("#r-search").innerHTML = r.search_ok
    ? `${statusBadge("ok", "ok")} <code data-testid="rest-url">${r.rest_url || ""}</code>`
    : statusBadge("starting…", "pending");
  $("#r-eval").innerHTML = r.eval_ok
    ? statusBadge("ok", "ok")
    : `${statusBadge(s.eval.status, s.eval.status)}`;
  $("#readiness-errors").textContent = (r.errors || []).join(" · ");
  $("#repro-config").textContent = r.reproduction_config;
  $("#repro-condition").textContent = r.reproduction_condition;
}

function renderEval(s) {
  const e = s.eval;
  $("#e-status").innerHTML = statusBadge(e.status, e.status);
  $("#e-elapsed").textContent = e.elapsed_seconds ? `${e.elapsed_seconds.toFixed(2)}s` : "–";
  $("#e-source").textContent = e.fresh ? "fresh rerun" : "cached setup run";
  $("#e-source").setAttribute("data-testid", "eval-source");
  const body = $("#metrics-body");
  body.innerHTML = "";
  // Always include the expected-metric row first.
  for (const row of (e.comparisons || [])) {
    const tr = document.createElement("tr");
    tr.dataset.testid = `metric-${row.metric}`;
    tr.innerHTML = `
      <td><code>${row.metric}</code></td>
      <td data-testid="expected-${row.metric}">${fmtNum(row.expected)}</td>
      <td data-testid="observed-${row.metric}">${fmtNum(row.observed)}</td>
      <td data-testid="delta-${row.metric}">${row.delta == null ? "–" : (row.delta>=0?"+":"") + fmtNum(row.delta)}</td>
      <td>${statusBadge(row.status, row.status)}</td>`;
    body.appendChild(tr);
  }
  // Extra metrics with no expected value.
  for (const m of Object.keys(e.observed || {})) {
    if ((e.comparisons || []).find((r) => r.metric === m)) continue;
    const tr = document.createElement("tr");
    tr.dataset.testid = `metric-${m}`;
    tr.innerHTML = `
      <td><code>${m}</code></td>
      <td>–</td>
      <td data-testid="observed-${m}">${fmtNum(e.observed[m])}</td>
      <td>–</td>
      <td><span class="muted">observed only</span></td>`;
    body.appendChild(tr);
  }
  $("#eval-error").textContent = e.error || "";
}

function renderDrawer(s) {
  const cmdHost = $("#commands");
  cmdHost.innerHTML = "";
  const order = [
    ["fatjar_verify", "Fatjar verification (install-anserini-fatjar skill: PrebuiltIndexRegistry)"],
    ["reproduction_show", "Reproduction discovery (anserini-reproduction skill: --show)"],
    ["index_warmup", "NFCorpus index setup (anserini-cli skill: Search warmup)"],
    ["rest_server", "Anserini RestServer (powers live search)"],
    ["bm25_search", "BM25 retrieval (SearchCollection)"],
    ["bm25_eval", "Evaluation (TrecEval against beir-v1.0.0-nfcorpus.test qrels)"],
  ];
  for (const [k, label] of order) {
    if (!s.commands[k]) continue;
    const div = document.createElement("div");
    div.className = "cmd";
    div.dataset.testid = `cmd-${k}`;
    div.innerHTML = `<span class="label">${label}</span>${s.commands[k]}`;
    cmdHost.appendChild(div);
  }

  const artHost = $("#artifacts");
  artHost.innerHTML = "";
  for (const [k, v] of Object.entries(s.artifacts || {})) {
    const div = document.createElement("div");
    div.className = "art";
    div.dataset.testid = `art-${k}`;
    div.innerHTML = `<span class="label">${k}</span>${v}`;
    artHost.appendChild(div);
  }
  // Eval run file + eval file (also listed in artifacts but surfaced again for the test).
  if (s.eval.run_file) {
    const div = document.createElement("div");
    div.className = "art";
    div.dataset.testid = "art-eval-run-file";
    div.innerHTML = `<span class="label">Run file (TREC format)</span>${s.eval.run_file}`;
    artHost.appendChild(div);
  }

  const previewHost = $("#previews");
  previewHost.innerHTML = "";
  for (const [k, v] of Object.entries(s.previews || {})) {
    const div = document.createElement("div");
    div.className = "preview";
    div.dataset.testid = `preview-${k}`;
    div.innerHTML = `<span class="label">${k}</span>${v}`;
    previewHost.appendChild(div);
  }
}

async function refresh() {
  try {
    const r = await fetch("/api/state");
    const s = await r.json();
    renderReadiness(s);
    renderEval(s);
    renderDrawer(s);
    window.__lastState = s;
    document.body.dataset.ready = (s.readiness.search_ok && s.readiness.eval_ok) ? "1" : "0";
  } catch (e) {
    console.warn("state refresh failed", e);
  }
}

async function runSearch(q) {
  $("#q").value = q;
  $("#search-meta").textContent = `Searching NFCorpus for "${q}"…`;
  $("#results").innerHTML = "";
  try {
    const r = await fetch("/api/search?q=" + encodeURIComponent(q) + "&hits=10");
    if (!r.ok) {
      const t = await r.text();
      $("#search-meta").textContent = `Error: ${t}`;
      return;
    }
    const data = await r.json();
    $("#search-meta").innerHTML =
      `<span data-testid="search-elapsed">${data.elapsed_seconds.toFixed(3)}s</span> · ` +
      `<span data-testid="search-hits">${data.hits} hits</span> · ` +
      `Live REST URL: <code>${data.rest_url}</code> · ` +
      `Equivalent CLI: <code>${data.command_equivalent}</code>`;
    const ol = $("#results");
    ol.innerHTML = "";
    for (const item of data.results) {
      const li = document.createElement("li");
      li.dataset.testid = "result-item";
      li.innerHTML =
        `<div class="meta">rank <span data-testid="result-rank">${item.rank}</span> · ` +
        `docid <code data-testid="result-docid">${item.docid}</code> · ` +
        `score <span data-testid="result-score">${item.score}</span></div>` +
        `<div class="title" data-testid="result-title">${item.title || "(untitled)"}</div>` +
        `<div class="snippet" data-testid="result-snippet">${item.snippet}</div>`;
      ol.appendChild(li);
    }
  } catch (e) {
    $("#search-meta").textContent = "Error: " + e;
  }
}

async function loadSamples() {
  const r = await fetch("/api/sample-queries");
  const data = await r.json();
  const host = $("#sample-queries");
  for (const q of data.queries) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = q;
    b.dataset.testid = "sample-query";
    b.addEventListener("click", () => runSearch(q));
    host.appendChild(b);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("#search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("#q").value.trim();
    if (q) runSearch(q);
  });
  $("#rerun-btn").addEventListener("click", async () => {
    $("#rerun-btn").disabled = true;
    try {
      await fetch("/api/eval/rerun", { method: "POST" });
    } finally {
      setTimeout(() => { $("#rerun-btn").disabled = false; }, 1500);
    }
    refresh();
  });
  loadSamples();
  refresh();
  setInterval(refresh, 2000);
});
