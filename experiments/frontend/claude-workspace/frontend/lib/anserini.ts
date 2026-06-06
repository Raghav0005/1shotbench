import { config } from "./config";

// Response shape per Anserini RestServer v1 (see anserini-cli skill):
//   { api, index, query: { text }, candidates: [{ docid, score, rank, doc }] }
export type AnseriniCandidate = {
  docid: string;
  score: number;
  rank: number;
  doc: string;
};

export type AnseriniSearchResponse = {
  api: string;
  index: string;
  query: { text: string };
  candidates: AnseriniCandidate[];
};

export class AnseriniError extends Error {
  status: number;
  constructor(message: string, status = 502) {
    super(message);
    this.status = status;
  }
}

export async function searchAnserini(query: string, hits: number): Promise<AnseriniSearchResponse> {
  const url =
    `${config.anseriniBaseUrl}/v1/${encodeURIComponent(config.anseriniIndex)}/search` +
    `?query=${encodeURIComponent(query)}&hits=${encodeURIComponent(String(hits))}`;

  let res: Response;
  try {
    res = await fetch(url, { cache: "no-store" });
  } catch (err) {
    throw new AnseriniError(
      `Could not reach Anserini REST server at ${config.anseriniBaseUrl}: ${
        err instanceof Error ? err.message : String(err)
      }`,
      503,
    );
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new AnseriniError(
      `Anserini REST server returned ${res.status} ${res.statusText}${body ? `: ${body.slice(0, 200)}` : ""}`,
      502,
    );
  }

  const json = (await res.json()) as AnseriniSearchResponse;
  if (!json || !Array.isArray(json.candidates)) {
    throw new AnseriniError("Anserini REST response was not in the expected shape.", 502);
  }
  return json;
}
