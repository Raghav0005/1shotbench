"use client";

import { useState, useEffect } from "react";
import { SearchResult } from "@/lib/types";

interface SampleQuery {
  id: string;
  query: string;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [sampleQueries, setSampleQueries] = useState<SampleQuery[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const backendUrl =
    process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";

  useEffect(() => {
    fetchSampleQueries();
  }, []);

  async function fetchSampleQueries() {
    try {
      const res = await fetch(`${backendUrl}/api/sample-queries`);
      if (!res.ok) throw new Error("Failed to fetch sample queries");
      const data = await res.json();
      setSampleQueries(data);
    } catch {
      // Fallback sample queries if backend is not running
      setSampleQueries([
        { id: "1", query: "what is a lobster roll" },
        { id: "2", query: "how do I make pancakes from scratch" },
        { id: "3", query: "benefits of drinking green tea" },
        { id: "4", query: "who invented the printing press" },
        { id: "5", query: "difference between virus and bacteria" },
      ]);
    }
  }

  async function handleSearch(searchQuery: string) {
    if (!searchQuery.trim()) {
      setError("Please enter a query");
      return;
    }

    setIsLoading(true);
    setError(null);
    setHasSearched(true);
    setQuery(searchQuery);

    try {
      const encodedQuery = encodeURIComponent(searchQuery);
      const res = await fetch(
        `${backendUrl}/v1/msmarco-v1-passage/search?query=${encodedQuery}&hits=10`
      );

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(
          errorData.message || `HTTP error ${res.status}`
        );
      }

      const data = await res.json();
      setResults(data.hits || []);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "An error occurred while searching"
      );
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    handleSearch(query);
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      {/* Header */}
      <header className="bg-white dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-800">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">
            MS MARCO Passage Search
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
            Search over the MS MARCO passage corpus using Anserini
          </p>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Search Box */}
        <form onSubmit={handleSubmit} className="mb-8">
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your search query..."
              className="flex-1 px-4 py-3 border border-zinc-300 dark:border-zinc-700 rounded-lg 
                         bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-50
                         placeholder-zinc-400 focus:outline-none focus:ring-2 
                         focus:ring-blue-500 dark:focus:ring-blue-400"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium 
                         rounded-lg transition-colors disabled:opacity-50 
                         disabled:cursor-not-allowed"
            >
              {isLoading ? "Searching..." : "Search"}
            </button>
          </div>
        </form>

        {/* Error Message */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 
                           dark:border-red-800 rounded-lg">
            <p className="text-red-700 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Sample Queries */}
        {!hasSearched && sampleQueries.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-semibold text-zinc-700 dark:text-zinc-300 mb-3">
              Try a sample query
            </h2>
            <div className="flex flex-wrap gap-2">
              {sampleQueries.map((sq) => (
                <button
                  key={sq.id}
                  onClick={() => handleSearch(sq.query)}
                  disabled={isLoading}
                  className="px-4 py-2 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 
                             dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-300 
                             rounded-full text-sm transition-colors disabled:opacity-50"
                >
                  {sq.query}
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Loading Spinner */}
        {isLoading && (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-4 
                             border-blue-500 border-t-transparent"></div>
          </div>
        )}

        {/* Search Results */}
        {!isLoading && hasSearched && results.length === 0 && !error && (
          <div className="text-center py-12">
            <p className="text-zinc-500 dark:text-zinc-400">
              No results found for "{query}"
            </p>
          </div>
        )}

        {!isLoading && results.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-zinc-700 dark:text-zinc-300 mb-4">
              Search Results for "{query}"
            </h2>
            <div className="space-y-4">
              {results.map((result, index) => (
                <div
                  key={result.docid}
                  className="p-4 bg-white dark:bg-zinc-900 border border-zinc-200 
                             dark:border-zinc-800 rounded-lg"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="inline-flex items-center justify-center w-6 h-6 
                                         bg-blue-100 dark:bg-blue-900 text-blue-700 
                                         dark:text-blue-300 text-xs font-medium rounded">
                          {index + 1}
                        </span>
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">
                          ID: {result.docid}
                        </span>
                      </div>
                      <p className="text-zinc-800 dark:text-zinc-200">
                        {result.content}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="text-xs text-zinc-500 dark:text-zinc-400 block">
                        Score
                      </span>
                      <span className="font-mono text-sm text-zinc-600 dark:text-zinc-400">
                        {result.score.toFixed(4)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="mt-auto py-6 text-center text-sm text-zinc-500 dark:text-zinc-400">
        <p>Powered by Anserini REST API</p>
      </footer>
    </div>
  );
}