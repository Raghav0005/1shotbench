"use client";

import { useState, useEffect, useCallback } from "react";
import queries from "./sample_queries.json";

const NUM_SAMPLES = 10;

function getRandomQueries(count: number): string[] {
  const shuffled = [...queries].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, count);
}

interface SearchResult {
  docid: string;
  score: number;
  rank: number;
  doc: string;
}

function SampleQueries({
  queries: sampleQueries,
  onQueryClick,
}: {
  queries: string[];
  onQueryClick: (q: string) => void;
}) {
  return (
    <div className="w-full">
      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
        Sample Queries
      </h2>
      <div className="flex flex-wrap gap-2">
        {sampleQueries.map((q, i) => (
          <button
            key={i}
            onClick={() => onQueryClick(q)}
            className="px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-full
                       hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700
                       transition-colors cursor-pointer text-gray-600 shadow-sm"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function SearchResults({
  results,
  query,
}: {
  results: SearchResult[];
  query: string;
}) {
  return (
    <div className="w-full">
      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
        Results for &ldquo;{query}&rdquo; ({results.length} hits)
      </h2>
      <div className="space-y-3">
        {results.map((r, i) => {
          // doc can be a plain string or a JSON string with a contents field
          let rawText = "";
          if (typeof r.doc === "string") {
            try {
              const parsed = JSON.parse(r.doc);
              rawText = parsed.contents || r.doc;
            } catch {
              rawText = r.doc;
            }
          } else {
            rawText = String(r.doc);
          }
          return (
            <div
              key={r.docid}
              className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm"
            >
              <div className="flex items-center gap-3 mb-2">
                <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-blue-100 text-blue-700 text-xs font-bold">
                  {i + 1}
                </span>
                <span className="text-xs text-gray-400 font-mono">
                  {r.docid}
                </span>
                <span className="text-xs text-gray-400 ml-auto">
                  score: {r.score.toFixed(4)}
                </span>
              </div>
              <p className="text-gray-700 text-sm leading-relaxed pl-10">
                {rawText}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Home() {
  const [sampleQueries, setSampleQueries] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [lastQuery, setLastQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pick random sample queries on mount
  useEffect(() => {
    setSampleQueries(getRandomQueries(NUM_SAMPLES));
  }, []);

  const doSearch = useCallback(async (searchQuery: string) => {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      setError("Please enter a query.");
      return;
    }

    setLoading(true);
    setError(null);
    setLastQuery(trimmed);
    setResults([]);

    try {
      const res = await fetch(
        `/api/search?query=${encodeURIComponent(trimmed)}&hits=10`
      );
      if (!res.ok) {
        const text = await res.text();
        throw new Error(
          `Backend returned ${res.status}: ${text || res.statusText}`
        );
      }
      const data = await res.json();
      const hits: SearchResult[] = data.candidates ?? [];
      if (hits.length === 0) {
        setError("No results found for this query.");
      } else {
        // Convert doc string field to match our interface
        setResults(hits);
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "An unknown error occurred.";
      setError(
        message.includes("fetch")
          ? "Could not reach the Anserini backend. Make sure it is running."
          : message
      );
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
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <header className="bg-blue-700 text-white py-8 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-3xl font-bold mb-2">MS MARCO Passage Search</h1>
          <p className="text-blue-200 text-sm">
            Search the MS MARCO passage corpus powered by Anserini
          </p>
        </div>
      </header>

      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-8 space-y-8">
        {/* Search form */}
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter a search query..."
            className="flex-1 px-4 py-3 border border-gray-300 rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                       shadow-sm"
          />
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg text-sm font-medium
                       hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors cursor-pointer shadow-sm"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        {/* Sample queries */}
        {sampleQueries.length > 0 && (
          <SampleQueries queries={sampleQueries} onQueryClick={handleSampleClick} />
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 text-sm">
            {error}
          </div>
        )}

        {/* Results */}
        {results.length > 0 && (
          <SearchResults results={results} query={lastQuery} />
        )}
      </main>

      {/* Footer */}
      <footer className="py-4 text-center text-xs text-gray-400 border-t border-gray-100">
        MS MARCO Passage Search &middot; Next.js + Anserini REST API
      </footer>
    </div>
  );
}
