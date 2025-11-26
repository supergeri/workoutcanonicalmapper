# Mapper API Tests

## Structure

```
tests/
├── unit/                   # Unit tests for individual components
│   ├── test_canonicalize.py
│   ├── test_catalog.py
│   ├── test_cir_to_garmin.py
│   ├── test_ingest_to_cir.py
│   ├── test_match.py
│   └── test_normalize.py
└── integration/            # Integration and API tests
    ├── test_api_full.py
    ├── test_api_blocks.sh
    ├── test_full_conversion.py
    ├── test_workflow_simple.py
    └── test_*.json         # Test data files
    └── test_*.yaml         # Test output files
```

## Running Tests

```bash
# Run all tests
pytest tests/

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run API tests
bash tests/integration/test_api_blocks.sh
python3 tests/integration/test_api_full.py

# Run with coverage
pytest tests/ --cov=backend --cov-report=html
```

## Test Data

Test JSON and YAML files in `tests/integration/` are used as:
- Input payloads for API tests
- Expected output comparisons
- Workflow test data





