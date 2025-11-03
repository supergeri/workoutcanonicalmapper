import yaml
import re
import pathlib
from datetime import datetime, timedelta
from backend.core.normalize import normalize
from backend.core.match import classify
from backend.core.garmin_matcher import fuzzy_match_garmin
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
    
    # Check for distance pattern like "200M SKI"
    distance_match = re.search(r'(\d+)\s*M\s+(.+)', ex_name, re.IGNORECASE)
    if distance_match:
        distance = f"{distance_match.group(1)}m"
        base_name = distance_match.group(2).strip()
        original_desc = distance
        return base_name, "", original_desc
    
    return ex_name, "", ""


def clean_exercise_name(ex_name: str) -> str:
    """Clean exercise name for matching."""
    # Remove common prefixes and suffixes
    ex_name = ex_name.strip()
    # Remove "X10", "X8" etc if still there (but keep words before numbers)
    ex_name = re.sub(r'\s+X\d+.*$', '', ex_name, flags=re.IGNORECASE)
    # Remove patterns like "X4 wb", "X6-10 0"
    ex_name = re.sub(r'\s+X[0-9-]+\s+[a-z0-9]+\s*$', '', ex_name, flags=re.IGNORECASE)
    # Remove special characters like §
    ex_name = re.sub(r'[§©®™]', '', ex_name)
    # Remove trailing single characters/numbers
    ex_name = re.sub(r'\s+[0-9a-z]\s*$', '', ex_name, flags=re.IGNORECASE)
    return ex_name.strip()


def map_exercise_to_garmin(ex_name: str, ex_reps=None, ex_distance_m=None, use_user_mappings: bool = True) -> tuple[str, str]:
    """
    Map exercise name to Garmin exercise name and description.
    Returns (garmin_name, description)
    """
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
        "sled push": "Sled Push",
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
    
    # 2. Try exact or substring matches in mappings
    # Sort by length (longest first) for better matches - longest matches first
    sorted_mappings = sorted(mappings.items(), key=lambda x: len(x[0]), reverse=True)
    
    best_match = None
    best_match_length = 0
    
    for key, value in sorted_mappings:
        # Exact match
        if normalized == key:
            garmin_name = value
            break
        # Key is substring of normalized (most specific match)
        elif key in normalized:
            if len(key) > best_match_length:
                best_match = value
                best_match_length = len(key)
    
    if best_match:
        garmin_name = best_match
    
    # Fallback 1: try fuzzy matching against Garmin exercise database
    if not garmin_name:
        garmin_name = fuzzy_match_garmin(clean_name)
    
    # Fallback 2: try canonical matching
    if not garmin_name:
        result = classify(clean_name)
        canonical = result["canonical"] if result["status"] != "unknown" else None
        if canonical:
            garmin_map = GARMIN.get(canonical)
            if garmin_map:
                garmin_name = garmin_map["name"]
    
    # Final fallback
    if not garmin_name:
        garmin_name = clean_name.replace('/', ' ').title()
    
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
            if reps_desc:
                # Fix spacing: "x 8" -> "x8" or keep "x 8" based on style
                reps_formatted = reps_desc.replace('x ', 'x') if 'each side' in reps_desc else reps_desc.replace(' ', '')
                description = f"{desc_name} {reps_formatted}"
            elif ex_reps is not None:
                description = f"{desc_name} x{ex_reps}"
            else:
                description = desc_name
    else:
        desc_parts = []
        # Use the original base_name (cleaned) for description
        name_part = base_name.replace('/', ' ').title()
        
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
    
    # Format as "lap | description" if there's a description (and not distance)
    if description and not ex_distance_m:
        description = f"lap | {description}"
    
    return garmin_name, description


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
            
            garmin_name, description = map_exercise_to_garmin(ex_name, ex_reps=reps, ex_distance_m=None)  # Ignore distance
            
            # Add category to exercise name
            garmin_name_with_category = add_category_to_exercise_name(garmin_name)
            
            ex_entry = {}
            # Handle time-based exercises with sets (interval training)
            if duration_sec and sets:
                # Create repeat structure for interval exercises
                interval_exercises = []
                interval_exercises.append({garmin_name_with_category: f"{duration_sec}s"})
                if rest_sec:
                    interval_exercises.append({"rest": f"{rest_sec}s"})
                # Wrap in repeat
                repeat_block = {f"repeat({sets})": interval_exercises}
                exercises_list.append(repeat_block)
            elif duration_sec:
                # Single time-based exercise
                ex_entry[garmin_name_with_category] = f"{duration_sec}s"
                exercises_list.append(ex_entry)
            elif description:
                # Use description with "lap |" prefix
                ex_entry[garmin_name_with_category] = description
                exercises_list.append(ex_entry)
            elif reps is not None:
                ex_entry[garmin_name_with_category] = f"{reps} reps"
                exercises_list.append(ex_entry)
            else:
                # Default to "lap" (ignore distance)
                ex_entry[garmin_name_with_category] = "lap"
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
                
                garmin_name, description = map_exercise_to_garmin(ex_name, ex_reps=reps, ex_distance_m=None)  # Ignore distance
                
                # Add category to exercise name
                garmin_name_with_category = add_category_to_exercise_name(garmin_name)
                
                # Build exercise entry - always default to "lap" instead of distance
                ex_entry = {}
                
                # Determine the value based on expected output format (ignore distance)
                if description:
                    # Use the description with "lap |" prefix
                    ex_entry[garmin_name_with_category] = description
                elif reps is not None:
                    # Just reps, no description
                    ex_entry[garmin_name_with_category] = f"{reps} reps"
                else:
                    # Default to "lap" (ignore distance_m)
                    ex_entry[garmin_name_with_category] = "lap"
                
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
    
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False, allow_unicode=True)


