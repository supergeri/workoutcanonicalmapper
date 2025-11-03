"""
User-defined exercise mappings storage.
Remembers user selections for future automatic mapping.
"""
import yaml
import pathlib
from typing import Optional, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAPPINGS_FILE = ROOT / "shared/dictionaries/user_mappings.yaml"


def load_user_mappings() -> Dict[str, str]:
    """Load user-defined mappings from file."""
    if not MAPPINGS_FILE.exists():
        return {}
    
    try:
        with open(MAPPINGS_FILE, 'r') as f:
            data = yaml.safe_load(f) or {}
            return data.get("mappings", {})
    except Exception:
        return {}


def save_user_mappings(mappings: Dict[str, str]):
    """Save user-defined mappings to file."""
    MAPPINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "mappings": mappings,
        "note": "User-defined exercise mappings. Format: normalized_exercise_name -> garmin_exercise_name"
    }
    
    with open(MAPPINGS_FILE, 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)


def add_user_mapping(exercise_name: str, garmin_name: str):
    """
    Add or update a user mapping.
    Stores normalized exercise name -> Garmin exercise name.
    """
    from backend.core.normalize import normalize
    
    normalized = normalize(exercise_name)
    mappings = load_user_mappings()
    mappings[normalized] = garmin_name
    save_user_mappings(mappings)
    
    return {"normalized": normalized, "garmin_name": garmin_name}


def remove_user_mapping(exercise_name: str) -> bool:
    """Remove a user mapping."""
    from backend.core.normalize import normalize
    
    normalized = normalize(exercise_name)
    mappings = load_user_mappings()
    
    if normalized in mappings:
        del mappings[normalized]
        save_user_mappings(mappings)
        return True
    
    return False


def get_user_mapping(exercise_name: str) -> Optional[str]:
    """
    Get user mapping for an exercise name.
    Returns Garmin exercise name if mapping exists, None otherwise.
    """
    from backend.core.normalize import normalize
    
    normalized = normalize(exercise_name)
    mappings = load_user_mappings()
    return mappings.get(normalized)


def get_all_user_mappings() -> Dict[str, str]:
    """Get all user mappings."""
    return load_user_mappings()


def clear_all_user_mappings():
    """Clear all user mappings."""
    save_user_mappings({})

