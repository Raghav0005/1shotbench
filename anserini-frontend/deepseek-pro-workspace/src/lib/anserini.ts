export interface AnseriniSearchResult {
  docid: string;
  score: number;
  contents: string;
}

export interface AnseriniSearchResponse {
  query: string;
  results: AnseriniSearchResult[];
  totalHits?: number;
}

export interface AnseriniDocResponse {
  docid: string;
  contents: string;
}

export interface AnseriniErrorResponse {
  error: string;
}

const BACKEND_PORT = process.env.BACKEND_PORT || '8080';
const BACKEND_HOST = process.env.BACKEND_HOST || 'localhost';
const INDEX_NAME = process.env.ANSERINI_INDEX || 'msmarco-v1-passage';

function getBaseUrl(): string {
  return `http://${BACKEND_HOST}:${BACKEND_PORT}`;
}

export class AnseriniApiError extends Error {
  statusCode: number;
  constructor(message: string, statusCode: number) {
    super(message);
    this.name = 'AnseriniApiError';
    this.statusCode = statusCode;
  }
}

/**
 * Search the MS MARCO passage corpus via the Anserini REST API.
 *
 * GET /v1/{index}/search?query={query}&hits={hits}
 */
export async function search(
  query: string,
  hits: number = 10
): Promise<AnseriniSearchResponse> {
  const url = `${getBaseUrl()}/v1/${INDEX_NAME}/search?query=${encodeURIComponent(query)}&hits=${hits}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
  } catch (err) {
    throw new AnseriniApiError(
      `Cannot connect to Anserini backend. Is the REST server running on ${BACKEND_HOST}:${BACKEND_PORT}?`,
      0
    );
  }

  if (!response.ok) {
    let errorMsg = `Anserini backend returned status ${response.status}`;
    try {
      const body = await response.json();
      if (body.error) errorMsg = body.error;
    } catch {
      // ignore parse errors, use default message
    }
    throw new AnseriniApiError(errorMsg, response.status);
  }

  const data = await response.json();
  return data;
}

/**
 * Fetch a single document by docid via the Anserini REST API.
 *
 * GET /v1/{index}/doc/{docid}
 */
export async function getDocument(docid: string): Promise<AnseriniDocResponse> {
  const url = `${getBaseUrl()}/v1/${INDEX_NAME}/doc/${docid}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
  } catch (err) {
    throw new AnseriniApiError(
      `Cannot connect to Anserini backend. Is the REST server running on ${BACKEND_HOST}:${BACKEND_PORT}?`,
      0
    );
  }

  if (!response.ok) {
    let errorMsg = `Anserini backend returned status ${response.status}`;
    try {
      const body = await response.json();
      if (body.error) errorMsg = body.error;
    } catch {
      // ignore parse errors
    }
    throw new AnseriniApiError(errorMsg, response.status);
  }

  const data = await response.json();
  return data;
}
