"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Sample = { id: string; text: string };

type Candidate = {
  docid: string;
  score: number;
  rank: number;
  doc: string;
};

type Status =
  | { kind: "idle" }
  | { kind: "loading"; message: string }
  | { kind: "error"; message: string }
  | { kind: "warn"; message: string };

const DEFAULT_SAMPLE_COUNT = 5;

export default function Home() {
  const [query, setQuery] = useState("");
  const [samples, setSamples] = useState<Sample[]>([]);
  const [results, setResults] = useState<Candidate[] | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [samplesLoading, setSamplesLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [lastSubmittedQuery, setLastSubmittedQuery] = useState<string | null>(
    null,
  );
  const inputRef = useRef<HTMLInputElement>(null);

  const loadSamples = useCallback(async () => {
    setSamplesLoading(true);
    try {
      const res = await fetch(
        `/api/samples?count=${DEFAULT_SAMPLE_COUNT}`,
        { cache: "no-store" },
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.error ?? `HTTP ${res.status}`);
      }
      if (Array.isArray(data?.samples)) {
        setSamples(data.samples);
      }
    } catch (err) {
      // Sample loading is a nice-to-have; surface the error but keep the page usable.
      setStatus({
        kind: "error",
        message:
          "Could not load sample queries: " + (err as Error).message,
      });
    } finally {
      setSamplesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSamples();
  }, [loadSamples]);

  const runSearch = useCallback(
    async (rawQuery: string) => {
      const trimmed = rawQuery.trim();
      if (!trimmed) {
        setStatus({
          kind: "warn",
          message: "Please enter a query, or click one of the samples below.",
        });
        setResults(null);
        return;
      }
      setSearching(true);
      setStatus({ kind: "loading", message: "Searching the corpus..." });
      setLastSubmittedQuery(trimmed);
      try {
        const res = await fetch(
          `/api/search?query=${encodeURIComponent(trimmed)}&hits=10`,
          { cache: "no-store" },
        );
        const data = await res.json();
        if (!res.ok) {
          setStatus({
            kind: "error",
            message: data?.error ?? `Search failed (HTTP ${res.status}).`,
          });
          setResults(null);
          return;
        }
        const candidates: Candidate[] = Array.isArray(data?.candidates)
          ? data.candidates
          : [];
        if (candidates.length === 0) {
          setStatus({
            kind: "warn",
            message:
              "No passages matched this query. Try different keywords.",
          });
        } else {
          setStatus({ kind: "idle" });
        }
        setResults(candidates);
      } catch (err) {
        setStatus({
          kind: "error",
          message:
            "Could not reach the search backend. " +
            (err as Error).message,
        });
        setResults(null);
      } finally {
        setSearching(false);
      }
    },
    [],
  );

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    void runSearch(query);
  };

  const onSampleClick = (sample: Sample) => {
    setQuery(sample.text);
    void runSearch(sample.text);
  };

  return (
    <main className="container">
      <header className="header">
        <h1>MS MARCO Passage Search</h1>
        <p>
          Type a query or click a sample to search the MS MARCO passage corpus
          via the Anserini REST backend.
        </p>
      </header>

      <form className="search-form" onSubmit={onSubmit} role="search">
        <input
          ref={inputRef}
          className="search-input"
          type="text"
          placeholder="Search MS MARCO passages..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search query"
          disabled={searching}
        />
        <button
          type="submit"
          className="search-button"
          disabled={searching}
        >
          {searching ? "Searching..." : "Search"}
        </button>
      </form>

      <section className="samples-section" aria-label="Sample queries">
        <div className="samples-header">
          <h2>Sample queries</h2>
          <button
            type="button"
            className="samples-refresh"
            onClick={() => void loadSamples()}
            disabled={samplesLoading}
          >
            {samplesLoading ? "Loading..." : "Shuffle"}
          </button>
        </div>
        {samplesLoading && samples.length === 0 ? (
          <div className="status info">
            <span className="spinner" />
            Loading sample queries from the MS MARCO passage dev set...
          </div>
        ) : samples.length === 0 ? (
          <div className="status warn">
            No sample queries are available. The dev queries file may be
            missing.
          </div>
        ) : (
          <div className="samples-list">
            {samples.map((sample) => (
              <button
                key={sample.id}
                type="button"
                className="sample-pill"
                onClick={() => onSampleClick(sample)}
                disabled={searching}
                title={`MS MARCO dev qid ${sample.id}`}
              >
                {sample.text}
              </button>
            ))}
          </div>
        )}
      </section>

      {status.kind === "loading" && (
        <div className="status info" role="status">
          <span className="spinner" />
          {status.message}
        </div>
      )}
      {status.kind === "error" && (
        <div className="status error" role="alert">
          {status.message}
        </div>
      )}
      {status.kind === "warn" && results === null && (
        <div className="status warn" role="status">
          {status.message}
        </div>
      )}
      {status.kind === "warn" && results !== null && results.length === 0 && (
        <div className="status warn" role="status">
          {status.message}
        </div>
      )}

      {results !== null && results.length > 0 && (
        <>
          <div className="results-header">
            <span>
              Showing <strong>{results.length}</strong> results for{" "}
              <strong>&ldquo;{lastSubmittedQuery}&rdquo;</strong>
            </span>
            <span>msmarco-v1-passage</span>
          </div>
          {results.map((c) => (
            <article key={c.docid} className="result-card">
              <div className="result-meta">
                <span>Rank {c.rank}</span>
                <span>Score {c.score.toFixed(4)}</span>
              </div>
              <div className="result-doc">docid: {c.docid}</div>
              <p className="result-text">{c.doc}</p>
            </article>
          ))}
        </>
      )}

      {results === null && status.kind !== "error" && (
        <div className="empty">
          Enter a query above, or click a sample to see ranked passages.
        </div>
      )}

      <footer className="footer">
        Backend: Anserini REST API · Default index: msmarco-v1-passage
      </footer>
    </main>
  );
}
