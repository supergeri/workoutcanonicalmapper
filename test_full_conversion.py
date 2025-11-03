#!/usr/bin/env python3
"""
Full test script for blocks JSON to Hyrox YAML conversion.
Tests the conversion and exercise mapping with suggestions.
"""
import json
import sys
from backend.adapters.blocks_to_hyrox_yaml import to_hyrox_yaml, map_exercise_to_garmin
from backend.core.exercise_suggestions import suggest_alternatives


def extract_all_exercises(blocks_json):
    """Extract all exercise names from blocks."""
    exercises = []
    for block in blocks_json.get("blocks", []):
        # From exercises array
        for ex in block.get("exercises", []):
            exercises.append(ex.get("name", ""))
        
        # From supersets
        for superset in block.get("supersets", []):
            for ex in superset.get("exercises", []):
                exercises.append(ex.get("name", ""))
    return exercises


def test_conversion(input_file):
    """Test the full conversion pipeline."""
    print("=" * 80)
    print("FULL CONVERSION TEST")
    print("=" * 80)
    print()
    
    # Load JSON
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    print(f"Title: {data.get('title', 'N/A')}")
    print(f"Source: {data.get('source', 'N/A')}")
    print()
    
    # Extract all exercises
    all_exercises = extract_all_exercises(data)
    print(f"Found {len(all_exercises)} exercises:")
    for ex in all_exercises:
        print(f"  - {ex}")
    print()
    
    # Test exercise mappings
    print("=" * 80)
    print("EXERCISE MAPPING RESULTS")
    print("=" * 80)
    print()
    
    unmapped = []
    for ex_name in all_exercises:
        if not ex_name:
            continue
            
        garmin_name, description = map_exercise_to_garmin(ex_name)
        
        # Check if mapping is good
        if garmin_name and len(garmin_name.split()) <= 2 and garmin_name.lower() in ['push', 'carry', 'squat']:
            # Generic match - might need suggestions
            suggestions = suggest_alternatives(ex_name, include_similar_types=True)
            if suggestions.get("needs_user_search") or (suggestions.get("best_match") and suggestions["best_match"]["score"] < 0.85):
                unmapped.append((ex_name, garmin_name, suggestions))
        
        status = "✓" if garmin_name and garmin_name not in ['Push', 'Carry', 'Squat', 'Plank', 'Burpee'] else "⚠"
        print(f"{status} {ex_name[:40]:40} → {garmin_name or 'None':30} | {description[:30]}")
    
    print()
    
    # Show unmapped exercises with suggestions
    if unmapped:
        print("=" * 80)
        print("EXERCISES NEEDING REVIEW (with suggestions)")
        print("=" * 80)
        print()
        
        for ex_name, current_map, suggestions in unmapped:
            print(f"Exercise: {ex_name}")
            print(f"  Current mapping: {current_map}")
            print(f"  Best match: {suggestions['best_match']['name'] if suggestions['best_match'] else 'None'} (score: {suggestions['best_match']['score']:.2f if suggestions['best_match'] else 0:.2f})")
            print(f"  Category: {suggestions['category']}")
            
            if suggestions['similar_exercises']:
                print(f"  Similar exercises ({len(suggestions['similar_exercises'])}):")
                for sim in suggestions['similar_exercises'][:5]:
                    print(f"    - {sim['name']} (score: {sim['score']:.2f})")
            
            if suggestions['exercises_by_type']:
                print(f"  Exercises by type ({len(suggestions['exercises_by_type'])}):")
                for ex in suggestions['exercises_by_type'][:5]:
                    print(f"    - {ex['name']} (score: {ex['score']:.2f})")
            
            if suggestions['needs_user_search']:
                print(f"  ⚠ Needs manual search in Garmin database")
            
            print()
    
    # Run full conversion
    print("=" * 80)
    print("FULL YAML OUTPUT")
    print("=" * 80)
    print()
    
    try:
        yaml_output = to_hyrox_yaml(data)
        print(yaml_output)
        
        # Save to file
        output_file = input_file.replace('.json', '_output.yaml')
        with open(output_file, 'w') as f:
            f.write(yaml_output)
        print()
        print(f"✓ Output saved to: {output_file}")
        
    except Exception as e:
        print(f"✗ Error during conversion: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "test_week7_full.json"
    sys.exit(test_conversion(input_file))

