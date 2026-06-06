/**
 * Build a unified catalog of Anserini prebuilt Lucene inverted indexes,
 * pairing each with topic / qrels / metric information derived from the
 * shipped reproduction configs whenever such a pairing exists.
 *
 * Pairing logic:
 *   - Pull all inverted prebuilt indexes from PrebuiltIndexRegistry.
 *   - Pull all reproduce configs from ReproduceFromPrebuiltIndexes.
 *   - For each (condition, topic) pair, expand the `-index` flag in the
 *     condition's command template by substituting `$topics` with the
 *     topic_key and tagging the index with the resulting pairing.
 *
 * No pairings are hardcoded. CACM appears as evaluable only because the
 * shipped `cacm` reproduction config defines that pairing.
 */

const YAML = require('yaml');
const anserini = require('./anserini');

// Metrics that the app exposes on top of whatever the reproduction config
// already defines. These map a user-friendly label to the exact `-c -m ...`
// trec_eval args expected by io.anserini.eval.TrecEval. Every metric here is a
// real trec_eval metric and the args are taken from Anserini's own
// reproduction configs (see msmarco-v1-passage.core, beir.core, etc.).
const STANDARD_METRICS = [
  { label: 'nDCG@10', args: ['-c', '-m', 'ndcg_cut.10'] },
  { label: 'Recall@1000', args: ['-c', '-m', 'recall.1000'] },
  { label: 'MAP', args: ['-c', '-m', 'map'] },
  { label: 'P@30', args: ['-c', '-m', 'P.30'] },
];

function parseCommand(commandStr) {
  // Lightweight tokenizer that respects double-quoted args. The shipped
  // reproduce-config commands don't currently use shell quoting but this keeps
  // the parser robust to future additions.
  const tokens = [];
  let cur = '';
  let inQuotes = false;
  for (const ch of commandStr) {
    if (ch === '"') { inQuotes = !inQuotes; continue; }
    if (!inQuotes && /\s/.test(ch)) {
      if (cur) { tokens.push(cur); cur = ''; }
    } else {
      cur += ch;
    }
  }
  if (cur) tokens.push(cur);
  return tokens;
}

function extractFlag(tokens, flag) {
  const idx = tokens.indexOf(flag);
  if (idx === -1 || idx + 1 >= tokens.length) return null;
  return tokens[idx + 1];
}

function substitute(template, vars) {
  if (template == null) return template;
  // Replace $name and ${name} occurrences using a simple, ordered scan.
  return template.replace(/\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?/g, (m, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? vars[name] : m
  );
}

function metricArgsFor(label, perPairingMap) {
  if (perPairingMap && perPairingMap[label]) {
    // Per-pairing definitions from the reproduce config are the ground truth.
    return perPairingMap[label].split(/\s+/).filter(Boolean);
  }
  const std = STANDARD_METRICS.find((m) => m.label === label);
  return std ? [...std.args] : null;
}

/**
 * Extract a list of pairings { indexName, topics, evalKey, metrics, condition, configName }
 * from a single reproduction config YAML string.
 */
function pairingsFromConfig(configName, yamlText) {
  const doc = YAML.parse(yamlText);
  const pairings = [];
  if (!doc || !Array.isArray(doc.conditions)) return pairings;
  for (const condition of doc.conditions) {
    if (!condition || !condition.command || !Array.isArray(condition.topics)) continue;
    const tokens = parseCommand(condition.command);
    const indexTpl = extractFlag(tokens, '-index');
    const topicsTpl = extractFlag(tokens, '-topics');
    if (!indexTpl || !topicsTpl) continue;
    for (const t of condition.topics) {
      if (!t || !t.topic_key || !t.eval_key) continue;
      const vars = { topics: t.topic_key, threads: '1' };
      const resolvedIndex = substitute(indexTpl, vars);
      const resolvedTopics = substitute(topicsTpl, vars);
      // Only keep pairings whose -index resolves to something concrete.
      if (resolvedIndex.includes('$')) continue;

      const perPairing = t.metric_definitions || {};
      const metrics = [];
      const seen = new Set();
      // Per-pairing metrics first (preferred when available).
      for (const [label, raw] of Object.entries(perPairing)) {
        metrics.push({
          label,
          args: raw.split(/\s+/).filter(Boolean),
          source: 'reproduce-config',
        });
        seen.add(label);
      }
      // Then add any standard metrics that aren't already listed.
      for (const std of STANDARD_METRICS) {
        if (!seen.has(std.label)) {
          metrics.push({ label: std.label, args: [...std.args], source: 'standard' });
        }
      }

      pairings.push({
        configName,
        conditionName: condition.name,
        conditionDisplay: condition.display || condition.name,
        indexName: resolvedIndex,
        topics: resolvedTopics,
        topicKey: t.topic_key,
        evalKey: t.eval_key,
        metrics,
        expectedScores: t.expected_scores || {},
      });
    }
  }
  return pairings;
}

/**
 * Group raw pairings by index name, keeping all conditions/topics that map to
 * each index. The CACM pairing ends up as one entry per condition; BEIR
 * indexes (e.g. beir-v1.0.0-trec-covid.flat) end up with one entry per topic.
 */
function groupPairingsByIndex(pairings) {
  const byIndex = new Map();
  for (const p of pairings) {
    if (!byIndex.has(p.indexName)) byIndex.set(p.indexName, []);
    byIndex.get(p.indexName).push(p);
  }
  return byIndex;
}

/**
 * Build the full catalog by combining the prebuilt-index registry with the
 * pairings extracted from the reproduce configs.
 *
 * @returns {Promise<{indexes: Array, pairings: Array, generatedAt: string,
 *                   anseriniJar: string, configCount: number, indexCount: number}>}
 */
async function buildCatalog() {
  const [indexes, configs] = await Promise.all([
    anserini.listPrebuiltIndexes('inverted'),
    anserini.listReproduceConfigs(),
  ]);

  const allPairings = [];
  for (const cfg of configs) {
    let text;
    try {
      text = await anserini.showReproduceConfig(cfg);
    } catch (err) {
      // Skip unreadable configs but keep the rest of the catalog usable.
      continue;
    }
    try {
      const pairings = pairingsFromConfig(cfg, text);
      allPairings.push(...pairings);
    } catch (err) {
      // Skip configs that don't follow the expected YAML shape.
      continue;
    }
  }

  const grouped = groupPairingsByIndex(allPairings);

  const enriched = indexes.map((idx) => {
    const indexPairings = grouped.get(idx.name) || [];
    return {
      name: idx.name,
      type: idx.type,
      description: idx.description || '',
      filename: idx.filename || null,
      size: idx.size || null,
      documents: idx.documents || null,
      uniqueTerms: idx.unique_terms || null,
      totalTerms: idx.total_terms || null,
      evaluable: indexPairings.length > 0,
      pairings: indexPairings,
    };
  });

  // Stable sort: evaluable first, CACM at the very top because the PRD makes it
  // the default end-to-end target.
  enriched.sort((a, b) => {
    if (a.name === 'cacm') return -1;
    if (b.name === 'cacm') return 1;
    if (a.evaluable !== b.evaluable) return a.evaluable ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  return {
    indexes: enriched,
    pairings: allPairings,
    generatedAt: new Date().toISOString(),
    anseriniJar: anserini.resolveAnseriniJar(),
    configCount: configs.length,
    indexCount: indexes.length,
  };
}

module.exports = {
  buildCatalog,
  pairingsFromConfig,
  parseCommand,
  substitute,
  STANDARD_METRICS,
  metricArgsFor,
};
