import SearchApp from "./components/SearchApp";

export default function Page() {
  return (
    <main>
      <header className="app-header">
        <h1>MS MARCO Passage Search</h1>
        <p>
          BM25 retrieval over the MS MARCO V1 passage corpus via the Anserini REST API. Pick a
          sample dev query below or type your own.
        </p>
      </header>

      <SearchApp />

      <footer className="app-footer">
        Powered by Anserini · UI built with Next.js
      </footer>
    </main>
  );
}
