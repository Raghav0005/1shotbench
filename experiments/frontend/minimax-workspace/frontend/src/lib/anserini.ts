// Configuration for talking to the Anserini REST backend.

export type AnseriniConfig = {
  baseUrl: string;
  index: string;
};

const DEFAULT_INDEX = "msmarco-v1-passage";
const DEFAULT_BACKEND_PORT = "8080";

export function getAnseriniConfig(): AnseriniConfig {
  // Allow operators to point the frontend at any Anserini REST server.
  // ANSERINI_URL takes precedence; otherwise build from ANSERINI_PORT (default 8080)
  // so the application can be configured purely through environment variables.
  const explicitUrl = process.env.ANSERINI_URL;
  const port = process.env.ANSERINI_PORT ?? DEFAULT_BACKEND_PORT;
  const baseUrl = (explicitUrl && explicitUrl.trim().length > 0
    ? explicitUrl.replace(/\/+$/, "")
    : `http://localhost:${port}`);

  const index = process.env.ANSERINI_INDEX ?? DEFAULT_INDEX;
  return { baseUrl, index };
}
