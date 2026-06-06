"use client";

import { useState, useEffect } from "react";

interface SampleQuery {
  id: string;
  title: string;
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

export default function Home() {
  const [query, setQuery] = useState("");
  const [samples, setSamples] = useState<SampleQuery[]>([]);
  const [results, setResults] = useState<Candidate[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/topics")
      .then((res) => res.json())
      .then((data) => {
        if (!data.error) {
          setSamples(data);
        }
      })
      .catch(console.error);
  }, []);

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) {
      setResults(null);
      setError("Please enter a query");
      return;
    }

    setQuery(searchQuery);
    setLoading(true);
    setError(null);
    setResults(null);

    try {
      const res = await fetch(
        `/api/search?query=${encodeURIComponent(searchQuery)}&hits=10`
      );
      if (!res.ok) {
        throw new Error("Failed to fetch results");
      }
      const data: SearchResponse = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }
      setResults(data.candidates || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen max-w-4xl mx-auto p-8 font-[family-name:var(--font-geist-sans)]">
      <h1 className="text-3xl font-bold mb-8 text-center">MS MARCO Passage Search</h1>

      <div className="mb-8 flex flex-col gap-4 max-w-2xl mx-auto">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSearch(query);
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search passages..."
            className="flex-1 border border-gray-300 rounded px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-black dark:text-white dark:bg-zinc-800 dark:border-zinc-700"
          />
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        {samples.length > 0 && (
          <div className="text-sm">
            <span className="text-gray-500 mr-2">Sample queries:</span>
            <div className="flex flex-wrap gap-2 mt-2">
              {samples.map((sample) => (
                <button
                  key={sample.id}
                  onClick={() => handleSearch(sample.title)}
                  className="bg-gray-100 dark:bg-zinc-800 hover:bg-gray-200 dark:hover:bg-zinc-700 px-3 py-1 rounded-full text-xs text-left"
                >
                  {sample.title}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="max-w-3xl mx-auto">
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            {error}
          </div>
        )}

        {results && results.length === 0 && (
          <div className="text-gray-500 text-center py-8">
            No results found for &quot;{query}&quot;.
          </div>
        )}

        {results && results.length > 0 && (
          <div className="flex flex-col gap-6">
            <h2 className="text-xl font-semibold mb-2">Results ({results.length})</h2>
            {results.map((cand) => (
              <div
                key={cand.docid}
                className="border border-gray-200 dark:border-zinc-800 p-4 rounded shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="text-sm text-gray-500 mb-2 flex justify-between">
                  <span>Doc ID: {cand.docid}</span>
                  <span>Score: {cand.score.toFixed(4)} | Rank: {cand.rank}</span>
                </div>
                <p className="text-gray-800 dark:text-gray-200 leading-relaxed">
                  {cand.doc}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
