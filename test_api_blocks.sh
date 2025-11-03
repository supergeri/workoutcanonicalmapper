#!/bin/bash
# Quick test script for blocks-to-hyrox API

SERVER="http://localhost:8000"

echo "Testing Blocks-to-Hyrox API"
echo "============================"
echo ""

# Test direct conversion
echo "1. Testing POST /map/blocks-to-hyrox"
echo "------------------------------------"
curl -s -X POST "${SERVER}/map/blocks-to-hyrox" \
  -H "Content-Type: application/json" \
  -d @- << 'EOF' | python3 -m json.tool | head -30
{
  "blocks_json": {
    "title": "Test Workout",
    "blocks": [
      {
        "label": "Test",
        "structure": "3 rounds",
        "exercises": [],
        "supersets": [
          {
            "exercises": [
              {
                "name": "A1: GOODMORNINGS X10",
                "sets": 3,
                "reps": 10,
                "type": "strength"
              }
            ]
          }
        ]
      }
    ]
  }
}
EOF

echo ""
echo ""
echo "2. Test with your full JSON file:"
echo "------------------------------------"
echo "curl -X POST \"${SERVER}/map/blocks-to-hyrox\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"blocks_json\": '$(cat test_week7_full.json | jq -c .)'}'"

