"use client";

import { useState, useCallback } from "react";

const SAMPLE_QUERIES = [
  "what is disease models",
  "types of java fonts",
  "the largest wide area network (wan) in existence is the",
  "here there be dragons comic",
  "how does genome editing work",
  "how many minutes to fry fish",
  "price chopper locations in ct",
  "turpentine slang meaning",
  "what blood stream messenger",
  "call delta reservations phone number",
];

function getRandomSamples(
  pool: string[],
  count: number
): { idx: number; text: string }[] {
  const indices = Array.from({ length: pool.length }, (_, i) => i);
  // Fisher-Yates shuffle
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [indices[i], indices[j]] = [indices[j], indices[i]];
  }
  return indices.slice(0, count).map((i) => ({ idx: i, text: pool[i] }));
}

interface Candidate {
  docid: string;
  score: number;
  rank: number;
  doc: string;
}

interface SearchResult {
  api: string;
  index: string;
  query: { text: string };
  candidates: Candidate[];
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [samples] = useState(() => getRandomSamples(SAMPLE_QUERIES, 5));

  const runSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) {
      setError("Please enter a query.");
      return;
    }

    setLoading(true);
    setError(null);
    setResults(null);

    try {
      const res = await fetch(
        `/api/search?query=${encodeURIComponent(trimmed)}&hits=10`
      );

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || `Unexpected error (${res.status})`);
        return;
      }

      setResults(data);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Unknown error";
      setError(`Failed to reach the search backend. ${message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runSearch(query);
  };

  return (
    <div className="flex-1 bg-zinc-50 dark:bg-zinc-950">
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        {/* Header */}
        <header className="mb-10 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
            MS MARCO Passage Search
          </h1>
          <p className="mt-2 text-zinc-500 dark:text-zinc-400">
            Search over 8.8 million passages with Anserini
          </p>
        </header>

        {/* Search form */}
        <form onSubmit={handleSubmit} className="mb-8">
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your search query…"
              className="flex-1 rounded-lg border border-zinc-300 bg-white px-4 py-2.5 text-zinc-900 shadow-sm placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:placeholder:text-zinc-500 dark:focus:border-zinc-500 dark:focus:ring-zinc-800"
            />
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-zinc-900 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
            >
              {loading ? "Searching…" : "Search"}
            </button>
          </div>
        </form>

        {/* Sample queries */}
        <div className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Try a sample query
          </h2>
          <div className="flex flex-wrap gap-2">
            {samples.map(({ idx, text }) => (
              <button
                key={idx}
                onClick={() => {
                  setQuery(text);
                  runSearch(text);
                }}
                disabled={loading}
                className="rounded-full border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 transition-colors hover:border-zinc-400 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-zinc-600 dark:hover:bg-zinc-800"
              >
                {text}
              </button>
            ))}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
            {error}
          </div>
        )}

        {/* Results */}
        {results && results.candidates.length === 0 && !error && (
          <div className="rounded-lg border border-zinc-200 bg-white px-4 py-8 text-center text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
            No results found for &ldquo;{results.query.text}&rdquo;.
          </div>
        )}

        {results && results.candidates.length > 0 && (
          <div>
            <p className="mb-4 text-sm text-zinc-500 dark:text-zinc-400">
              {results.candidates.length} result
              {results.candidates.length !== 1 ? "s" : ""} for &ldquo;
              {results.query.text}&rdquo;
            </p>
            <ol className="space-y-4">
              {results.candidates.map((c) => (
                <li
                  key={c.docid}
                  className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <div className="mb-1 flex items-center gap-2 text-xs text-zinc-400 dark:text-zinc-500">
                    <span className="font-mono">docid: {c.docid}</span>
                    <span>&middot;</span>
                    <span>score: {c.score.toFixed(4)}</span>
                    <span>&middot;</span>
                    <span>rank: {c.rank}</span>
                  </div>
                  <p className="text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
                    {c.doc}
                  </p>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}
