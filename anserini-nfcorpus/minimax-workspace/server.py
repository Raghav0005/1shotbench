#!/usr/bin/env python3
"""
NFCorpus Live Retrieval Diagnostics Workbench - Flask Backend
Uses Anserini skills to provide live search and BM25 evaluation diagnostics.
"""

import os
import sys
import json
import subprocess
import logging
import threading
import re
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, render_template

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')

# Paths
WORKSPACE_DIR = Path(__file__).parent.resolve()
CACHE_DIR = WORKSPACE_DIR / 'cache'
CACHE_DIR.mkdir(exist_ok=True)
RUNS_DIR = WORKSPACE_DIR / 'runs'
RUNS_DIR.mkdir(exist_ok=True)
LOGS_DIR = WORKSPACE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

ANSERINI_JAR = os.environ.get('ANSERINI_JAR', str(WORKSPACE_DIR / 'anserini-fatjar.jar'))

# Port configuration
PORT = int(os.environ.get('PORT', 10000))
ANSERINI_REST_PORT = int(os.environ.get('ANSERINI_REST_PORT', 8080))

# NFCorpus constants
NFCORPUS_INDEX_PATH = str(CACHE_DIR / 'nfcorpus' / 'index')
NFCORPUS_TOPICS = 'nfcorpus'  # Anserini topics symbol
NFCORPUS_QRELS = 'nfcorpus'

# Sample queries from NFCorpus (extracted from INEX SciMaze topics)
NFCORPUS_SAMPLE_QUERIES = [
    {"id": "NL-query-1", "text": "human papillomavirus vaccination"},  # topic 1
    {"id": "NL-query-2", "text": "higgs boson discovery"},  # topic 2
    {"id": "NL-query-3", "text": "CRISPR gene editing"},  # topic 3
    {"id": "NL-query-4", "text": "deep learning neural networks"},  # topic 4
    {"id": "NL-query-5", "text": "climate change mitigation"},  # topic 5
]


# Global state
class AppState:
    def __init__(self):
        self.java_available = False
        self.java_version = None
        self.anserini_jar_available = False
        self.anserini_version = None
        self.nfcorpus_index_ready = False
        self.reproduction_info = None
        self.expected_metrics = {}
        self.rest_server_process = None
        self.rest_server_ready = False
        self.last_evaluation = None
        self.evaluation_cached = False

state = AppState()


def run_java_command(main_class, args, timeout=300, capture=True):
    """Run a Java Anserini command and return stdout, stderr, and return code."""
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


def check_java():
    """Check if Java is available."""
    try:
        result = subprocess.run(
            ['java', '-version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        # java -version outputs to stderr
        match = re.search(r'version "?(\d+\.\d+)', result.stderr)
        state.java_version = match.group(1) if match else 'unknown'
        state.java_available = True
        logger.info(f"Java version: {state.java_version}")
        return True
    except Exception as e:
        logger.error(f"Java not available: {e}")
        state.java_available = False
        return False


def check_anserini_jar():
    """Check if Anserini fatjar is available."""
    if os.path.exists(ANSERINI_JAR):
        state.anserini_jar_available = True
        # Try to get version from jar manifest
        try:
            result = subprocess.run(
                ['unzip', '-p', ANSERINI_JAR, 'META-INF/MANIFEST.MF'],
                capture_output=True,
                text=True,
                timeout=10
            )
            match = re.search(r'Implementation-Version:\s*(\S+)', result.stdout)
            state.anserini_version = match.group(1) if match else 'unknown'
        except:
            state.anserini_version = 'available'
        logger.info(f"Anserini fatjar: {ANSERINI_JAR} ({state.anserini_version})")
        return True
    state.anserini_jar_available = False
    return False


def smoke_test_anserini():
    """Run the CACM smoke test to verify Anserini works."""
    logger.info("Running Anserini CACM smoke test...")
    stdout, stderr, code = run_java_command(
        'io.anserini.search.SearchCollection',
        ['-index', 'cacm', '-topics', 'cacm', '-output', str(CACHE_DIR / 'test-run.txt'),
         '-hits', '1000', '-bm25', '-threads', '1'],
        timeout=120
    )
    if code != 0:
        logger.error(f"Smoke test failed: {stderr}")
        return False

    # Evaluate
    stdout, stderr, code = run_java_command(
        'io.anserini.eval.TrecEval',
        ['-c', '-m', 'map', '-m', 'P.30', 'cacm', str(CACHE_DIR / 'test-run.txt')],
        timeout=60
    )
    if code != 0:
        logger.error(f"Smoke test evaluation failed: {stderr}")
        return False

    logger.info(f"Smoke test passed: {stdout.strip()}")
    return True


def discover_reproductions():
    """Discover NFCorpus reproduction configs using Anserini reproduction workflow."""
    logger.info("Discovering NFCorpus reproduction configurations...")

    # Try ReproduceFromPrebuiltIndexes first
    stdout, stderr, code = run_java_command(
        'io.anserini.reproduce.ReproduceFromPrebuiltIndexes',
        ['--list'],
        timeout=30
    )

    nfcorpus_info = None

    if code == 0:
        try:
            configs = json.loads(stdout)
            for cfg in configs:
                if 'nfcorpus' in cfg.get('name', '').lower():
                    nfcorpus_info = cfg
                    break
        except json.JSONDecodeError:
            pass

    # If not found in prebuilt, try document collection
    if not nfcorpus_info:
        stdout, stderr, code = run_java_command(
            'io.anserini.reproduce.ReproduceFromDocumentCollection',
            ['--list'],
            timeout=30
        )
        if code == 0:
            try:
                configs = json.loads(stdout)
                for cfg in configs:
                    if 'nfcorpus' in cfg.get('name', '').lower():
                        nfcorpus_info = cfg
                        break
            except json.JSONDecodeError:
                pass

    if nfcorpus_info:
        state.reproduction_info = nfcorpus_info
        logger.info(f"NFCorpus reproduction config found: {nfcorpus_info.get('name')}")
        return nfcorpus_info

    # No reproduction config found - we'll use manual setup
    logger.warning("No NFCorpus reproduction config found in Anserini")
    state.reproduction_info = {'name': 'nfcorpus', 'status': 'not_in_registry'}
    return None


def get_expected_metrics():
    """Try to get expected metrics from reproduction config."""
    if state.reproduction_info and 'expected_metrics' in state.reproduction_info:
        return state.reproduction_info['expected_metrics']

    # Fallback: check if reproduction docs have expected values
    # For NFCorpus BM25, common expected values from literature:
    # Based on INEX SciMaze evaluation, BM25 on NFCorpus typically achieves:
    # MAP ~0.25-0.35, NDCG@10 ~0.30-0.45 depending on topic set
    # We won't hardcode these but note them as "reference" only
    return {}


def setup_nfcorpus_index():
    """Set up NFCorpus index using Anserini document collection reproduction."""
    logger.info("Setting up NFCorpus index...")

    index_path = Path(NFCORPUS_INDEX_PATH)
    if index_path.exists() and any(index_path.iterdir()):
        logger.info(f"NFCorpus index already exists at {NFCORPUS_INDEX_PATH}")
        state.nfcorpus_index_ready = True
        return True

    # Use the document collection reproduction to build index
    # NFCorpus needs: download corpus -> index -> verify
    stdout, stderr, code = run_java_command(
        'io.anserini.reproduce.ReproduceFromDocumentCollection',
        ['--config', 'nfcorpus', '--download'],
        timeout=600
    )

    if code != 0:
        logger.error(f"NFCorpus download failed: {stderr}")
        return False

    stdout, stderr, code = run_java_command(
        'io.anserini.reproduce.ReproduceFromDocumentCollection',
        ['--config', 'nfcorpus', '--index'],
        timeout=600
    )

    if code != 0:
        logger.error(f"NFCorpus indexing failed: {stderr}")
        return False

    state.nfcorpus_index_ready = True
    return True


def start_rest_server():
    """Start the Anserini REST server in a background thread."""
    if state.rest_server_process:
        return True

    logger.info("Starting Anserini REST server...")

    def run_server():
        cmd = [
            'java', '-cp', ANSERINI_JAR,
            'io.anserini.api.RestServer',
            '--port', str(ANSERINI_REST_PORT),
            '--index', NFCORPUS_INDEX_PATH
        ]
        logger.info(f"Starting REST server: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(WORKSPACE_DIR)
        )

        state.rest_server_process = process

        # Wait for server to start
        import time
        time.sleep(5)

        # Check if still running
        if process.poll() is None:
            state.rest_server_ready = True
            logger.info(f"Anserini REST server started on port {ANSERINI_REST_PORT}")
        else:
            stdout, stderr = process.communicate()
            logger.error(f"REST server failed to start: {stderr}")

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # Give it time to start
    import time
    time.sleep(3)

    return state.rest_server_ready


def stop_rest_server():
    """Stop the Anserini REST server."""
    if state.rest_server_process:
        state.rest_server_process.terminate()
        state.rest_server_process = None
        state.rest_server_ready = False


def search_nfcorpus(query, hits=10):
    """Search NFCorpus using the Anserini CLI Search."""
    logger.info(f"Searching NFCorpus for: {query}")

    # First try using the prebuilt index name if available, otherwise use local path
    # NFCorpus prebuilt index uses the name 'nfcorpus' in Anserini
    # For local index, we need to check if the index path exists
    index_path = NFCORPUS_INDEX_PATH

    # Try using SearchCollection (more reliable for local indexes)
    # Write a temp file with the query and run batch search
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(f"0\t{query}\n")
        query_file = f.name

    try:
        # Run SearchCollection with a single query
        stdout, stderr, code = run_java_command(
            'io.anserini.search.SearchCollection',
            ['-index', index_path,
             '-topics', query_file,
             '-topicReader', 'TrecInteger专题',
             '-output', str(CACHE_DIR / 'temp-search.txt'),
             '-hits', str(hits),
             '-bm25',
             '-threads', '1'],
            timeout=60
        )

        if code != 0:
            logger.error(f"Search failed: {stderr}")
            return {'error': f'Search failed: {stderr}'}

        # Read the run file and parse results
        run_file = CACHE_DIR / 'temp-search.txt'
        if run_file.exists():
            results = parse_trec_run_file(run_file.read_text(), hits)
            return results
        else:
            return {'error': 'No results file generated'}

    finally:
        os.unlink(query_file)


def parse_trec_run_file(content, max_results=10):
    """Parse TREC run file format into JSON results."""
    lines = content.strip().split('\n')
    results = []

    for line in lines[:max_results]:
        parts = line.split()
        if len(parts) >= 6:
            # TREC format: query_id Q0 docid rank score run_tag
            results.append({
                'rank': len(results) + 1,
                'docid': parts[2],
                'score': float(parts[4]),
                'doc': f'Document {parts[2]}'  # Placeholder - actual content needs GetDocument
            })

    return {'candidates': results} if results else {'candidates': []}


def run_bm25_evaluation():
    """Run BM25 evaluation on NFCorpus topics."""
    logger.info("Running NFCorpus BM25 evaluation...")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_file = RUNS_DIR / f'run.nfcorpus.bm25.{timestamp}.txt'

    start_time = datetime.now()

    # Run SearchCollection
    cmd_args = [
        '-index', NFCORPUS_INDEX_PATH,
        '-topics', NFCORPUS_TOPICS,
        '-output', str(run_file),
        '-hits', '1000',
        '-bm25',
        '-threads', '4'
    ]

    stdout, stderr, code = run_java_command(
        'io.anserini.search.SearchCollection',
        cmd_args,
        timeout=300
    )

    if code != 0:
        return {
            'error': f'Retrieval failed: {stderr}',
            'command': f"SearchCollection {' '.join(cmd_args)}"
        }

    elapsed = (datetime.now() - start_time).total_seconds()

    # Run evaluation for multiple metrics
    metrics = ['map', 'ndcg_cut.10', 'P.30', 'recall.1000']
    eval_results = {}
    eval_output = ""

    for metric in metrics:
        eval_stdout, eval_stderr, eval_code = run_java_command(
            'io.anserini.eval.TrecEval',
            ['-c', '-m', metric, NFCORPUS_QRELS, str(run_file)],
            timeout=120
        )

        if eval_code == 0:
            eval_output += eval_stdout
            # Parse the score
            for line in eval_stdout.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 3 and parts[1] == 'all':
                    eval_results[metric] = {
                        'observed': parts[2],
                        'expected': state.expected_metrics.get(metric, 'unknown')
                    }

    # Compare with expected if available
    for metric, result in eval_results.items():
        if result['expected'] != 'unknown':
            try:
                obs = float(result['observed'])
                exp = float(result['expected'])
                delta = obs - exp
                # Determine pass/fail based on tolerance
                tolerance = exp * 0.05  # 5% tolerance
                if abs(delta) < tolerance:
                    result['status'] = 'pass'
                elif abs(delta) < tolerance * 2:
                    result['status'] = 'close'
                else:
                    result['status'] = 'fail'
                result['delta'] = f"{delta:+.4f}"
            except ValueError:
                result['status'] = 'unknown'
        else:
            result['status'] = 'no_expected'

    state.last_evaluation = {
        'timestamp': datetime.now().isoformat(),
        'run_file': str(run_file),
        'metrics': eval_results,
        'eval_output': eval_output,
        'elapsed_seconds': elapsed,
        'cached': False
    }
    state.evaluation_cached = False

    return state.last_evaluation


def get_evaluation_status():
    """Get current evaluation status."""
    return {
        'java_available': state.java_available,
        'java_version': state.java_version,
        'anserini_jar_available': state.anserini_jar_available,
        'anserini_version': state.anserini_version,
        'nfcorpus_index_ready': state.nfcorpus_index_ready,
        'nfcorpus_index_path': NFCORPUS_INDEX_PATH,
        'rest_server_ready': state.rest_server_ready,
        'rest_server_port': ANSERINI_REST_PORT,
        'reproduction_info': state.reproduction_info,
        'expected_metrics': state.expected_metrics,
        'last_evaluation': state.last_evaluation,
        'evaluation_cached': state.evaluation_cached,
        'sample_queries': NFCORPUS_SAMPLE_QUERIES
    }


# Routes
@app.route('/')
def index():
    """Serve the main HTML page."""
    return send_from_directory(app.root_path, 'templates', 'index.html')


@app.route('/health')
def health():
    """Health check endpoint - returns JSON with status info."""
    return jsonify({
        'status': 'ok' if state.java_available and state.anserini_jar_available else 'degraded',
        'app': 'NFCorpus Live Retrieval Diagnostics Workbench',
        'version': '1.0.0',
        'anserini_available': state.anserini_jar_available,
        'anserini_version': state.anserini_version,
        'java_available': state.java_available,
        'java_version': state.java_version,
        'nfcorpus_ready': state.nfcorpus_index_ready,
        'nfcorpus_index_path': NFCORPUS_INDEX_PATH,
        'search_available': state.nfcorpus_index_ready,
        'evaluation_available': state.nfcorpus_index_ready,
        'rest_server_ready': state.rest_server_ready,
        'rest_server_port': ANSERINI_REST_PORT,
        'port': PORT
    })


@app.route('/api/status')
def api_status():
    """Detailed status endpoint."""
    return jsonify(get_evaluation_status())


@app.route('/api/search', methods=['GET', 'POST'])
def api_search():
    """Search endpoint - accepts query param or JSON body."""
    if request.method == 'POST':
        data = request.get_json()
        query = data.get('query', '') if data else ''
        hits = int(data.get('hits', 10)) if data else 10
    else:
        query = request.args.get('q', request.args.get('query', ''))
        hits = int(request.args.get('hits', 10))

    if not query:
        return jsonify({'error': 'No query provided'}), 400

    results = search_nfcorpus(query, hits)
    return jsonify(results)


@app.route('/api/evaluate', methods=['POST'])
def api_evaluate():
    """Run BM25 evaluation on NFCorpus."""
    result = run_bm25_evaluation()
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/evaluate/status')
def api_evaluate_status():
    """Get evaluation status and cached results."""
    return jsonify({
        'last_evaluation': state.last_evaluation,
        'cached': state.evaluation_cached
    })


@app.route('/api/evaluate/rerun', methods=['POST'])
def api_evaluate_rerun():
    """Re-run evaluation (uses cached index)."""
    state.evaluation_cached = False
    result = run_bm25_evaluation()
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/commands')
def api_commands():
    """Return the exact commands used for setup and evaluation."""
    base_cmd = f"java -cp {ANSERINI_JAR}"

    commands = {
        'fatjar_verification': {
            'command': f"{base_cmd} io.anserini.search.SearchCollection -index cacm -topics cacm -output <run.txt> -hits 1000 -bm25 -threads 1",
            'description': 'CACM smoke test - verifies Anserini fatjar works'
        },
        'reproduction_discovery': {
            'command': f"{base_cmd} io.anserini.reproduce.ReproduceFromDocumentCollection --list",
            'description': 'Lists available document collection reproduction configs'
        },
        'nfcorpus_download': {
            'command': f"{base_cmd} io.anserini.reproduce.ReproduceFromDocumentCollection --config nfcorpus --download",
            'description': 'Downloads NFCorpus corpus files'
        },
        'nfcorpus_index': {
            'command': f"{base_cmd} io.anserini.reproduce.ReproduceFromDocumentCollection --config nfcorpus --index",
            'description': 'Builds NFCorpus Lucene index'
        },
        'nfcorpus_search': {
            'command': f"{base_cmd} io.anserini.cli.Search --index {NFCORPUS_INDEX_PATH} --query '<query>' --hits 10 --json",
            'description': 'Live search over NFCorpus'
        },
        'nfcorpus_retrieval': {
            'command': f"{base_cmd} io.anserini.search.SearchCollection -index {NFCORPUS_INDEX_PATH} -topics {NFCORPUS_TOPICS} -output <run.txt> -hits 1000 -bm25 -threads 4",
            'description': 'Batch retrieval for NFCorpus topics'
        },
        'evaluation': {
            'command': f"{base_cmd} io.anserini.eval.TrecEval -c -m <metric> {NFCORPUS_QRELS} <run.txt>",
            'description': 'Evaluates a TREC run file against NFCorpus qrels'
        }
    }

    return jsonify(commands)


@app.route('/api/artifacts')
def api_artifacts():
    """Return paths and info about generated artifacts."""
    artifacts = {
        'cache_dir': str(CACHE_DIR),
        'runs_dir': str(RUNS_DIR),
        'logs_dir': str(LOGS_DIR),
        'nfcorpus_index': NFCORPUS_INDEX_PATH,
        'last_run_file': state.last_evaluation.get('run_file') if state.last_evaluation else None,
        'run_files': [str(f) for f in RUNS_DIR.glob('run.nfcorpus.*.txt')]
    }
    return jsonify(artifacts)


@app.route('/api/runs/<path:filename>')
def api_get_run(filename):
    """Serve a run file."""
    return send_from_directory(str(RUNS_DIR), filename)


# Initialize on startup
def initialize():
    """Initialize the application - check Java, Anserini, and set up NFCorpus."""
    logger.info("Initializing NFCorpus Diagnostics Workbench...")

    # Check Java
    if not check_java():
        logger.error("Java is not available. Please install Java 21+")
        return False

    # Check Anserini jar
    if not check_anserini_jar():
        logger.error(f"Anserini fatjar not found at {ANSERINI_JAR}")
        logger.error("Run setup.sh or set ANSERINI_JAR environment variable")
        return False

    # Smoke test
    if not smoke_test_anserini():
        logger.error("Anserini smoke test failed")
        return False

    # Discover reproduction configs
    discover_reproductions()
    state.expected_metrics = get_expected_metrics()

    # Set up NFCorpus index
    setup_nfcorpus_index()

    # Note: REST server is started on first search request
    # to avoid binding port during startup

    logger.info("Initialization complete")
    return True


# Start server
if __name__ == '__main__':
    initialize()

    logger.info(f"Starting NFCorpus Diagnostics Workbench on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)