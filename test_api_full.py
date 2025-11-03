#!/usr/bin/env python3
"""
Test the full API workflow with blocks JSON.
Tests both the conversion and the exercise suggestion API.
"""
import json
import requests
import sys

BASE_URL = "http://localhost:8000"


def test_exercise_suggestions(exercise_name):
    """Test the exercise suggestion endpoint."""
    response = requests.post(
        f"{BASE_URL}/exercise/suggest",
        json={
            "exercise_name": exercise_name,
            "include_similar_types": True
        }
    )
    return response.json()


def test_full_conversion(input_file):
    """Test the full blocks to YAML conversion via API."""
    print("=" * 80)
    print("API TEST - FULL CONVERSION WORKFLOW")
    print("=" * 80)
    print()
    
    # Load JSON
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    # Extract exercises
    exercises = []
    for block in data.get("blocks", []):
        for ex in block.get("exercises", []):
            exercises.append(ex.get("name", ""))
        for superset in block.get("supersets", []):
            for ex in superset.get("exercises", []):
                exercises.append(ex.get("name", ""))
    
    print(f"Found {len(exercises)} exercises to test")
    print()
    
    # Test each exercise with suggestion API
    print("=" * 80)
    print("TESTING EXERCISE SUGGESTIONS")
    print("=" * 80)
    print()
    
    problem_exercises = []
    
    for ex_name in exercises:
        if not ex_name:
            continue
        
        print(f"Testing: {ex_name}")
        try:
            suggestions = test_exercise_suggestions(ex_name)
            
            best_match = suggestions.get("best_match")
            if best_match:
                print(f"  ✓ Best match: {best_match['name']} (score: {best_match['score']:.2f})")
            else:
                print(f"  ✗ No match found")
            
            if suggestions.get("category"):
                print(f"  Category: {suggestions['category']}")
            
            similar_count = len(suggestions.get("similar_exercises", []))
            by_type_count = len(suggestions.get("exercises_by_type", []))
            
            if similar_count > 0:
                print(f"  Similar exercises: {similar_count} found")
                print(f"    Top 3: {[e['name'] for e in suggestions['similar_exercises'][:3]]}")
            
            if by_type_count > 0:
                print(f"  Exercises by type: {by_type_count} found")
                print(f"    Top 3: {[e['name'] for e in suggestions['exercises_by_type'][:3]]}")
            
            if suggestions.get("needs_user_search"):
                print(f"  ⚠ Needs manual search")
                problem_exercises.append((ex_name, suggestions))
            
            print()
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            print()
    
    if problem_exercises:
        print("=" * 80)
        print("EXERCISES NEEDING USER ATTENTION")
        print("=" * 80)
        print()
        
        for ex_name, suggestions in problem_exercises:
            print(f"Exercise: {ex_name}")
            if suggestions.get("similar_exercises"):
                print("  Suggested alternatives:")
                for alt in suggestions["similar_exercises"][:5]:
                    print(f"    - {alt['name']} (confidence: {alt['score']:.2f})")
            if suggestions.get("exercises_by_type"):
                print(f"  All {suggestions['category']} exercises:")
                for alt in suggestions["exercises_by_type"][:10]:
                    print(f"    - {alt['name']}")
            print()
    
    # Note: The blocks to YAML conversion would need a separate endpoint
    # For now, showing how to use the suggestion API
    print("=" * 80)
    print("NOTE: Use Python script for full conversion")
    print("=" * 80)
    print("Run: python test_full_conversion.py test_week7_full.json")
    print()


if __name__ == "__main__":
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=2)
        print(f"✓ Server is running at {BASE_URL}")
        print()
    except Exception as e:
        print(f"✗ Server not running at {BASE_URL}")
        print("Start server with: uvicorn backend.app:app --reload")
        sys.exit(1)
    
    input_file = sys.argv[1] if len(sys.argv) > 1 else "test_week7_full.json"
    test_full_conversion(input_file)

