"""
Blocks to FIT Adapter v5

Fixes:
- Correct FIT field numbers (field 2 = duration_value, not field 0)
- Rest steps don't set exercise_category (avoids bench_press showing)
- Proper repeat structure for sets
"""

import re
import struct
import time
from pathlib import Path
from io import BytesIO

try:
    from fastapi.responses import StreamingResponse
except ImportError:
    StreamingResponse = None

try:
    from backend.adapters.garmin_lookup import GarminExerciseLookup
    LOOKUP_PATH = Path(__file__).parent.parent.parent / "shared" / "dictionaries" / "garmin_exercises.json"
except ImportError:
    from garmin_lookup import GarminExerciseLookup
    LOOKUP_PATH = Path(__file__).parent / "garmin_exercises.json"

_lookup = None

# Maximum valid FIT SDK exercise category ID
# Categories 0-32 are standard FIT SDK categories
# Categories 33+ are extended and may not work on all Garmin watches
MAX_VALID_CATEGORY_ID = 32

# Fallback remapping for invalid categories
# Maps invalid category IDs to valid FIT SDK categories
INVALID_CATEGORY_FALLBACK = {
    # 33-43 are "extended" categories that some watches don't support
    33: 2,   # Map to Cardio
    34: 2,   # Map to Cardio
    35: 2,   # Map to Cardio
    36: 2,   # Map to Cardio
    37: 2,   # Map to Cardio
    38: 2,   # Indoor Rower -> Cardio (Row 23 doesn't work for erg machines)
    39: 29,  # Map to Total Body
    40: 29,  # Map to Total Body
    41: 29,  # Map to Total Body
    42: 29,  # Map to Total Body
    43: 29,  # Map to Total Body
}

def validate_category_id(category_id, exercise_name=None):
    """
    Validate and remap exercise category ID to ensure Garmin compatibility.

    FIT SDK only defines categories 0-32 as standard. Extended categories (33+)
    may cause the watch to reject the entire workout.

    Returns a valid category ID (0-32).
    """
    if category_id <= MAX_VALID_CATEGORY_ID:
        return category_id

    # Check for specific remapping
    if category_id in INVALID_CATEGORY_FALLBACK:
        return INVALID_CATEGORY_FALLBACK[category_id]

    # Default fallback for any unknown invalid category
    # Total Body (29) is a safe generic choice
    return 29


def get_lookup():
    global _lookup
    if _lookup is None:
        _lookup = GarminExerciseLookup(str(LOOKUP_PATH))
    return _lookup


def _is_user_confirmed_name(name):
    """
    Check if the input name looks like a user-confirmed Garmin exercise name.

    User-confirmed names are typically:
    - Title Case (e.g., "Burpee Box Jump", "Wall Ball")
    - Don't have distance prefixes (e.g., "500m", "1km")
    - Don't have rep counts (e.g., "x10")

    Returns True if the name should be preserved as-is (user confirmed),
    False if it should go through the normal lookup mapping.
    """
    if not name or len(name) < 2:
        return False

    # Check for distance prefix (e.g., "500m Run", "1km Row")
    if re.match(r'^[\d.]+\s*(m|km|mi)\s+', name, re.IGNORECASE):
        return False

    # Check for rep/set counts (e.g., "Push Up x10", "Squat 3x10")
    if re.search(r'\s*\d*x\d+', name, re.IGNORECASE):
        return False

    # Check if it looks like Title Case (first letter of most words capitalized)
    # This indicates a user has selected/confirmed a specific exercise name
    words = name.split()
    if len(words) == 0:
        return False

    # Count words that start with uppercase
    capitalized = sum(1 for w in words if w[0].isupper())

    # If most words are capitalized, it's likely a user-confirmed name
    # Allow for small words like "to", "of", "the" which might be lowercase
    return capitalized >= len(words) * 0.6


def crc16(data):
    crc_table = [
        0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
        0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400
    ]
    crc = 0
    for byte in data:
        tmp = crc_table[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ crc_table[byte & 0xF]
        tmp = crc_table[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ crc_table[(byte >> 4) & 0xF]
    return crc


def write_string(s, length):
    encoded = s.encode('utf-8')[:length-1]
    return encoded + b'\x00' * (length - len(encoded))


def parse_structure(structure_str):
    if not structure_str:
        return 1
    match = re.search(r'(\d+)', structure_str)
    return int(match.group(1)) if match else 1


def blocks_to_steps(blocks_json, use_lap_button=False):
    """
    Convert blocks JSON to FIT workout steps.

    Args:
        blocks_json: Workout data with blocks/exercises
        use_lap_button: If True, use "lap button press" for all exercises instead of reps/distance.
                       This is often preferred for conditioning workouts where you press lap when done.
    """
    lookup = get_lookup()
    steps = []
    category_ids_used = set()  # Track which categories are in the workout

    for block in blocks_json.get('blocks', []):
        rounds = parse_structure(block.get('structure'))
        rest_between = block.get('rest_between_sec', 30) or 30

        all_exercises = []
        for superset in block.get('supersets', []):
            for exercise in superset.get('exercises', []):
                all_exercises.append(exercise)
        for exercise in block.get('exercises', []):
            all_exercises.append(exercise)

        for exercise in all_exercises:
            name = exercise.get('name', 'Exercise')
            reps_raw = exercise.get('reps') or 10
            sets = exercise.get('sets') or rounds
            duration_sec = exercise.get('duration_sec')
            distance_m = exercise.get('distance_m')  # Numeric distance in meters from ingestor

            match = lookup.find(name)
            raw_category_id = match['category_id']
            # Validate category ID - remap invalid (33+) to valid (0-32)
            category_id = validate_category_id(raw_category_id, name)
            category_ids_used.add(category_id)

            # IMPORTANT: If the input name is an exact match in the Garmin database,
            # use the DB's display_name. This preserves the canonical Garmin name.
            # If not an exact match, check if the input name looks like a user-confirmed
            # Garmin name (Title Case, no distance prefixes) and use it directly.
            # This preserves user-confirmed mappings like "Burpee Box Jump".
            if match.get('match_type') == 'exact' or match.get('match_type') == 'exact_with_category_override':
                display_name = match.get('display_name') or name
            elif _is_user_confirmed_name(name):
                # Input looks like a user-confirmed Garmin name - preserve it
                display_name = name
            else:
                display_name = match.get('display_name') or match['category_name']

            # Determine duration type and value
            # FIT duration types: 0=time(ms), 1=lap_button, 3=distance(cm), 29=reps
            duration_type = 29  # default: reps
            duration_value = 10  # default

            if use_lap_button:
                # Use lap button press - user presses lap when done with exercise
                duration_type = 1  # lap_button / until_lap_pressed
                duration_value = 0  # not used for lap button
            else:
                # Check for distance - first from distance_m field, then from reps string
                distance_meters = None

                # Priority 1: Use numeric distance_m field from ingestor (e.g., 500 for 500m)
                if distance_m is not None and distance_m > 0:
                    distance_meters = float(distance_m)
                # Priority 2: Parse distance from reps string (e.g., "500m", "1km")
                elif isinstance(reps_raw, str):
                    reps_str = reps_raw.lower().strip()
                    # Match patterns like "500m", "1.5km", "1000 m", "2 km"
                    km_match = re.match(r'^([\d.]+)\s*km$', reps_str)
                    m_match = re.match(r'^([\d.]+)\s*m$', reps_str)
                    if km_match:
                        distance_meters = float(km_match.group(1)) * 1000
                    elif m_match:
                        distance_meters = float(m_match.group(1))

                if distance_meters is not None:
                    # Use distance type (3) with value in centimeters
                    duration_type = 3
                    duration_value = int(distance_meters * 100)  # convert to cm
                elif duration_sec:
                    # Use time type (0) with value in milliseconds
                    duration_type = 0
                    duration_value = int(duration_sec * 1000)
                else:
                    # Use reps type (29)
                    duration_type = 29
                    if isinstance(reps_raw, str):
                        try:
                            duration_value = int(reps_raw.split('-')[0])  # Handle ranges like "8-10"
                        except:
                            duration_value = 10
                    else:
                        duration_value = int(reps_raw) if reps_raw else 10

            start_index = len(steps)

            # Exercise step
            # Include exercise_name_id (real FIT SDK ID) if available from lookup
            step = {
                'type': 'exercise',
                'display_name': display_name,
                'category_id': category_id,
                'intensity': 0,  # active
                'duration_type': duration_type,
                'duration_value': duration_value,
            }
            # Add real FIT SDK exercise_name_id if available (e.g., 37 for GOBLET_SQUAT)
            if match.get('exercise_name_id') is not None:
                step['exercise_name_id'] = match['exercise_name_id']
            steps.append(step)

            # Rest step (if sets > 1)
            if sets > 1 and rest_between > 0:
                steps.append({
                    'type': 'rest',
                    'display_name': 'Rest',
                    'intensity': 1,  # rest
                    'duration_type': 0,  # time
                    'duration_value': int(rest_between * 1000),
                })

            # Repeat step (if sets > 1)
            if sets > 1:
                steps.append({
                    'type': 'repeat',
                    'duration_step': start_index,
                    'repeat_count': sets - 1,
                })

    return steps, category_ids_used


def detect_sport_type(category_ids):
    """
    Detect optimal Garmin sport type based on exercise categories used.

    Returns tuple of (sport_id, sub_sport_id, sport_name, warnings)

    Sport types:
    - 1 = running (for run-only workouts)
    - 4 = fitness_equipment (for mixed cardio/strength, rowing, skiing)
    - 10 = training (for pure strength)

    Category IDs that indicate specific sports:
    - 32 = Run
    - 2 = Cardio (also used for erg machines like ski/rower)
    - 23 = Row

    Note: Invalid categories (33+) are remapped before reaching here.
    """
    # Categories that work best with different sport types
    RUNNING_CATEGORIES = {32}  # Run
    CARDIO_MACHINE_CATEGORIES = {2, 23}  # Cardio, Row

    has_running = bool(category_ids & RUNNING_CATEGORIES)
    has_cardio_machines = bool(category_ids & CARDIO_MACHINE_CATEGORIES)
    strength_categories = category_ids - RUNNING_CATEGORIES - CARDIO_MACHINE_CATEGORIES
    has_strength = bool(strength_categories)

    warnings = []

    # Determine best sport type
    if has_running and not has_strength and not has_cardio_machines:
        # Pure running workout
        return 1, 0, "running", warnings

    if has_running or has_cardio_machines:
        # Mixed workout with runs or cardio machines - use fitness_equipment
        # This is the most flexible option for conditioning workouts
        if has_strength:
            warnings.append(
                "This workout has both cardio (running/rowing/ski) and strength exercises. "
                "Exported as 'Cardio' type for best Garmin compatibility."
            )
        return 4, 0, "cardio", warnings

    # Pure strength workout
    return 10, 20, "strength", warnings


def to_fit(blocks_json, force_sport_type=None, use_lap_button=False):
    """
    Convert blocks JSON to Garmin FIT binary format.

    Args:
        blocks_json: Workout data with blocks/exercises
        force_sport_type: Override auto-detection. Options: "strength", "cardio", "running"
        use_lap_button: If True, use "lap button press" for all exercises instead of reps/distance.
                       User presses lap button when done with each exercise.

    Returns:
        bytes: FIT file binary data
    """
    title = blocks_json.get('title', 'Workout')[:31]
    steps, category_ids = blocks_to_steps(blocks_json, use_lap_button=use_lap_button)

    if not steps:
        raise ValueError("No exercises found")

    # Auto-detect or use forced sport type
    if force_sport_type == "strength":
        sport_id, sub_sport_id = 10, 20
    elif force_sport_type == "cardio":
        sport_id, sub_sport_id = 4, 0
    elif force_sport_type == "running":
        sport_id, sub_sport_id = 1, 0
    else:
        sport_id, sub_sport_id, _, _ = detect_sport_type(category_ids)

    # Track exercise IDs per category
    # We prefer real FIT SDK exercise_name_id when available (e.g., 37 for GOBLET_SQUAT)
    # Fall back to sequential IDs for exercises without a known FIT SDK ID
    category_exercise_ids = {}  # (category_id, display_name) -> exercise_name ID
    exercise_name_counter = {}  # category_id -> next_id for fallback

    def get_exercise_id(step):
        """Get exercise_name ID for a step.

        Uses real FIT SDK exercise_name_id when available (e.g., GOBLET_SQUAT=37).
        Falls back to sequential ID if no real ID is known.
        """
        category_id = step['category_id']
        display_name = step['display_name']
        key = (category_id, display_name)

        # First check if we already assigned an ID for this (category, name) pair
        if key in category_exercise_ids:
            return category_exercise_ids[key]

        # Use real FIT SDK ID if available
        if 'exercise_name_id' in step:
            category_exercise_ids[key] = step['exercise_name_id']
            return step['exercise_name_id']

        # Fallback: assign a sequential ID starting from 0
        # Note: Using 1000+ is invalid for FIT SDK exercise_name and causes Garmin watches to reject
        if category_id not in exercise_name_counter:
            exercise_name_counter[category_id] = 0
        category_exercise_ids[key] = exercise_name_counter[category_id]
        exercise_name_counter[category_id] += 1
        return category_exercise_ids[key]

    # First pass: collect all unique exercise IDs
    for step in steps:
        if step['type'] == 'exercise':
            get_exercise_id(step)

    data = b''
    timestamp = int(time.time()) - 631065600
    serial = timestamp & 0xFFFFFFFF

    # === file_id (local 0, global 0) ===
    data += struct.pack('<BBBHB', 0x40, 0, 0, 0, 5)
    data += struct.pack('<BBB', 3, 4, 0x8C)   # serial_number
    data += struct.pack('<BBB', 4, 4, 0x86)   # time_created
    data += struct.pack('<BBB', 1, 2, 0x84)   # manufacturer
    data += struct.pack('<BBB', 2, 2, 0x84)   # product
    data += struct.pack('<BBB', 0, 1, 0x00)   # type

    data += struct.pack('<B', 0x00)
    data += struct.pack('<I', serial)
    data += struct.pack('<I', timestamp)
    data += struct.pack('<H', 1)
    data += struct.pack('<H', 65534)
    data += struct.pack('<B', 5)  # workout file type

    # === file_creator (local 1, global 49) ===
    data += struct.pack('<BBBHB', 0x41, 0, 0, 49, 2)
    data += struct.pack('<BBB', 0, 2, 0x84)
    data += struct.pack('<BBB', 1, 1, 0x02)

    data += struct.pack('<B', 0x01)
    data += struct.pack('<H', 0)
    data += struct.pack('<B', 0)

    # === workout (local 2, global 26) ===
    data += struct.pack('<BBBHB', 0x42, 0, 0, 26, 5)
    data += struct.pack('<BBB', 4, 1, 0x00)   # sport
    data += struct.pack('<BBB', 5, 4, 0x8C)   # capabilities
    data += struct.pack('<BBB', 6, 2, 0x84)   # num_valid_steps
    data += struct.pack('<BBB', 8, 32, 0x07)  # wkt_name
    data += struct.pack('<BBB', 11, 1, 0x00)  # sub_sport

    data += struct.pack('<B', 0x02)
    data += struct.pack('<B', sport_id)  # sport (auto-detected or forced)
    data += struct.pack('<I', 32)
    data += struct.pack('<H', len(steps))
    data += write_string(title, 32)
    data += struct.pack('<B', sub_sport_id)  # sub_sport

    # === workout_step for exercise (local 3, global 27) ===
    # FIT SDK field numbers:
    #   254 = message_index
    #   1 = duration_type
    #   2 = duration_value
    #   3 = target_type (not 5!)
    #   7 = intensity
    #   10 = exercise_category
    #   11 = exercise_name
    data += struct.pack('<BBBHB', 0x43, 0, 0, 27, 7)
    data += struct.pack('<BBB', 254, 2, 0x84)  # message_index
    data += struct.pack('<BBB', 2, 4, 0x86)    # duration_value (FIELD 2!)
    data += struct.pack('<BBB', 1, 1, 0x00)    # duration_type
    data += struct.pack('<BBB', 3, 1, 0x00)    # target_type (FIELD 3 per FIT SDK)
    data += struct.pack('<BBB', 7, 1, 0x00)    # intensity
    data += struct.pack('<BBB', 10, 2, 0x84)   # exercise_category
    data += struct.pack('<BBB', 11, 2, 0x84)   # exercise_name

    # === workout_step for rest (local 4, global 27) - NO exercise_category ===
    data += struct.pack('<BBBHB', 0x44, 0, 0, 27, 5)
    data += struct.pack('<BBB', 254, 2, 0x84)  # message_index
    data += struct.pack('<BBB', 2, 4, 0x86)    # duration_value
    data += struct.pack('<BBB', 1, 1, 0x00)    # duration_type
    data += struct.pack('<BBB', 5, 1, 0x00)    # target_type
    data += struct.pack('<BBB', 7, 1, 0x00)    # intensity

    # === workout_step for repeat (local 5, global 27) ===
    data += struct.pack('<BBBHB', 0x45, 0, 0, 27, 4)
    data += struct.pack('<BBB', 254, 2, 0x84)  # message_index
    data += struct.pack('<BBB', 3, 4, 0x86)    # duration_step (field 3)
    data += struct.pack('<BBB', 4, 4, 0x86)    # repeat_steps (field 4)
    data += struct.pack('<BBB', 1, 1, 0x00)    # duration_type

    # Write workout steps
    for i, step in enumerate(steps):
        if step['type'] == 'repeat':
            data += struct.pack('<B', 0x05)  # local 5
            data += struct.pack('<H', i)
            data += struct.pack('<I', step['duration_step'])
            data += struct.pack('<I', step['repeat_count'])
            data += struct.pack('<B', 6)     # repeat_until_steps_cmplt
        elif step['type'] == 'rest':
            data += struct.pack('<B', 0x04)  # local 4 (rest - no category)
            data += struct.pack('<H', i)
            data += struct.pack('<I', step['duration_value'])
            data += struct.pack('<B', step['duration_type'])
            data += struct.pack('<B', 1)     # target_type: open
            data += struct.pack('<B', 1)     # intensity: rest
        else:  # exercise
            data += struct.pack('<B', 0x03)  # local 3
            data += struct.pack('<H', i)
            data += struct.pack('<I', step['duration_value'])
            data += struct.pack('<B', step['duration_type'])
            data += struct.pack('<B', 1)     # target_type: open
            data += struct.pack('<B', 0)     # intensity: active
            data += struct.pack('<H', step['category_id'])
            data += struct.pack('<H', get_exercise_id(step))  # exercise_name index

    # === exercise_title (local 6, global 264) ===
    data += struct.pack('<BBBHB', 0x46, 0, 0, 264, 4)
    data += struct.pack('<BBB', 254, 2, 0x84)  # message_index
    data += struct.pack('<BBB', 0, 2, 0x84)    # exercise_category
    data += struct.pack('<BBB', 1, 2, 0x84)    # exercise_name
    data += struct.pack('<BBB', 2, 32, 0x07)   # wkt_step_name (string)

    for i, step in enumerate(steps):
        if step['type'] == 'exercise':
            data += struct.pack('<B', 0x06)
            data += struct.pack('<H', i)
            data += struct.pack('<H', step['category_id'])
            data += struct.pack('<H', get_exercise_id(step))
            data += write_string(step['display_name'], 32)

    data_crc = crc16(data)

    header = struct.pack('<BBHI4s', 14, 0x10, 0x527D, len(data), b'.FIT')
    header_crc = crc16(header)
    header += struct.pack('<H', header_crc)

    return header + data + struct.pack('<H', data_crc)


def get_fit_metadata(blocks_json, use_lap_button=False):
    """
    Analyze workout and return metadata about FIT export.

    Args:
        blocks_json: Workout data with blocks/exercises
        use_lap_button: If True, indicates lap button mode will be used

    Returns dict with:
        - detected_sport: The auto-detected sport type
        - detected_sport_id: FIT sport ID
        - warnings: List of warnings about the export
        - exercise_count: Total number of exercises
        - has_running: Whether workout contains running exercises
        - has_cardio: Whether workout contains cardio machine exercises
        - has_strength: Whether workout contains strength exercises
        - use_lap_button: Whether lap button mode is enabled
    """
    steps, category_ids = blocks_to_steps(blocks_json, use_lap_button=use_lap_button)
    sport_id, sub_sport_id, sport_name, warnings = detect_sport_type(category_ids)

    # Category analysis
    RUNNING_CATEGORIES = {32}
    CARDIO_MACHINE_CATEGORIES = {2, 23}  # Cardio, Row (38 is remapped to 2)

    has_running = bool(category_ids & RUNNING_CATEGORIES)
    has_cardio = bool(category_ids & CARDIO_MACHINE_CATEGORIES)
    strength_cats = category_ids - RUNNING_CATEGORIES - CARDIO_MACHINE_CATEGORIES
    has_strength = bool(strength_cats)

    return {
        "detected_sport": sport_name,
        "detected_sport_id": sport_id,
        "detected_sub_sport_id": sub_sport_id,
        "warnings": warnings,
        "exercise_count": len([s for s in steps if s['type'] == 'exercise']),
        "has_running": has_running,
        "has_cardio": has_cardio,
        "has_strength": has_strength,
        "category_ids": list(category_ids),
        "use_lap_button": use_lap_button
    }


def to_fit_response(blocks_json, filename=None, force_sport_type=None, use_lap_button=False):
    if StreamingResponse is None:
        raise ImportError("FastAPI not installed")

    fit_bytes = to_fit(blocks_json, force_sport_type=force_sport_type, use_lap_button=use_lap_button)

    if filename is None:
        title = blocks_json.get('title', 'workout')
        filename = f"{title.replace(' ', '_')}.fit"

    return StreamingResponse(
        BytesIO(fit_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    test_blocks = {
        "title": "Test Workout",
        "blocks": [{
            "structure": "3 rounds",
            "rest_between_sec": 30,
            "supersets": [{
                "exercises": [
                    {"name": "Push Ups", "reps": 10, "sets": 3},
                    {"name": "Squats", "reps": 15, "sets": 3}
                ]
            }]
        }]
    }

    fit_bytes = to_fit(test_blocks)
    print(f"Generated {len(fit_bytes)} bytes")
    
    with open("/tmp/test_v5.fit", "wb") as f:
        f.write(fit_bytes)
    print("Saved to /tmp/test_v5.fit")
