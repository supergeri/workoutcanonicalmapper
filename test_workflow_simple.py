#!/usr/bin/env python3
"""Simple test of the workflow."""
import json
from backend.adapters.blocks_to_hyrox_yaml import to_hyrox_yaml

# Quick test
with open('test_week7_full.json') as f:
    data = json.load(f)

print("Testing blocks-to-hyrox conversion...")
result = to_hyrox_yaml(data)
print("✓ Conversion successful!")
print("\nOutput preview:")
print(result[:500])
print("\n... (truncated)")

