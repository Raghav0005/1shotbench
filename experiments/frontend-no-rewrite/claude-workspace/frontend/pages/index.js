import { useCallback, useEffect, useRef, useState } from 'react';
import Head from 'next/head';

const SAMPLE_COUNT = 6;
const DEFAULT_HITS = 10;

export default function Home({ initialSamples, initialTotal, initialError }) {
  const [query, setQuery] = useState('');
  const [samples, setSamples] = useState(initialSamples || []);
  const [totalSamples, setTotalSamples] = useState(initialTotal || 0);
  const [samplesError, setSamplesError] = useState(initialError || null);

  const [results, setResults] = useState(null); // null | { candidates, query, index, hits }
  const [searchError, setSearchError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submittedQuery, setSubmittedQuery] = useState(null);

  const inputRef = useRef(null);

  const refreshSamples = useCallback(async () => {
    try {
      const r = await fetch(`/api/sample-queries?n=${SAMPLE_COUNT}`);
      const data = await r.json();
      if (!r.ok) {
        setSamplesError(data.error || 'Could not load sample queries.');
      } else {
        setSamples(data.samples || []);
        setTotalSamples(data.total || 0);
        setSamplesError(null);
      }
    } catch (err) {
      setSamplesError(String(err && err.message ? err.message : err));
    }
  }, []);

  const runSearch = useCallback(async (q) => {
    const trimmed = (q || '').trim();
    if (!trimmed) {
      setSearchError('Please enter a query.');
      setResults(null);
      setSubmittedQuery(null);
      return;
    }
    setLoading(true);
    setSearchError(null);
    setSubmittedQuery(trimmed);
    try {
      const r = await fetch(
        `/api/search?q=${encodeURIComponent(trimmed)}&hits=${DEFAULT_HITS}`
      );
      const data = await r.json();
      if (!r.ok) {
        setSearchError(
          data.error
            ? `${data.error}${data.detail ? ` — ${data.detail}` : ''}`
            : 'Search failed.'
        );
        setResults(null);
      } else {
        setResults(data);
      }
    } catch (err) {
      setSearchError(
        `Network error talking to /api/search: ${
          err && err.message ? err.message : err
        }`
      );
      setResults(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const onSubmit = (e) => {
    e.preventDefault();
    runSearch(query);
  };

  const onSampleClick = (s) => {
    setQuery(s);
    runSearch(s);
    if (inputRef.current) inputRef.current.focus();
  };

  return (
    <div className="container">
      <Head>
        <title>MS MARCO Passage Search</title>
        <meta
          name="description"
          content="Search the MS MARCO passage corpus via Anserini."
        />
      </Head>

      <h1>MS MARCO Passage Search</h1>
      <p className="subtitle">
        Powered by the Anserini REST API over the{' '}
        <code>msmarco-v1-passage</code> prebuilt index.
      </p>

      <form className="search-form" onSubmit={onSubmit}>
        <input
          ref={inputRef}
          type="text"
          placeholder="Type a query, e.g. what is a lobster roll"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search query"
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      <section className="samples" aria-label="Sample queries">
        <h2>
          Try a sample query from MS MARCO dev
          <button
            type="button"
            className="refresh-btn"
            onClick={refreshSamples}
            aria-label="Pick new random samples"
          >
            shuffle
          </button>
        </h2>
        {samplesError ? (
          <div className="status error">{samplesError}</div>
        ) : (
          <div className="sample-row">
            {samples.map((s, i) => (
              <button
                key={`${i}-${s}`}
                type="button"
                className="sample-chip"
                onClick={() => onSampleClick(s)}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {totalSamples > 0 && (
          <div className="footer-meta">
            Sampling from {totalSamples.toLocaleString()} MS MARCO passage dev
            queries.
          </div>
        )}
      </section>

      {searchError && <div className="status error">{searchError}</div>}

      {!searchError && results && results.candidates.length === 0 && (
        <div className="status empty">
          No results for <strong>{submittedQuery}</strong>.
        </div>
      )}

      {!searchError && results && results.candidates.length > 0 && (
        <>
          <div className="status info">
            Showing top {results.candidates.length} results for{' '}
            <strong>{submittedQuery}</strong> from <code>{results.index}</code>.
          </div>
          <div className="results">
            {results.candidates.map((c) => (
              <article className="result-card" key={`${c.rank}-${c.docid}`}>
                <header className="result-header">
                  <span className="result-rank">#{c.rank}</span>
                  <span className="result-meta">
                    docid {c.docid} · score {Number(c.score).toFixed(4)}
                  </span>
                </header>
                <div className="result-body">{c.doc}</div>
              </article>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export async function getServerSideProps() {
  // Load sample queries server-side so first render already has them.
  try {
    const fs = await import('fs');
    const path = await import('path');
    const file = path.join(process.cwd(), 'data', 'msmarco-dev-queries.json');
    const raw = fs.readFileSync(file, 'utf8');
    const all = JSON.parse(raw);
    const picks = new Set();
    while (picks.size < Math.min(SAMPLE_COUNT, all.length)) {
      picks.add(Math.floor(Math.random() * all.length));
    }
    const samples = Array.from(picks).map((i) => all[i]);
    return {
      props: {
        initialSamples: samples,
        initialTotal: all.length,
        initialError: null,
      },
    };
  } catch (err) {
    return {
      props: {
        initialSamples: [],
        initialTotal: 0,
        initialError: `Failed to load sample queries: ${
          err && err.message ? err.message : String(err)
        }`,
      },
    };
  }
}
