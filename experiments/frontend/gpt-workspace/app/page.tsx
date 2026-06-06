'use client';

import { FormEvent, useEffect, useState } from 'react';

type SampleQuery = {
  id: string;
  query: string;
};

type SearchResult = {
  docid?: string;
  score?: number;
  rank?: number;
  doc?: string;
};

const defaultHits = Number(process.env.NEXT_PUBLIC_DEFAULT_HITS ?? '10') || 10;

export default function Home() {
  const [query, setQuery] = useState('');
  const [samples, setSamples] = useState<SampleQuery[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchedQuery, setSearchedQuery] = useState('');
  const [loadingSamples, setLoadingSamples] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;

    async function loadSamples() {
      setLoadingSamples(true);
      try {
        const response = await fetch('/api/samples?count=6', { cache: 'no-store' });
        const payload = await response.json();
        if (active) setSamples(payload.samples ?? []);
      } catch {
        if (active) setSamples([]);
      } finally {
        if (active) setLoadingSamples(false);
      }
    }

    loadSamples();
    return () => {
      active = false;
    };
  }, []);

  async function runSearch(nextQuery = query) {
    const trimmed = nextQuery.trim();
    setError('');

    if (!trimmed) {
      setResults([]);
      setSearchedQuery('');
      setError('Enter a query or choose a sample query.');
      return;
    }

    setSearching(true);
    setQuery(trimmed);
    setSearchedQuery(trimmed);

    try {
      const response = await fetch(`/api/search?q=${encodeURIComponent(trimmed)}&hits=${defaultHits}`, {
        cache: 'no-store',
      });
      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.error || 'Search failed.');
      }

      setResults(payload.candidates ?? []);
      if ((payload.candidates ?? []).length === 0) {
        setError('No results were returned for this query.');
      }
    } catch (searchError) {
      setResults([]);
      setError(searchError instanceof Error ? searchError.message : 'Search failed.');
    } finally {
      setSearching(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    runSearch();
  }

  function handleSampleClick(sample: SampleQuery) {
    runSearch(sample.query);
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Local Anserini + Next.js</p>
        <h1>MS MARCO Passage Search</h1>
        <p className="lede">
          Search the MS MARCO passage corpus through the Anserini REST API. Start with one of the
          randomly selected development-set queries below or enter your own.
        </p>
      </section>

      <section className="panel search-panel" aria-label="Search form">
        <form onSubmit={handleSubmit} className="search-form">
          <label htmlFor="query">Search query</label>
          <div className="search-row">
            <input
              id="query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="e.g. what is a lobster roll"
              autoComplete="off"
            />
            <button type="submit" disabled={searching}>
              {searching ? 'Searching…' : 'Search'}
            </button>
          </div>
        </form>

        <div className="samples" aria-label="Sample queries">
          <div className="section-title">Sample MS MARCO dev queries</div>
          {loadingSamples ? (
            <p className="muted">Loading samples…</p>
          ) : samples.length > 0 ? (
            <div className="sample-list">
              {samples.map((sample) => (
                <button key={sample.id} type="button" onClick={() => handleSampleClick(sample)}>
                  {sample.query}
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">Sample queries are unavailable.</p>
          )}
        </div>
      </section>

      {error && <div className="notice" role="status">{error}</div>}

      <section className="results" aria-label="Search results">
        {searchedQuery && (
          <div className="results-header">
            <h2>Results for “{searchedQuery}”</h2>
            <span>{results.length} ranked results</span>
          </div>
        )}

        {results.map((result, index) => (
          <article key={`${result.docid ?? 'doc'}-${index}`} className="result-card">
            <div className="result-meta">
              <strong>#{result.rank ?? index + 1}</strong>
              {result.docid && <span>docid {result.docid}</span>}
              {typeof result.score === 'number' && <span>score {result.score.toFixed(4)}</span>}
            </div>
            <pre>{result.doc || 'No stored passage text returned for this result.'}</pre>
          </article>
        ))}
      </section>
    </main>
  );
}
