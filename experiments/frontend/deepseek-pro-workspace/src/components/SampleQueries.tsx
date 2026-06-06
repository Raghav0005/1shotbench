'use client';

interface SampleQueriesProps {
  queries: string[];
  onSelect: (query: string) => void;
  isLoading: boolean;
}

export default function SampleQueries({ queries, onSelect, isLoading }: SampleQueriesProps) {
  if (queries.length === 0) {
    return null;
  }

  return (
    <div className="sample-queries">
      <h2 className="sample-queries-title">Try a sample query:</h2>
      <div className="sample-queries-list">
        {queries.map((q, i) => (
          <button
            key={`${i}-${q}`}
            type="button"
            className="sample-query-chip"
            onClick={() => onSelect(q)}
            disabled={isLoading}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
