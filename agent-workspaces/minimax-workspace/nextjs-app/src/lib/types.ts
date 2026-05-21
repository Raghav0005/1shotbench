export interface SearchResult {
  docid: string;
  score: number;
  content: string;
}

export interface SearchResponse {
  hits: SearchResult[];
  totalHits: number;
  query: string;
}

export interface ApiError {
  error: string;
  message: string;
  statusCode?: number;
}