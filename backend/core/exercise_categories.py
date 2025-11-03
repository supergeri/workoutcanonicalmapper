"""
Exercise category detection and mapping for Garmin workouts.
"""
from backend.core.normalize import normalize


def detect_exercise_category(exercise_name: str) -> str:
    """
    Automatically detect exercise category based on exercise name.
    Returns category name or None if not detected.
    """
    normalized = normalize(exercise_name).lower()
    
    # Category detection rules (in order of specificity - most specific first)
    # Based on the Strength Workout Guide categories
    category_rules = [
        # Most specific exercises first
        ("bulgarian split squat", "LUNGE"),
        ("good morning", "LEG_CURL"),
        ("clean and jerk", "OLYMPIC_LIFT"),
        ("medicine ball slam", "PLYO"),
        ("ski moguls", "CARDIO"),
        ("pike push", "PUSH_UP"),
        ("pike push-up", "PUSH_UP"),
        ("pike pushup", "PUSH_UP"),
        ("plank", "PLANK"),
        ("burpee", "TOTAL_BODY"),
        ("inverted row", "ROW"),
        ("trx inverted row", "ROW"),
        ("trx row", "ROW"),
        ("kettlebell floor to shelf", "DEADLIFT"),
        ("kettlebell swing", "HIP_SWING"),
        ("single arm kettlebell swing", "HIP_SWING"),
        ("push up", "PUSH_UP"),
        ("push-up", "PUSH_UP"),
        ("pushup", "PUSH_UP"),
        ("hand release push up", "PUSH_UP"),
        ("hand release push-up", "PUSH_UP"),
        ("sled push", "SLED"),
        ("sled drag", "SLED"),
        ("backward drag", "SLED"),
        ("forward drag", "SLED"),
        ("sled", "SLED"),
        ("farmer carry", "CARRY"),
        ("farmer's carry", "CARRY"),
        ("farmers carry", "CARRY"),
        ("carry", "CARRY"),
        
        # Pattern-based detection (order matters - more specific first)
        ("squat", "SQUAT"),
        ("push press", "SHOULDER_PRESS"),  # Before generic "press"
        ("press", "BENCH_PRESS"),
        ("deadlift", "DEADLIFT"),
        ("rdl", "DEADLIFT"),
        ("romanian deadlift", "DEADLIFT"),
        ("lat", "PULL_UP"),
        ("pull", "PULL_UP"),
        ("row", "ROW"),
        ("lunge", "LUNGE"),
        ("swing", "HIP_SWING"),  # Generic swing -> HIP_SWING
        ("drag", "SLED"),  # Generic drag -> SLED
        ("ski", "CARDIO"),
        ("push", "BENCH_PRESS"),  # Generic push (fallback after specific checks)
    ]
    
    # Check rules (most specific first)
    for pattern, category in category_rules:
        if pattern in normalized:
            return category
    
    # Default fallback
    return None


def add_category_to_exercise_name(exercise_name: str, category: str = None) -> str:
    """
    Add category to exercise name in Garmin format.
    Format: "Exercise Name [category: CATEGORY]"
    """
    if not category:
        category = detect_exercise_category(exercise_name)
    
    if category:
        return f"{exercise_name} [category: {category}]"
    else:
        return exercise_name

