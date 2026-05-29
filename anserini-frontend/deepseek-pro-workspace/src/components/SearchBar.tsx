'use client';

import { useState, FormEvent, useRef, useEffect } from 'react';

interface SearchBarProps {
  onSearch: (query: string) => void;
  isLoading: boolean;
  initialQuery?: string;
}

export default function SearchBar({ onSearch, isLoading, initialQuery }: SearchBarProps) {
  const [query, setQuery] = useState(initialQuery ?? '');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (initialQuery !== undefined) {
      setQuery(initialQuery);
    }
  }, [initialQuery]);

  // Focus the input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length > 0) {
      onSearch(trimmed);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="search-bar">
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search MS MARCO passages..."
        className="search-input"
        disabled={isLoading}
        aria-label="Search query"
      />
      <button
        type="submit"
        className="search-button"
        disabled={isLoading || query.trim().length === 0}
      >
        {isLoading ? 'Searching...' : 'Search'}
      </button>
    </form>
  );
}
