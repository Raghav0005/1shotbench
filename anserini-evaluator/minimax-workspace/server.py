#!/usr/bin/env python3
"""
Anserini Prebuilt Index Evaluator - Flask Backend
Serves the index catalog, runs retrieval, and evaluates results.
"""

import os
import sys
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, render_template

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')

# Paths
WORKSPACE_DIR = Path(__file__).parent.resolve()
ANSERINI_JAR = os.environ.get('ANSERINI_JAR', str(WORKSPACE_DIR / 'anserini-2.1.1-fatjar.jar'))
RUNS_DIR = WORKSPACE_DIR / 'runs'
RUNS_DIR.mkdir(exist_ok=True)

# Hardcoded evaluable index -> (topics, qrels) mappings
# These are index names that map to Anserini's known prebuilt index symbols
EVALUABLE_INDEXES = {
    'cacm': {
        'topics': 'cacm',
        'qrels': 'cacm',
        'description': 'CACM Computer Abstract Search'
    }
}

# Metrics supported per qrels set
METRICS_BY_QRELS = {
    'cacm': [
        {'id': 'map', 'label': 'MAP (Mean Average Precision)'},
        {'id': 'P.30', 'label': 'P@30 (Precision at 30)'},
        {'id': 'ndcg_cut.10', 'label': 'NDCG@10'},
        {'id': 'recall.1000', 'label': 'Recall@1000'},
    ]
}

def run_java_command(main_class, args, timeout=300):
    """Run a Java command and return stdout, stderr, and return code."""
    cmd = ['java', '-cp', ANSERINI_JAR, main_class] + args
    logger.info(f"Executing: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_DIR)
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        return '', f'Command timed out after {timeout}s', -1
    except Exception as e:
        logger.error(f"Error running command: {e}")
        return '', str(e), -1

def fetch_prebuilt_indexes():
    """Fetch prebuilt inverted indexes from Anserini registry."""
    stdout, stderr, code = run_java_command(
        'io.anserini.cli.PrebuiltIndexRegistry',
        ['--type', 'inverted', '--list']
    )
    if code != 0:
        logger.error(f"Failed to fetch indexes: {stderr}")
        return []
    
    try:
        # Registry outputs JSON array
        indexes = json.loads(stdout)
        logger.info(f"Loaded {len(indexes)} indexes from registry")
        
        # Mark evaluable indexes
        for idx in indexes:
            idx['evaluable'] = idx['name'] in EVALUABLE_INDEXES
            if idx['evaluable']:
                idx['topics'] = EVALUABLE_INDEXES[idx['name']]['topics']
                idx['qrels'] = EVALUABLE_INDEXES[idx['name']]['qrels']
                idx['description'] = EVALUABLE_INDEXES[idx['name']]['description']
                idx['available_metrics'] = METRICS_BY_QRELS.get(idx['qrels'], [])
        
        return indexes
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse index registry JSON: {e}")
        return []

def fetch_topics():
    """Fetch available topics from Anserini registry."""
    stdout, stderr, code = run_java_command(
        'io.anserini.cli.TopicsRegistry',
        ['--list']
    )
    if code != 0:
        logger.error(f"Failed to fetch topics: {stderr}")
        return []
    
    try:
        # Topics registry outputs JSON array
        topics = json.loads(stdout)
        return topics
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse topics registry JSON: {e}")
        return []

# Routes
@app.route('/')
def index():
    """Serve the main HTML page."""
    return send_from_directory(app.root_path, 'templates/index.html')

@app.route('/api/health')
def health():
    """Health check endpoint."""
    jar_exists = os.path.exists(ANSERINI_JAR)
    return jsonify({
        'status': 'ok',
        'jar_exists': jar_exists,
        'jar_path': ANSERINI_JAR
    })

@app.route('/api/indexes')
def get_indexes():
    """Return prebuilt indexes from Anserini registry."""
    indexes = fetch_prebuilt_indexes()
    return jsonify(indexes)

@app.route('/api/topics')
def get_topics():
    """Return available topics from Anserini registry."""
    topics = fetch_topics()
    return jsonify(topics)

@app.route('/api/metrics')
def get_metrics():
    """Return available metrics for a given qrels."""
    qrels = request.args.get('qrels', '')
    metrics = METRICS_BY_QRELS.get(qrels, [])
    return jsonify(metrics)

@app.route('/api/evaluate', methods=['POST'])
def evaluate():
    """Run retrieval and evaluation for a selected index/topics/metric combo."""
    data = request.get_json()
    index_name = data.get('index')
    topics_name = data.get('topics')
    qrels_name = data.get('qrels')
    metric = data.get('metric')
    
    if not all([index_name, topics_name, qrels_name, metric]):
        return jsonify({'error': 'Missing required parameters'}), 400
    
    # Generate run file with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_file = RUNS_DIR / f'run.{index_name}.{timestamp}.txt'
    
    logger.info(f"Running evaluation: index={index_name}, topics={topics_name}, qrels={qrels_name}, metric={metric}")
    
    # Step 1: Run retrieval
    logger.info(f"Running retrieval: SearchCollection -index {index_name} -topics {topics_name} -output {run_file} -hits 1000 -bm25 -threads 1")
    stdout, stderr, code = run_java_command(
        'io.anserini.search.SearchCollection',
        ['-index', index_name, '-topics', topics_name, '-output', str(run_file), '-hits', '1000', '-bm25', '-threads', '1']
    )
    
    if code != 0:
        logger.error(f"Retrieval failed: {stderr}")
        return jsonify({'error': f'Retrieval failed: {stderr}', 'stderr': stderr}), 500
    
    logger.info(f"Retrieval complete, run file: {run_file}")
    
    # Step 2: Run evaluation
    logger.info(f"Running evaluation: TrecEval -c -m {metric} {qrels_name} {run_file}")
    eval_stdout, eval_stderr, eval_code = run_java_command(
        'io.anserini.eval.TrecEval',
        ['-c', '-m', metric, qrels_name, str(run_file)]
    )
    
    if eval_code != 0:
        logger.error(f"Evaluation failed: {eval_stderr}")
        return jsonify({'error': f'Evaluation failed: {eval_stderr}', 'stderr': eval_stderr}), 500
    
    # Parse score from evaluation output
    # Format is typically: metric\tall\tscore
    # Note: metric names may have underscores instead of dots in output
    score = None
    # Normalize metric for comparison (replace . with _ and vice versa)
    normalized_metric = metric.replace('.', '_').replace('-', '_')
    for line in eval_stdout.strip().split('\n'):
        parts = line.split('\t')
        if len(parts) >= 3:
            output_metric = parts[0].strip()
            # Check both exact match and normalized match
            if (output_metric == metric or output_metric == normalized_metric) and parts[1] == 'all':
                score = parts[2]
                break
    
    # Also try without normalization as fallback
    if score is None:
        for line in eval_stdout.strip().split('\n'):
            parts = line.split('\t')
            if len(parts) >= 3 and parts[1] == 'all':
                score = parts[2]
                break
    
    logger.info(f"Evaluation complete, score: {score}")
    
    return jsonify({
        'success': True,
        'score': score,
        'metric': metric,
        'index': index_name,
        'topics': topics_name,
        'qrels': qrels_name,
        'run_file': str(run_file),
        'eval_output': eval_stdout,
        'retrieval_output': stdout
    })

@app.route('/api/runs')
def list_runs():
    """List available run files."""
    runs = []
    for f in RUNS_DIR.glob('run.*.txt'):
        runs.append({
            'name': f.name,
            'path': str(f),
            'size': f.stat().st_size,
            'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
        })
    return jsonify(runs)

@app.route('/api/run/<path:filename>')
def get_run(filename):
    """Serve a run file."""
    return send_from_directory(str(RUNS_DIR), filename)

if __name__ == '__main__':
    # Check Java is available
    try:
        result = subprocess.run(['java', '-version'], capture_output=True, text=True)
        logger.info(f"Java version: {result.stderr.splitlines()[0]}")
    except Exception as e:
        logger.error(f"Java not found: {e}")
        sys.exit(1)
    
    # Check jar exists
    if not os.path.exists(ANSERINI_JAR):
        logger.error(f"Anserini jar not found at: {ANSERINI_JAR}")
        logger.error("Run: curl -fL -o anserini-2.1.1-fatjar.jar https://repo1.maven.org/maven2/io/anserini/anserini/2.1.1/anserini-2.1.1-fatjar.jar")
        sys.exit(1)
    
    port = int(os.environ.get('PORT', 5555))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)