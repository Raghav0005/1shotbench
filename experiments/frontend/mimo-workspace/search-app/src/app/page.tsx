'use client';

import { useState, useEffect, useCallback } from 'react';

interface SearchResult {
  docid: string;
  score: number;
  doc: string;
}

interface SampleQuery {
  id: number;
  query: string;
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sampleQueries, setSampleQueries] = useState<SampleQuery[]>([]);
  const [searchedQuery, setSearchedQuery] = useState('');

  useEffect(() => {
    // Load sample queries and randomly select 5
    import('@/data/sample-queries.json').then((data) => {
      const shuffled = [...data.default].sort(() => Math.random() - 0.5);
      setSampleQueries(shuffled.slice(0, 5));
    });
  }, []);

  const handleSearch = useCallback(async (searchQuery?: string) => {
    const q = searchQuery || query.trim();
    if (!q) {
      setError('Please enter a search query');
      return;
    }

    setLoading(true);
    setError(null);
    setSearchedQuery(q);

    try {
      const response = await fetch(`/api/search?query=${encodeURIComponent(q)}&hits=10`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Search failed');
      }

      setResults(data.results || []);
      if (data.results && data.results.length === 0) {
        setError('No results found for your query');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [query]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch();
  };

  const handleSampleClick = (sampleQuery: string) => {
    setQuery(sampleQuery);
    handleSearch(sampleQuery);
  };

  const refreshSamples = () => {
    import('@/data/sample-queries.json').then((data) => {
      const shuffled = [...data.default].sort(() => Math.random() - 0.5);
      setSampleQueries(shuffled.slice(0, 5));
    });
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            MS MARCO Passage Search
          </h1>
          <p className="text-lg text-gray-600">
            Search through the MS MARCO passage collection using Anserini
          </p>
        </div>

        {/* Search Form */}
        <form onSubmit={handleSubmit} className="mb-8">
          <div className="flex gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your search query..."
              className="flex-1 px-5 py-3 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900 text-lg"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading}
              className="px-8 py-3 bg-blue-600 text-white rounded-lg shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-lg transition-colors"
            >
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>
        </form>

        {/* Sample Queries */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-600 uppercase tracking-wide">
              Try these sample queries
            </h2>
            <button
              onClick={refreshSamples}
              className="text-sm text-blue-600 hover:text-blue-800 font-medium"
            >
              ↻ Refresh
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {sampleQueries.map((sq) => (
              <button
                key={sq.id}
                onClick={() => handleSampleClick(sq.query)}
                disabled={loading}
                className="px-4 py-2 bg-white border border-gray-200 rounded-full text-sm text-gray-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors disabled:opacity-50 shadow-sm"
              >
                {sq.query}
              </button>
            ))}
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-red-700">{error}</p>
          </div>
        )}

        {/* Results */}
        {searchedQuery && !error && results.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">
                Results for &ldquo;{searchedQuery}&rdquo;
              </h2>
              <span className="text-sm text-gray-500">
                {results.length} results
              </span>
            </div>
            <div className="space-y-4">
              {results.map((result, index) => (
                <div
                  key={`${result.docid}-${index}`}
                  className="bg-white p-5 rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow"
                >
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-xs font-mono text-gray-500 bg-gray-100 px-2 py-1 rounded">
                      Doc ID: {result.docid}
                    </span>
                    <span className="text-sm font-semibold text-blue-600">
                      Score: {result.score.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-gray-800 leading-relaxed">
                    {result.doc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* No Results */}
        {searchedQuery && !error && results.length === 0 && !loading && (
          <div className="text-center py-12">
            <p className="text-gray-500 text-lg">
              No results found for &ldquo;{searchedQuery}&rdquo;
            </p>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-600 border-r-transparent"></div>
            <p className="mt-3 text-gray-600">Searching...</p>
          </div>
        )}
      </div>
    </main>
  );
}
