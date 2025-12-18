from typing import Iterable, Tuple, Optional, Dict, List
import re

from rapidfuzz import fuzz, process


def normalize_name(name: str) -> str:
    """
    Normalize exercise names for better fuzzy matching.

    - lowercase
    - strip whitespace
    - replace hyphens/underscores with spaces
    - remove non-alphanumeric characters (keep spaces)
    - collapse multiple spaces
    """
    if not name:
        return ""
    s = name.lower().strip()

    # common short aliases → expanded forms
    replacements = {
        "db ": "dumbbell ",
        "bb ": "barbell ",
        "wb ": "wall ball ",
        "kb ": "kettlebell ",
        "oh ": "overhead ",
        "ohp": "overhead press",
        "pu ": "push up ",
        "pressup": "push up",
    }
    for short, long in replacements.items():
        s = s.replace(short, long)

    s = s.replace("-", " ").replace("_", " ")

    # keep alnum and spaces
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Comprehensive alias map for common exercise name variations
# Maps normalized names to canonical Garmin exercise names
ALIAS_MAP: Dict[str, str] = {
    # Push exercises
    "pushups": "push up",
    "push up": "push up",
    "push ups": "push up",
    "pressup": "push up",
    "pressups": "push up",
    "press up": "push up",
    "press ups": "push up",

    # Bench press variations
    "bench press": "barbell bench press",
    "bench": "barbell bench press",
    "flat bench press": "barbell bench press",
    "flat bench": "barbell bench press",
    "incline bench": "incline barbell bench press",
    "incline press": "incline barbell bench press",
    "decline bench": "decline barbell bench press",
    "decline press": "decline barbell bench press",
    "dumbbell bench": "dumbbell bench press",

    # Squats
    "squat": "barbell back squat",
    "squats": "barbell back squat",
    "back squat": "barbell back squat",
    "back squats": "barbell back squat",
    "front squat": "barbell front squat",
    "front squats": "barbell front squat",
    "air squat": "air squat",
    "bodyweight squat": "air squat",

    # Deadlifts
    "deadlift": "barbell deadlift",
    "deadlifts": "barbell deadlift",
    "conventional deadlift": "barbell deadlift",
    "rdl": "romanian deadlift",
    "romanian dl": "romanian deadlift",
    "stiff leg deadlift": "romanian deadlift",
    "sldl": "romanian deadlift",

    # Overhead press
    "shoulder press": "barbell overhead press",
    "military press": "barbell overhead press",
    "strict press": "barbell overhead press",
    "standing press": "barbell overhead press",
    "dumbbell shoulder press": "dumbbell overhead press",

    # Rows
    "row": "barbell row",
    "rows": "barbell row",
    "bent over row": "barbell row",
    "pendlay row": "barbell row",
    "one arm row": "dumbbell row",
    "seated row": "cable row",

    # Pull exercises
    "pullup": "pull up",
    "pullups": "pull up",
    "pull ups": "pull up",
    "chin up": "chin up",
    "chin ups": "chin up",
    "chinup": "chin up",
    "chinups": "chin up",
    "pulldown": "lat pulldown",
    "pull down": "lat pulldown",

    # Hip thrust
    "hip thrusts": "hip thrust",
    "glute bridge": "glute bridge",
    "bridge": "glute bridge",

    # Curls
    "bicep curls": "bicep curl",
    "curl": "bicep curl",
    "curls": "bicep curl",
    "dumbbell curls": "dumbbell bicep curl",
    "alt db curl": "alternating dumbbell curl",
    "alt db curls": "alternating dumbbell curl",
    "alternating curl": "alternating dumbbell curl",
    "hammer curls": "hammer curl",
    "preacher curl": "preacher curl",

    # Triceps
    "tricep extensions": "tricep extension",
    "skull crushers": "skull crusher",
    "pushdown": "tricep pushdown",
    "rope pushdown": "tricep pushdown",
    "dips": "dip",
    "bench dips": "bench dip",

    # Lunges
    "lunges": "lunge",
    "walking lunges": "walking lunge",
    "reverse lunges": "reverse lunge",
    "bulgarian split squat": "bulgarian split squat",
    "bss": "bulgarian split squat",

    # Core
    "planks": "plank",
    "side plank": "side plank",
    "crunches": "crunch",
    "sit ups": "sit up",
    "situp": "sit up",
    "situps": "sit up",
    "leg raises": "leg raise",
    "russian twists": "russian twist",
    "ab rollout": "ab wheel rollout",

    # CrossFit / Functional
    "wall balls": "wall ball",
    "burpees": "burpee",
    "box jumps": "box jump",
    "kettlebell swings": "kettlebell swing",
    "thrusters": "thruster",
    "power clean": "power clean",
    "hang clean": "hang clean",
    "muscle ups": "muscle up",
    "toes to bar": "toes to bar",
    "t2b": "toes to bar",
    "ttb": "toes to bar",
    "knees to elbow": "knees to elbow",
    "k2e": "knees to elbow",
    "double unders": "double under",
    "du": "double under",
    "dus": "double under",

    # Cardio
    "run": "running",
    "jog": "running",
    "jogging": "running",
    "sprint": "running",
    "rowing": "rowing",
    "bike": "cycling",
    "assault bike": "assault bike",
    "airdyne": "assault bike",
    "skierg": "ski erg",
    "jump rope": "jump rope",
    "skipping": "jump rope",

    # Stretching
    "stretch": "stretching",
    "foam roll": "foam rolling",
}


def best_match(
    query: str, choices: Iterable[str]
) -> Tuple[Optional[str], float]:
    """
    Return (best_choice, confidence) for a given exercise name against a list
    of device exercise names.

    confidence is 0-1.
    """
    if not query:
        return None, 0.0

    normalized_query = normalize_name(query)
    if not normalized_query:
        return None, 0.0

    # alias: if normalized_query directly maps to a known alias within the
    # device's names, try that first
    alias_target = ALIAS_MAP.get(normalized_query)
    if alias_target and alias_target in choices:
        return alias_target, 1.0

    # Build a list of (original_name, normalized_name)
    norm_choices = [(c, normalize_name(c)) for c in choices]

    # Use rapidfuzz token_set_ratio on normalized tokens
    best_choice = None
    best_score = -1.0

    for original, norm in norm_choices:
        if not norm:
            continue
        score = fuzz.token_set_ratio(normalized_query, norm)
        if score > best_score:
            best_score = score
            best_choice = original

    if best_choice is None:
        return None, 0.0

    # map 0-100 → 0-1
    return best_choice, best_score / 100.0


def top_matches(
    query: str,
    choices: Iterable[str],
    limit: int = 5,
    score_cutoff: float = 0.3,
) -> List[Tuple[str, float]]:
    """
    Return a list of (choice, confidence) sorted by confidence desc.

    confidence is 0-1. Only include matches with confidence >= score_cutoff.
    """
    if not query:
        return []

    normalized_query = normalize_name(query)
    if not normalized_query:
        return []

    # Build list of (original, normalized)
    norm_choices = [(c, normalize_name(c)) for c in choices]

    scored: List[Tuple[str, float]] = []
    for original, norm in norm_choices:
        if not norm:
            continue
        score = fuzz.token_set_ratio(normalized_query, norm) / 100.0
        if score >= score_cutoff:
            scored.append((original, score))

    # sort by confidence desc
    scored.sort(key=lambda x: x[1], reverse=True)
    if limit is not None:
        scored = scored[:limit]
    return scored
