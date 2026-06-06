"""
NFCorpus Live Retrieval Diagnostics Workbench - Playwright Configuration
"""

import os

# Test configuration
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:10000')
HEADLESS = True
TIMEOUT = 60000  # 60 seconds for evaluation runs

# Test files
TEST_DIR = os.path.dirname(__file__)