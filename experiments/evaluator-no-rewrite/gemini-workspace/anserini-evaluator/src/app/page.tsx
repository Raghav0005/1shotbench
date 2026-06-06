import { getPrebuiltIndexes, getTopics } from './actions';
import Dashboard from './Dashboard';

export const dynamic = 'force-dynamic';

export default async function Home() {
  let indexes = [];
  let topics = [];
  let errorMsg = null;

  try {
    indexes = await getPrebuiltIndexes();
    topics = await getTopics();
  } catch (error: unknown) {
    if (error instanceof Error) {
      errorMsg = error.message;
    } else {
      errorMsg = String(error);
    }
  }

  return (
    <main className="min-h-screen p-8 bg-gray-50 text-gray-900">
      <div className="max-w-6xl mx-auto space-y-8">
        <header>
          <h1 className="text-3xl font-bold">Anserini Prebuilt Index Evaluator</h1>
          <p className="text-gray-600 mt-2">Browse and evaluate Anserini&apos;s prebuilt Lucene inverted indexes</p>
        </header>
        
        {errorMsg ? (
          <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded shadow">
            <h2 className="font-semibold text-xl mb-2">Setup Error</h2>
            <p>Failed to initialize Anserini registries. Please ensure Java 21 is installed and the Anserini fatjar is available.</p>
            <pre className="mt-4 text-xs bg-red-100 p-2 rounded whitespace-pre-wrap">{errorMsg}</pre>
          </div>
        ) : (
          <Dashboard initialIndexes={indexes} initialTopics={topics} />
        )}
      </div>
    </main>
  );
}
