"""
Fetch Garmin exercise data from their public API endpoints.
Based on: https://github.com/maximecharriere/GarminExercisesCollector
"""
import json
import requests
import yaml
from pathlib import Path


ROOT = Path(__file__).parents[1]

# Garmin exercise data URLs
EXERCISES_URL = "https://connect.garmin.com/web-data/exercises/Exercises.json"
EXERCISE_TYPES_URL = "https://connect.garmin.com/web-data/exercises/exercise_types.properties"


def fetch_exercises():
    """Fetch exercises from Garmin's API."""
    print("Fetching Garmin exercises...")
    try:
        response = requests.get(EXERCISES_URL, timeout=10)
        response.raise_for_status()
        exercises = response.json()
        print(f"Fetched {len(exercises)} exercises")
        return exercises
    except Exception as e:
        print(f"Error fetching exercises: {e}")
        return None


def fetch_exercise_types():
    """Fetch exercise type translations."""
    print("Fetching exercise types...")
    try:
        response = requests.get(EXERCISE_TYPES_URL, timeout=10)
        response.raise_for_status()
        # Parse properties file
        types_dict = {}
        for line in response.text.split('\n'):
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.split('=', 1)
                types_dict[key.strip()] = value.strip()
        print(f"Fetched {len(types_dict)} exercise types")
        return types_dict
    except Exception as e:
        print(f"Error fetching exercise types: {e}")
        return {}


def normalize_exercise_name(name: str) -> str:
    """Normalize exercise name for matching."""
    import re
    # Remove special characters, lowercase
    name = re.sub(r'[^\w\s-]', '', name.lower())
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def build_mapping_dictionary(exercises_data, output_file=None):
    """Build a mapping dictionary from Garmin exercises."""
    if not exercises_data:
        print("No exercises to process")
        return {}
    
    # Group by normalized name patterns
    mapping = {}
    exercise_names = []
    
    # Handle nested structure: {categories: {CATEGORY: {exercises: {NAME: {...}}}}}
    if isinstance(exercises_data, dict) and 'categories' in exercises_data:
        categories = exercises_data['categories']
        for category_name, category_data in categories.items():
            if isinstance(category_data, dict) and 'exercises' in category_data:
                exercises = category_data['exercises']
                for ex_key, ex_data in exercises.items():
                    # Exercise key is like "AB_TWIST", convert to readable name
                    ex_name = ex_key.replace('_', ' ').title()
                    
                    exercise_names.append(ex_name)
                    
                    # Create normalized key for matching
                    normalized = normalize_exercise_name(ex_name)
                    
                    # Store mapping
                    if normalized not in mapping:
                        mapping[normalized] = {
                            'name': ex_name,
                            'key': ex_key,
                            'category': category_name.replace('_', ' ').title(),
                            'data': ex_data
                        }
    elif isinstance(exercises_data, list):
        # Handle list structure
        for ex in exercises_data:
            if isinstance(ex, dict):
                name = ex.get('name') or ex.get('exerciseName') or ''
                if name:
                    normalized = normalize_exercise_name(name)
                    mapping[normalized] = {
                        'name': name,
                        'category': ex.get('category', ''),
                        'data': ex
                    }
                    exercise_names.append(name)
    
    print(f"Built mapping with {len(mapping)} unique exercise patterns")
    
    if output_file:
        # Save to YAML
        output_path = ROOT / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Format for our use case - create a searchable mapping
        garmin_mapping = {}
        for norm, data in sorted(mapping.items()):
            garmin_mapping[norm] = {
                'name': data['name'],
                'category': data.get('category', 'Unknown')
            }
        
        with open(output_path, 'w') as f:
            yaml.dump(garmin_mapping, f, sort_keys=True, default_flow_style=False)
        print(f"Saved mapping to {output_path}")
    
    return mapping


def main():
    """Main function."""
    exercises = fetch_exercises()
    if exercises:
        mapping = build_mapping_dictionary(
            exercises, 
            output_file="shared/dictionaries/garmin_exercises_raw.yaml"
        )
        
        # Save simple list
        list_path = ROOT / "shared/dictionaries/garmin_exercise_names.txt"
        # Extract names from mapping
        names = [data['name'] for data in mapping.values()]
        with open(list_path, 'w') as f:
            f.write('\n'.join(sorted(set(names))))
        print(f"Saved {len(set(names))} unique exercise names to {list_path}")
    
    types = fetch_exercise_types()
    if types:
        types_path = ROOT / "shared/dictionaries/garmin_exercise_types.yaml"
        with open(types_path, 'w') as f:
            yaml.dump(types, f, sort_keys=True)
        print(f"Saved exercise types to {types_path}")


if __name__ == "__main__":
    main()

