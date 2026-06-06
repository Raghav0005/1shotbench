"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import styles from "./SearchApp.module.css";

type SampleQuery = { id: string; text: string };

type Candidate = {
  docid: string;
  score: number;
  rank: number;
  doc: string;
};

type SearchResponse = {
  api?: string;
  index?: string;
  query?: { text: string };
  candidates?: Candidate[];
  error?: string;
};

const DEFAULT_HITS = 10;
const SAMPLE_COUNT = 5;
const QUERY_HISTORY_KEY = "msmarco.lastQueries.v1";

export default function SearchApp() {
  const [query, setQuery] = useState("");
  const [samples, setSamples] = useState<SampleQuery[]>([]);
  const [samplesError, setSamplesError] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);

  // Load random sample queries on first render and any time the user clicks
  // "Shuffle samples". Each call is a fresh request, so users get a new
  // mix on page reload.
  const loadSamples = useCallback(async () => {
    setSamplesError(null);
    try {
      const res = await fetch(`/api/sample-queries?count=${SAMPLE_COUNT}`, { cache: "no-store" });
      const data = (await res.json()) as { queries?: SampleQuery[]; error?: string };
      if (!res.ok) {
        setSamplesError(data.error ?? `Failed to load samples (status ${res.status}).`);
        setSamples([]);
        return;
      }
      setSamples(data.queries ?? []);
    } catch (err) {
      setSamplesError(
        err instanceof Error ? err.message : "Network error loading sample queries.",
      );
      setSamples([]);
    }
  }, []);

  useEffect(() => {
    loadSamples();
    if (typeof window !== "undefined") {
      try {
        const raw = window.localStorage.getItem(QUERY_HISTORY_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed)) {
            setHistory(parsed.filter((v): v is string => typeof v === "string").slice(0, 8));
          }
        }
      } catch {
        // Ignore localStorage errors (e.g. private mode).
      }
    }
  }, [loadSamples]);

  const runSearch = useCallback(
    async (q: string) => {
      const trimmed = q.trim();
      if (!trimmed) {
        setSearchError("Please enter a query or pick a sample.");
        setResults(null);
        return;
      }
      setIsSearching(true);
      setSearchError(null);
      setResults(null);
      try {
        const url = `/api/search?query=${encodeURIComponent(trimmed)}&hits=${DEFAULT_HITS}`;
        const res = await fetch(url, { cache: "no-store" });
        const data = (await res.json()) as SearchResponse;
        if (!res.ok) {
          setSearchError(data.error ?? `Search failed (status ${res.status}).`);
          setResults(null);
          return;
        }
        if (data.error) {
          setSearchError(data.error);
          setResults(null);
          return;
        }
        setResults(data);
        setQuery(trimmed);
        setHistory((prev) => {
          const next = [trimmed, ...prev.filter((v) => v !== trimmed)].slice(0, 8);
          if (typeof window !== "undefined") {
            try {
              window.localStorage.setItem(QUERY_HISTORY_KEY, JSON.stringify(next));
            } catch {
              // Ignore.
            }
          }
          return next;
        });
      } catch (err) {
        setSearchError(
          err instanceof Error
            ? `Could not reach the backend: ${err.message}`
            : "Could not reach the backend.",
        );
        setResults(null);
      } finally {
        setIsSearching(false);
      }
    },
    [],
  );

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    void runSearch(query);
  };

  const onSampleClick = (q: string) => {
    void runSearch(q);
  };

  const candidates = results?.candidates ?? [];
  const hasQuery = query.trim().length > 0;
  const showEmptyState =
    !isSearching && !searchError && results !== null && candidates.length === 0;

  return (
    <>
      <section className="panel" aria-labelledby="search-heading">
        <h2 id="search-heading">Search</h2>
        <form className={styles.searchForm} onSubmit={onSubmit}>
          <input
            className={styles.searchInput}
            type="text"
            name="query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a query and press Enter…"
            autoComplete="off"
            spellCheck={false}
            aria-label="Query"
          />
          <button
            type="submit"
            className={styles.searchButton}
            disabled={!hasQuery || isSearching}
          >
            {isSearching ? "Searching…" : "Search"}
          </button>
        </form>
        {history.length > 0 && (
          <div className={styles.historyRow}>
            <span className={styles.historyLabel}>Recent:</span>
            {history.map((h) => (
              <button
                key={h}
                type="button"
                className={styles.historyChip}
                onClick={() => onSampleClick(h)}
                disabled={isSearching}
                title={h}
              >
                {h}
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="samples-heading">
        <div className={styles.samplesHeader}>
          <h2 id="samples-heading">Sample queries (MS MARCO V1 passage dev)</h2>
          <button
            type="button"
            className={styles.shuffleButton}
            onClick={loadSamples}
            disabled={isSearching}
          >
            Shuffle
          </button>
        </div>
        {samplesError && <p className={styles.errorText}>Could not load samples: {samplesError}</p>}
        {samples.length === 0 && !samplesError ? (
          <p className={styles.muted}>Loading samples…</p>
        ) : (
          <ul className={styles.samplesList}>
            {samples.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className={styles.sampleButton}
                  onClick={() => onSampleClick(s.text)}
                  disabled={isSearching}
                  title={`Dev qid ${s.id}`}
                >
                  <span className={styles.sampleQid}>qid {s.id}</span>
                  <span className={styles.sampleText}>{s.text}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="results-heading">
        <h2 id="results-heading">Results</h2>

        {searchError && <p className={styles.errorText}>{searchError}</p>}

        {isSearching && <p className={styles.muted}>Searching the MS MARCO passage corpus…</p>}

        {!isSearching && !searchError && results === null && (
          <p className={styles.muted}>
            Run a search to see ranked MS MARCO passage results here.
          </p>
        )}

        {showEmptyState && (
          <p className={styles.muted}>
            No matching passages found for <strong>{results?.query?.text ?? query}</strong>.
          </p>
        )}

        {!isSearching && !searchError && candidates.length > 0 && (
          <>
            <p className={styles.resultsMeta}>
              Showing {candidates.length} result{candidates.length === 1 ? "" : "s"} for{" "}
              <strong>{results?.query?.text ?? query}</strong> on index{" "}
              <code>{results?.index ?? "msmarco-v1-passage"}</code>.
            </p>
            <ol className={styles.resultsList}>
              {candidates.map((c) => (
                <li key={`${c.rank}-${c.docid}`} className={styles.resultItem}>
                  <div className={styles.resultHeader}>
                    <span className={styles.resultRank}>#{c.rank}</span>
                    <span className={styles.resultDocid}>docid {c.docid}</span>
                    <span className={styles.resultScore}>score {c.score.toFixed(4)}</span>
                  </div>
                  <p className={styles.resultDoc}>{c.doc}</p>
                </li>
              ))}
            </ol>
          </>
        )}
      </section>
    </>
  );
}
