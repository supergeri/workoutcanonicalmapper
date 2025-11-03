"""
Global exercise mapping popularity tracking.
Records what exercises users have chosen, creating a crowd-sourced mapping database.
Popular mappings are prioritized in auto-mapping.
"""
import yaml
import pathlib
from typing import Optional, Dict, List, Tuple
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
POPULARITY_FILE = ROOT / "shared/dictionaries/global_mappings.yaml"


def load_global_mappings() -> Dict[str, Dict[str, int]]:
    """
    Load global mapping popularity data.
    Returns: {normalized_exercise_name: {garmin_name: count}}
    """
    if not POPULARITY_FILE.exists():
        return {}
    
    try:
        with open(POPULARITY_FILE, 'r') as f:
            data = yaml.safe_load(f) or {}
            return data.get("popular_mappings", {})
    except Exception:
        return {}


def save_global_mappings(mappings: Dict[str, Dict[str, int]]):
    """Save global mapping popularity data."""
    POPULARITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "popular_mappings": mappings,
        "note": "Global exercise mapping popularity. Tracks how many users have chosen each mapping."
    }
    
    with open(POPULARITY_FILE, 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)


def record_mapping_choice(exercise_name: str, garmin_name: str):
    """
    Record that a user chose this mapping.
    Increments the popularity count for this exercise -> garmin_name mapping.
    """
    from backend.core.normalize import normalize
    
    normalized = normalize(exercise_name)
    mappings = load_global_mappings()
    
    if normalized not in mappings:
        mappings[normalized] = {}
    
    if garmin_name not in mappings[normalized]:
        mappings[normalized][garmin_name] = 0
    
    mappings[normalized][garmin_name] += 1
    save_global_mappings(mappings)


def get_popular_mappings(exercise_name: str, limit: int = 5) -> List[Tuple[str, int]]:
    """
    Get the most popular mappings for an exercise, sorted by popularity.
    Returns: [(garmin_name, count), ...] sorted by count (descending)
    """
    from backend.core.normalize import normalize
    
    normalized = normalize(exercise_name)
    mappings = load_global_mappings()
    
    if normalized not in mappings:
        return []
    
    popular = list(mappings[normalized].items())
    # Sort by count (descending), then by name (ascending) for consistency
    popular.sort(key=lambda x: (-x[1], x[0]))
    
    return popular[:limit]


def get_most_popular_mapping(exercise_name: str) -> Optional[Tuple[str, int]]:
    """
    Get the single most popular mapping for an exercise.
    Returns: (garmin_name, count) or None if no mappings exist
    """
    popular = get_popular_mappings(exercise_name, limit=1)
    return popular[0] if popular else None


def get_all_popular_mappings() -> Dict[str, Dict[str, int]]:
    """Get all global mapping popularity data."""
    return load_global_mappings()


def get_popularity_stats() -> Dict[str, any]:
    """
    Get statistics about global mappings.
    Returns summary of total mappings, unique exercises, etc.
    """
    mappings = load_global_mappings()
    
    total_choices = sum(sum(counts.values()) for counts in mappings.values())
    unique_exercises = len(mappings)
    unique_mappings = sum(len(counts) for counts in mappings.values())
    
    # Find most popular overall
    all_mappings_flat = []
    for exercise, choices in mappings.items():
        for garmin_name, count in choices.items():
            all_mappings_flat.append((exercise, garmin_name, count))
    
    most_popular = sorted(all_mappings_flat, key=lambda x: -x[2])[:10] if all_mappings_flat else []
    
    return {
        "total_choices": total_choices,
        "unique_exercises": unique_exercises,
        "unique_mappings": unique_mappings,
        "most_popular": [
            {"exercise": ex, "garmin_name": garmin, "count": count}
            for ex, garmin, count in most_popular
        ]
    }

