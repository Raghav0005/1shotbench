# NFCorpus Diagnostics Workbench - Playwright E2E Tests

## Testing Philosophy

These tests verify that the app uses **real Anserini-backed workflows** rather than mocked search results or hardcoded metrics. The tests are designed to fail if the app only displays static/hardcoded data without executing actual Anserini commands.

## Running the Tests

```bash
# Install dependencies
pip install playwright pytest

# Install browser
playwright install chromium

# Run tests (assumes app is running on port 10000)
pytest tests/test_e2e.py -v

# Or run with custom host
python -m pytest tests/test_e2e.py -v --base-url=http://localhost:10000
```

## Test Coverage

1. **Health Check**: App responds with proper JSON health status
2. **Status Panel**: All Anserini/NFCorpus status items are visible
3. **Dataset Identification**: NFCorpus is correctly identified as active dataset
4. **Live Search**: Real Anserini search returns ranked results
5. **Evaluation Metrics**: Observed metrics are displayed from actual evaluation
6. **Expected Metrics**: Expected metric info appears when available
7. **Observed vs Expected**: Comparison status/delta is shown
8. **Command Transparency**: Exact Anserini commands are visible
9. **Artifact Paths**: Run file paths and artifact locations are shown
10. **Docker/Render Contract**: PORT binding and deployment docs are verified