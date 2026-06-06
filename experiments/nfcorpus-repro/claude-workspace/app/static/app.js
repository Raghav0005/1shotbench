// Minimal vanilla JS controller for the diagnostics dashboard.
//
// Polls /api/status on a short interval to surface readiness, last evaluation,
// and recorded Anserini command lines. Wires up the search and rerun forms.

(function () {
  const $ = (sel) => document.querySelector(sel);
  const byId = (id) => document.querySelector(`[data-testid="${id}"]`);

  const cardIds = ["java", "fatjar", "nfcorpus", "reproduction", "search", "evaluation"];
  let lastStatusSerialized = "";

  function updateCard(name, card) {
    const root = byId(`status-${name}`);
    if (!root) return;
    root.classList.remove("state-ok", "state-warn", "state-error", "state-pending");
    root.classList.add("state-" + (card.state || "pending"));
    const v = byId(`status-${name}-value`);
    const d = byId(`status-${name}-detail`);
    if (v) v.textContent = card.value || "—";
    if (d) d.textContent = card.detail || "";
  }

  function updatePhase(phase) {
    const pill = byId("phase-pill");
    const label = byId("phase-label");
    if (!pill || !label) return;
    pill.classList.remove("ready", "error", "warn");
    if (phase === "ready") pill.classList.add("ready");
    else if (phase.startsWith("failed")) pill.classList.add("error");
    else pill.classList.add("warn");
    label.textContent = phase;
  }

  function renderSamples(samples) {
    const wrap = byId("sample-queries");
    if (!wrap || wrap.dataset.rendered === "1") return;
    wrap.innerHTML = "";
    (samples || []).forEach((q) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "sample-chip";
      chip.dataset.testid = "sample-chip";
      chip.textContent = q;
      chip.addEventListener("click", () => {
        $("#search-input").value = q;
        runSearch();
      });
      wrap.appendChild(chip);
    });
    wrap.dataset.rendered = "1";
  }

  function renderSetupLog(lines) {
    const pre = byId("setup-log");
    if (!pre) return;
    pre.textContent = (lines || []).join("\n");
  }

  function renderErrors(errors) {
    const box = byId("errors");
    if (!box) return;
    if (!errors || errors.length === 0) {
      box.hidden = true;
      box.textContent = "";
    } else {
      box.hidden = false;
      box.textContent = errors.join("\n");
    }
  }

  function renderEvaluation(ev, expectedMetrics) {
    byId("eval-status").textContent = ev.status || "pending";
    byId("eval-elapsed").textContent =
      ev.elapsed_seconds != null ? `${ev.elapsed_seconds}s` : "—";
    byId("eval-source").textContent = ev.source || "—";
    byId("eval-rerun-count").textContent = String(ev.rerun_count || 0);
    byId("eval-run-path").textContent = ev.run_path || "—";
    byId("eval-eval-path").textContent = ev.eval_path || "—";

    const tbody = byId("metrics-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";
    const rows = (ev.metrics && ev.metrics.length)
      ? ev.metrics
      : Object.entries(expectedMetrics || {}).map(([name, meta]) => ({
          name,
          trec_eval_args: (meta && meta.trec_eval_args_str) || "",
          expected: meta && meta.value,
          observed: null,
          delta: null,
          status: "pending",
        }));
    rows.forEach((m) => {
      const tr = document.createElement("tr");
      tr.dataset.testid = "metric-row";
      tr.dataset.metric = m.name;
      tr.innerHTML = `
        <td data-testid="metric-name">${m.name}</td>
        <td><code>${escapeHtml(m.trec_eval_args || "")}</code></td>
        <td data-testid="metric-expected">${fmt(m.expected)}</td>
        <td data-testid="metric-observed">${fmt(m.observed)}</td>
        <td data-testid="metric-delta">${fmt(m.delta)}</td>
        <td class="metric-status-${m.status}" data-testid="metric-status">${m.status}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderCommands(commands) {
    const list = byId("commands-list");
    if (!list) return;
    list.innerHTML = "";
    (commands || []).slice(-30).reverse().forEach((c, idx) => {
      const det = document.createElement("details");
      det.className = "command-record";
      det.dataset.testid = "command-record";
      if (idx === 0) det.open = true;
      const exitTxt = c.exit_code === null
        ? "running"
        : c.exit_code === 0 ? "exit 0" : `exit ${c.exit_code}`;
      const exitCls = c.exit_code === 0 ? "ok" : c.exit_code === null ? "" : "err";
      det.innerHTML = `
        <summary>
          <span class="cmd-label">${escapeHtml(c.label)}</span>
          <span class="cmd-exit ${exitCls}">${exitTxt}</span>
        </summary>
        <div class="cmd-display" data-testid="command-text">${escapeHtml(c.display)}</div>
        ${c.stdout_preview ? `<div class="cmd-preview" data-testid="command-stdout"><strong>stdout:</strong>\n${escapeHtml(c.stdout_preview)}</div>` : ""}
        ${c.stderr_preview ? `<div class="cmd-preview" data-testid="command-stderr"><strong>stderr:</strong>\n${escapeHtml(c.stderr_preview)}</div>` : ""}
      `;
      list.appendChild(det);
    });
  }

  function fmt(v) {
    if (v == null || v === "") return "—";
    if (typeof v === "number") return v.toFixed(4);
    return String(v);
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }

  async function refreshStatus() {
    try {
      const r = await fetch("/api/status", { cache: "no-store" });
      if (!r.ok) return;
      const s = await r.json();
      const serialized = JSON.stringify({
        phase: s.phase,
        cards: s.cards,
        ev: s.evaluation,
        cmds: (s.commands || []).length,
        errs: s.errors,
      });
      if (serialized === lastStatusSerialized) return;
      lastStatusSerialized = serialized;
      updatePhase(s.phase || "starting");
      cardIds.forEach((n) => updateCard(n, (s.cards || {})[n] || {}));
      renderSamples(s.sample_queries);
      renderSetupLog(s.setup_log);
      renderErrors(s.errors);
      renderEvaluation(s.evaluation || {}, s.expected_metrics || {});
      renderCommands(s.commands || []);
    } catch (e) {
      console.warn("status poll failed", e);
    }
  }

  async function runSearch() {
    const q = $("#search-input").value.trim();
    if (!q) return;
    const hits = parseInt($("#hits-input").value || "10", 10);
    const meta = byId("search-meta");
    const results = byId("search-results");
    meta.textContent = `Searching "${q}" (hits=${hits})…`;
    results.innerHTML = "";
    try {
      const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&hits=${hits}`);
      if (!r.ok) {
        const txt = await r.text();
        meta.textContent = `Search failed: ${r.status} ${txt}`;
        return;
      }
      const data = await r.json();
      meta.textContent = `Returned ${data.hits_returned} hits from ${data.index} via ${data.rest_url}`;
      data.results.forEach((row) => {
        const li = document.createElement("li");
        li.className = "result";
        li.dataset.testid = "search-result";
        li.dataset.rank = row.rank;
        li.dataset.docid = row.docid;
        li.innerHTML = `
          <div class="top">
            <span>rank <strong data-testid="result-rank">${row.rank}</strong>
              · docid <code data-testid="result-docid">${escapeHtml(row.docid)}</code></span>
            <span>score <strong data-testid="result-score">${(+row.score).toFixed(4)}</strong></span>
          </div>
          <div class="title" data-testid="result-title">${escapeHtml(row.title || "(no title)")}</div>
          <p class="text" data-testid="result-text">${escapeHtml(row.text || "")}</p>
        `;
        results.appendChild(li);
      });
      lastStatusSerialized = ""; // force refresh of commands
      refreshStatus();
    } catch (e) {
      meta.textContent = `Search error: ${e}`;
    }
  }

  async function rerunEval() {
    const btn = $("#rerun-btn");
    const orig = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Running…";
    byId("eval-status").textContent = "running";
    try {
      const r = await fetch("/api/evaluate", { method: "POST" });
      if (!r.ok) {
        const txt = await r.text();
        alert(`Rerun failed: ${r.status} ${txt}`);
      }
    } catch (e) {
      alert(`Rerun error: ${e}`);
    } finally {
      btn.disabled = false;
      btn.textContent = orig;
      lastStatusSerialized = "";
      refreshStatus();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("#search-form").addEventListener("submit", (e) => {
      e.preventDefault();
      runSearch();
    });
    $("#rerun-btn").addEventListener("click", rerunEval);
    byId("deployment-port").textContent = `$PORT`;
    refreshStatus();
    setInterval(refreshStatus, 1500);
  });
})();
