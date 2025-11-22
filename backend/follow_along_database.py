"""
Database module for Follow-Along workout storage in Supabase.
"""
import os
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def get_supabase_client() -> Optional[Client]:
    """Get Supabase client instance."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    
    if not supabase_url or not supabase_key:
        logger.warning("Supabase credentials not configured. Follow-along storage will be disabled.")
        return None
    
    try:
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None


def save_follow_along_workout(
    user_id: str,
    source: str,
    source_url: str,
    title: str,
    description: Optional[str] = None,
    video_duration_sec: Optional[int] = None,
    thumbnail_url: Optional[str] = None,
    video_proxy_url: Optional[str] = None,
    steps: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Save a follow-along workout to Supabase.
    
    Args:
        user_id: User ID
        source: Source type (e.g., "instagram")
        source_url: Original URL
        title: Workout title
        description: Optional description
        video_duration_sec: Video duration in seconds
        thumbnail_url: Thumbnail image URL
        video_proxy_url: Video proxy URL
        steps: List of step dictionaries
        
    Returns:
        Saved workout data or None if failed
    """
    supabase = get_supabase_client()
    if not supabase:
        return None
    
    try:
        # Insert workout
        workout_data = {
            "user_id": user_id,
            "source": source,
            "source_url": source_url,
            "title": title,
            "description": description,
            "video_duration_sec": video_duration_sec,
            "thumbnail_url": thumbnail_url,
            "video_proxy_url": video_proxy_url,
        }
        
        result = supabase.table("follow_along_workouts").insert(workout_data).execute()
        
        if not result.data or len(result.data) == 0:
            return None
        
        workout = result.data[0]
        workout_id = workout["id"]
        
        # Insert steps if provided
        if steps:
            step_records = []
            for idx, step in enumerate(steps):
                # Handle different step formats from ingestor API
                step_order = step.get("order", idx + 1)
                step_label = step.get("label") or step.get("name") or f"Step {step_order}"
                start_sec = step.get("startTimeSec") or step.get("start", 0)
                end_sec = step.get("endTimeSec") or step.get("end", 0)
                duration_sec = step.get("durationSec") or step.get("duration", 0)
                
                # Calculate duration if not provided
                if duration_sec == 0 and end_sec > start_sec:
                    duration_sec = end_sec - start_sec
                
                step_records.append({
                    "follow_along_workout_id": workout_id,
                    "order": step_order,
                    "label": step_label,
                    "canonical_exercise_id": step.get("canonicalExerciseId"),
                    "start_time_sec": start_sec,
                    "end_time_sec": end_sec,
                    "duration_sec": duration_sec,
                    "target_reps": step.get("targetReps"),
                    "target_duration_sec": step.get("targetDurationSec"),
                    "intensity_hint": step.get("intensityHint"),
                    "notes": step.get("notes"),
                })
            
            if step_records:
                supabase.table("follow_along_steps").insert(step_records).execute()
        
        # Fetch complete workout with steps
        return get_follow_along_workout(workout_id, user_id)
        
    except Exception as e:
        logger.error(f"Failed to save follow-along workout: {e}")
        return None


def get_follow_along_workouts(
    user_id: str,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get follow-along workouts for a user.
    
    Args:
        user_id: User ID
        limit: Maximum number of workouts to return
        
    Returns:
        List of workout records with steps
    """
    supabase = get_supabase_client()
    if not supabase:
        return []
    
    try:
        result = supabase.table("follow_along_workouts").select(
            "*, steps:follow_along_steps(*)"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
        
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Failed to get follow-along workouts: {e}")
        return []


def get_follow_along_workout(workout_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single follow-along workout by ID.
    
    Args:
        workout_id: Workout ID
        user_id: User ID (for security)
        
    Returns:
        Workout data with steps or None if not found
    """
    supabase = get_supabase_client()
    if not supabase:
        return None
    
    try:
        result = supabase.table("follow_along_workouts").select(
            "*, steps:follow_along_steps(*)"
        ).eq("id", workout_id).eq("user_id", user_id).single().execute()
        
        if result.data:
            # Sort steps by order
            if "steps" in result.data and result.data["steps"]:
                result.data["steps"].sort(key=lambda x: x.get("order", 0))
            return result.data
        return None
    except Exception as e:
        logger.error(f"Failed to get follow-along workout {workout_id}: {e}")
        return None


def update_follow_along_garmin_sync(
    workout_id: str,
    user_id: str,
    garmin_workout_id: str
) -> bool:
    """
    Update Garmin sync status for a follow-along workout.
    
    Args:
        workout_id: Workout ID
        user_id: User ID (for security)
        garmin_workout_id: Garmin workout ID
        
    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase_client()
    if not supabase:
        return False
    
    try:
        result = supabase.table("follow_along_workouts").update({
            "garmin_workout_id": garmin_workout_id,
            "garmin_last_sync_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", workout_id).eq("user_id", user_id).execute()
        
        return result.data is not None
    except Exception as e:
        logger.error(f"Failed to update Garmin sync: {e}")
        return False


def update_follow_along_apple_watch_sync(
    workout_id: str,
    user_id: str,
    apple_watch_workout_id: str
) -> bool:
    """
    Update Apple Watch sync status for a follow-along workout.
    
    Args:
        workout_id: Workout ID
        user_id: User ID (for security)
        apple_watch_workout_id: Apple Watch workout ID
        
    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase_client()
    if not supabase:
        return False
    
    try:
        result = supabase.table("follow_along_workouts").update({
            "apple_watch_workout_id": apple_watch_workout_id,
            "apple_watch_last_sync_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", workout_id).eq("user_id", user_id).execute()
        
        return result.data is not None
    except Exception as e:
        logger.error(f"Failed to update Apple Watch sync: {e}")
        return False

