"use client";

import { useState, useEffect, useCallback, FormEvent } from "react";

interface SearchResult {
  docid: string;
  score: number;
  rank: number;
  doc: string;
}

interface SearchResponse {
  candidates?: SearchResult[];
  error?: string;
}

interface SampleQuery {
  id: string;
  title: string;
}

const SAMPLE_COUNT = 8;

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sampleQueries, setSampleQueries] = useState<SampleQuery[]>([]);
  const [executedQuery, setExecutedQuery] = useState<string | null>(null);

  // Load random sample queries on mount
  useEffect(() => {
    async function loadSamples() {
      try {
        const res = await fetch("/sample_queries.json");
        const data: Record<string, string> = await res.json();
        const keys = Object.keys(data);
        const sampled: SampleQuery[] = [];
        const shuffled = [...keys].sort(() => Math.random() - 0.5);
        for (let i = 0; i < Math.min(SAMPLE_COUNT, shuffled.length); i++) {
          sampled.push({ id: shuffled[i], title: data[shuffled[i]] });
        }
        setSampleQueries(sampled);
      } catch {
        console.error("Failed to load sample queries");
      }
    }
    loadSamples();
  }, []);

  const doSearch = useCallback(
    async (searchQuery: string) => {
      const trimmed = searchQuery.trim();
      if (!trimmed) {
        setError("Please enter a search query.");
        setResults(null);
        setExecutedQuery(null);
        return;
      }

      setLoading(true);
      setError(null);
      setExecutedQuery(trimmed);
      setResults(null);

      try {
        const url = `/api/search?query=${encodeURIComponent(trimmed)}&hits=10`;
        const res = await fetch(url, { signal: AbortSignal.timeout(30_000) });

        if (!res.ok) {
          const data = await res.json().catch(() => null);
          const msg = data?.error || `Backend error (${res.status})`;
          setError(msg);
          return;
        }

        const data: SearchResponse = await res.json();
        if (data.candidates && data.candidates.length > 0) {
          setResults(data.candidates);
        } else {
          setResults([]);
        }
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Unknown error occurred";
        setError(`Failed to connect to search backend: ${message}`);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    doSearch(query);
  };

  const handleSampleClick = (title: string) => {
    setQuery(title);
    doSearch(title);
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-950 dark:to-gray-900">
      <header className="border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            MS MARCO Passage Search
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Search the MS MARCO passage corpus using Anserini
          </p>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Search Form */}
        <form onSubmit={handleSubmit} className="flex gap-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter a search query..."
            className="flex-1 px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-700
              bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100
              focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
              placeholder-gray-400 dark:placeholder-gray-500 text-base"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300
              dark:disabled:bg-gray-700 text-white font-medium rounded-lg
              transition-colors duration-150 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <svg
                  className="animate-spin h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Searching
              </span>
            ) : (
              "Search"
            )}
          </button>
        </form>

        {/* Sample Queries */}
        {sampleQueries.length > 0 && (
          <div className="mt-8">
            <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
              Sample Queries — click to search
            </h2>
            <div className="flex flex-wrap gap-2">
              {sampleQueries.map((sq) => (
                <button
                  key={sq.id}
                  onClick={() => handleSampleClick(sq.title)}
                  disabled={loading}
                  className="px-3 py-1.5 text-sm rounded-full border border-gray-200 dark:border-gray-700
                    bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300
                    hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700
                    dark:hover:bg-blue-900/30 dark:hover:border-blue-600 dark:hover:text-blue-300
                    transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {sq.title}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-6 p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
            <p className="text-red-700 dark:text-red-400 text-sm">{error}</p>
          </div>
        )}

        {/* Results */}
        {executedQuery && results !== null && (
          <div className="mt-8">
            <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
              {results.length > 0
                ? `Results for "${executedQuery}" — ${results.length} passage${results.length !== 1 ? "s" : ""} found`
                : `No results found for "${executedQuery}"`}
            </h2>
            {results.length === 0 && (
              <p className="text-gray-500 dark:text-gray-400 text-sm">
                Try a different query or one of the sample queries above.
              </p>
            )}
            <div className="space-y-4">
              {results.map((r) => (
                <div
                  key={r.docid}
                  className="p-4 rounded-lg border border-gray-200 dark:border-gray-700
                    bg-white dark:bg-gray-800 hover:shadow-md transition-shadow duration-150"
                >
                  <div className="flex items-center gap-3 mb-2">
                    <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-xs font-bold">
                      {r.rank}
                    </span>
                    <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">
                      docid: {r.docid}
                    </span>
                    <span className="text-xs text-gray-400 dark:text-gray-500">
                      score: {r.score.toFixed(4)}
                    </span>
                  </div>
                  <p className="text-gray-800 dark:text-gray-200 text-sm leading-relaxed">
                    {r.doc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-gray-200 dark:border-gray-800 mt-16">
        <div className="max-w-4xl mx-auto px-4 py-4 text-center text-xs text-gray-400 dark:text-gray-600">
          MS MARCO Passage Search — Powered by Anserini
        </div>
      </footer>
    </div>
  );
}
