'use client';

import { useEffect, useState } from 'react';

const DEFAULT_ERROR = 'Something went wrong. Please try again.';

export default function Home() {
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [samples, setSamples] = useState([]);
  const [sampleError, setSampleError] = useState('');
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function loadSamples() {
      try {
        const response = await fetch('/api/sample-queries?count=8', { cache: 'no-store' });
        const payload = await response.json();
        if (!cancelled) {
          setSamples(Array.isArray(payload.queries) ? payload.queries : []);
          setSampleError('');
        }
      } catch {
        if (!cancelled) {
          setSampleError('Sample queries are unavailable right now.');
        }
      }
    }

    loadSamples();
    return () => {
      cancelled = true;
    };
  }, []);

  async function runSearch(nextQuery = query) {
    const trimmed = nextQuery.trim();
    setError('');

    if (!trimmed) {
      setStatus('idle');
      setResults([]);
      setSubmittedQuery('');
      setError('Enter a search query before searching.');
      return;
    }

    setQuery(trimmed);
    setSubmittedQuery(trimmed);
    setStatus('loading');
    setResults([]);

    try {
      const response = await fetch(`/api/search?q=${encodeURIComponent(trimmed)}&hits=10`, { cache: 'no-store' });
      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.error || DEFAULT_ERROR);
      }

      setResults(Array.isArray(payload.results) ? payload.results : []);
      setStatus('done');
    } catch (caught) {
      setStatus('error');
      setError(caught instanceof Error ? caught.message : DEFAULT_ERROR);
    }
  }

  function onSubmit(event) {
    event.preventDefault();
    runSearch();
  }

  function onSampleClick(sampleQuery) {
    runSearch(sampleQuery);
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Anserini REST API · MS MARCO V1 Passage</p>
        <h1>Search MS MARCO passages locally</h1>
        <p className="lede">
          Enter a question or choose a dev-set sample query. Results are ranked by Anserini from the
          <code> msmarco-v1-passage </code> prebuilt index.
        </p>

        <form className="searchForm" onSubmit={onSubmit}>
          <label className="srOnly" htmlFor="query">Search query</label>
          <input
            id="query"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="what is a lobster roll"
            autoComplete="off"
          />
          <button type="submit" disabled={status === 'loading'}>
            {status === 'loading' ? 'Searching…' : 'Search'}
          </button>
        </form>

        {error ? <div className="notice error" role="alert">{error}</div> : null}
      </section>

      <section className="card samples" aria-labelledby="samples-heading">
        <div className="sectionHeader">
          <h2 id="samples-heading">Try sample MS MARCO dev queries</h2>
          <span>{samples.length ? `${samples.length} random samples` : 'Loading samples…'}</span>
        </div>
        {sampleError ? <p className="muted">{sampleError}</p> : null}
        <div className="sampleGrid">
          {samples.map((sample) => (
            <button key={sample.id} type="button" onClick={() => onSampleClick(sample.query)}>
              <span className="qid">#{sample.id}</span>
              {sample.query}
            </button>
          ))}
        </div>
      </section>

      <section className="card results" aria-live="polite" aria-busy={status === 'loading'}>
        <div className="sectionHeader">
          <h2>Ranked results</h2>
          {submittedQuery ? <span>Query: “{submittedQuery}”</span> : <span>No query submitted</span>}
        </div>

        {status === 'idle' ? (
          <p className="muted">Submit a query to see ranked passages.</p>
        ) : null}

        {status === 'loading' ? (
          <div className="loadingList">
            {Array.from({ length: 3 }).map((_, index) => <div className="skeleton" key={index} />)}
          </div>
        ) : null}

        {status === 'done' && results.length === 0 ? (
          <p className="muted">No results found for this query.</p>
        ) : null}

        {status === 'done' && results.length > 0 ? (
          <ol className="resultList">
            {results.map((result) => (
              <li key={`${result.rank}-${result.docid}`}>
                <div className="resultMeta">
                  <strong>Rank {result.rank}</strong>
                  <span>DocID {result.docid || 'unknown'}</span>
                  <span>Score {result.score.toFixed(4)}</span>
                </div>
                <p>{result.passage || 'This result did not include stored passage text.'}</p>
              </li>
            ))}
          </ol>
        ) : null}
      </section>
    </main>
  );
}
