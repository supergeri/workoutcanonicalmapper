from typing import Optional
from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
import logging
import httpx
import os
import json

from pydantic import BaseModel

logger = logging.getLogger(__name__)

from backend.adapters.ingest_to_cir import to_cir

from backend.core.canonicalize import canonicalize

from backend.adapters.cir_to_garmin_yaml import to_garmin_yaml

from backend.adapters.blocks_to_hyrox_yaml import (
    to_hyrox_yaml,
    load_user_defaults,
    map_exercise_to_garmin,
)
from backend.adapters.blocks_to_hiit_garmin_yaml import to_hiit_garmin_yaml, is_hiit_workout
from backend.adapters.blocks_to_workoutkit import to_workoutkit
from backend.adapters.blocks_to_zwo import to_zwo

from backend.core.exercise_suggestions import suggest_alternatives, find_similar_exercises, find_exercises_by_type, categorize_exercise
from backend.core.exercise_categories import add_category_to_exercise_name

from backend.core.workflow import validate_workout_mapping, process_workout_with_validation

from backend.core.user_mappings import (
    add_user_mapping,
    remove_user_mapping,
    get_user_mapping,
    get_all_user_mappings,
    clear_all_user_mappings
)
from backend.core.global_mappings import (
    record_mapping_choice,
    get_popular_mappings,
    get_popularity_stats
)

from backend.database import (
    save_workout,
    get_workouts,
    get_workout,
    update_workout_export_status,
    delete_workout
)
from backend.follow_along_database import (
    save_follow_along_workout,
    get_follow_along_workouts,
    get_follow_along_workout,
    update_follow_along_garmin_sync,
    update_follow_along_apple_watch_sync
)

# Feature flag for unofficial Garmin sync
GARMIN_UNOFFICIAL_SYNC_ENABLED = os.getenv("GARMIN_UNOFFICIAL_SYNC_ENABLED", "false").lower() == "true"



app = FastAPI()

# Garmin export debug flag - log status at startup
GARMIN_EXPORT_DEBUG = os.getenv("GARMIN_EXPORT_DEBUG", "false").lower() == "true"

if GARMIN_EXPORT_DEBUG:
    logger.warning("=== GARMIN_EXPORT_DEBUG ACTIVE (mapper-api) ===")
else:
    logger.info("GARMIN_EXPORT_DEBUG is disabled (mapper-api)")

# Configure CORS to allow requests from the UI and iOS app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "*"],  # Allow all for iOS
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



class IngestPayload(BaseModel):

    ingest_json: dict



class ExerciseSuggestionRequest(BaseModel):

    exercise_name: str

    include_similar_types: bool = True


class BlocksPayload(BaseModel):

    blocks_json: dict



@app.get("/debug/garmin-test")
def test_garmin_debug():
    """
    Test endpoint to verify GARMIN_EXPORT_DEBUG logging is working.
    Returns a simple message and triggers debug logs if enabled.
    """
    if GARMIN_EXPORT_DEBUG:
        logger.warning("=== GARMIN_DEBUG_TEST_ENDPOINT ===")
        print("=== GARMIN_EXPORT_STEP ===")
        print(json.dumps({
            "original_name": "Test Exercise",
            "normalized_name": "test exercise",
            "mapped_name": "Test Exercise",
            "confidence": 1.0,
            "garmin_name_final": "Test Exercise",
            "sets": "N/A",
            "reps": "10",
            "target_type": "reps",
            "target_value": "10"
        }, indent=2))
        
        print("=== GARMIN_CATEGORY_ASSIGN ===")
        print(json.dumps({
            "garmin_name_before": "Test Exercise",
            "assigned_category": "TEST",
            "garmin_name_after": "Test Exercise [category: TEST]"
        }, indent=2))
        
        return {
            "status": "success",
            "message": "GARMIN_EXPORT_DEBUG is ACTIVE - check Docker logs for debug output",
            "debug_enabled": True
        }
    else:
        return {
            "status": "info",
            "message": "GARMIN_EXPORT_DEBUG is disabled - set GARMIN_EXPORT_DEBUG=true to enable",
            "debug_enabled": False
        }

@app.post("/map/final")

def map_final(p: IngestPayload):

    """Convert old format (with exercises array) to Garmin YAML via CIR."""
    cir = canonicalize(to_cir(p.ingest_json))

    return {"yaml": to_garmin_yaml(cir)}


@app.post("/map/auto-map")

def auto_map_workout(p: BlocksPayload):

    """Automatically convert blocks JSON to Garmin YAML. Picks best exercise matches automatically - no user interaction needed.
    Automatically detects HIIT workouts and uses appropriate format."""
    # Check if this is a HIIT workout
    if is_hiit_workout(p.blocks_json):
        yaml_output = to_hiit_garmin_yaml(p.blocks_json)
    else:
        yaml_output = to_hyrox_yaml(p.blocks_json)
    
    return {"yaml": yaml_output}


@app.get("/debug/garmin-test")
def test_garmin_debug():
    """
    Test endpoint to verify GARMIN_EXPORT_DEBUG logging is working.
    Returns a simple message and triggers debug logs if enabled.
    """
    if GARMIN_EXPORT_DEBUG:
        logger.warning("=== GARMIN_DEBUG_TEST_ENDPOINT ===")
        print("=== GARMIN_EXPORT_STEP ===")
        print(json.dumps({
            "original_name": "Test Exercise",
            "normalized_name": "test exercise",
            "mapped_name": "Test Exercise",
            "confidence": 1.0,
            "garmin_name_final": "Test Exercise",
            "sets": "N/A",
            "reps": "10",
            "target_type": "reps",
            "target_value": "10"
        }, indent=2))
        
        print("=== GARMIN_CATEGORY_ASSIGN ===")
        print(json.dumps({
            "garmin_name_before": "Test Exercise",
            "assigned_category": "TEST",
            "garmin_name_after": "Test Exercise [category: TEST]"
        }, indent=2))
        
        return {
            "status": "success",
            "message": "GARMIN_EXPORT_DEBUG is ACTIVE - check Docker logs for debug output",
            "debug_enabled": True
        }
    else:
        return {
            "status": "info",
            "message": "GARMIN_EXPORT_DEBUG is disabled - set GARMIN_EXPORT_DEBUG=true to enable",
            "debug_enabled": False
        }


@app.post("/map/to-hiit")

def map_to_hiit(p: BlocksPayload):

    """Convert blocks JSON to Garmin HIIT workout YAML format.
    Use this endpoint specifically for HIIT workouts (for time, AMRAP, EMOM, etc.)."""
    yaml_output = to_hiit_garmin_yaml(p.blocks_json)
    
    return {"yaml": yaml_output}


@app.post("/map/to-workoutkit")

def map_to_workoutkit(p: BlocksPayload):

    """Convert blocks JSON to Apple WorkoutKit DTO format for creating workouts on Apple Watch."""
    workoutkit_dto = to_workoutkit(p.blocks_json)
    
    return workoutkit_dto.model_dump()


@app.post("/map/to-zwo")

def map_to_zwo(p: BlocksPayload, sport: str = Query(None, description="Sport type: 'run' or 'ride'. Auto-detected if not provided."), format: str = Query("zwo", description="File format: 'zwo' for Zwift, 'xml' for generic XML (TrainingPeaks may accept .xml extension)")):

    """Convert blocks JSON to Zwift ZWO XML format for running or cycling workouts.
    
    Args:
        p: Blocks JSON payload
        sport: Optional sport type ("run" or "ride"). If not provided, will auto-detect from workout content.
        format: File extension - 'zwo' for Zwift, 'xml' for generic XML (some systems prefer .xml)
    
    Returns:
        ZWO XML file download that can be imported into Zwift or TrainingPeaks
    """
    zwo_xml = to_zwo(p.blocks_json, sport=sport)
    
    # Extract workout name for filename
    workout_name = p.blocks_json.get("title", "workout")
    # Sanitize filename: remove invalid characters and limit length
    import re
    safe_name = re.sub(r'[^\w\s-]', '', workout_name).strip()
    safe_name = re.sub(r'[-\s]+', '-', safe_name)[:50]  # Limit to 50 chars
    
    # Use format parameter for file extension
    file_ext = format.lower() if format.lower() in ["zwo", "xml"] else "zwo"
    
    # Return as file download
    return Response(
        content=zwo_xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.{file_ext}"'
        }
    )


# Deprecated endpoints - use /map/auto-map instead
@app.post("/map/workout")

def map_workout(p: BlocksPayload):

    """[Deprecated] Use /map/auto-map instead."""
    return auto_map_workout(p)


@app.post("/map/blocks-to-hyrox")

def map_blocks_to_hyrox(p: BlocksPayload):

    """[Deprecated] Use /map/auto-map instead."""
    return auto_map_workout(p)


@app.post("/workflow/validate")

def validate_workout(p: BlocksPayload):

    """Validate workout mapping and identify exercises needing review."""
    validation = validate_workout_mapping(p.blocks_json)
    
    # Log unmapped exercises for debugging
    unmapped = validation.get("unmapped_exercises", [])
    if unmapped:
        logger.warning(
            f"Validation found {len(unmapped)} unmapped exercises out of {validation.get('total_exercises', 0)} total"
        )
        for ex in unmapped:
            suggestions = ex.get("suggestions", [])
            top_suggestion = suggestions[0] if suggestions else None
            logger.debug(
                f"Unmapped: '{ex.get('original_name')}' "
                f"(confidence: {ex.get('confidence', 0):.2f}, "
                f"top suggestion: {top_suggestion['name'] if top_suggestion else 'none'})"
            )
    
    return validation


@app.post("/workflow/process")

def process_workout(p: BlocksPayload, auto_proceed: bool = True):

    """Complete workflow: validate exercises and generate YAML. Defaults to auto-proceed with best matches."""
    result = process_workout_with_validation(p.blocks_json, auto_proceed=auto_proceed)
    return result


@app.post("/workflow/process-with-review")

def process_workout_with_review(p: BlocksPayload):

    """Process workout but require review of unmapped exercises (stricter validation)."""
    result = process_workout_with_validation(p.blocks_json, auto_proceed=False)
    return result


@app.post("/exercise/suggest")

def suggest_exercise(p: ExerciseSuggestionRequest):

    """Get exercise suggestions and alternatives from Garmin database."""
    suggestions = suggest_alternatives(
        p.exercise_name, 
        include_similar_types=p.include_similar_types
    )
    return suggestions


@app.get("/exercise/similar/{exercise_name}")

def get_similar_exercises(exercise_name: str, limit: int = 10):

    """Get similar exercises to the given name."""
    return {
        "exercise_name": exercise_name,
        "similar": find_similar_exercises(exercise_name, limit=limit)
    }


@app.get("/exercise/by-type/{exercise_name}")

def get_exercises_by_type(exercise_name: str, limit: int = 20):

    """Get all exercises of the same type (e.g., all squats)."""
    category = categorize_exercise(exercise_name)
    exercises = find_exercises_by_type(exercise_name, limit=limit)
    return {
        "exercise_name": exercise_name,
        "category": category,
        "exercises": exercises
    }


class UserMappingRequest(BaseModel):

    exercise_name: str

    garmin_name: str


@app.post("/mappings/add")

def save_mapping(p: UserMappingRequest):

    """Save a user-defined mapping: exercise_name -> garmin_name. Also records global popularity."""
    # Save user's personal mapping
    result = add_user_mapping(p.exercise_name, p.garmin_name)
    
    # Also record in global popularity (crowd-sourced)
    record_mapping_choice(p.exercise_name, p.garmin_name)
    
    return {
        "message": "Mapping saved successfully (also recorded for global popularity)",
        "mapping": result
    }


@app.delete("/mappings/remove/{exercise_name}")

def delete_mapping(exercise_name: str):

    """Remove a user-defined mapping."""
    removed = remove_user_mapping(exercise_name)
    if removed:
        return {"message": f"Mapping for '{exercise_name}' removed successfully"}
    else:
        return {"message": f"No mapping found for '{exercise_name}'"}


@app.get("/mappings")

def list_mappings():

    """Get all user-defined mappings."""
    mappings = get_all_user_mappings()
    return {
        "total": len(mappings),
        "mappings": mappings
    }


@app.get("/mappings/lookup/{exercise_name}")

def lookup_mapping(exercise_name: str):

    """Check if a user mapping exists for an exercise."""
    garmin_name = get_user_mapping(exercise_name)
    if garmin_name:
        return {
            "exercise_name": exercise_name,
            "mapped_to": garmin_name,
            "exists": True
        }
    else:
        return {
            "exercise_name": exercise_name,
            "mapped_to": None,
            "exists": False
        }


@app.delete("/mappings/clear")

def clear_mappings():

    """Clear all user mappings."""
    clear_all_user_mappings()
    return {"message": "All user mappings cleared successfully"}


@app.get("/mappings/popularity/stats")

def get_popularity_stats_endpoint():

    """Get statistics about global mapping popularity (crowd-sourced choices)."""
    stats = get_popularity_stats()
    return stats


@app.get("/mappings/popularity/{exercise_name}")

def get_exercise_popularity(exercise_name: str):

    """Get popular mappings for a specific exercise."""
    popular = get_popular_mappings(exercise_name, limit=10)
    return {
        "exercise_name": exercise_name,
        "popular_mappings": [{"garmin_name": garmin, "count": count} for garmin, count in popular]
    }


@app.post("/mappings/popularity/record")

def record_mapping_choice_endpoint(p: UserMappingRequest):

    """Record a mapping choice for global popularity (without saving as personal mapping)."""
    record_mapping_choice(p.exercise_name, p.garmin_name)
    return {
        "message": "Mapping choice recorded for global popularity",
        "exercise_name": p.exercise_name,
        "garmin_name": p.garmin_name
    }


class UserDefaultsRequest(BaseModel):

    distance_handling: str = "lap"  # "lap" or "distance"
    default_exercise_value: str = "lap"  # "lap" or "button"
    ignore_distance: bool = True


@app.get("/settings/defaults")

def get_defaults():

    """Get current user default settings."""
    return load_user_defaults()


@app.put("/settings/defaults")

def update_defaults(p: UserDefaultsRequest):

    """Update user default settings."""
    import yaml
    import pathlib
    
    ROOT = pathlib.Path(__file__).resolve().parents[2]
    USER_DEFAULTS_FILE = ROOT / "shared/settings/user_defaults.yaml"
    
    # Create directory if needed
    USER_DEFAULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Save settings
    data = {
        "defaults": {
            "distance_handling": p.distance_handling,
            "default_exercise_value": p.default_exercise_value,
            "ignore_distance": p.ignore_distance
        }
    }
    
    with open(USER_DEFAULTS_FILE, 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)
    
    return {
        "message": "Settings updated successfully",
        "settings": data["defaults"]
    }


# ============================================================================
# Workout Storage Endpoints
# ============================================================================

class SaveWorkoutRequest(BaseModel):
    profile_id: str
    workout_data: dict
    sources: list[str] = []
    device: str
    exports: dict = None
    validation: dict = None
    title: str = None
    description: str = None


class UpdateWorkoutExportRequest(BaseModel):
    profile_id: str
    is_exported: bool = True
    exported_to_device: str = None


@app.post("/workouts/save")
def save_workout_endpoint(request: SaveWorkoutRequest):
    """Save a workout to Supabase before syncing to device."""
    result = save_workout(
        profile_id=request.profile_id,
        workout_data=request.workout_data,
        sources=request.sources,
        device=request.device,
        exports=request.exports,
        validation=request.validation,
        title=request.title,
        description=request.description
    )
    
    if result:
        return {
            "success": True,
            "workout_id": result.get("id"),
            "message": "Workout saved successfully"
        }
    else:
        return {
            "success": False,
            "message": "Failed to save workout. Check server logs."
        }


@app.get("/workouts")
def get_workouts_endpoint(
    profile_id: str = Query(..., description="User profile ID"),
    device: str = Query(None, description="Filter by device"),
    is_exported: bool = Query(None, description="Filter by export status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of workouts")
):
    """Get workouts for a user, optionally filtered by device and export status."""
    workouts = get_workouts(
        profile_id=profile_id,
        device=device,
        is_exported=is_exported,
        limit=limit
    )
    
    return {
        "success": True,
        "workouts": workouts,
        "count": len(workouts)
    }


@app.get("/workouts/{workout_id}")
def get_workout_endpoint(
    workout_id: str,
    profile_id: str = Query(..., description="User profile ID")
):
    """Get a single workout by ID."""
    workout = get_workout(workout_id, profile_id)
    
    if workout:
        return {
            "success": True,
            "workout": workout
        }
    else:
        return {
            "success": False,
            "message": "Workout not found"
        }


@app.put("/workouts/{workout_id}/export-status")
def update_workout_export_endpoint(workout_id: str, request: UpdateWorkoutExportRequest):
    """Update workout export status after syncing to device."""
    success = update_workout_export_status(
        workout_id=workout_id,
        profile_id=request.profile_id,
        is_exported=request.is_exported,
        exported_to_device=request.exported_to_device
    )
    
    if success:
        return {
            "success": True,
            "message": "Export status updated successfully"
        }
    else:
        return {
            "success": False,
            "message": "Failed to update export status"
        }


@app.delete("/workouts/{workout_id}")
def delete_workout_endpoint(
    workout_id: str,
    profile_id: str = Query(..., description="User profile ID")
):
    """Delete a workout."""
    success = delete_workout(workout_id, profile_id)
    
    if success:
        return {
            "success": True,
            "message": "Workout deleted successfully"
        }
    else:
        return {
            "success": False,
            "message": "Failed to delete workout"
        }


# ============================================================================
# Follow-Along Workout Endpoints
# ============================================================================

class IngestFollowAlongRequest(BaseModel):
    instagramUrl: str
    userId: str


class PushToGarminRequest(BaseModel):
    userId: str
    scheduleDate: Optional[str] = None  # YYYY-MM-DD format, or None for immediate import


class PushToAppleWatchRequest(BaseModel):
    userId: str


@app.post("/follow-along/ingest")
def ingest_follow_along_endpoint(request: IngestFollowAlongRequest):
    """
    Ingest a follow-along workout from Instagram URL.
    Calls workout-ingestor-api to extract workout data, then stores in Supabase.
    """
    import httpx
    import os
    
    ingestor_url = os.getenv("INGESTOR_URL", "http://workout-ingestor-api:8004")
    
    try:
        # Call workout-ingestor-api
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{ingestor_url}/ingest/instagram_test",
                json={
                    "url": request.instagramUrl,
                    "use_vision": True,
                    "vision_provider": "openai",
                    "vision_model": "gpt-4o-mini",
                }
            )
            response.raise_for_status()
            ingestor_data = response.json()
        
        # Save to Supabase
        workout = save_follow_along_workout(
            user_id=request.userId,
            source="instagram",
            source_url=request.instagramUrl,
            title=ingestor_data.get("title", "Instagram Workout"),
            description=ingestor_data.get("description"),
            video_duration_sec=ingestor_data.get("videoDuration"),
            thumbnail_url=ingestor_data.get("thumbnail"),
            video_proxy_url=ingestor_data.get("videoUrl"),
            steps=ingestor_data.get("steps", [])
        )
        
        if workout:
            return {
                "success": True,
                "followAlongWorkout": workout
            }
        else:
            return {
                "success": False,
                "message": "Failed to save workout to database"
            }
    except Exception as e:
        logger.error(f"Failed to ingest follow-along workout: {e}")
        return {
            "success": False,
            "message": str(e)
        }


@app.get("/follow-along")
def list_follow_along_endpoint(
    userId: str = Query(..., description="User ID")
):
    """List all follow-along workouts for a user."""
    workouts = get_follow_along_workouts(user_id=userId)
    
    return {
        "success": True,
        "items": workouts
    }


@app.get("/follow-along/{workout_id}")
def get_follow_along_endpoint(
    workout_id: str,
    userId: str = Query(..., description="User ID")
):
    """Get a single follow-along workout by ID."""
    workout = get_follow_along_workout(workout_id, userId)
    
    if workout:
        return {
            "success": True,
            "followAlongWorkout": workout
        }
    else:
        return {
            "success": False,
            "message": "Workout not found"
        }


# Idempotency registry (in-memory — fine for dev)
FOLLOW_ALONG_SYNC_CACHE = {}

def has_synced_before(workout_id: str, user_id: str, title: str):
    key = f"{user_id}:{workout_id}:{title}"
    return FOLLOW_ALONG_SYNC_CACHE.get(key) is True

def mark_synced(workout_id: str, user_id: str, title: str):
    key = f"{user_id}:{workout_id}:{title}"
    FOLLOW_ALONG_SYNC_CACHE[key] = True

@app.post("/follow-along/{workout_id}/push/garmin")
def push_to_garmin_endpoint(workout_id: str, request: PushToGarminRequest):
    """
    Push follow-along workout to Garmin via garmin-sync-api.

    - Respects GARMIN_UNOFFICIAL_SYNC_ENABLED.
    - Uses the same exercise mapping pipeline as YAML export
      (map_exercise_to_garmin + add_category_to_exercise_name).
    - Sends steps in the format expected by the unofficial Garmin Sync API:
      { "Garmin Exercise Name [category: XYZ]": "10 reps" } or "60s".
    - Prevents duplicate syncs using idempotency key.
    """
    import httpx
    import json

    # Backend guard for unofficial API
    if not GARMIN_UNOFFICIAL_SYNC_ENABLED:
        return {
            "success": False,
            "status": "error",
            "message": "Unofficial Garmin sync is disabled. Set GARMIN_UNOFFICIAL_SYNC_ENABLED=true to use this endpoint.",
        }

    # Get workout
    workout = get_follow_along_workout(workout_id, request.userId)
    if not workout:
        return {
            "success": False,
            "status": "error",
            "message": "Workout not found",
        }

    # Prevent duplicate syncs
    if has_synced_before(workout_id, request.userId, workout.get("title", "")):
        return {
            "success": True,
            "status": "already_synced",
            "message": "This workout was already synced to Garmin.",
            "garminWorkoutId": workout.get("title", ""),
        }

    # Get Garmin credentials from environment
    garmin_email = os.getenv("GARMIN_EMAIL")
    garmin_password = os.getenv("GARMIN_PASSWORD")

    if not garmin_email or not garmin_password:
        return {
            "success": False,
            "status": "error",
            "message": "Garmin credentials not configured. Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables.",
        }

    steps: list[dict[str, str]] = []

    def build_step_from_follow_along_step(step: dict):
        """
        Build a single Garmin step from a follow-along step.

        Follow-along structure:
        - label: exercise label/name
        - target_reps: optional reps
        - duration_sec: optional duration in seconds
        """
        ex_name = step.get("label", "") or ""
        if not ex_name:
            return None

        reps = step.get("target_reps")
        duration = step.get("duration_sec")

        # In follow-along there is no pre-validated mapped_name, so we just use the label
        mapped_name = None
        candidate_names = [ex_name]

        garmin_name, _description, mapping_info = map_exercise_to_garmin(
            ex_name,
            ex_reps=reps,
            ex_distance_m=None,
            mapped_name=mapped_name,
            candidate_names=candidate_names,
        )

        garmin_name_with_category = add_category_to_exercise_name(garmin_name)

        if reps:
            step_detail = f"{reps} reps"
        elif duration:
            step_detail = f"{duration}s"
        else:
            step_detail = "10 reps"

        step_obj = {garmin_name_with_category: step_detail}

        logger.info(
            "GARMIN_SYNC_FOLLOW_STEP original=%r garmin=%r detail=%r source=%s conf=%s",
            ex_name,
            garmin_name_with_category,
            step_detail,
            mapping_info.get("source"),
            mapping_info.get("confidence"),
        )

        return step_obj

    # Build steps list from follow-along workout steps
    for step in workout.get("steps", []):
        garmin_step = build_step_from_follow_along_step(step)
        if garmin_step:
            steps.append(garmin_step)

    if not steps:
        return {
            "success": False,
            "status": "error",
            "message": "No valid steps found to sync",
        }

    garmin_workouts = {
        workout["title"]: steps,
    }

    garmin_url = os.getenv("GARMIN_SERVICE_URL", "http://garmin-sync-api:8002")

    garmin_payload = {
        "email": garmin_email,
        "password": garmin_password,
        "workouts": garmin_workouts,
        "delete_same_name": False,
    }

    # Compare YAML export vs Follow-Along export
    try:
        # Convert follow-along workout to blocks format for YAML export
        blocks_json = {
            "title": workout["title"],
            "blocks": [{
                "label": "Main Block",
                "structure": "",
                "exercises": [
                    {
                        "name": step.get("label", ""),
                        "reps": step.get("target_reps"),
                        "duration_sec": step.get("duration_sec"),
                    }
                    for step in workout.get("steps", [])
                ]
            }]
        }
        yaml_export = to_hyrox_yaml(blocks_json)
        
        if GARMIN_EXPORT_DEBUG:
            print("=== GARMIN_EXPORT_VS_FOLLOW_ALONG_COMPARISON ===")
            print(json.dumps({
                "yaml_export": yaml_export,
                "follow_along_payload": garmin_payload
            }, indent=2))
    except Exception as e:
        if GARMIN_EXPORT_DEBUG:
            print("=== COMPARISON_ERROR ===", str(e))

    # Debug logging for sync payload
    if GARMIN_EXPORT_DEBUG:
        print("=== GARMIN_SYNC_PAYLOAD ===")
        print(json.dumps(garmin_payload, indent=2))

    try:
        with httpx.Client(timeout=30.0) as client:
            # Import workout
            logger.info("GARMIN_SYNC_FOLLOW_IMPORT payload=%s", json.dumps(garmin_payload, indent=2))
            response = client.post(f"{garmin_url}/workouts/import", json=garmin_payload)
            response.raise_for_status()

            # If scheduleDate is provided, schedule the workout
            if request.scheduleDate:
                schedule_date = request.scheduleDate
                schedule_payload = {
                    "email": garmin_email,
                    "password": garmin_password,
                    "start_from": schedule_date,
                    "workouts": [workout["title"]],
                }
                logger.info("GARMIN_SYNC_FOLLOW_SCHEDULE payload=%s", json.dumps(schedule_payload, indent=2))
                schedule_response = client.post(
                    f"{garmin_url}/workouts/schedule",
                    json=schedule_payload,
                )
                schedule_response.raise_for_status()

        garmin_workout_id = workout["title"]

        # Mark as synced to prevent duplicates
        mark_synced(workout_id, request.userId, workout["title"])

        # Update sync status
        update_follow_along_garmin_sync(
            workout_id=workout_id,
            user_id=request.userId,
            garmin_workout_id=garmin_workout_id,
        )

        return {
            "success": True,
            "status": "success",
            "garminWorkoutId": garmin_workout_id,
        }
    except Exception as e:
        logger.error(f"Failed to push follow-along workout to Garmin: {e}")
        return {
            "success": False,
            "status": "error",
            "message": str(e),
        }



@app.post("/workout/sync/garmin")
def sync_workout_to_garmin(request: dict):
    """
    Sync a regular workout to Garmin Connect via garmin-sync-api.

    - Respects GARMIN_UNOFFICIAL_SYNC_ENABLED.
    - Uses the same exercise mapping pipeline as the YAML export
      (map_exercise_to_garmin + add_category_to_exercise_name), so
      Garmin receives valid exercise names instead of generic steps.
    """
    import httpx
    import json

    logger = logging.getLogger(__name__)

    # Backend guard for unofficial API
    if not GARMIN_UNOFFICIAL_SYNC_ENABLED:
        return {
            "success": False,
            "status": "error",
            "message": "Unofficial Garmin sync is disabled. Set GARMIN_UNOFFICIAL_SYNC_ENABLED=true to use this endpoint.",
        }

    # Get workout data from request
    blocks_json = request.get("blocks_json")
    workout_title = request.get("workout_title", "Workout")
    schedule_date = request.get("schedule_date")

    if not blocks_json:
        return {
            "success": False,
            "status": "error",
            "message": "Workout data is required",
        }

    # Get Garmin credentials from environment
    garmin_email = os.getenv("GARMIN_EMAIL")
    garmin_password = os.getenv("GARMIN_PASSWORD")

    if not garmin_email or not garmin_password:
        return {
            "success": False,
            "status": "error",
            "message": "Garmin credentials not configured. Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables.",
        }

    steps: list[dict[str, str]] = []

    def build_step_from_exercise(exercise: dict):
        """Build a single Garmin step (garmin_name_with_category -> '10 reps' / '60s')."""
        ex_name = exercise.get("name", "") or ""
        if not ex_name:
            return None

        reps = exercise.get("reps")
        reps_range = exercise.get("reps_range")
        duration = exercise.get("duration_sec")
        distance_m = exercise.get("distance_m")

        # Use validated mapped_name if available
        mapped_name = exercise.get("mapped_name") or exercise.get("mapped_to")
        candidate_names: list[str] = []
        if mapped_name:
            candidate_names.append(mapped_name)
        candidate_names.append(ex_name)

        # Reuse the same mapping pipeline as blocks_to_hyrox_yaml
        # Note: map_exercise_to_garmin signature: (ex_name, ex_reps=None, ex_distance_m=None, use_user_mappings=True)
        # Use mapped_name as the primary name if available
        exercise_name_to_map = mapped_name if mapped_name else ex_name
        garmin_name, _description, mapping_info = map_exercise_to_garmin(
            exercise_name_to_map,
            ex_reps=reps,
            ex_distance_m=distance_m,
        )

        garmin_name_with_category = add_category_to_exercise_name(garmin_name)

        # End condition: keep it simple for the sync API (no "lap |" decorations here)
        if reps:
            step_detail = f"{reps} reps"
        elif reps_range:
            step_detail = f"{reps_range} reps"
        elif duration:
            step_detail = f"{duration}s"
        elif distance_m:
            step_detail = f"{distance_m}m"
        else:
            step_detail = "10 reps"

        step = {garmin_name_with_category: step_detail}

        logger.info(
            "GARMIN_SYNC_STEP original=%r mapped_name=%r garmin=%r detail=%r source=%s conf=%s",
            ex_name,
            mapped_name,
            garmin_name_with_category,
            step_detail,
            mapping_info.get("source"),
            mapping_info.get("confidence"),
        )

        return step

    # Walk through blocks / exercises / supersets and build steps list
    for block in blocks_json.get("blocks", []):
        # Standalone exercises
        for exercise in block.get("exercises", []):
            step = build_step_from_exercise(exercise)
            if step:
                steps.append(step)

        # Supersets
        for superset in block.get("supersets", []):
            for exercise in superset.get("exercises", []):
                step = build_step_from_exercise(exercise)
                if step:
                    steps.append(step)

    if not steps:
        return {
            "success": False,
            "status": "error",
            "message": "No valid exercises found to sync",
        }

    # Final workouts payload for garmin-sync-api
    garmin_workouts = {workout_title: steps}

    garmin_url = os.getenv("GARMIN_SERVICE_URL", "http://garmin-sync-api:8002")

    garmin_payload = {
        "email": garmin_email,
        "password": garmin_password,
        "workouts": garmin_workouts,
        "delete_same_name": False,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            # Import workout
            logger.info("GARMIN_SYNC_IMPORT payload=%s", json.dumps(garmin_payload, indent=2))
            response = client.post(f"{garmin_url}/workouts/import", json=garmin_payload)
            response.raise_for_status()

            # Optionally schedule the workout
            if schedule_date:
                schedule_payload = {
                    "email": garmin_email,
                    "password": garmin_password,
                    "start_from": schedule_date,
                    "workouts": [workout_title],
                }
                logger.info("GARMIN_SYNC_SCHEDULE payload=%s", json.dumps(schedule_payload, indent=2))
                schedule_response = client.post(
                    f"{garmin_url}/workouts/schedule",
                    json=schedule_payload,
                )
                schedule_response.raise_for_status()

        return {
            "success": True,
            "status": "success",
            "message": "Workout synced to Garmin successfully",
            "garminWorkoutId": workout_title,
        }
    except Exception as e:
        logger.error(f"Failed to sync workout to Garmin: {e}")
        return {
            "success": False,
            "status": "error",
            "message": str(e),
        }

@app.post("/follow-along/{workout_id}/push/apple-watch")
def push_to_apple_watch_endpoint(workout_id: str, request: PushToAppleWatchRequest):
    """
    Push follow-along workout to Apple Watch.
    Returns payload that can be sent via WatchConnectivity.
    """
    # Get workout
    workout = get_follow_along_workout(workout_id, request.userId)
    if not workout:
        return {
            "success": False,
            "status": "error",
            "message": "Workout not found"
        }
    
    # Create payload for Apple Watch
    payload = {
        "id": workout["id"],
        "title": workout["title"],
        "steps": [
            {
                "order": step.get("order", 0),
                "label": step.get("label", ""),
                "durationSec": step.get("duration_sec", 0)
            }
            for step in workout.get("steps", [])
        ]
    }
    
    # Update sync status
    update_follow_along_apple_watch_sync(
        workout_id=workout_id,
        user_id=request.userId,
        apple_watch_workout_id=workout_id
    )
    
    return {
        "success": True,
        "status": "success",
        "appleWatchWorkoutId": workout_id,
        "payload": payload
    }

