from fastapi import FastAPI

from pydantic import BaseModel

from backend.adapters.ingest_to_cir import to_cir

from backend.core.canonicalize import canonicalize

from backend.adapters.cir_to_garmin_yaml import to_garmin_yaml

from backend.core.exercise_suggestions import suggest_alternatives, find_similar_exercises, find_exercises_by_type, categorize_exercise



app = FastAPI()



class IngestPayload(BaseModel):

    ingest_json: dict



class ExerciseSuggestionRequest(BaseModel):

    exercise_name: str

    include_similar_types: bool = True



@app.post("/map/final")

def map_final(p: IngestPayload):

    cir = canonicalize(to_cir(p.ingest_json))

    return {"yaml": to_garmin_yaml(cir)}


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

