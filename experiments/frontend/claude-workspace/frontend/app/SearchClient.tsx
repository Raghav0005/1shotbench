"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

type SampleQuery = { id: string; text: string };

type ResultRow = {
  rank: number;
  docid: string;
  score: number;
  text: string;
};

type SearchResponse = {
  index: string;
  query: string;
  results: ResultRow[];
};

type Status =
  | { kind: "idle" }
  | { kind: "loading"; query: string }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: SearchResponse };

export default function SearchClient({
  initialSamples,
  samplesError,
}: {
  initialSamples: SampleQuery[];
  samplesError: string | null;
}) {
  const [query, setQuery] = useState("");
  const [samples, setSamples] = useState<SampleQuery[]>(initialSamples);
  const [sampleErr, setSampleErr] = useState<string | null>(samplesError);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const inputRef = useRef<HTMLInputElement>(null);
  const reqIdRef = useRef(0);

  // If server-side sample loading failed (or returned nothing) try refetching
  // from the API once the client mounts — this makes the page recover from
  // transient FS / startup issues without a full reload.
  useEffect(() => {
    if (initialSamples.length > 0) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/sample-queries", { cache: "no-store" });
        const body = await res.json();
        if (cancelled) return;
        if (res.ok && Array.isArray(body.samples)) {
          setSamples(body.samples);
          setSampleErr(null);
        } else if (body?.error) {
          setSampleErr(String(body.error));
        }
      } catch (err) {
        if (!cancelled) {
          setSampleErr(err instanceof Error ? err.message : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initialSamples.length]);

  const runSearch = useCallback(async (rawQuery: string) => {
    const q = rawQuery.trim();
    if (!q) {
      setStatus({ kind: "error", message: "Please enter a query before searching." });
      return;
    }
    const myReq = ++reqIdRef.current;
    setStatus({ kind: "loading", query: q });
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`, {
        cache: "no-store",
      });
      const body = await res.json();
      if (myReq !== reqIdRef.current) return; // stale response
      if (!res.ok) {
        const message =
          (body && typeof body.error === "string" && body.error) ||
          `Search failed with status ${res.status}.`;
        setStatus({ kind: "error", message });
        return;
      }
      setStatus({ kind: "ready", data: body as SearchResponse });
    } catch (err) {
      if (myReq !== reqIdRef.current) return;
      setStatus({
        kind: "error",
        message:
          err instanceof Error
            ? `Network error: ${err.message}`
            : "Network error while contacting the search API.",
      });
    }
  }, []);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    runSearch(query);
  };

  const onSampleClick = (text: string) => {
    setQuery(text);
    inputRef.current?.focus();
    runSearch(text);
  };

  return (
    <>
      <form className="search" onSubmit={onSubmit} role="search">
        <input
          ref={inputRef}
          type="text"
          name="q"
          placeholder="Search MS MARCO passages…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search query"
          autoFocus
        />
        <button type="submit" disabled={status.kind === "loading"}>
          {status.kind === "loading" ? "Searching…" : "Search"}
        </button>
      </form>

      <section className="samples" aria-label="Sample queries">
        <h2>Try a sample query</h2>
        {sampleErr ? (
          <div className="status error" role="alert">
            Couldn’t load sample queries: {sampleErr}
          </div>
        ) : samples.length === 0 ? (
          <div className="status">Loading sample queries…</div>
        ) : (
          <ul>
            {samples.map((s) => (
              <li key={s.id}>
                <button type="button" onClick={() => onSampleClick(s.text)}>
                  {s.text}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ResultsView status={status} />
    </>
  );
}

function ResultsView({ status }: { status: Status }) {
  if (status.kind === "idle") {
    return (
      <div className="status">
        Enter a query above or click one of the sample queries to get started.
      </div>
    );
  }
  if (status.kind === "loading") {
    return <div className="status">Searching for “{status.query}”…</div>;
  }
  if (status.kind === "error") {
    return (
      <div className="status error" role="alert">
        {status.message}
      </div>
    );
  }
  const { data } = status;
  if (data.results.length === 0) {
    return (
      <div className="status">
        No results found for “{data.query}”. Try a different query.
      </div>
    );
  }
  return (
    <>
      <p className="results-meta">
        Showing {data.results.length} result{data.results.length === 1 ? "" : "s"} for
        “{data.query}” on <code>{data.index}</code>.
      </p>
      <ol className="results">
        {data.results.map((r) => (
          <li key={`${r.rank}-${r.docid}`}>
            <div className="result-head">
              <span>
                #{r.rank} · docid <code>{r.docid}</code>
              </span>
              <span>score {r.score.toFixed(4)}</span>
            </div>
            <div className="result-body">{r.text}</div>
          </li>
        ))}
      </ol>
    </>
  );
}
