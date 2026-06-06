'use client';

import { useState, useMemo } from 'react';
import { runEvaluation } from './actions';

type IndexMetadata = {
  name: string;
  type: string;
  description: string;
  filename: string;
};

export default function Dashboard({
  initialIndexes,
  initialTopics,
}: {
  initialIndexes: IndexMetadata[];
  initialTopics: string[];
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState<IndexMetadata | null>(
    initialIndexes.find(idx => idx.name === 'cacm') || null
  );

  const [selectedTopic, setSelectedTopic] = useState('cacm');
  const [selectedMetric, setSelectedMetric] = useState('map');
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const evaluableMap = useMemo(() => {
    // For simplicity, an index is "evaluable" if we know a direct topic/qrels mapping for it.
    // We explicitly support cacm and some msmarco pairings if they exist in topics.
    const map = new Map<string, string[]>();
    
    // Check cacm
    if (initialTopics.includes('cacm')) {
      map.set('cacm', ['cacm']);
    }

    // Check msmarco-v1-passage
    const msmarcoPassageTopics = ['msmarco-passage.dev-subset', 'dl19-passage', 'dl20-passage'].filter(t => initialTopics.includes(t));
    if (msmarcoPassageTopics.length > 0) {
      map.set('msmarco-v1-passage', msmarcoPassageTopics);
      map.set('msmarco-v1-passage-slim', msmarcoPassageTopics);
    }
    
    // Add other generic heuristics: if the index name exactly matches a topic
    for (const idx of initialIndexes) {
      if (!map.has(idx.name) && initialTopics.includes(idx.name)) {
        map.set(idx.name, [idx.name]);
      }
    }

    return map;
  }, [initialIndexes, initialTopics]);

  const filteredIndexes = initialIndexes.filter(idx => 
    idx.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
    idx.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const evaluableTopics = selectedIndex ? evaluableMap.get(selectedIndex.name) || [] : [];
  const isEvaluable = evaluableTopics.length > 0;

  // Modern metrics
  const availableMetrics = [
    { label: 'MAP', value: 'map' },
    { label: 'P@30', value: 'P.30' },
    { label: 'nDCG@10', value: 'ndcg_cut.10' },
    { label: 'Recall@1000', value: 'recall.1000' }
  ];

  const handleRunEvaluation = async () => {
    if (!selectedIndex || !selectedTopic) return;
    
    setIsRunning(true);
    setError(null);
    setResult(null);

    try {
      const res = await runEvaluation(selectedIndex.name, selectedTopic, selectedMetric);
      if (res.error) {
         setError(res.error);
      } else {
         setResult(res);
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An error occurred during evaluation.');
      }
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Catalog */}
      <div className="md:col-span-1 bg-white p-4 rounded shadow flex flex-col max-h-[80vh]">
        <h2 className="text-xl font-semibold mb-4">Index Catalog</h2>
        <input 
          type="text" 
          placeholder="Search indexes..." 
          className="border p-2 rounded mb-4 w-full"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
        />
        <div className="overflow-y-auto flex-1 space-y-2">
          {filteredIndexes.map(idx => {
            const evaluable = evaluableMap.has(idx.name);
            const isSelected = selectedIndex?.name === idx.name;
            return (
              <div 
                key={idx.name}
                className={`p-3 border rounded cursor-pointer transition-colors ${isSelected ? 'bg-blue-50 border-blue-400' : 'hover:bg-gray-50'}`}
                onClick={() => {
                  setSelectedIndex(idx);
                  const topics = evaluableMap.get(idx.name);
                  if (topics && topics.length > 0) {
                    setSelectedTopic(topics[0]);
                  } else {
                    setSelectedTopic('');
                  }
                }}
              >
                <div className="font-medium truncate" title={idx.name}>{idx.name}</div>
                <div className="text-xs text-gray-500 mt-1 line-clamp-2" title={idx.description}>{idx.description}</div>
                <div className="mt-2 text-xs font-semibold">
                  {evaluable ? <span className="text-green-600">Evaluable</span> : <span className="text-gray-400">Catalog Only</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Evaluation Dashboard */}
      <div className="md:col-span-2 space-y-6">
        <div className="bg-white p-6 rounded shadow">
          <h2 className="text-xl font-semibold mb-4">Evaluation Setup</h2>
          
          {selectedIndex ? (
            <div className="space-y-4">
              <div>
                <span className="font-medium">Selected Index:</span> 
                <span className="ml-2">{selectedIndex.name}</span>
                <p className="text-sm text-gray-600 mt-1">{selectedIndex.description}</p>
              </div>

              {isEvaluable ? (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-1">Topic / Qrels Source</label>
                      <select 
                        className="w-full border p-2 rounded bg-white"
                        value={selectedTopic}
                        onChange={e => setSelectedTopic(e.target.value)}
                      >
                        {evaluableTopics.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-1">Metric</label>
                      <select 
                        className="w-full border p-2 rounded bg-white"
                        value={selectedMetric}
                        onChange={e => setSelectedMetric(e.target.value)}
                      >
                        {availableMetrics.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                      </select>
                    </div>
                  </div>

                  <button 
                    className={`mt-4 px-4 py-2 rounded font-medium text-white transition-colors ${isRunning ? 'bg-blue-300 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'}`}
                    onClick={handleRunEvaluation}
                    disabled={isRunning}
                  >
                    {isRunning ? 'Running Evaluation...' : 'Run Evaluation'}
                  </button>
                </>
              ) : (
                <div className="p-4 bg-yellow-50 border border-yellow-200 rounded text-yellow-800">
                  This index lacks an automatically discovered topics/qrels pairing and cannot be evaluated here. It is visible as a catalog-only entry.
                </div>
              )}
            </div>
          ) : (
            <div className="text-gray-500">Select an index from the catalog to begin.</div>
          )}
        </div>

        {/* Results */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded shadow">
            <h3 className="font-semibold">Error</h3>
            <pre className="mt-2 text-sm whitespace-pre-wrap">{error}</pre>
          </div>
        )}

        {result && (
          <div className="bg-white p-6 rounded shadow space-y-4">
            <h2 className="text-xl font-semibold border-b pb-2">Evaluation Results</h2>
            
            <div className="flex items-center space-x-4">
              <div className="text-4xl font-bold text-blue-600">
                {result.score ? Number(result.score).toFixed(4) : 'N/A'}
              </div>
              <div className="text-gray-600">
                Score for <span className="font-semibold">{String(result.metric)}</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-y-2 text-sm bg-gray-50 p-4 rounded border">
              <div className="font-medium text-gray-500">Index:</div>
              <div className="font-mono">{String(result.index)}</div>
              
              <div className="font-medium text-gray-500">Topics / Qrels:</div>
              <div className="font-mono">{String(result.topics)}</div>
              
              <div className="font-medium text-gray-500">Retrieval Time:</div>
              <div>{String(result.searchElapsed)} ms</div>

              <div className="font-medium text-gray-500">Run Artifact:</div>
              <div className="font-mono text-blue-600 break-all">{String(result.runFile)}</div>
            </div>

            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-1">trec_eval Output Preview</h3>
              <pre className="text-xs bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto max-h-48">
                {String(result.evalOutput)}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
