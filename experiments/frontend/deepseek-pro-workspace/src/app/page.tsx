'use client';

import { useState, useCallback, useMemo } from 'react';
import SearchBar from '@/components/SearchBar';
import SampleQueries from '@/components/SampleQueries';
import SearchResults from '@/components/SearchResults';
import ErrorMessage from '@/components/ErrorMessage';
import { search, AnseriniSearchResult, AnseriniApiError } from '@/lib/anserini';
import { getRandomSampleQueries } from '@/lib/sampleQueries';

export default function HomePage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<AnseriniSearchResult[] | null>(null);
  const [lastSearchedQuery, setLastSearchedQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Generate random sample queries on first render (stable for the session)
  const sampleQueries = useMemo(() => getRandomSampleQueries(5), []);

  const handleSearch = useCallback(async (q: string) => {
    setQuery(q);
    setError(null);
    setResults(null);
    setLastSearchedQuery(q);
    setIsLoading(true);

    try {
      const response = await search(q, 10);
      setResults(response.results ?? []);
    } catch (err) {
      if (err instanceof AnseriniApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred.');
      }
      setResults(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleSampleSelect = useCallback((q: string) => {
    handleSearch(q);
  }, [handleSearch]);

  const handleRetry = useCallback(() => {
    if (lastSearchedQuery) {
      handleSearch(lastSearchedQuery);
    }
  }, [lastSearchedQuery, handleSearch]);

  return (
    <main className="app-container">
      <header className="app-header">
        <h1 className="app-title">MS MARCO Passage Search</h1>
        <p className="app-subtitle">
          Search the MS MARCO passage corpus using the Anserini search engine.
        </p>
      </header>

      <SearchBar
        onSearch={handleSearch}
        isLoading={isLoading}
        initialQuery={query}
      />

      {results === null && !isLoading && !error && (
        <SampleQueries
          queries={sampleQueries}
          onSelect={handleSampleSelect}
          isLoading={isLoading}
        />
      )}

      {isLoading && (
        <div className="loading" role="status">
          <span className="loading-spinner" />
          <p>Searching for &ldquo;{lastSearchedQuery}&rdquo;...</p>
        </div>
      )}

      {error && (
        <ErrorMessage message={error} onRetry={handleRetry} />
      )}

      {results !== null && !isLoading && !error && (
        <SearchResults results={results} query={lastSearchedQuery} />
      )}

      <footer className="app-footer">
        <p>
          Powered by{' '}
          <a href="https://github.com/castorini/anserini" target="_blank" rel="noopener noreferrer">
            Anserini
          </a>
          {' '}— MS MARCO Passage Ranking
        </p>
      </footer>
    </main>
  );
}
