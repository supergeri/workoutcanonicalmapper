"""
Workflow functions for processing blocks JSON with exercise validation.
"""
from typing import List, Dict, Optional
from backend.adapters.blocks_to_hyrox_yaml import map_exercise_to_garmin, to_hyrox_yaml
from backend.core.exercise_suggestions import suggest_alternatives


def extract_all_exercises_from_blocks(blocks_json: dict) -> List[Dict]:
    """Extract all exercises from blocks JSON with their metadata."""
    exercises = []
    
    for block_idx, block in enumerate(blocks_json.get("blocks", [])):
        block_label = block.get("label", f"Block {block_idx + 1}")
        
        # From exercises array
        for ex_idx, ex in enumerate(block.get("exercises", [])):
            exercises.append({
                "name": ex.get("name", ""),
                "block": block_label,
                "location": f"exercises[{ex_idx}]",
                "sets": ex.get("sets"),
                "reps": ex.get("reps"),
                "distance_m": ex.get("distance_m"),
                "type": ex.get("type")
            })
        
        # From supersets
        for superset_idx, superset in enumerate(block.get("supersets", [])):
            for ex_idx, ex in enumerate(superset.get("exercises", [])):
                exercises.append({
                    "name": ex.get("name", ""),
                    "block": block_label,
                    "location": f"supersets[{superset_idx}].exercises[{ex_idx}]",
                    "sets": ex.get("sets"),
                    "reps": ex.get("reps"),
                    "distance_m": ex.get("distance_m"),
                    "type": ex.get("type")
                })
    
    return exercises


def validate_workout_mapping(blocks_json: dict, confidence_threshold: float = 0.85) -> Dict:
    """
    Validate workout mapping and identify exercises that need review.
    Returns validation results with suggestions.
    """
    exercises = extract_all_exercises_from_blocks(blocks_json)
    
    results = {
        "total_exercises": len(exercises),
        "validated_exercises": [],
        "needs_review": [],
        "unmapped_exercises": [],
        "can_proceed": True
    }
    
    for ex_info in exercises:
        ex_name = ex_info["name"]
        if not ex_name:
            continue
        
        # Map to Garmin
        garmin_name, description = map_exercise_to_garmin(
            ex_name,
            ex_reps=ex_info.get("reps"),
            ex_distance_m=ex_info.get("distance_m")
        )
        
        # Get suggestions
        suggestions = suggest_alternatives(ex_name, include_similar_types=True)
        
        # Determine status
        best_match = suggestions.get("best_match")
        confidence = best_match["score"] if best_match else 0.0
        
        is_generic = garmin_name and garmin_name.lower() in ['push', 'carry', 'squat', 'plank', 'burpee']
        needs_review = (
            not garmin_name or
            confidence < confidence_threshold or
            is_generic or
            suggestions.get("needs_user_search", False)
        )
        
        ex_result = {
            "original_name": ex_name,
            "mapped_to": garmin_name,
            "confidence": confidence,
            "description": description,
            "block": ex_info["block"],
            "location": ex_info["location"],
            "status": "needs_review" if needs_review else "valid",
            "suggestions": {
                "similar": suggestions.get("similar_exercises", [])[:5],
                "by_type": suggestions.get("exercises_by_type", [])[:10],
                "category": suggestions.get("category"),
                "needs_user_search": suggestions.get("needs_user_search", False)
            }
        }
        
        if needs_review:
            results["needs_review"].append(ex_result)
            if not garmin_name or suggestions.get("needs_user_search"):
                results["unmapped_exercises"].append(ex_result)
        else:
            results["validated_exercises"].append(ex_result)
    
    # If there are unmapped exercises, can't proceed without user input
    if results["unmapped_exercises"]:
        results["can_proceed"] = False
    
    return results


def process_workout_with_validation(blocks_json: dict, auto_proceed: bool = False) -> Dict:
    """
    Complete workflow: validate exercises and optionally generate YAML.
    """
    validation = validate_workout_mapping(blocks_json)
    
    result = {
        "validation": validation,
        "yaml": None,
        "message": None
    }
    
    if validation["can_proceed"] or auto_proceed:
        try:
            yaml_output = to_hyrox_yaml(blocks_json)
            result["yaml"] = yaml_output
            result["message"] = "Workout converted successfully"
        except Exception as e:
            result["message"] = f"Error generating YAML: {str(e)}"
    else:
        result["message"] = f"Please review {len(validation['unmapped_exercises'])} unmapped exercises before proceeding"
    
    return result

