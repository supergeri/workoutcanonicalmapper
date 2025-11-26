import yaml
import re
import pathlib
from datetime import datetime, timedelta
from backend.core.normalize import normalize
from backend.core.match import classify
from backend.core.garmin_matcher import fuzzy_match_garmin, find_garmin_exercise
from backend.core.user_mappings import get_user_mapping
from backend.core.exercise_categories import add_category_to_exercise_name
from backend.adapters.cir_to_garmin_yaml import GARMIN

ROOT = pathlib.Path(__file__).resolve().parents[2]
USER_DEFAULTS_FILE = ROOT / "shared/settings/user_defaults.yaml"


def load_user_defaults():
    """Load user default settings."""
    if USER_DEFAULTS_FILE.exists():
        try:
            with open(USER_DEFAULTS_FILE, 'r') as f:
                data = yaml.safe_load(f) or {}
                return data.get("defaults", {})
        except Exception:
            pass
    # Return defaults
    return {
        "distance_handling": "lap",
        "default_exercise_value": "lap",
        "ignore_distance": True
    }


def parse_exercise_name(ex_name: str) -> tuple[str, str, str]:
    """
    Parse exercise name to extract base name, reps description, and original description.
    Returns (base_name, reps_desc, original_desc)
    Examples:
    - "A1; CABLE/BAND STRAIGHT ARM PULL DOWN X10" -> ("CABLE/BAND STRAIGHT ARM PULL DOWN", "x10", "Straight Arm Pull down x 10")
    - "B1: DB INCLINE BENCH PRESS X8" -> ("DB INCLINE BENCH PRESS", "x8", "8 reps")
    - "D2: 200M SKI" -> ("SKI", "", "200m")
    """
    original = ex_name
    # Remove prefix like "A1;", "A1:", "B1:", etc.
    ex_name = re.sub(r'^[A-Z]\d+[:\s;]+', '', ex_name, flags=re.IGNORECASE).strip()
    
    reps_desc = ""
    original_desc = ""
    
    # Try to extract X10, X8 pattern at the end with "EACH SIDE"
    match = re.search(r'\s+X\s*(\d+)\s+EACH\s+SIDE$', ex_name, re.IGNORECASE)
    if match:
        reps_desc = f"x{match.group(1)} each side"
        base_name = ex_name[:match.start()].strip()
        # Extract core exercise name
        parts = re.split(r'[/:]', base_name)
        if len(parts) > 1:
            desc_name = parts[-1].strip()
        else:
            desc_name = base_name
        
        # Remove equipment prefixes
        desc_name = re.sub(r'^(KB|DB|OB|TRX)\s+', '', desc_name, flags=re.IGNORECASE).strip()
        
        # Title case
        words = desc_name.split()
        desc_name = ' '.join(w.capitalize() for w in words)
        desc_name = desc_name.replace(' Into ', ' into ')
        original_desc = f"{desc_name} x{match.group(1)} each side"
        return base_name, reps_desc, original_desc
    
    # Try to extract X10, X8 pattern at the end
    match = re.search(r'\s+X\s*(\d+)$', ex_name, re.IGNORECASE)
    if match:
        reps_desc = f"x{match.group(1)}"
        base_name = ex_name[:match.start()].strip()
        
        # Extract core exercise name (remove equipment prefixes like CABLE/BAND, KB, DB, etc.)
        # Split by common separators and take the main part
        parts = re.split(r'[/:]', base_name)
        if len(parts) > 1:
            # Take the last meaningful part (usually the exercise name)
            desc_name = parts[-1].strip()
        else:
            desc_name = base_name
        
        # Use the full base_name for description to preserve KB/DB/etc prefixes
        desc_name = base_name
        
        # Title case with proper capitalization (first letter uppercase, rest lowercase)
        words = desc_name.split()
        desc_name = ' '.join(w.capitalize() for w in words)
        # Fix common terms - "Into" not "INTO"
        desc_name = desc_name.replace(' Into ', ' into ')
        original_desc = f"{desc_name} x{match.group(1)}"
        return base_name, reps_desc, original_desc
    
    # Check for Xi2 pattern
    match = re.search(r'\s+Xi(\d+)$', ex_name, re.IGNORECASE)
    if match:
        reps_desc = f"x{match.group(1)}"
        base_name = ex_name[:match.start()].strip()
        desc_name = base_name.replace('/', ' ').title()
        original_desc = f"{desc_name} x{match.group(1)}"
        return base_name, reps_desc, original_desc
    
    # Check for distance pattern like "200M SKI" or "100 m KB Farmers (32/24kg)"
    distance_match = re.search(r'(\d+)\s*[Mm]\s+(.+)', ex_name, re.IGNORECASE)
    if distance_match:
        distance = f"{distance_match.group(1)}m"
        base_name = distance_match.group(2).strip()
        # Remove weight specifications in parentheses like "(32/24kg)"
        base_name = re.sub(r'\s*\([^)]+\)\s*$', '', base_name, flags=re.IGNORECASE).strip()
        original_desc = distance
        return base_name, "", original_desc
    
    return ex_name, "", ""


def clean_exercise_name(ex_name: str) -> str:
    """Clean exercise name for matching."""
    # Remove common prefixes and suffixes
    ex_name = ex_name.strip()
    # Remove weight specifications in parentheses like "(32/24kg)" or "(9/6kg)"
    ex_name = re.sub(r'\s*\([^)]+\)\s*', ' ', ex_name, flags=re.IGNORECASE)
    # Remove "X10", "X8" etc if still there (but keep words before numbers)
    ex_name = re.sub(r'\s+X\d+.*$', '', ex_name, flags=re.IGNORECASE)
    # Remove patterns like "X4 wb", "X6-10 0"
    ex_name = re.sub(r'\s+X[0-9-]+\s+[a-z0-9]+\s*$', '', ex_name, flags=re.IGNORECASE)
    # Remove special characters like §
    ex_name = re.sub(r'[§©®™]', '', ex_name)
    # Remove trailing single characters/numbers
    ex_name = re.sub(r'\s+[0-9a-z]\s*$', '', ex_name, flags=re.IGNORECASE)
    # Clean up extra spaces
    ex_name = re.sub(r'\s+', ' ', ex_name).strip()
    return ex_name.strip()


def map_exercise_to_garmin(ex_name: str, ex_reps=None, ex_distance_m=None, use_user_mappings: bool = True) -> tuple[str, str, dict]:
    """
    Map exercise name to Garmin exercise name and description.
    Returns (garmin_name, description, mapping_info)
    mapping_info contains: {source, confidence, original_name}
    """
    mapping_info = {
        "original_name": ex_name,
        "source": None,
        "confidence": None,
        "method": None
    }
    base_name, reps_desc, original_desc = parse_exercise_name(ex_name)
    clean_name = clean_exercise_name(base_name)
    
    # Manual mappings based on the example - check these first
    mappings = {
        "cable/band straight arm pull down": "30-degree Lat Pull-down",
        "cable band straight arm pull down": "30-degree Lat Pull-down",
        "straight arm pull down": "30-degree Lat Pull-down",
        "kb rol into goblet squat": "Goblet Squat",
        "kb rdl into goblet squat": "Goblet Squat",
        "rdl into goblet squat": "Goblet Squat",
        "goblet squat": "Goblet Squat",
        "kb bottoms up press": "Kettlebell Floor to Shelf",
        "bottoms up press": "Kettlebell Floor to Shelf",
        "db incline bench press": "Incline Dumbbell Bench Press",
        "incline bench press": "Incline Dumbbell Bench Press",
        "ob single arm push jerk": "Dumbbell Power Clean and Jerk",
        "single arm push jerk": "Dumbbell Power Clean and Jerk",
        "bulgarian split squat": "Dumbbell Bulgarian Split Squat",
        "incline back extension/ goodmornings": "Bar Good Morning",
        "incline back extension goodmornings": "Bar Good Morning",
        "back extension goodmornings": "Bar Good Morning",
        "goodmornings": "Bar Good Morning",
        "trx rows": "TRX Inverted Row",
        "trx row": "TRX Inverted Row",
        "kneeling medball slams": "Medicine Ball Slam",
        "medball slams": "Medicine Ball Slam",
        "200m ski": "Ski Moguls",
        "ski": "Ski Moguls",
        "plank into pike": "Pike Push-up",
        # Additional mappings for better specificity
        "kb alternating plank drag": "Plank",
        "alternating plank drag": "Plank",
        "plank drag": "Plank",
        "backward sled drag": "Sled Backward Drag",
        "sled drag": "Sled Backward Drag",
        "backward drag": "Sled Backward Drag",
        "burpee max broad jumps": "Burpee",
        "burpee broad jump": "Burpee",
        "farmer carry": "Farmer's Carry",
        "farmers carry": "Farmer's Carry",
        "farmer's carry": "Farmer's Carry",
        "kb farmers": "Farmer's Carry",
        "kettlebell farmers": "Farmer's Carry",
        "kb farmer": "Farmer's Carry",
        "kettlebell farmer": "Farmer's Carry",
        "sled push": "Sled Push",
        "walking lunge": "Walking Lunge",
        "walking lunges": "Walking Lunge",
        "lunge": "Walking Lunge",
        "lunges": "Walking Lunge",
        "row": "Row",
        "rowing": "Row",
        "skireg": "Ski Moguls",
        "ski erg": "Ski Moguls",
        "ski ergometer": "Ski Moguls",
        "row / skireg": "Row",
        "row/skireg": "Row",
        "wall ball": "Wall Ball",
        "wall balls": "Wall Ball",
        "medicine ball wall ball": "Wall Ball",
        "hand release push ups": "Hand Release Push Up",
        "hand release push up": "Hand Release Push Up",
        # More specific mappings
        "db push press": "Dumbbell Push Press",
        "push press": "Dumbbell Push Press",
        "dual kb front squat": "Dumbbell Front Squat",
        "dual kettlebell front squat": "Dumbbell Front Squat",
        "kb front squat": "Dumbbell Front Squat",
        "kettlebell front squat": "Dumbbell Front Squat",
        "front squat": "Dumbbell Front Squat",
        # RDL mappings - prefer Romanian Deadlift over generic Deadlift
        "rdl": "Romanian Deadlift",
        "rdls": "Romanian Deadlift",
        "romanian deadlift": "Romanian Deadlift",
        "dumbbell rdls": "Romanian Deadlift",
        "db rdls": "Romanian Deadlift",
        "kb rdls": "Romanian Deadlift",
        # Push-up mappings - prefer Push Up over Bench Press for push-ups
        "band-resisted push-ups": "Push Up",
        "band resisted push-ups": "Push Up",
        "band-resisted push ups": "Push Up",
        "band resisted push ups": "Push Up",
        "band push-ups": "Push Up",
        "band push ups": "Push Up",
        "push-ups": "Push Up",
        "push ups": "Push Up",
        "push-up": "Push Up",
        "push up": "Push Up",
        # X-Abs mapping
        "pure torque device": "X Abs",
        "pure torque device twists": "X Abs",
        "pure torque device holds": "X Abs",
        "pure torque device twists or holds": "X Abs",
        "torque device": "X Abs",
        "torque twists": "X Abs",
        "torque holds": "X Abs",
        # GHD Back Extensions mapping
        "freak athlete back extensions": "Ghd Back Extensions",
        "freak athlete hyper": "Ghd Back Extensions",
        "back extensions": "Ghd Back Extensions",
        "back extension": "Ghd Back Extensions",
        "ghd back extensions": "Ghd Back Extensions",
        "ghd back extension": "Ghd Back Extensions",
        # Chest-Supported Dumbbell Row mapping
        "seal row": "Chest-Supported Dumbbell Row",
        "seal rows": "Chest-Supported Dumbbell Row",
        "chest-supported dumbbell row": "Chest-Supported Dumbbell Row",
        "chest supported dumbbell row": "Chest-Supported Dumbbell Row",
        "chest-supported row": "Chest-Supported Dumbbell Row",
        "chest supported row": "Chest-Supported Dumbbell Row",
    }
    
    normalized = normalize(clean_name).lower()
    garmin_name = None
    
    # 1. Check user mappings first (highest priority)
    if use_user_mappings:
        user_mapped = get_user_mapping(clean_name)
        if user_mapped:
            garmin_name = user_mapped
            # User mapping found - skip to description building
            # (will build description below)
    
    # 2. Check global popular mappings (crowd-sourced choices)
    if not garmin_name:
        from backend.core.global_mappings import get_most_popular_mapping
        popular = get_most_popular_mapping(clean_name)
        if popular:
            garmin_name, popularity_count = popular
            mapping_info["source"] = "popular_mapping"
            mapping_info["confidence"] = min(0.95, 0.7 + (popularity_count * 0.05))  # Boost confidence based on popularity
            mapping_info["method"] = f"popular_choice_{popularity_count}_users"
            mapping_info["popularity_count"] = popularity_count  # Store for easier access
    
    # 3. Try exact or substring matches in mappings
    if not garmin_name:
        # Sort by length (longest first) for better matches - longest matches first
        sorted_mappings = sorted(mappings.items(), key=lambda x: len(x[0]), reverse=True)
        
        best_match = None
        best_match_length = 0
        
        for key, value in sorted_mappings:
            # Exact match
            if normalized == key:
                garmin_name = value
                mapping_info["source"] = "manual_mapping"
                mapping_info["confidence"] = 1.0
                mapping_info["method"] = "exact_match"
                break
            # Key is substring of normalized (most specific match)
            elif key in normalized:
                if len(key) > best_match_length:
                    best_match = value
                    best_match_length = len(key)
        
        if best_match and not garmin_name:
            garmin_name = best_match
            mapping_info["source"] = "manual_mapping"
            mapping_info["confidence"] = 0.95
            mapping_info["method"] = "substring_match"
    
    # Fallback 1: try fuzzy matching against Garmin exercise database
    # Uses new exercise_name_matcher with alias matching + normalization
    # Threshold 40 (0.40) matches unmapped threshold - only use matches >= 0.40 confidence
    if not garmin_name:
        garmin_name, confidence = find_garmin_exercise(clean_name, threshold=40)
        if garmin_name:
            mapping_info["source"] = "garmin_database"
            mapping_info["confidence"] = confidence
            mapping_info["method"] = "fuzzy_match"
    
    # Fallback 2: try canonical matching
    if not garmin_name:
        result = classify(clean_name)
        canonical = result["canonical"] if result["status"] != "unknown" else None
        if canonical:
            garmin_map = GARMIN.get(canonical)
            if garmin_map:
                garmin_name = garmin_map["name"]
                mapping_info["source"] = "canonical_mapping"
                mapping_info["confidence"] = result.get("score", 0.8)
                mapping_info["method"] = "canonical_match"
    
    # Final fallback
    if not garmin_name:
        garmin_name = clean_name.replace('/', ' ').title()
        mapping_info["source"] = "fallback"
        mapping_info["confidence"] = 0.0
        mapping_info["method"] = "title_case_fallback"
    
    # Build description - format to match expected output
    # For some exercises, just use reps. For others, use full name.
    # Rules based on expected output:
    # - "Straight Arm Pull down" - remove CABLE/BAND prefix
    # - "KB RDL Into Goblet Squat" - keep KB, keep RDL
    # - "KB Bottoms Up Press" - keep KB
    # - "8 reps" for DB Incline Bench Press - just reps, no name
    
    if original_desc:
        # Extract the exercise name part
        desc_name = base_name.replace('/', ' ').strip()
        
        # Special handling: remove CABLE/BAND prefix for "Straight Arm Pull down"
        if 'straight arm pull down' in normalized or 'cable' in normalized or 'band' in normalized:
            desc_name = re.sub(r'^(CABLE/BAND|CABLE|BAND)\s+', '', desc_name, flags=re.IGNORECASE).strip()
            desc_name = re.sub(r'^(STRAIGHT ARM)\s+', 'Straight Arm ', desc_name, flags=re.IGNORECASE)
            # Fix "Down" to "down" (lowercase)
            desc_name = desc_name.replace(' Down', ' down')
        
        # Special handling: for DB Incline Bench Press, just use reps (no name)
        if 'incline bench press' in normalized and 'db' in normalized and ex_reps is not None:
            description = f"{ex_reps} reps"
        else:
            # Format the name properly
            words = desc_name.split()
            desc_name = ' '.join(w.capitalize() for w in words)
            desc_name = desc_name.replace(' Into ', ' into ').replace(' Rdl ', ' RDL ').replace(' Rol ', ' ROL ')
            desc_name = desc_name.replace(' Kb ', ' KB ').replace(' Db ', ' DB ').replace(' Ob ', ' OB ')
            # Fix double spaces
            desc_name = re.sub(r'\s+', ' ', desc_name).strip()
            
            # Combine with reps
    
    # Final fallback - check confidence threshold
    final_confidence = mapping_info.get("confidence", 0.0)
    if not garmin_name or final_confidence < 0.40:
        # Try one more time with the effective_name (mapped_name if available)
        if effective_name != ex_name and not garmin_name:
            garmin_name, confidence = find_garmin_exercise(effective_name, threshold=40)
            if garmin_name:
                mapping_info["source"] = "garmin_database"
                mapping_info["confidence"] = confidence
                mapping_info["method"] = "fuzzy_match_mapped_name"
                final_confidence = confidence
        
        # If still no match or confidence too low, use generic fallback with warning
        if not garmin_name or final_confidence < 0.40:
            garmin_name = clean_name.replace('/', ' ').title()
            mapping_info["source"] = "fallback"
            mapping_info["confidence"] = 0.0
            mapping_info["method"] = "title_case_fallback"
            logger.warning(
                "GARMIN_EXPORT_FALLBACK generic step used for %r (original=%r mapped=%r candidates=%r conf=%r)",
                ex_name, ex_name, mapped_name, candidate_names, final_confidence
            )
    
        
        if ex_distance_m:
            desc_parts.append(f"{ex_distance_m}m")
        elif ex_reps is not None:
            # Format: "Exercise Name x reps" or "Exercise Name reps reps"
            if name_part and name_part.lower() != garmin_name.lower():
                desc_parts.append(f"{name_part} {ex_reps} reps")
            else:
                desc_parts.append(f"{ex_reps} reps")
        elif reps_desc:
            if name_part and name_part.lower() != garmin_name.lower():
                desc_parts.append(f"{name_part} {reps_desc}")
            else:
                desc_parts.append(reps_desc)
        
        description = " ".join(desc_parts) if desc_parts else ""
    
    # Build the description to include original exercise name with details
    # Format: "lap | Original Exercise Name x5 (chosen as closest match)"
    
    # Generate simple mapping reason for notes
    source = mapping_info.get("source")
    method = mapping_info.get("method", "")
    
    if source == "user_mapping":
        mapping_reason = "chosen from your saved preferences"
    elif source == "popular_mapping":
        # Get popularity count from mapping_info if available, otherwise parse from method
        popularity_count = mapping_info.get("popularity_count", 1)
        if popularity_count == 1 and "popular_choice_" in method:
            try:
                popularity_count = int(method.split("_")[-1].replace("users", ""))
            except:
                popularity_count = 1
        if popularity_count == 1:
            mapping_reason = "chosen as popular choice by users"
        else:
            mapping_reason = f"chosen as popular choice by {popularity_count} users"
    elif source == "manual_mapping":
        mapping_reason = "chosen as exact match"
    elif source == "garmin_database":
        mapping_reason = "chosen as closest match"
    elif source == "canonical_mapping":
        mapping_reason = "chosen as best match"
    elif source == "fallback":
        mapping_reason = "used name as-is (no match found)"
    else:
        mapping_reason = "chosen automatically"
    
    mapping_info["reason"] = mapping_reason
    mapping_info["garmin_name"] = garmin_name
    
    # Build description from original exercise name with details
    original_with_details = ex_name.strip()
    # Clean up the original name but keep reps/details
    # Remove prefixes like "A1:", "B2:", etc.
    original_with_details = re.sub(r'^[A-Z]\d+[:\s;]+', '', original_with_details, flags=re.IGNORECASE)
    original_with_details = original_with_details.strip()
    
    # Check if reps are already in the name (like "X10", "x5", etc.)
    has_reps_in_name = bool(re.search(r'[Xx]\d+', original_with_details))
    has_reps_word = bool(re.search(r'\d+\s+reps?', original_with_details, re.IGNORECASE))
    
    # Check if the rep number from ex_reps is already represented in the name
    rep_number_already_in_name = False
    if ex_reps is not None:
        # Check if the rep number appears in X4, x4, or "4 reps" format
        rep_str = str(ex_reps)
        rep_patterns = [
            rf'\b{re.escape(rep_str)}\s+reps?\b',  # "4 reps"
            rf'\b[Xx]{re.escape(rep_str)}\b',      # "X4" or "x4"
            rf'\b{re.escape(rep_str)}\s*[Ww]b\b',  # "4 wb" or "4 WB"
        ]
        for pattern in rep_patterns:
            if re.search(pattern, original_with_details, re.IGNORECASE):
                rep_number_already_in_name = True
                break
    
    # Only add reps if they're not already in the name and we have rep info
    if not has_reps_in_name and not has_reps_word and not rep_number_already_in_name:
        if ex_reps is not None:
            original_with_details = f"{original_with_details} x{ex_reps}"
        elif reps_desc and reps_desc.lower() not in original_with_details.lower():
            original_with_details = f"{original_with_details} {reps_desc}"
    
    # Format as "lap | original name (reason)"
    # Always include description for rep-based exercises
    if original_with_details:
        final_description = f"lap | {original_with_details} ({mapping_reason})"
    else:
        # Fallback if we don't have original name - use garmin name
        final_description = f"lap ({mapping_reason})"
    
    return garmin_name, final_description, mapping_info


def extract_rounds(structure: str) -> int:
    """Extract number of rounds from structure string like '3 rounds'."""
    if not structure:
        return 1
    match = re.search(r'(\d+)\s+rounds?', structure, re.IGNORECASE)
    return int(match.group(1)) if match else 1


def workout_name_from_title(title: str) -> str:
    """Convert title to workout name (lowercase, no spaces)."""
    # "Week 5 Of 12" -> "fullhyroxweek5"
    # Extract number from title
    match = re.search(r'week\s*(\d+)', title, re.IGNORECASE)
    if match:
        week_num = match.group(1)
        return f"fullhyroxweek{week_num}"
    
    # Fallback: lowercase, remove special chars
    name = re.sub(r'[^a-z0-9]', '', title.lower())
    return name or "workout"


def to_hyrox_yaml(blocks_json: dict) -> str:
    """
    Convert blocks JSON format to Hyrox YAML format.
    """
    settings = {"deleteSameNameWorkout": True}
    workouts = {}
    
    workout_name = workout_name_from_title(blocks_json.get("title", "Workout"))
    workout_steps = []
    
    # Initialize mapping notes tracker
    to_hyrox_yaml._mapping_notes = []
    
    # Add warmup
    workout_steps.append({
        "warmup": [{"cardio": "lap"}]
    })
    
    # Process blocks
    for block in blocks_json.get("blocks", []):
        label = block.get("label", "")
        structure = block.get("structure", "")
        rounds = extract_rounds(structure) if structure else 1
        
        # Process standalone exercises (not in supersets)
        exercises_list = []
        for ex in block.get("exercises", []):
            ex_name = ex.get("name", "")
            sets = ex.get("sets")
            reps = ex.get("reps")
            distance_m = ex.get("distance_m")
            duration_sec = ex.get("duration_sec")
            rest_sec = ex.get("rest_sec")
            
            garmin_name, description, mapping_info = map_exercise_to_garmin(ex_name, ex_reps=reps, ex_distance_m=None)  # Ignore distance
            
            # Add category to exercise name
            garmin_name_with_category = add_category_to_exercise_name(garmin_name)
            
            # Store mapping info for notes
            if not hasattr(to_hyrox_yaml, '_mapping_notes'):
                to_hyrox_yaml._mapping_notes = []
            to_hyrox_yaml._mapping_notes.append(mapping_info)
            
            ex_entry = {}
            # Handle time-based exercises with sets (interval training)
            # Time-based exercises should NOT include mapping reason (per Strength Workout Guide)
            if duration_sec and sets:
                # Create repeat structure for interval exercises
                interval_exercises = []
                duration_value = f"{duration_sec}s"
                interval_exercises.append({garmin_name_with_category: duration_value})
                if rest_sec:
                    interval_exercises.append({"rest": f"{rest_sec}s"})
                # Wrap in repeat
                repeat_block = {f"repeat({sets})": interval_exercises}
                exercises_list.append(repeat_block)
            elif duration_sec:
                # Single time-based exercise - just show time, no description
                duration_value = f"{duration_sec}s"
                ex_entry[garmin_name_with_category] = duration_value
                exercises_list.append(ex_entry)
            else:
                # For rep-based and other exercises, always use description
                # Description already includes "lap | original name (reason)" format
                if description:
                    ex_entry[garmin_name_with_category] = description
                elif reps is not None:
                    # Build a minimal description if we don't have one
                    original_clean = re.sub(r'^[A-Z]\d+[:\s;]+', '', ex_name, flags=re.IGNORECASE).strip()
                    ex_entry[garmin_name_with_category] = f"lap | {original_clean} x{reps} ({mapping_info.get('reason', 'chosen automatically')})"
                else:
                    # Default fallback
                    original_clean = re.sub(r'^[A-Z]\d+[:\s;]+', '', ex_name, flags=re.IGNORECASE).strip()
                    ex_entry[garmin_name_with_category] = f"lap | {original_clean} ({mapping_info.get('reason', 'chosen automatically')})"
                exercises_list.append(ex_entry)
        
        # Process supersets - combine all supersets in a block into one repeat
        all_block_exercises = []
        rest_between_sec = block.get("rest_between_sec")
        
        for superset_idx, superset in enumerate(block.get("supersets", [])):
            exercises = []
            
            for ex in superset.get("exercises", []):
                ex_name = ex.get("name", "")
                sets = ex.get("sets")
                reps = ex.get("reps")
                distance_m = ex.get("distance_m")
                
                garmin_name, description, mapping_info = map_exercise_to_garmin(ex_name, ex_reps=reps, ex_distance_m=None)  # Ignore distance
                
                # Add category to exercise name
                garmin_name_with_category = add_category_to_exercise_name(garmin_name)
                
                # Store mapping info for notes
                if not hasattr(to_hyrox_yaml, '_mapping_notes'):
                    to_hyrox_yaml._mapping_notes = []
                to_hyrox_yaml._mapping_notes.append(mapping_info)
                
                # Build exercise entry - always default to "lap" instead of distance
                ex_entry = {}
                
                # Determine the value based on expected output format (ignore distance)
                # Description already includes "lap | original name (reason)" format
                # Always use the description that was built in map_exercise_to_garmin
                # If no description, create a basic one
                if description:
                    ex_entry[garmin_name_with_category] = description
                else:
                    # Fallback: create description from original name
                    original_clean = re.sub(r'^[A-Z]\d+[:\s;]+', '', ex_name, flags=re.IGNORECASE).strip()
                    if reps is not None:
                        ex_entry[garmin_name_with_category] = f"lap | {original_clean} x{reps} ({mapping_info.get('reason', 'chosen automatically')})"
                    else:
                        ex_entry[garmin_name_with_category] = f"lap | {original_clean} ({mapping_info.get('reason', 'chosen automatically')})"
                
                exercises.append(ex_entry)
            
            # Add exercises from this superset to the block
            all_block_exercises.extend(exercises)
            
            # Add rest between supersets (use block's rest_between_sec)
            # Don't add rest after the last superset
            if superset_idx < len(block.get("supersets", [])) - 1:
                if rest_between_sec:
                    all_block_exercises.append({"rest": f"{rest_between_sec}s"})
                else:
                    all_block_exercises.append({"rest": "lap"})
        
        # Add final rest after all supersets in the block
        if all_block_exercises:
            all_block_exercises.append({"rest": "lap"})
        
        # Create repeat block if rounds > 1, otherwise just add exercises
        if rounds > 1 and all_block_exercises:
            repeat_block = {f"repeat({rounds})": all_block_exercises}
            workout_steps.append(repeat_block)
        elif all_block_exercises:
            workout_steps.extend(all_block_exercises)
        
        # Add standalone exercises if any
        if exercises_list:
            if rounds > 1:
                repeat_block = {f"repeat({rounds})": exercises_list}
                workout_steps.append(repeat_block)
            else:
                workout_steps.extend(exercises_list)
    
    workouts[workout_name] = workout_steps
    
    # Create schedule plan (default to today + 7 days)
    start_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    schedule_plan = {
        "start_from": start_date,
        "workouts": [workout_name]
    }
    
    # Build final document
    doc = {
        "settings": settings,
        "workouts": workouts,
        "schedulePlan": schedule_plan
    }
    
    result = yaml.safe_dump(doc, sort_keys=False, default_flow_style=False, allow_unicode=True)
    
    # Clean up
    if hasattr(to_hyrox_yaml, '_mapping_notes'):
        delattr(to_hyrox_yaml, '_mapping_notes')
    
    return result


