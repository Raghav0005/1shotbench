"use client";

import { useState, useCallback } from "react";

interface SampleQuery {
  id: string;
  query: string;
}

interface Candidate {
  docid: string;
  score: number;
  rank: number;
  doc: string;
}

interface SearchResponse {
  api?: string;
  index?: string;
  query?: { text: string };
  candidates?: Candidate[];
  error?: string;
}

export default function SearchPage({
  sampleQueries,
}: {
  sampleQueries: SampleQuery[];
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchedQuery, setSearchedQuery] = useState<string | null>(null);

  const doSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) {
      setError("Please enter a query.");
      return;
    }

    setLoading(true);
    setError(null);
    setResults([]);
    setSearchedQuery(trimmed);

    try {
      const res = await fetch(`/api/search?query=${encodeURIComponent(trimmed)}`);
      const data: SearchResponse = await res.json();

      if (!res.ok) {
        setError(data.error || "Search failed.");
        return;
      }

      if (!data.candidates || data.candidates.length === 0) {
        setError("No results found.");
        return;
      }

      setResults(data.candidates);
    } catch {
      setError("Could not reach the search server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    doSearch(query);
  };

  const handleSampleClick = (sampleQuery: string) => {
    setQuery(sampleQuery);
    doSearch(sampleQuery);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <h1 className="text-2xl font-bold text-gray-900">
            MS MARCO Passage Search
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Powered by Anserini &middot; BM25 retrieval over 8.8M passages
          </p>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Search form */}
        <form onSubmit={handleSubmit} className="flex gap-2 mb-6">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter your search query..."
            className="flex-1 px-4 py-3 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 text-base"
            aria-label="Search query"
          />
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        {/* Sample queries */}
        {!searchedQuery && (
          <div className="mb-8">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
              Try a sample query
            </h2>
            <div className="flex flex-wrap gap-2">
              {sampleQueries.map((sq) => (
                <button
                  key={sq.id}
                  onClick={() => handleSampleClick(sq.query)}
                  className="px-3 py-1.5 bg-white border border-gray-200 rounded-full text-sm text-gray-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors cursor-pointer"
                >
                  {sq.query}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="text-center py-12 text-gray-500">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-gray-300 border-t-blue-600 mb-3"></div>
            <p>Searching...</p>
          </div>
        )}

        {/* Results */}
        {searchedQuery && !loading && results.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">
                Results for &ldquo;{searchedQuery}&rdquo;
              </h2>
              <span className="text-sm text-gray-500">
                {results.length} passages
              </span>
            </div>
            <ol className="space-y-4">
              {results.map((r) => (
                <li
                  key={r.docid}
                  className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
                >
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex-shrink-0">
                      {r.rank}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-gray-400">
                          docid: {r.docid}
                        </span>
                        <span className="text-xs text-gray-400">
                          score: {r.score.toFixed(4)}
                        </span>
                      </div>
                      <p className="text-sm text-gray-700 leading-relaxed">
                        {r.doc}
                      </p>
                    </div>
                  </div>
                </li>
              ))}
            </ol>

            {/* Back to samples */}
            <button
              onClick={() => {
                setSearchedQuery(null);
                setResults([]);
                setQuery("");
                setError(null);
              }}
              className="mt-6 text-sm text-blue-600 hover:text-blue-800 underline"
            >
              ← Back to sample queries
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
