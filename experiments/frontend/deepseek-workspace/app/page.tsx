"use client";

import { useState, useCallback, useMemo } from "react";
import sampleQueries from "../sample-queries.json";

interface SearchResult {
  docid: string;
  score: number;
  content: string;
}

function pickRandom<T>(arr: T[], n: number): T[] {
  const shuffled = [...arr];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled.slice(0, n);
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchedQuery, setSearchedQuery] = useState("");

  const randomSamples = useMemo(() => pickRandom(sampleQueries, 6), []);

  const handleSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);
    setResults(null);
    setSearchedQuery(trimmed);
    setQuery(trimmed);

    try {
      const backendPort = process.env.NEXT_PUBLIC_BACKEND_PORT || "8080";
      const url = `http://localhost:${backendPort}/v1/msmarco-v1-passage/search?query=${encodeURIComponent(trimmed)}&hits=10`;
      const res = await fetch(url);

      if (!res.ok) {
        throw new Error(`Backend returned status ${res.status}`);
      }

      const data = await res.json();
      const hits: SearchResult[] = (data.candidates || []).map((c: any) => ({
        docid: c.docid,
        score: c.score,
        content: c.doc || "",
      }));
      setResults(hits);
    } catch (err: any) {
      setError(err.message || "Failed to connect to search backend");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch(query);
  };

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: "2rem 1rem" }}>
      <h1 style={{ fontSize: "1.8rem", marginBottom: "0.25rem" }}>
        MS MARCO Passage Search
      </h1>
      <p style={{ color: "#666", marginBottom: "1.5rem" }}>
        Search the MS MARCO passage corpus via Anserini BM25
      </p>

      {/* Search form */}
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter a search query..."
          style={{
            flex: 1,
            padding: "0.75rem 1rem",
            fontSize: "1rem",
            border: "1px solid #ccc",
            borderRadius: "6px",
            outline: "none",
          }}
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          style={{
            padding: "0.75rem 1.5rem",
            fontSize: "1rem",
            backgroundColor: loading || !query.trim() ? "#93c5fd" : "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            cursor: loading || !query.trim() ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {/* Sample queries */}
      <div style={{ marginBottom: "1.5rem" }}>
        <p style={{ fontSize: "0.875rem", color: "#666", marginBottom: "0.5rem" }}>
          Try a sample query:
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          {randomSamples.map((q, i) => (
            <button
              key={i}
              onClick={() => handleSearch(q)}
              disabled={loading}
              style={{
                padding: "0.4rem 0.75rem",
                fontSize: "0.85rem",
                backgroundColor: "#f3f4f6",
                border: "1px solid #d1d5db",
                borderRadius: "20px",
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.5 : 1,
              }}
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Empty query warning */}
      {error === null && results === null && !loading && searchedQuery === "" && query.trim() === "" && (
        <div
          style={{
            padding: "2rem",
            textAlign: "center",
            color: "#9ca3af",
            border: "1px dashed #d1d5db",
            borderRadius: "8px",
          }}
        >
          Enter a query above or click a sample query to start searching.
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div style={{ textAlign: "center", padding: "2rem", color: "#666" }}>
          Searching for &ldquo;{searchedQuery}&rdquo;...
        </div>
      )}

      {/* Error state */}
      {error && (
        <div
          style={{
            padding: "1rem",
            backgroundColor: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: "8px",
            color: "#991b1b",
          }}
        >
          <strong>Error:</strong> {error}
          <p style={{ margin: "0.5rem 0 0", fontSize: "0.875rem" }}>
            Make sure the Anserini REST server is running on the configured
            backend port.
          </p>
        </div>
      )}

      {/* Zero results */}
      {results !== null && results.length === 0 && !loading && !error && (
        <div
          style={{
            padding: "2rem",
            textAlign: "center",
            color: "#6b7280",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
          }}
        >
          No results found for &ldquo;{searchedQuery}&rdquo;.
        </div>
      )}

      {/* Results */}
      {results !== null && results.length > 0 && (
        <div>
          <p style={{ color: "#666", fontSize: "0.875rem", marginBottom: "1rem" }}>
            {results.length} result{results.length !== 1 ? "s" : ""} for
            &ldquo;{searchedQuery}&rdquo;
          </p>
          <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {results.map((r, i) => (
              <li
                key={r.docid}
                style={{
                  padding: "1rem",
                  marginBottom: "0.75rem",
                  border: "1px solid #e5e7eb",
                  borderRadius: "8px",
                  backgroundColor: "#fafafa",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "0.5rem",
                  }}
                >
                  <span style={{ fontWeight: 600, color: "#2563eb" }}>
                    #{i + 1}
                  </span>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      color: "#9ca3af",
                    }}
                  >
                    docid: {r.docid} | score: {r.score.toFixed(4)}
                  </span>
                </div>
                <p
                  style={{
                    margin: 0,
                    fontSize: "0.9rem",
                    lineHeight: 1.6,
                    color: "#374151",
                  }}
                >
                  {r.content || <em style={{ color: "#9ca3af" }}>No content available</em>}
                </p>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
