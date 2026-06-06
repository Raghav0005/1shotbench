import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Search, Activity, FileText, Settings, Play, CheckCircle, XCircle } from 'lucide-react';
import './App.css';

const API_BASE = ''; // relative to same host

function App() {
  const [health, setHealth] = useState(null);
  const [evalData, setEvalData] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchCommand, setSearchCommand] = useState('');
  const [searchLoading, setSearchLoading] = useState(false);
  const [evalLoading, setEvalLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('search');
  
  useEffect(() => {
    fetchHealth();
    fetchEvalStatus();
  }, []);

  const fetchHealth = async () => {
    try {
      const res = await axios.get(`${API_BASE}/health`);
      setHealth(res.data);
    } catch (error) {
      console.error('Failed to fetch health', error);
    }
  };

  const fetchEvalStatus = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/evalStatus`);
      setEvalData(res.data);
    } catch (error) {
      console.error('Failed to fetch eval status', error);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery) return;
    setSearchLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/api/search?q=${encodeURIComponent(searchQuery)}`);
      setSearchResults(res.data.hits);
      setSearchCommand(res.data.command);
    } catch (err) {
      console.error(err);
      alert('Search failed');
    } finally {
      setSearchLoading(false);
    }
  };

  const handleRerunEval = async () => {
    setEvalLoading(true);
    setEvalData(null);
    try {
      await axios.post(`${API_BASE}/api/rerunEval`);
      await fetchEvalStatus();
    } catch (err) {
      console.error(err);
      alert('Eval rerun failed');
    } finally {
      setEvalLoading(false);
    }
  };

  return (
    <div className="container">
      <header>
        <h1>NFCorpus Live Retrieval Diagnostics Workbench</h1>
      </header>

      <div className="layout">
        {/* SIDEBAR: Status Panel */}
        <aside className="sidebar">
          <div className="panel">
            <h2><Activity size={18} /> Readiness Status</h2>
            <div className="status-list">
              <div className="status-item">
                <span>Application:</span>
                <StatusBadge status={health?.status === 'ready'} />
              </div>
              <div className="status-item">
                <span>Java Runtime:</span>
                <StatusBadge status={health?.java} />
              </div>
              <div className="status-item">
                <span>Anserini Fatjar:</span>
                <StatusBadge status={health?.fatjar} />
              </div>
              <div className="status-item">
                <span>NFCorpus Index:</span>
                <StatusBadge status={health?.nfcorpus_ready} />
              </div>
              <div className="status-item">
                <span>Live Search:</span>
                <StatusBadge status={health?.search_available} />
              </div>
            </div>
            {health?.status !== 'ready' && (
              <div className="error-text">
                <p><strong>System is initializing or encountered an error.</strong></p>
                {health?.status === 'error' && <p>Please check the deployment logs. Ensure Java 21 is installed and the fatjar is downloaded.</p>}
              </div>
            )}
          </div>

          <div className="panel">
            <h2><Settings size={18} /> Configuration</h2>
            <p>Dataset: <strong>NFCorpus</strong></p>
            <p>Model: <strong>BM25</strong></p>
            <p>Topics: <strong>beir-v1.0.0-nfcorpus.test</strong></p>
            <p>Port Binding: <strong>Uses $PORT env var (default: 10000) for Render compatibility</strong></p>
          </div>

          {health?.setup_commands && health.setup_commands.length > 0 && (
            <div className="command-drawer">
              <h4>Setup & Diagnostic Commands</h4>
              {health.setup_commands.map((cmd, i) => (
                <code key={i} style={{fontSize: '11px'}}>{cmd}</code>
              ))}
            </div>
          )}
        </aside>

        {/* MAIN CONTENT */}
        <main className="main-content">
          <div className="tabs">
            <button className={activeTab === 'search' ? 'active' : ''} onClick={() => setActiveTab('search')}>Live Search</button>
            <button className={activeTab === 'eval' ? 'active' : ''} onClick={() => setActiveTab('eval')}>Evaluation Metrics</button>
          </div>

          {activeTab === 'search' && (
            <div className="tab-pane">
              <div className="search-box">
                <form onSubmit={handleSearch}>
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Enter query or select a sample..."
                    disabled={!health?.search_available || searchLoading}
                  />
                  <button type="submit" disabled={!health?.search_available || searchLoading}>
                    <Search size={16} /> {searchLoading ? 'Searching...' : 'Search'}
                  </button>
                </form>
                <div className="sample-queries">
                  Sample Queries:
                  <button onClick={() => setSearchQuery('breast cancer treatment')}>breast cancer treatment</button>
                  <button onClick={() => setSearchQuery('heart disease diet')}>heart disease diet</button>
                  <button onClick={() => setSearchQuery('obesity risk factors')}>obesity risk factors</button>
                </div>
              </div>

              {searchCommand && (
                <div className="command-drawer">
                  <h4>Exact Command Executed</h4>
                  <code>{searchCommand}</code>
                </div>
              )}

              <div className="search-results">
                {searchResults.map((hit, index) => (
                  <div key={hit.docid} className="result-card">
                    <div className="result-header">
                      <span className="rank">#{index + 1}</span>
                      <span className="docid">{hit.docid}</span>
                      <span className="score">Score: {hit.score.toFixed(4)}</span>
                    </div>
                    <div className="result-body">
                      {hit.doc?.title && <strong>{hit.doc.title}</strong>}
                      <p>{hit.doc?.text || hit.doc?.contents || hit.content}</p>
                    </div>
                  </div>
                ))}
                {searchResults.length === 0 && searchCommand && !searchLoading && (
                  <p>No results found.</p>
                )}
              </div>
            </div>
          )}

          {activeTab === 'eval' && (
            <div className="tab-pane">
              <div className="eval-panel">
                <div className="eval-header">
                  <h3>BM25 Evaluation vs Expected Targets</h3>
                  <button onClick={handleRerunEval} disabled={evalLoading || !health?.evaluation_available}>
                    <Play size={16} /> {evalLoading ? 'Running...' : 'Verify / Rerun'}
                  </button>
                </div>

                {!evalData?.metrics ? (
                  <p>Evaluation results are not available yet. Please wait or click Verify / Rerun.</p>
                ) : (
                  <div>
                    <div className="metrics-grid">
                      <div className="metric-card">
                        <h4>Metric</h4>
                        <div className="value">{evalData.metrics.metric}</div>
                      </div>
                      <div className="metric-card">
                        <h4>Expected</h4>
                        <div className="value">{evalData.metrics.expected}</div>
                      </div>
                      <div className="metric-card">
                        <h4>Observed</h4>
                        <div className="value">{evalData.metrics.observed?.toFixed(4) || 'N/A'}</div>
                      </div>
                      <div className="metric-card">
                        <h4>Delta</h4>
                        <div className="value">
                           {evalData.metrics.observed ? 
                             Math.abs(evalData.metrics.observed - evalData.metrics.expected).toFixed(4) 
                             : 'N/A'}
                        </div>
                      </div>
                      <div className="metric-card">
                        <h4>Status</h4>
                        <div className="value">
                           {evalData.metrics.observed && Math.abs(evalData.metrics.observed - evalData.metrics.expected) < 0.0001 ? (
                             <span className="pass">PASS</span>
                           ) : (
                             <span className="fail">FAIL</span>
                           )}
                        </div>
                      </div>
                    </div>
                    {evalData.time && (
                      <p className="eval-time">
                        {evalData.isCached ? "Displaying cached setup results." : "Fresh rerun completed."} 
                        {' '}Elapsed execution time: {evalData.time}ms
                      </p>
                    )}
                  </div>
                )}
              </div>

              {evalData?.commands && evalData.commands.length > 0 && (
                <div className="command-drawer">
                  <h4>Evaluation Commands</h4>
                  {evalData.commands.map((cmd, i) => (
                    <code key={i}>{cmd}</code>
                  ))}
                </div>
              )}

              {evalData?.artifacts && evalData.artifacts.length > 0 && (
                <div className="command-drawer">
                  <h4>Generated Artifacts</h4>
                  {evalData.artifacts.map((art, i) => (
                    <div key={i}><FileText size={14}/> {art}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

const StatusBadge = ({ status }) => {
  if (status === null || status === undefined) return <span className="badge unknown">...</span>;
  return status ? <CheckCircle className="icon pass" size={18} /> : <XCircle className="icon fail" size={18} />;
};

export default App;
