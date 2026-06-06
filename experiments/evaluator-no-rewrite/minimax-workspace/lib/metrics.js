// Mapping from user-facing metric labels to the exact flag accepted by
// `io.anserini.eval.TrecEval`. This list intentionally covers the
// ranking metrics called out in the PRD (nDCG@10, Recall@1000) plus a
// few common alternatives that TrecEval always supports for any qrels.

const METRICS = {
  'MAP': { flag: 'map', label: 'MAP', help: 'Mean Average Precision' },
  'MRR@10': { flag: 'recip_rank', label: 'MRR@10', help: 'Mean Reciprocal Rank' },
  'nDCG@10': { flag: 'ndcg_cut.10', label: 'nDCG@10', help: 'nDCG cut at rank 10' },
  'nDCG@100': { flag: 'ndcg_cut.100', label: 'nDCG@100', help: 'nDCG cut at rank 100' },
  'P.10': { flag: 'P.10', label: 'P@10', help: 'Precision at rank 10' },
  'P.30': { flag: 'P.30', label: 'P@30', help: 'Precision at rank 30' },
  'P.100': { flag: 'P.100', label: 'P@100', help: 'Precision at rank 100' },
  'Recall@100': { flag: 'recall.100', label: 'Recall@100', help: 'Recall at rank 100' },
  'Recall@1000': { flag: 'recall.1000', label: 'Recall@1000', help: 'Recall at rank 1000' },
};

const DEFAULT_METRICS = ['MAP', 'nDCG@10', 'Recall@1000'];

function metricFlag(label) {
  const m = METRICS[label];
  if (!m) {
    throw new Error(
      `Unknown metric label "${label}". Known labels: ${Object.keys(METRICS).join(', ')}`
    );
  }
  return m.flag;
}

function metricHelp(label) {
  const m = METRICS[label];
  return m ? m.help : '';
}

module.exports = {
  METRICS,
  DEFAULT_METRICS,
  metricFlag,
  metricHelp,
};
