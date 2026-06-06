// Dataset pairing logic.
//
// Anserini's prebuilt-index registry gives us the list of inverted indexes.
// Anserini's topics registry gives us the list of available topic sets.
// Anserini's `io.anserini.eval.Qrels` class ships with a fixed set of
// known qrels names. The pairing between these three resources is not
// dynamically derivable from the registries alone, so we maintain a small
// curated list of well-known Anserini reproduction pairings here.
//
// The defaults in this list follow the same configurations used by
// Anserini's `ReproduceFromPrebuiltIndexes` workflow for the supported
// collections. Each entry is intentionally a short, well-known pairing
// rather than an exhaustive list, and additional topics can be selected
// for a given index from the dropdown in the UI.
//
// `metrics` is a list of user-facing labels. The label->Anserini identifier
// mapping lives in `metrics.js` so that the UI strings and the CLI flags
// stay in sync.

const KNOWN_PAIRINGS = [
  {
    id: 'cacm',
    index: 'cacm',
    topics: ['cacm'],
    defaultTopic: 'cacm',
    qrels: 'cacm',
    description:
      'CACM classic IR test collection. Small, fast, ideal for the default end-to-end run.',
    metrics: ['MAP', 'P.10', 'P.30', 'nDCG@10', 'Recall@1000'],
  },
  {
    id: 'msmarco-v1-passage',
    index: 'msmarco-v1-passage',
    topics: ['msmarco-v1-passage.dev', 'dl19-passage', 'dl20-passage'],
    defaultTopic: 'msmarco-v1-passage.dev',
    qrels: 'msmarco-v1-passage.dev',
    description:
      'MS MARCO V1 passage corpus paired with its dev queries. TREC DL 19/20 topics are also exposed for convenience.',
    metrics: ['MAP', 'MRR@10', 'nDCG@10', 'Recall@1000'],
  },
  {
    id: 'msmarco-v1-doc',
    index: 'msmarco-v1-doc',
    topics: ['msmarco-doc.dev', 'dl19-doc', 'dl20-doc'],
    defaultTopic: 'msmarco-doc.dev',
    qrels: 'msmarco-doc.dev',
    description:
      'MS MARCO V1 document corpus. TREC DL 19/20 document topics share the same qrels.',
    metrics: ['MAP', 'nDCG@10', 'Recall@1000'],
  },
  {
    id: 'msmarco-v2-passage',
    index: 'msmarco-v2-passage',
    topics: ['msmarco-v2-passage.dev', 'msmarco-v2-passage.dev2'],
    defaultTopic: 'msmarco-v2-passage.dev',
    qrels: 'msmarco-v2-passage.dev',
    description: 'MS MARCO V2 passage corpus paired with its dev queries.',
    metrics: ['MAP', 'MRR@10', 'nDCG@10', 'Recall@1000'],
  },
  {
    id: 'msmarco-v2-doc',
    index: 'msmarco-v2-doc',
    topics: ['msmarco-v2-doc.dev', 'msmarco-v2-doc.dev2'],
    defaultTopic: 'msmarco-v2-doc.dev',
    qrels: 'msmarco-v2-doc.dev',
    description: 'MS MARCO V2 document corpus paired with its dev queries.',
    metrics: ['MAP', 'nDCG@10', 'Recall@1000'],
  },
  {
    id: 'robust04',
    index: 'robust04',
    topics: ['robust04'],
    defaultTopic: 'robust04',
    qrels: 'robust04',
    description: 'TREC Robust 2004 (TREC 6-8 ad-hoc) news corpus.',
    metrics: ['MAP', 'P.10', 'P.30', 'nDCG@10', 'Recall@1000'],
  },
  {
    id: 'robust05',
    index: 'robust05',
    topics: ['robust05'],
    defaultTopic: 'robust05',
    qrels: 'robust05',
    description: 'TREC Robust 2005 (TREC 2005 Hard) news corpus.',
    metrics: ['MAP', 'P.10', 'P.30', 'nDCG@10', 'Recall@1000'],
  },
  {
    id: 'core17',
    index: 'core17',
    topics: ['core17'],
    defaultTopic: 'core17',
    qrels: 'core17',
    description: 'TREC Common Core 2017 (New York Times) corpus.',
    metrics: ['MAP', 'P.10', 'P.30', 'nDCG@10', 'Recall@1000'],
  },
  {
    id: 'core18',
    index: 'core18',
    topics: ['core18'],
    defaultTopic: 'core18',
    qrels: 'core18',
    description: 'TREC Common Core 2018 (Washington Post) corpus.',
    metrics: ['MAP', 'P.10', 'P.30', 'nDCG@10', 'Recall@1000'],
  },
];

function findPairing(indexName) {
  return KNOWN_PAIRINGS.find((p) => p.index === indexName) || null;
}

function isEvaluable(indexName) {
  return findPairing(indexName) !== null;
}

// Drops any pairings whose topics, qrels, or prebuilt index aren't
// actually visible in the Anserini runtime, so we never offer a run
// that the fatjar can't execute.
function reconcileWithRegistries(pairings, knownTopics, knownQrels, knownIndexes) {
  const indexSet = new Set(knownIndexes || []);
  return pairings
    .map((p) => {
      if (indexSet.size > 0 && !indexSet.has(p.index)) return null;
      const availableTopics = p.topics.filter((t) => knownTopics.includes(t));
      if (availableTopics.length === 0) return null;
      const out = { ...p, topics: availableTopics };
      if (!availableTopics.includes(p.defaultTopic)) {
        out.defaultTopic = availableTopics[0];
      }
      return out;
    })
    .filter(Boolean)
    .filter((p) => knownQrels.has(p.qrels.toLowerCase()));
}

module.exports = {
  KNOWN_PAIRINGS,
  findPairing,
  isEvaluable,
  reconcileWithRegistries,
};
