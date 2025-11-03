from fastapi import FastAPI

from pydantic import BaseModel

from backend.adapters.ingest_to_cir import to_cir

from backend.core.canonicalize import canonicalize

from backend.adapters.cir_to_garmin_yaml import to_garmin_yaml

from backend.adapters.blocks_to_hyrox_yaml import to_hyrox_yaml

from backend.core.exercise_suggestions import suggest_alternatives, find_similar_exercises, find_exercises_by_type, categorize_exercise

from backend.core.workflow import validate_workout_mapping, process_workout_with_validation

from backend.core.user_mappings import (
    add_user_mapping,
    remove_user_mapping,
    get_user_mapping,
    get_all_user_mappings,
    clear_all_user_mappings
)

from backend.adapters.blocks_to_hyrox_yaml import load_user_defaults



app = FastAPI()



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

    """Automatically convert blocks JSON to Garmin YAML. Picks best exercise matches automatically - no user interaction needed."""
    yaml_output = to_hyrox_yaml(p.blocks_json)
    
    return {"yaml": yaml_output}


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

    """Save a user-defined mapping: exercise_name -> garmin_name."""
    result = add_user_mapping(p.exercise_name, p.garmin_name)
    return {
        "message": "Mapping saved successfully",
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

