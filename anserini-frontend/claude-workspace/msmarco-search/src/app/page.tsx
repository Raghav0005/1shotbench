"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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

type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: SearchResponse; queriedText: string }
  | { status: "empty"; queriedText: string }
  | { status: "error"; message: string; detail?: string };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SAMPLE_COUNT = 8;

function pickRandom<T>(arr: T[], n: number): T[] {
  const copy = [...arr];
  const result: T[] = [];
  for (let i = 0; i < Math.min(n, copy.length); i++) {
    const idx = Math.floor(Math.random() * (copy.length - i));
    result.push(copy[idx]);
    copy[idx] = copy[copy.length - 1 - i];
  }
  return result;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Home() {
  const [query, setQuery] = useState("");
  const [searchState, setSearchState] = useState<SearchState>({
    status: "idle",
  });
  const [sampleQueries, setSampleQueries] = useState<string[]>([]);
  const [allQueries, setAllQueries] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load MS MARCO dev queries on mount
  useEffect(() => {
    fetch("/msmarco-queries.json")
      .then((r) => r.json())
      .then((queries: string[]) => {
        setAllQueries(queries);
        setSampleQueries(pickRandom(queries, SAMPLE_COUNT));
      })
      .catch(() => {
        // Non-fatal: sample queries just won't appear
      });
  }, []);

  const refreshSamples = useCallback(() => {
    if (allQueries.length > 0) {
      setSampleQueries(pickRandom(allQueries, SAMPLE_COUNT));
    }
  }, [allQueries]);

  const runSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;

    setSearchState({ status: "loading" });

    try {
      const res = await fetch(
        `/api/search?query=${encodeURIComponent(trimmed)}&hits=10`
      );
      const data = await res.json();

      if (!res.ok) {
        setSearchState({
          status: "error",
          message: data.error ?? "Search failed.",
          detail: data.detail,
        });
        return;
      }

      const typed = data as SearchResponse;
      if (!typed.candidates || typed.candidates.length === 0) {
        setSearchState({ status: "empty", queriedText: trimmed });
      } else {
        setSearchState({
          status: "success",
          data: typed,
          queriedText: trimmed,
        });
      }
    } catch {
      setSearchState({
        status: "error",
        message: "Network error — could not reach the search API.",
      });
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runSearch(query);
  };

  const handleSampleClick = (q: string) => {
    setQuery(q);
    runSearch(q);
    inputRef.current?.focus();
  };

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const renderResults = () => {
    if (searchState.status === "idle") {
      return (
        <p className="text-gray-500 text-center mt-10">
          Enter a query above or click a sample to search.
        </p>
      );
    }

    if (searchState.status === "loading") {
      return (
        <div className="flex justify-center mt-10">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
        </div>
      );
    }

    if (searchState.status === "error") {
      return (
        <div className="mt-8 rounded-lg border border-red-300 bg-red-50 p-4">
          <p className="font-semibold text-red-700">Error</p>
          <p className="text-red-600 mt-1">{searchState.message}</p>
          {searchState.detail && (
            <pre className="mt-2 text-xs text-red-500 whitespace-pre-wrap break-all">
              {searchState.detail}
            </pre>
          )}
          <p className="mt-3 text-sm text-red-500">
            Make sure the Anserini REST server is running:
            <br />
            <code className="font-mono bg-red-100 px-1 rounded">
              java -cp anserini-*-fatjar.jar io.anserini.api.RestServer --port 8080
            </code>
          </p>
        </div>
      );
    }

    if (searchState.status === "empty") {
      return (
        <div className="mt-8 rounded-lg border border-yellow-300 bg-yellow-50 p-4">
          <p className="text-yellow-700">
            No results found for{" "}
            <strong>&ldquo;{searchState.queriedText}&rdquo;</strong>.
          </p>
        </div>
      );
    }

    // success
    const { data, queriedText } = searchState;
    return (
      <section className="mt-8">
        <p className="text-sm text-gray-500 mb-4">
          {data.candidates.length} result
          {data.candidates.length !== 1 ? "s" : ""} for{" "}
          <strong>&ldquo;{queriedText}&rdquo;</strong>
        </p>
        <ol className="space-y-4">
          {data.candidates.map((c) => (
            <li
              key={c.docid}
              className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono text-gray-400">
                  #{c.rank} &nbsp;·&nbsp; docid: {c.docid}
                </span>
                <span className="text-xs font-mono text-blue-500 font-semibold">
                  score: {c.score.toFixed(4)}
                </span>
              </div>
              <p className="text-sm text-gray-800 leading-relaxed line-clamp-6">
                {c.doc}
              </p>
            </li>
          ))}
        </ol>
      </section>
    );
  };

  // ---------------------------------------------------------------------------
  // Main render
  // ---------------------------------------------------------------------------

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-12">
        {/* Header */}
        <header className="mb-10 text-center">
          <h1 className="text-3xl font-bold text-gray-900 tracking-tight">
            MS MARCO Passage Search
          </h1>
          <p className="mt-2 text-gray-500">
            Powered by Anserini &mdash; BM25 over the MS MARCO V1 passage corpus
          </p>
        </header>

        {/* Search form */}
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter a search query…"
            className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm shadow-sm
                       focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <button
            type="submit"
            disabled={searchState.status === "loading" || !query.trim()}
            className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm
                       hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Search
          </button>
        </form>

        {/* Sample queries */}
        {sampleQueries.length > 0 && (
          <div className="mt-6">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                Sample queries from MS MARCO dev set
              </p>
              <button
                type="button"
                onClick={refreshSamples}
                className="text-xs text-blue-500 hover:text-blue-700 transition-colors"
                title="Refresh sample queries"
              >
                ↺ Refresh
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {sampleQueries.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => handleSampleClick(q)}
                  className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs text-gray-600
                             hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50 transition-colors shadow-sm"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Results */}
        {renderResults()}
      </div>
    </main>
  );
}
