'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import devQueries from '../src/data/msmarco-passage-dev-queries.json';

type QuerySample = {
  id: string;
  title: string;
};

type SearchResult = {
  docid?: string;
  score?: number;
  rank?: number;
  doc?: string;
};

type SearchState = {
  status: 'idle' | 'loading' | 'success' | 'error' | 'empty';
  message?: string;
  detail?: string;
  searchedQuery?: string;
  results: SearchResult[];
};

const SAMPLE_COUNT = 8;
const HITS = 10;
const allSamples = devQueries as QuerySample[];

function drawSamples(count = SAMPLE_COUNT) {
  const pool = [...allSamples];
  const samples: QuerySample[] = [];

  while (samples.length < count && pool.length > 0) {
    const index = Math.floor(Math.random() * pool.length);
    const [sample] = pool.splice(index, 1);
    samples.push(sample);
  }

  return samples;
}

function cleanPassage(doc?: string) {
  if (!doc) return 'No stored passage text was returned for this result.';

  return doc
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/\s+/g, ' ')
    .trim();
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [samples, setSamples] = useState<QuerySample[]>([]);
  const [state, setState] = useState<SearchState>({ status: 'idle', results: [] });

  const sampleCountLabel = useMemo(() => allSamples.length.toLocaleString(), []);

  useEffect(() => {
    setSamples(drawSamples());
  }, []);

  async function runSearch(nextQuery: string) {
    const trimmed = nextQuery.trim();
    setQuery(nextQuery);

    if (!trimmed) {
      setState({
        status: 'empty',
        message: 'Please enter a query or choose one of the MS MARCO dev queries below.',
        results: [],
      });
      return;
    }

    setState({ status: 'loading', searchedQuery: trimmed, results: [] });

    try {
      const response = await fetch(`/api/search?q=${encodeURIComponent(trimmed)}&hits=${HITS}`);
      const data = await response.json();

      if (!response.ok) {
        setState({
          status: 'error',
          message: data.error || 'Search failed.',
          detail: data.detail,
          searchedQuery: trimmed,
          results: [],
        });
        return;
      }

      const results = Array.isArray(data.candidates) ? data.candidates : [];
      setState({
        status: results.length > 0 ? 'success' : 'empty',
        message: results.length > 0 ? undefined : 'No passages matched this query.',
        searchedQuery: data.query || trimmed,
        results,
      });
    } catch (error) {
      setState({
        status: 'error',
        message: 'The frontend could not complete the search request.',
        detail: error instanceof Error ? error.message : undefined,
        searchedQuery: trimmed,
        results: [],
      });
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    runSearch(query);
  }

  return (
    <main className="page">
      <section className="hero">
        <p className="eyebrow">Anserini REST + Next.js</p>
        <h1>MS MARCO passage search</h1>
        <p className="subtitle">
          Search the MS MARCO passage corpus using the local Anserini REST API. Try a query from the
          dev set or enter your own to view ranked passages.
        </p>
      </section>

      <section className="search-card" aria-label="Search MS MARCO passages">
        <form className="search-form" onSubmit={onSubmit}>
          <input
            className="search-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. what is a lobster roll"
            aria-label="Search query"
          />
          <button className="primary-button" type="submit" disabled={state.status === 'loading'}>
            {state.status === 'loading' ? 'Searching…' : 'Search'}
          </button>
        </form>

        <div className="samples">
          <div className="samples-header">
            <p className="samples-title">Random MS MARCO passage dev queries</p>
            <button className="secondary-button" type="button" onClick={() => setSamples(drawSamples())}>
              Shuffle from {sampleCountLabel}
            </button>
          </div>
          <div className="sample-list">
            {samples.length === 0 && <span className="sample-placeholder">Loading sample queries…</span>}
            {samples.map((sample) => (
              <button
                className="sample-chip"
                key={sample.id}
                type="button"
                onClick={() => runSearch(sample.title)}
                disabled={state.status === 'loading'}
              >
                {sample.title}
              </button>
            ))}
          </div>
        </div>
      </section>

      {state.status === 'idle' && (
        <div className="status">Submit a query to retrieve ranked passages from msmarco-v1-passage.</div>
      )}

      {(state.status === 'empty' || state.status === 'error') && (
        <div className={`status ${state.status === 'error' ? 'error' : ''}`}>
          <strong>{state.message}</strong>
          {state.detail && <div>{state.detail}</div>}
        </div>
      )}

      {state.status === 'loading' && <div className="status">Searching Anserini for “{state.searchedQuery}”…</div>}

      {state.status === 'success' && (
        <section className="results-card" aria-live="polite">
          <div className="results-header">
            <h2 className="results-title">Ranked results</h2>
            <p className="results-meta">
              {state.results.length} hits for “{state.searchedQuery}”
            </p>
          </div>
          <ol className="result-list">
            {state.results.map((result, index) => (
              <li className="result-item" key={`${result.docid || 'doc'}-${result.rank || index}`}>
                <div className="result-topline">
                  <span className="rank">Rank {result.rank ?? index + 1}</span>
                  {typeof result.score === 'number' && <span className="score">Score {result.score.toFixed(4)}</span>}
                </div>
                <p className="docid">Document {result.docid || 'unknown'}</p>
                <p className="passage">{cleanPassage(result.doc)}</p>
              </li>
            ))}
          </ol>
        </section>
      )}
    </main>
  );
}
