"""
Exercise suggestion system for finding alternatives when mapping fails.
"""
from typing import List, Dict, Optional
from backend.core.garmin_matcher import load_garmin_exercises, find_garmin_exercise
from backend.core.normalize import normalize
from rapidfuzz import fuzz, process
import re


def find_similar_exercises(exercise_name: str, limit: int = 10, min_score: int = 50) -> List[Dict]:
    """
    Find similar exercises from Garmin database.
    Returns list of exercises with scores.
    """
    exercises = load_garmin_exercises()
    if not exercises:
        return []
    
    normalized_input = normalize(exercise_name)
    
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
                suggestions.append({
                    "name": ex,
                    "score": score / 100.0,
                    "normalized": matched_normalized
                })
                seen_names.add(ex)
                if len(suggestions) >= limit:
                    break
                break
    
    return suggestions


def find_exercises_by_type(exercise_name: str, limit: int = 20) -> List[Dict]:
    """
    Find all exercises of the same type (e.g., all squats, all push-ups).
    Uses keyword matching to find exercises with similar movement patterns.
    """
    exercises = load_garmin_exercises()
    if not exercises:
        return []
    
    normalized_input = normalize(exercise_name)
    
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
                    suggestions.append({
                        "name": ex,
                        "score": score,
                        "normalized": ex_normalized,
                        "keyword": keyword
                    })
                    seen_names.add(ex)
                    break
        
        if len(suggestions) >= limit:
            break
    
    # Sort by score
    suggestions.sort(key=lambda x: x["score"], reverse=True)
    
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
    """
    # Try to find exact match first
    best_match, best_score = find_garmin_exercise(exercise_name, threshold=70)
    
    result = {
        "input": exercise_name,
        "best_match": {
            "name": best_match,
            "score": best_score,
            "is_exact": best_score >= 0.9 if best_match else False
        } if best_match else None,
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

