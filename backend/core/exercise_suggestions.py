"""
Exercise suggestion system for finding alternatives when mapping fails.
"""
from typing import List, Dict, Optional
from backend.core.garmin_matcher import load_garmin_exercises, find_garmin_exercise
from backend.core.normalize import normalize
from backend.core.global_mappings import get_popular_mappings
from rapidfuzz import fuzz, process
import re


def find_similar_exercises(exercise_name: str, limit: int = 10, min_score: int = 50) -> List[Dict]:
    """
    Find similar exercises from Garmin database.
    Returns list of exercises with scores and popularity counts.
    """
    exercises = load_garmin_exercises()
    if not exercises:
        return []
    
    normalized_input = normalize(exercise_name)
    
    # Get popularity data for this exercise
    popular_mappings = {garmin: count for garmin, count in get_popular_mappings(exercise_name, limit=50)}
    
    # Get top matches
    results = process.extract(
        normalized_input,
        [normalize(ex) for ex in exercises],
        scorer=fuzz.token_set_ratio,
        limit=limit * 2  # Get more to filter
    )
    
    suggestions = []
    seen_names = set()
    
    for matched_normalized, score, idx in results:
        if score < min_score:
            continue
            
        # Find original exercise name
        for ex in exercises:
            if normalize(ex) == matched_normalized and ex not in seen_names:
                popularity_count = popular_mappings.get(ex, 0)
                suggestions.append({
                    "name": ex,
                    "score": score / 100.0,
                    "normalized": matched_normalized,
                    "popularity": popularity_count,
                    "is_popular": popularity_count > 0
                })
                seen_names.add(ex)
                if len(suggestions) >= limit:
                    break
                break
    
    # Sort by popularity first (if any), then by score
    suggestions.sort(key=lambda x: (-x["popularity"], -x["score"]))
    
    return suggestions


def find_exercises_by_type(exercise_name: str, limit: int = 20) -> List[Dict]:
    """
    Find all exercises of the same type (e.g., all squats, all push-ups).
    Uses keyword matching to find exercises with similar movement patterns.
    Includes popularity counts.
    """
    exercises = load_garmin_exercises()
    if not exercises:
        return []
    
    normalized_input = normalize(exercise_name)
    
    # Get popularity data for this exercise
    popular_mappings = {garmin: count for garmin, count in get_popular_mappings(exercise_name, limit=100)}
    
    # Extract key movement words
    movement_keywords = [
        "squat", "press", "push", "pull", "row", "curl", "flye", "extension",
        "deadlift", "lunge", "plank", "crunch", "situp", "burpee", "jump",
        "swing", "carry", "drag", "pullup", "chinup", "dip", "raise", "shrug"
    ]
    
    # Find which keywords match
    matched_keywords = [kw for kw in movement_keywords if kw in normalized_input]
    
    if not matched_keywords:
        # Fallback: use the whole normalized input as keyword
        matched_keywords = [normalized_input]
    
    suggestions = []
    seen_names = set()
    
    for ex in exercises:
        ex_normalized = normalize(ex)
        
        # Check if exercise contains any of the matched keywords
        for keyword in matched_keywords:
            if keyword in ex_normalized:
                if ex not in seen_names:
                    # Calculate similarity score
                    score = fuzz.token_set_ratio(normalized_input, ex_normalized) / 100.0
                    popularity_count = popular_mappings.get(ex, 0)
                    suggestions.append({
                        "name": ex,
                        "score": score,
                        "normalized": ex_normalized,
                        "keyword": keyword,
                        "popularity": popularity_count,
                        "is_popular": popularity_count > 0
                    })
                    seen_names.add(ex)
                    break
        
        if len(suggestions) >= limit:
            break
    
    # Sort by popularity first (if any), then by score
    suggestions.sort(key=lambda x: (-x["popularity"], -x["score"]))
    
    return suggestions[:limit]


def categorize_exercise(exercise_name: str) -> Optional[str]:
    """
    Categorize exercise by movement pattern.
    Returns category name or None.
    Uses both original and normalized name to catch all variations.
    """
    # Use both original and normalized for better matching
    original_lower = exercise_name.lower()
    normalized = normalize(exercise_name).lower()
    combined = f"{original_lower} {normalized}"
    
    # Order matters - more specific first
    categories = [
        ("push_up", ["push up", "pushup", "push-up", "hand release push"]),
        ("squat", ["squat"]),
        ("lunge", ["lunge", "split"]),
        ("deadlift", ["deadlift", "rdl", "romanian deadlift"]),
        ("swing", ["swing"]),
        ("burpee", ["burpee"]),
        ("plank", ["plank"]),
        ("carry", ["carry", "farmers", "walk"]),
        ("drag", ["drag"]),
        ("press", ["press", "shoulder press", "bench press", "push press"]),
        ("pull", ["pull", "pullup", "chinup", "chin up", "pull down"]),
        ("row", ["row", "inverted row"]),
        ("curl", ["curl", "biceps curl"]),
        ("extension", ["extension", "triceps extension", "back extension"]),
        ("flye", ["flye", "fly"]),
        ("crunch", ["crunch", "situp", "sit up", "ab", "abdominal"]),
        ("raise", ["raise", "lateral raise"]),
    ]
    
    for category, keywords in categories:
        if any(kw in combined for kw in keywords):
            return category
    
    return None


def suggest_alternatives(exercise_name: str, include_similar_types: bool = True) -> Dict:
    """
    Get comprehensive suggestions for an exercise.
    Returns best match, similar exercises, and exercises of same type.
    Includes popularity information from crowd-sourced choices.
    """
    # Check if there's a popular choice
    from backend.core.global_mappings import get_most_popular_mapping
    popular_mapping = get_most_popular_mapping(exercise_name)
    
    # Try to find exact match first
    best_match, best_score = find_garmin_exercise(exercise_name, threshold=70)
    
    # If there's a popular choice, boost it as the best match if it's reasonably similar
    if popular_mapping:
        popular_name, popular_count = popular_mapping
        # If popular choice matches the fuzzy match, use it
        if best_match and normalize(best_match) == normalize(popular_name):
            # Popular choice matches fuzzy match - boost it
            best_match = popular_name
            best_score = max(best_score, 0.85)  # Boost confidence
        elif not best_match or best_score < 0.7:
            # No good fuzzy match, but we have a popular choice - use it
            best_match = popular_name
            best_score = min(0.85, 0.6 + (popular_count * 0.05))  # Scale confidence by popularity
    
    # Determine popularity for best match
    best_match_popularity = 0
    if popular_mapping and best_match:
        popular_name, popular_count = popular_mapping
        if normalize(best_match) == normalize(popular_name):
            best_match_popularity = popular_count
    
    result = {
        "input": exercise_name,
        "best_match": {
            "name": best_match,
            "score": best_score,
            "is_exact": best_score >= 0.9 if best_match else False,
            "popularity": best_match_popularity,
            "is_popular": best_match_popularity > 0
        } if best_match else None,
        "popular_choices": [{"name": garmin, "count": count} for garmin, count in get_popular_mappings(exercise_name, limit=5)],
        "similar_exercises": [],
        "exercises_by_type": [],
        "category": None,
        "needs_user_search": False
    }
    
    # Always get suggestions for user review, but prioritize if no good match
    category = categorize_exercise(exercise_name)
    result["category"] = category
    
    # Get similar exercises (always show alternatives)
    result["similar_exercises"] = find_similar_exercises(exercise_name, limit=10, min_score=50)
    
    # Get exercises by type if requested
    if include_similar_types and category:
        result["exercises_by_type"] = find_exercises_by_type(exercise_name, limit=15)
    
    # If no good match and no suggestions, flag for user search
    if not best_match or best_score < 0.7:
        if not result["similar_exercises"] and not result["exercises_by_type"]:
            result["needs_user_search"] = True
        elif best_score < 0.5:
            # Low confidence match - suggest user reviews alternatives
            result["needs_user_search"] = True
    
    return result

