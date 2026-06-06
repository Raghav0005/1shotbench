'use client';

import { useState, useEffect, FormEvent } from 'react';
import sampleQueriesList from '@/sample-queries.json';

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

export default function Home() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sampleQueries, setSampleQueries] = useState<string[]>([]);

  useEffect(() => {
    // Select 5 random queries on initial load
    const shuffled = [...sampleQueriesList].sort(() => 0.5 - Math.random());
    setSampleQueries(shuffled.slice(0, 5));
  }, []);

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;

    setQuery(searchQuery);
    setLoading(true);
    setError(null);
    setResults(null);

    try {
      const res = await fetch(`/api/search?query=${encodeURIComponent(searchQuery)}`);
      
      if (!res.ok) {
        throw new Error('Backend error or unavailable');
      }

      const data: SearchResponse = await res.json();
      setResults(data.candidates || []);
    } catch (err: any) {
      setError(err.message || 'An error occurred while searching');
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleSearch(query);
  };

  return (
    <main className="min-h-screen p-8 max-w-4xl mx-auto font-sans">
      <h1 className="text-3xl font-bold mb-8 text-center">MS MARCO Passage Search</h1>

      <div className="mb-8 p-6 bg-gray-50 rounded-lg shadow-sm border">
        <h2 className="text-lg font-semibold mb-4 text-gray-700">Sample Queries</h2>
        <div className="flex flex-wrap gap-2">
          {sampleQueries.map((q, idx) => (
            <button
              key={idx}
              onClick={() => handleSearch(q)}
              className="px-4 py-2 bg-blue-100 text-blue-700 rounded-full hover:bg-blue-200 transition text-sm"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={onSubmit} className="mb-8 flex gap-4">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter your search query..."
          className="flex-1 p-3 border rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={!query.trim() || loading}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium transition"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </form>

      <div className="space-y-6">
        {error && (
          <div className="p-4 bg-red-50 text-red-700 rounded-lg border border-red-200">
            {error}
          </div>
        )}

        {results && results.length === 0 && (
          <div className="p-4 bg-yellow-50 text-yellow-700 rounded-lg border border-yellow-200">
            No results found for "{query}".
          </div>
        )}

        {results && results.length > 0 && (
          <div>
            <h2 className="text-xl font-semibold mb-4 text-gray-800">Results</h2>
            <div className="space-y-4">
              {results.map((result) => (
                <div key={result.docid} className="p-5 border rounded-lg shadow-sm hover:shadow-md transition bg-white">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm font-medium text-gray-500">Rank: {result.rank}</span>
                    <span className="text-sm font-medium text-gray-500">Score: {result.score.toFixed(4)}</span>
                  </div>
                  <div className="text-xs text-gray-400 mb-2">DocID: {result.docid}</div>
                  <p className="text-gray-800 text-sm leading-relaxed">{result.doc}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
