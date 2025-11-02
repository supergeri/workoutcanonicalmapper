"""
Garmin exercise name matcher using official Garmin exercise database.
"""
import pathlib
from rapidfuzz import fuzz, process
from .normalize import normalize

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Cache for loaded exercises
_GARMIN_EXERCISES = None


def load_garmin_exercises():
    """Load Garmin exercise names from file."""
    global _GARMIN_EXERCISES
    if _GARMIN_EXERCISES is None:
        exercises_file = ROOT / "shared/dictionaries/garmin_exercise_names.txt"
        if exercises_file.exists():
            with open(exercises_file, 'r') as f:
                _GARMIN_EXERCISES = [line.strip() for line in f if line.strip()]
        else:
            _GARMIN_EXERCISES = []
    return _GARMIN_EXERCISES


def find_garmin_exercise(raw_name: str, threshold: int = 80) -> tuple[str, float]:
    """
    Find best matching Garmin exercise name.
    Returns (garmin_name, score) or (None, 0) if no good match.
    """
    exercises = load_garmin_exercises()
    if not exercises:
        return None, 0.0
    
    # Normalize input
    normalized_input = normalize(raw_name)
    
    # First, try exact match (after normalization)
    for ex in exercises:
        if normalize(ex) == normalized_input:
            return ex, 1.0
    
    # Try partial exact match (input is substring of exercise name)
    # Prefer shorter matches for generic terms
    exact_matches = []
    for ex in exercises:
        ex_normalized = normalize(ex)
        if normalized_input in ex_normalized or ex_normalized in normalized_input:
            exact_matches.append((ex, len(ex)))
    
    if exact_matches:
        # Prefer exact match, then shorter names (more generic)
        exact_matches.sort(key=lambda x: (x[0].lower() != raw_name.lower(), len(x[0])))
        return exact_matches[0][0], 0.95
    
    # Use rapidfuzz for fuzzy matching
    # Get top matches to choose best one
    results = process.extract(
        normalized_input,
        [normalize(ex) for ex in exercises],
        scorer=fuzz.token_set_ratio,
        limit=5
    )
    
    if results:
        # Find the best match, preferring:
        # 1. Higher score
        # 2. Shorter names (for generic inputs)
        # 3. Exact word matches
        
        best_matches = []
        for matched_normalized, score, idx in results:
            if score < threshold:
                continue
            # Find original exercise name
            for ex in exercises:
                if normalize(ex) == matched_normalized:
                    # Score based on length similarity
                    length_penalty = abs(len(ex) - len(raw_name)) / max(len(ex), len(raw_name), 1)
                    adjusted_score = (score / 100.0) * (1 - length_penalty * 0.2)
                    best_matches.append((ex, adjusted_score, score / 100.0))
                    break
        
        if best_matches:
            # Sort by adjusted score, then by original length
            best_matches.sort(key=lambda x: (-x[1], len(x[0])))
            return best_matches[0][0], best_matches[0][2]
    
    return None, 0.0


def fuzzy_match_garmin(raw_name: str) -> str:
    """
    Fuzzy match to Garmin exercise name with fallback.
    Returns best matching Garmin name or None.
    
    For very generic/short names, require higher match quality.
    """
    # If name is very short/generic, require better matches
    if len(raw_name.split()) <= 1 and len(raw_name) <= 5:
        threshold = 85  # Require better match for single words
    else:
        threshold = 70
    
    garmin_name, score = find_garmin_exercise(raw_name, threshold=threshold)
    
    # For single-word matches, ensure it's a valid exercise name
    if garmin_name and len(raw_name.split()) == 1:
        # Check if the match is reasonable (not too different in length)
        if abs(len(garmin_name) - len(raw_name)) > len(raw_name) * 2:
            # Match seems too different, try again with higher threshold
            garmin_name2, score2 = find_garmin_exercise(raw_name, threshold=90)
            if score2 > score:
                return garmin_name2
    
    return garmin_name

