"use client";

import { useEffect, useState } from "react";

interface SearchResult {
  docid: string;
  score: number;
  rank: number;
  doc: string;
}

interface SearchResponse {
  query: { text: string };
  candidates: SearchResult[];
}

const SAMPLE_COUNT = 6;

function getRandomSample<T>(arr: T[], count: number): T[] {
  const shuffled = [...arr].sort(() => 0.5 - Math.random());
  return shuffled.slice(0, count);
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [sampleQueries, setSampleQueries] = useState<string[]>([]);
  const [allQueries, setAllQueries] = useState<string[]>([]);

  useEffect(() => {
    fetch("/queries.json")
      .then((res) => res.json())
      .then((data: string[]) => {
        setAllQueries(data);
        setSampleQueries(getRandomSample(data, SAMPLE_COUNT));
      })
      .catch(() => {
        setError("Failed to load sample queries.");
      });
  }, []);

  const handleSearch = async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) {
      setError("Please enter a query.");
      setResults([]);
      setSearched(true);
      return;
    }

    setLoading(true);
    setError(null);
    setSearched(true);
    setResults([]);

    try {
      const url = `/api/search?query=${encodeURIComponent(trimmed)}&hits=10`;
      const res = await fetch(url);
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend error (${res.status}): ${text}`);
      }
      const data: SearchResponse = await res.json();
      setResults(data.candidates || []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "An unexpected error occurred."
      );
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch(query);
  };

  const refreshSamples = () => {
    setSampleQueries(getRandomSample(allQueries, SAMPLE_COUNT));
  };

  return (
    <div className="flex flex-col flex-1 items-center bg-zinc-50 dark:bg-zinc-950">
      <main className="flex flex-1 w-full max-w-3xl flex-col py-12 px-6">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
            MS MARCO Passage Search
          </h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            Search the MS MARCO passage corpus via Anserini
          </p>
        </div>

        <form onSubmit={onSubmit} className="flex gap-2 mb-6">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter a query..."
            className="flex-1 rounded-lg border border-zinc-300 bg-white px-4 py-3 text-zinc-900 placeholder-zinc-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-blue-600 px-6 py-3 font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-60"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        <div className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
              Sample Queries
            </h2>
            <button
              onClick={refreshSamples}
              className="text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
            >
              Refresh
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {sampleQueries.map((q, i) => (
              <button
                key={i}
                onClick={() => {
                  setQuery(q);
                  handleSearch(q);
                }}
                className="rounded-full border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}

        {searched && !loading && !error && results.length === 0 && (
          <div className="text-center text-zinc-500 dark:text-zinc-400 py-12">
            No results found for your query.
          </div>
        )}

        {results.length > 0 && (
          <div className="flex flex-col gap-4">
            <div className="text-sm text-zinc-500 dark:text-zinc-400">
              {results.length} result{results.length !== 1 ? "s" : ""} for “
              {query.trim()}”
            </div>
            {results.map((r) => (
              <div
                key={r.docid}
                className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900"
              >
                <div className="flex items-center gap-3 mb-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                    {r.rank}
                  </span>
                  <span className="text-xs font-mono text-zinc-500 dark:text-zinc-400">
                    {r.docid}
                  </span>
                  <span className="ml-auto text-xs font-medium text-zinc-500 dark:text-zinc-400">
                    Score: {r.score.toFixed(4)}
                  </span>
                </div>
                <p className="text-zinc-800 dark:text-zinc-200 leading-relaxed">
                  {r.doc}
                </p>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
