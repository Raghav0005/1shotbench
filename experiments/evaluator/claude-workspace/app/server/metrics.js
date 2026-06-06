// User-facing metric labels mapped to the exact trec_eval identifiers that
// Anserini's TrecEval wrapper passes through to trec_eval via -m.

export const METRICS = [
  {
    id: "ndcg_cut_10",
    label: "nDCG@10",
    trecEvalArg: "ndcg_cut.10",
    resultKey: "ndcg_cut_10",
  },
  {
    id: "recall_1000",
    label: "Recall@1000",
    trecEvalArg: "recall.1000",
    resultKey: "recall_1000",
  },
  {
    id: "map",
    label: "MAP",
    trecEvalArg: "map",
    resultKey: "map",
  },
  {
    id: "p_30",
    label: "P@30",
    trecEvalArg: "P.30",
    resultKey: "P_30",
  },
];

export function metricById(id) {
  return METRICS.find((m) => m.id === id);
}
