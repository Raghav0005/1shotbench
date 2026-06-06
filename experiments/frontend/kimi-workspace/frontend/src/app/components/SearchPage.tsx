"use client";

import { useState, useEffect, useCallback } from "react";

interface SearchResult {
  docid: string;
  score: number;
  rank: number;
  doc: string;
}

interface SearchResponse {
  api: string;
  index: string;
  query: { text: string };
  candidates: SearchResult[];
}

function getRandomQueries(allQueries: string[], count: number): string[] {
  const shuffled = [...allQueries].sort(() => 0.5 - Math.random());
  return shuffled.slice(0, count);
}

export default function SearchPage({ queries }: { queries: string[] }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [sampleQueries, setSampleQueries] = useState<string[]>([]);

  useEffect(() => {
    setSampleQueries(getRandomQueries(queries, 8));
  }, [queries]);

  const performSearch = useCallback(
    async (searchQuery: string) => {
      const trimmed = searchQuery.trim();
      if (!trimmed) {
        setError("Please enter a query.");
        setResults([]);
        setSearched(true);
        return;
      }

      setLoading(true);
      setError(null);
      setSearched(true);

      try {
        const res = await fetch(
          `/api/search?query=${encodeURIComponent(trimmed)}&hits=10`
        );
        if (!res.ok) {
          throw new Error(`Backend error: ${res.status} ${res.statusText}`);
        }
        const data: SearchResponse = await res.json();
        setResults(data.candidates || []);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "An unexpected error occurred."
        );
        setResults([]);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    performSearch(query);
  };

  const handleSampleClick = (q: string) => {
    setQuery(q);
    performSearch(q);
  };

  return (
    <main className="max-w-4xl mx-auto px-4 py-12">
      <div className="text-center mb-10">
        <h1 className="text-4xl font-bold tracking-tight mb-3">
          MS MARCO Passage Search
        </h1>
        <p className="text-lg text-gray-600 dark:text-gray-400">
          Search the MS MARCO passage corpus powered by Anserini
        </p>
      </div>

      <form onSubmit={handleSubmit} className="mb-8">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter your query..."
            className="flex-1 px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </div>
      </form>

      <div className="mb-10">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">
          Sample Queries
        </h2>
        <div className="flex flex-wrap gap-2">
          {sampleQueries.map((q) => (
            <button
              key={q}
              onClick={() => handleSampleClick(q)}
              className="px-3 py-1.5 rounded-full text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-pointer border border-gray-200 dark:border-gray-700"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {searched && !loading && !error && results.length === 0 && (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <p className="text-lg">No results found for your query.</p>
          <p className="text-sm mt-1">Try a different search term.</p>
        </div>
      )}

      {results.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Results</h2>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {results.length} passages
            </span>
          </div>
          <div className="space-y-3">
            {results.map((result) => (
              <div
                key={result.docid}
                className="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 hover:border-gray-300 dark:hover:border-gray-700 transition-colors"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-xs font-bold">
                    {result.rank}
                  </span>
                  <span className="text-xs font-mono text-gray-500 dark:text-gray-400">
                    docid: {result.docid}
                  </span>
                  <span className="ml-auto text-xs font-medium text-gray-500 dark:text-gray-400">
                    score: {result.score.toFixed(4)}
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-gray-800 dark:text-gray-200">
                  {result.doc}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
