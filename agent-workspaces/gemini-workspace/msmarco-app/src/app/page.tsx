"use client";

import { useState, useEffect } from "react";

const SAMPLE_QUERIES = [
  "Androgen receptor define",
  "3 levels of government in canada and their responsibilities",
  "3/5 of 60",
  "60x40 slab cost",
  "Bethel University was founded in what year",
  "Does Suddenlink Carry ESPN3",
  "Explain what a bone scan is and what it is used for.",
  "Is the Louisiana sales tax 4.75",
  "Ludacris Net Worth",
  "Sony PS-LX300USB how to connect to pc",
  "The hormone that does the opposite of calcitonin is",
  "What Does Noel Mean in the Bible",
  "When did the earthquake hit San Francisco during the World Series",
  "_____ is the ability of cardiac pacemaker cells to spontaneously initiate an electrical impulse without being stimulated from another source, such as a nerve.",
  "_____ is the name used to refer to the era of legalized segregation in the united states",
  "_______ is a fuel produced by fermenting crops.",
  "________ disparity refers to the slightly different view of the world that each eye receives.cyclopeanbinocularmonoculartrichromatic",
  "____________________ is considered the father of modern medicine.",
  "a simple definition for the word bias.",
  "about how many fans does mexico soccer team"
];

function getRandomSamples(arr: string[], n: number) {
  const shuffled = [...arr].sort(() => 0.5 - Math.random());
  return shuffled.slice(0, n);
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Record<string, unknown>[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [samples, setSamples] = useState<string[]>([]);

  useEffect(() => {
    setSamples(getRandomSamples(SAMPLE_QUERIES, 5));
  }, []);

  const search = async (q: string) => {
    if (!q.trim()) {
      setResults(null);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    setResults(null);

    try {
      const res = await fetch(`/api/search?query=${encodeURIComponent(q)}`);
      if (!res.ok) {
        throw new Error("Failed to fetch results from backend");
      }
      const data = await res.json();
      setResults(data.candidates || []);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    search(query);
  };

  const handleSampleClick = (q: string) => {
    setQuery(q);
    search(q);
  };

  return (
    <main className="min-h-screen p-8 max-w-4xl mx-auto font-sans">
      <h1 className="text-3xl font-bold mb-6 text-center">MS MARCO Passage Search</h1>

      <form onSubmit={handleSearchSubmit} className="flex gap-2 mb-8">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter your search query..."
          className="flex-1 p-3 border rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-black"
        />
        <button
          type="submit"
          disabled={loading}
          className="bg-blue-600 text-white px-6 py-3 rounded shadow-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      <div className="mb-8">
        <h2 className="text-xl font-semibold mb-3">Try a sample query:</h2>
        <div className="flex flex-wrap gap-2">
          {samples.map((sq, idx) => (
            <button
              key={idx}
              onClick={() => handleSampleClick(sq)}
              className="bg-gray-100 text-gray-800 px-3 py-1.5 rounded-full text-sm hover:bg-gray-200"
            >
              {sq}
            </button>
          ))}
        </div>
      </div>

      <div className="results-container">
        {loading && <p className="text-center text-gray-500">Loading results...</p>}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded mb-4">
            {error}
          </div>
        )}

        {!loading && !error && results && results.length === 0 && (
          <p className="text-center text-gray-500">No results found for &quot;{query}&quot;.</p>
        )}

        {!loading && !error && results && results.length > 0 && (
          <div className="flex flex-col gap-6">
            <h2 className="text-2xl font-semibold border-b pb-2 mb-4">Search Results</h2>
            {results.map((result: Record<string, unknown>, idx: number) => (
              <div key={result.docid as string} className="border p-4 rounded shadow-sm bg-white text-gray-800">
                <div className="text-sm text-gray-500 mb-1 flex justify-between">
                  <span>Rank: {typeof result.rank === 'number' ? result.rank : idx + 1}</span>
                  <span>Score: {typeof result.score === 'number' ? result.score.toFixed(4) : result.score as string}</span>
                </div>
                <div className="font-semibold text-gray-700 mb-2">DocID: {result.docid as string}</div>
                <p className="text-gray-900">{result.doc as string}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
