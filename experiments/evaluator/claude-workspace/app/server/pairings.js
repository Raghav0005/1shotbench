// Derive topic/qrels pairings for prebuilt Lucene inverted indexes.
//
// Anserini's registries do not directly cross-link indexes to topics, but the
// conventions used across the registries (and documented in the repo-local
// skills + reproduction docs) make most evaluable pairings predictable from
// the index name.

/**
 * Build a lookup map of topic symbols by lowercased name so we can probe for
 * candidate pairings derived from the index name.
 *
 * @param {string[]} topics  All known topic symbols from TopicsRegistry --list.
 */
export function buildTopicIndex(topics) {
  const byLower = new Map();
  for (const t of topics) {
    byLower.set(t.toLowerCase(), t);
  }
  return byLower;
}

/**
 * Strip a known suffix like ".flat" or ".multifield" from an inverted-index
 * name to get the underlying collection key used in the topics registry.
 */
function stripIndexSuffix(name) {
  return name.replace(/\.(flat|multifield|slim|full)$/, "");
}

/**
 * Try to match the index name against the topics registry using known naming
 * conventions. The first match wins. Returns { topics, qrels } or null.
 *
 * Conventions covered (derived from Anserini's registries + reproduction docs):
 *   - "cacm" index pairs with the "cacm" topic symbol (qrels resolved via the
 *     same symbol by TrecEval's bundled qrels registry).
 *   - "<collection>.test" / "<collection>.dev" / "<collection>-dev" /
 *     "<collection>-dev-subset" symbols, e.g. BEIR, MS MARCO.
 *   - Otherwise: same name as the index (works for cacm, robust04, core17 etc.).
 */
export function inferPairing(indexName, topicByLower) {
  const base = stripIndexSuffix(indexName);
  const candidates = [
    indexName,
    base,
    `${base}.test`,
    `${base}.dev`,
    `${base}-dev`,
    `${base}-dev-subset`,
    `${base}.dev-subset`,
  ];

  // A handful of well-known special cases that the simple rules above miss.
  const specials = {
    "msmarco-v1-passage": ["msmarco-passage-dev-subset", "msmarco-passage-dev"],
    "msmarco-v1-passage-slim": ["msmarco-passage-dev-subset"],
    "msmarco-v1-passage-full": ["msmarco-passage-dev-subset"],
    "msmarco-v1-passage.d2q-t5": ["msmarco-passage-dev-subset"],
    "msmarco-v1-doc": ["msmarco-doc.dev"],
    "msmarco-v1-doc-slim": ["msmarco-doc.dev"],
    "msmarco-v1-doc-full": ["msmarco-doc.dev"],
    "msmarco-v1-doc-segmented": ["msmarco-doc.dev"],
    "msmarco-v2-passage": ["msmarco-v2-passage-dev"],
    "msmarco-v2-doc": ["msmarco-v2-doc-dev"],
    "robust04": ["robust04"],
    "disk12": ["trec1-3"],
  };
  if (specials[indexName]) {
    for (const c of specials[indexName]) {
      const hit = topicByLower.get(c.toLowerCase());
      if (hit) return { topics: hit, qrels: hit };
    }
  }

  for (const c of candidates) {
    const hit = topicByLower.get(c.toLowerCase());
    if (hit) return { topics: hit, qrels: hit };
  }
  return null;
}

/**
 * Annotate a list of prebuilt indexes with pairing info and an `evaluable`
 * flag. The first evaluable entry is marked as the default if name === "cacm";
 * CACM is also pre-sorted to the top of the catalog by the caller.
 */
export function annotateCatalog(indexes, topics) {
  const byLower = buildTopicIndex(topics);
  return indexes.map((entry) => {
    const pairing = inferPairing(entry.name, byLower);
    return {
      ...entry,
      pairing,
      evaluable: pairing !== null,
    };
  });
}
