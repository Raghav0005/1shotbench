'use client';

import { useState, useEffect } from 'react';

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
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sampleQueries, setSampleQueries] = useState<string[]>([]);
  const [hasSearched, setHasSearched] = useState(false);

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8080';

  useEffect(() => {
    // Load sample queries from the static file
    fetch('/msmarco_sample_queries.txt')
      .then(res => res.text())
      .then(text => {
        const queries = text.trim().split('\n');
        // Randomly select 8 sample queries
        const shuffled = [...queries].sort(() => 0.5 - Math.random());
        setSampleQueries(shuffled.slice(0, 8));
      })
      .catch(err => {
        console.error('Failed to load sample queries:', err);
        setSampleQueries([
          'what is a lobster roll',
          'average salary software engineer',
          'benefits of green tea',
          'how to learn python',
          'what is machine learning',
          'best restaurants in new york',
          'how does photosynthesis work',
          'what is the capital of france'
        ]);
      });
  }, []);

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) {
      setError('Please enter a search query');
      return;
    }

    setLoading(true);
    setError(null);
    setHasSearched(true);

    try {
      const response = await fetch(
        `${backendUrl}/v1/msmarco-v1-passage/search?query=${encodeURIComponent(searchQuery)}&hits=10`
      );

      if (!response.ok) {
        throw new Error(`Backend error: ${response.status} ${response.statusText}`);
      }

      const data: SearchResponse = await response.json();
      setResults(data.candidates || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred');
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch(query);
  };

  const handleSampleClick = (sampleQuery: string) => {
    setQuery(sampleQuery);
    handleSearch(sampleQuery);
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <main className="max-w-4xl mx-auto px-4 py-12">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-3">
            MS MARCO Passage Search
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-400">
            Search over the MS MARCO passage corpus using Anserini
          </p>
        </div>

        {/* Search Box */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6 mb-8">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your search query..."
              className="flex-1 px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
            />
            <button
              type="submit"
              disabled={loading}
              className="px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Searching...' : 'Search'}
            </button>
          </form>

          {/* Sample Queries */}
          <div className="mt-4">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">Try a sample query:</p>
            <div className="flex flex-wrap gap-2">
              {sampleQueries.map((sampleQuery, index) => (
                <button
                  key={index}
                  onClick={() => handleSampleClick(sampleQuery)}
                  className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  {sampleQuery}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
            <p className="text-red-700 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Results */}
        {hasSearched && !loading && !error && (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              {results.length > 0 ? `Found ${results.length} results` : 'No results found'}
            </h2>

            {results.length === 0 ? (
              <p className="text-gray-500 dark:text-gray-400">
                No passages found for your query. Try a different search term.
              </p>
            ) : (
              <div className="space-y-4">
                {results.map((result) => (
                  <div
                    key={result.docid}
                    className="border-b border-gray-200 dark:border-gray-700 last:border-0 pb-4 last:pb-0"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm font-medium text-blue-600 dark:text-blue-400">
                        Rank #{result.rank}
                      </span>
                      <span className="text-sm text-gray-400">|</span>
                      <span className="text-sm text-gray-500 dark:text-gray-400">
                        Doc ID: {result.docid}
                      </span>
                      <span className="text-sm text-gray-400">|</span>
                      <span className="text-sm text-gray-500 dark:text-gray-400">
                        Score: {result.score.toFixed(4)}
                      </span>
                    </div>
                    <p className="text-gray-800 dark:text-gray-200 leading-relaxed">
                      {result.doc}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-600 border-t-transparent"></div>
            <p className="mt-3 text-gray-600 dark:text-gray-400">Searching...</p>
          </div>
        )}
      </main>
    </div>
  );
}
