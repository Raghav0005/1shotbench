"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface QueryEntry {
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
  api: string;
  index: string;
  query: { text: string };
  candidates: Candidate[];
}

type ViewState = "idle" | "loading" | "results" | "error";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SAMPLE_COUNT = 6;
const DEFAULT_HITS = 10;
const DISPLAY_API_BASE = process.env.NEXT_PUBLIC_ANSERINI_API_URL ?? "http://localhost:8080";
const INDEX_NAME = "msmarco-v1-passage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Pick `n` random elements from an array (Fisher–Yates partial shuffle). */
function pickRandom<T>(arr: T[], n: number): T[] {
  const copy = [...arr];
  const result: T[] = [];
  const limit = Math.min(n, copy.length);
  for (let i = 0; i < limit; i++) {
    const idx = i + Math.floor(Math.random() * (copy.length - i));
    [copy[i], copy[idx]] = [copy[idx] as T, copy[i] as T];
    result.push(copy[i] as T);
  }
  return result;
}

/** Search via the internal API proxy route. */
async function search(query: string, hits: number): Promise<SearchResponse> {
  const url = `/api/search?query=${encodeURIComponent(query)}&hits=${hits}`;
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Backend returned ${res.status}${body ? `: ${body}` : ""}`);
  }
  return res.json() as Promise<SearchResponse>;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Home() {
  const [allQueries, setAllQueries] = useState<QueryEntry[]>([]);
  const [samples, setSamples] = useState<QueryEntry[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Candidate[] | null>(null);
  const [viewState, setViewState] = useState<ViewState>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Load queries on mount
  useEffect(() => {
    fetch("/msmarco-passage-dev-queries.json")
      .then((r) => r.json() as Promise<QueryEntry[]>)
      .then((data) => {
        setAllQueries(data);
        setSamples(pickRandom(data, SAMPLE_COUNT));
      })
      .catch(() => {
        // If the file doesn't load, we just won't show samples
        setAllQueries([]);
        setSamples([]);
      });
  }, []);

  // Refresh samples from the full set
  const refreshSamples = useCallback(() => {
    if (allQueries.length > 0) {
      setSamples(pickRandom(allQueries, SAMPLE_COUNT));
    }
  }, [allQueries]);

  // Run a search
  const runSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;

    setQuery(trimmed);
    setViewState("loading");
    setResults(null);
    setErrorMsg("");

    try {
      const data = await search(trimmed, DEFAULT_HITS);
      setResults(data.candidates);
      setViewState("results");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "An unexpected error occurred.";
      setErrorMsg(msg);
      setViewState("error");
    }
  }, []);

  // Handle form submission
  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      runSearch(query);
    },
    [query, runSearch],
  );

  // Handle clicking a sample query
  const handleSampleClick = useCallback(
    (q: string) => {
      setQuery(q);
      runSearch(q);
    },
    [runSearch],
  );

  return (
    <div className="flex flex-col flex-1">
      {/* Header */}
      <header className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950">
        <div className="mx-auto max-w-4xl px-4 py-4 sm:px-6">
          <h1 className="text-xl font-bold tracking-tight">
            MS MARCO Passage Search
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">
            Search 8.8M passages via Anserini + BM25
          </p>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 mx-auto w-full max-w-4xl px-4 sm:px-6 py-6">
        {/* Search form */}
        <form onSubmit={handleSubmit} className="mb-6">
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search MS MARCO passages..."
              className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
            />
            <button
              type="submit"
              disabled={viewState === "loading"}
              className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {viewState === "loading" ? "Searching…" : "Search"}
            </button>
          </div>
        </form>

        {/* Sample queries */}
        {samples.length > 0 && (
          <section className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">
                Sample Queries
              </h2>
              <button
                onClick={refreshSamples}
                className="text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 transition-colors"
              >
                Refresh
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {samples.map((s) => (
                <button
                  key={s.id}
                  onClick={() => handleSampleClick(s.title)}
                  disabled={viewState === "loading"}
                  className="rounded-full border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 px-3.5 py-1.5 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 dark:hover:bg-blue-950 dark:hover:border-blue-700 dark:hover:text-blue-300 disabled:opacity-50 transition-colors"
                >
                  {s.title}
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Loading state */}
        {viewState === "loading" && (
          <div className="flex items-center justify-center py-16">
            <div className="flex items-center gap-3 text-zinc-400">
              <svg
                className="animate-spin h-5 w-5"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
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
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span className="text-sm">Searching...</span>
            </div>
          </div>
        )}

        {/* Error state */}
        {viewState === "error" && (
          <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950 px-4 py-3 text-sm text-red-700 dark:text-red-300">
            <p className="font-medium">Search failed</p>
            <p className="mt-1">{errorMsg}</p>
            <p className="mt-2 text-xs text-red-500 dark:text-red-400">
              Make sure the Anserini REST server is running on{" "}
              <code className="font-mono">{DISPLAY_API_BASE}</code> with the{" "}
              <code className="font-mono">{INDEX_NAME}</code> prebuilt index.
            </p>
          </div>
        )}

        {/* Results */}
        {viewState === "results" && results && (
          <section>
            {results.length === 0 ? (
              <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 px-4 py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
                No matching passages found for &ldquo;{query}&rdquo;.
              </div>
            ) : (
              <>
                <div className="mb-3 text-sm text-zinc-500 dark:text-zinc-400">
                  {results.length} result{results.length !== 1 ? "s" : ""} for
                  &ldquo;<span className="font-medium text-zinc-700 dark:text-zinc-300">{query}</span>&rdquo;
                </div>
                <ol className="space-y-3">
                  {results.map((c) => (
                    <li
                      key={c.docid}
                      className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-4 py-3"
                    >
                      <div className="flex items-baseline gap-3 mb-1">
                        <span className="text-xs font-bold text-blue-600 dark:text-blue-400 min-w-[1.5rem]">
                          #{c.rank}
                        </span>
                        <span className="text-xs text-zinc-400 font-mono">
                          score {c.score.toFixed(4)}
                        </span>
                        <span className="text-xs text-zinc-400 font-mono">
                          doc {c.docid}
                        </span>
                      </div>
                      <p className="text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
                        {c.doc}
                      </p>
                    </li>
                  ))}
                </ol>
              </>
            )}
          </section>
        )}

        {/* Idle state */}
        {viewState === "idle" && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <svg
              className="h-10 w-10 text-zinc-300 dark:text-zinc-700 mb-3"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"
              />
            </svg>
            <p className="text-sm text-zinc-400 dark:text-zinc-500">
              Type a query or click a sample query above to search MS MARCO passages.
            </p>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-200 dark:border-zinc-800">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 py-3 text-center text-xs text-zinc-400">
          <span>
            Backend: <code className="font-mono">{DISPLAY_API_BASE}</code> &middot; Index:{" "}
            <code className="font-mono">{INDEX_NAME}</code> &middot;{" "}
            {allQueries.length > 0
              ? `${allQueries.length.toLocaleString()} dev queries loaded`
              : "Dev queries"}
          </span>
        </div>
      </footer>
    </div>
  );
}
