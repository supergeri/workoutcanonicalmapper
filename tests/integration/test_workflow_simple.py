#!/usr/bin/env python3
"""Simple test of the workflow."""
import json
from pathlib import Path
from backend.adapters.blocks_to_hyrox_yaml import to_hyrox_yaml

# Resolve path relative to this test file
BASE_DIR = Path(__file__).parent

# Load input JSON correctly no matter where pytest is run
json_path = BASE_DIR / "test_week7_full.json"
with json_path.open() as f:
    data = json.load(f)

print("Testing blocks-to-hyrox conversion...")
result = to_hyrox_yaml(data)
print("✓ Conversion successful!")

print("\nOutput preview:")
print(result[:500])
print("\n... (truncated)")