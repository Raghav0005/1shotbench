import SearchClient from "./SearchClient";
import { pickRandomSampleQueries } from "@/lib/sample-queries";
import { config } from "@/lib/config";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let initialSamples: { id: string; text: string }[] = [];
  let samplesError: string | null = null;

  try {
    initialSamples = await pickRandomSampleQueries(config.sampleQueriesCount);
  } catch (err) {
    samplesError =
      err instanceof Error ? err.message : "Could not load sample queries.";
  }

  return (
    <main className="container">
      <header className="hero">
        <h1>MS MARCO Passage Search</h1>
        <p>
          Search the MS MARCO passage corpus via the Anserini REST API. Sample queries
          are drawn at random from the MS MARCO passage dev set on every page load.
        </p>
      </header>

      <SearchClient initialSamples={initialSamples} samplesError={samplesError} />

      <footer className="notes">
        Backend: <code>{config.anseriniBaseUrl}</code>{" "}
        · Index: <code>{config.anseriniIndex}</code>
      </footer>
    </main>
  );
}
