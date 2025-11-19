from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from backend.adapters.ingest_to_cir import to_cir

from backend.core.canonicalize import canonicalize

from backend.adapters.cir_to_garmin_yaml import to_garmin_yaml

from backend.adapters.blocks_to_hyrox_yaml import to_hyrox_yaml
from backend.adapters.blocks_to_hiit_garmin_yaml import to_hiit_garmin_yaml, is_hiit_workout
from backend.adapters.blocks_to_workoutkit import to_workoutkit
from backend.adapters.blocks_to_zwo import to_zwo

from backend.core.exercise_suggestions import suggest_alternatives, find_similar_exercises, find_exercises_by_type, categorize_exercise

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

from backend.adapters.blocks_to_hyrox_yaml import load_user_defaults



app = FastAPI()

# Configure CORS to allow requests from the UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
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

