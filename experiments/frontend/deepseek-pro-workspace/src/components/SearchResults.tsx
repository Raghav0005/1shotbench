'use client';

import { AnseriniSearchResult } from '@/lib/anserini';

interface SearchResultsProps {
  results: AnseriniSearchResult[];
  query: string;
}

export default function SearchResults({ results, query }: SearchResultsProps) {
  if (results.length === 0) {
    return (
      <div className="search-results-empty">
        <p>
          No results found for <strong>&ldquo;{query}&rdquo;</strong>.
        </p>
        <p className="hint">Try a different query or check the sample queries above.</p>
      </div>
    );
  }

  return (
    <div className="search-results">
      <p className="results-summary">
        Showing {results.length} result{results.length !== 1 ? 's' : ''}{' '}
        for <strong>&ldquo;{query}&rdquo;</strong>:
      </p>
      <ol className="results-list">
        {results.map((result, i) => (
          <li key={result.docid} className="result-item">
            <div className="result-header">
              <span className="result-rank">#{i + 1}</span>
              <span className="result-docid">DocID: {result.docid}</span>
              <span className="result-score">
                Score: {result.score.toFixed(4)}
              </span>
            </div>
            <p className="result-contents">{result.contents}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
