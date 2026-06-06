"use client";

import { useState, useCallback } from "react";
import { SAMPLE_QUERIES } from "@/data/sample-queries";

interface Candidate {
  docid: string;
  score: number;
  rank: number;
  doc: string;
}

interface SearchResult {
  candidates?: Candidate[];
  error?: string;
  query?: { text: string };
}

function getRandomSamples(count: number): string[] {
  const shuffled = [...SAMPLE_QUERIES].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, count);
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sampleQueries] = useState<string[]>(() => getRandomSamples(8));
  const [lastQuery, setLastQuery] = useState("");

  const doSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) {
      setError("Please enter a search query.");
      setResults(null);
      return;
    }

    setLoading(true);
    setError(null);
    setLastQuery(trimmed);
    setQuery(trimmed);

    try {
      const res = await fetch(
        `/api/search?query=${encodeURIComponent(trimmed)}`
      );
      const data = await res.json();

      if (data.error) {
        setError(data.error);
        setResults(null);
      } else {
        setResults(data);
      }
    } catch {
      setError("Failed to reach the search API. Is the backend running?");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    doSearch(query);
  };

  const handleSampleClick = (q: string) => {
    setQuery(q);
    doSearch(q);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <h1 className="text-2xl font-bold text-gray-900">
            MS MARCO Passage Search
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Search the MS MARCO passage corpus powered by Anserini
          </p>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Search Form */}
        <form onSubmit={handleSubmit} className="flex gap-3 mb-6">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter a search query..."
            className="flex-1 px-4 py-3 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 placeholder-gray-400"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        {/* Sample Queries */}
        {!results && !error && !loading && (
          <section className="mb-8">
            <h2 className="text-lg font-semibold text-gray-700 mb-3">
              Try a sample query
            </h2>
            <div className="flex flex-wrap gap-2">
              {sampleQueries.map((q, i) => (
                <button
                  key={i}
                  onClick={() => handleSampleClick(q)}
                  className="px-3 py-1.5 bg-white text-sm text-blue-700 border border-blue-200 rounded-full hover:bg-blue-50 hover:border-blue-300 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <span className="ml-3 text-gray-600">Searching...</span>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
            <p className="font-medium">Error</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        {/* Results */}
        {results && !loading && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-700">
                Results for &ldquo;{lastQuery}&rdquo;
              </h2>
              {results.candidates && (
                <span className="text-sm text-gray-500">
                  {results.candidates.length} result
                  {results.candidates.length !== 1 ? "s" : ""}
                </span>
              )}
            </div>

            {results.candidates && results.candidates.length === 0 && (
              <div className="bg-gray-50 border border-gray-200 text-gray-600 px-4 py-8 rounded-lg text-center">
                <p className="text-lg font-medium">No results found</p>
                <p className="text-sm mt-1">
                  Try a different query or check your spelling.
                </p>
              </div>
            )}

            {results.candidates && results.candidates.length > 0 && (
              <div className="space-y-4">
                {results.candidates.map((c) => (
                  <article
                    key={c.docid}
                    className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <span className="text-xs font-mono bg-gray-100 text-gray-500 px-2 py-0.5 rounded">
                        {c.docid}
                      </span>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-xs text-gray-400">
                          Rank #{c.rank}
                        </span>
                        <span className="text-xs font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
                          {c.score.toFixed(4)}
                        </span>
                      </div>
                    </div>
                    <p className="text-gray-800 text-sm leading-relaxed">
                      {c.doc}
                    </p>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Sample queries for re-search */}
        {results && !loading && (
          <section className="mt-8 pt-6 border-t border-gray-200">
            <h2 className="text-lg font-semibold text-gray-700 mb-3">
              Try another sample query
            </h2>
            <div className="flex flex-wrap gap-2">
              {sampleQueries.map((q, i) => (
                <button
                  key={i}
                  onClick={() => handleSampleClick(q)}
                  className="px-3 py-1.5 bg-white text-sm text-blue-700 border border-blue-200 rounded-full hover:bg-blue-50 hover:border-blue-300 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 mt-12">
        <div className="max-w-4xl mx-auto px-4 py-4 text-center text-xs text-gray-400">
          MS MARCO Passage Search &middot; Powered by Anserini
        </div>
      </footer>
    </div>
  );
}
