"""
Database module for Supabase integration.
Handles workout storage and retrieval.
"""
import os
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
import logging

logger = logging.getLogger(__name__)

# Initialize Supabase client
def get_supabase_client() -> Optional[Client]:
    """Get Supabase client instance."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    
    if not supabase_url or not supabase_key:
        logger.warning("Supabase credentials not configured. Workout storage will be disabled.")
        return None
    
    try:
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None


def save_workout(
    profile_id: str,
    workout_data: Dict[str, Any],
    sources: List[str],
    device: str,
    exports: Optional[Dict[str, Any]] = None,
    validation: Optional[Dict[str, Any]] = None,
    title: Optional[str] = None,
    description: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Save a workout to Supabase.
    
    Args:
        profile_id: User profile ID
        workout_data: Full workout structure
        sources: List of source strings
        device: Device ID (garmin, apple, zwift, etc.)
        exports: Export formats if available
        validation: Validation response if available
        title: Optional workout title
        description: Optional workout description
        
    Returns:
        Saved workout data or None if failed
    """
    supabase = get_supabase_client()
    if not supabase:
        return None
    
    try:
        data = {
            "profile_id": profile_id,
            "workout_data": workout_data,
            "sources": sources,
            "device": device,
            "is_exported": False,
        }
        
        if exports:
            data["exports"] = exports
        if validation:
            data["validation"] = validation
        if title:
            data["title"] = title
        if description:
            data["description"] = description
        
        result = supabase.table("workouts").insert(data).execute()
        
        if result.data and len(result.data) > 0:
            logger.info(f"Workout saved for profile {profile_id}")
            return result.data[0]
        return None
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to save workout: {e}")
        # Check if it's an RLS/permissions error
        if "PGRST" in error_msg or "permission" in error_msg.lower() or "row-level security" in error_msg.lower():
            logger.error("RLS/Permissions error: Consider using SUPABASE_SERVICE_ROLE_KEY instead of SUPABASE_ANON_KEY for backend API")
        return None


def get_workouts(
    profile_id: str,
    device: Optional[str] = None,
    is_exported: Optional[bool] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get workouts for a user.
    
    Args:
        profile_id: User profile ID
        device: Filter by device (optional)
        is_exported: Filter by export status (optional)
        limit: Maximum number of workouts to return
        
    Returns:
        List of workout records
    """
    supabase = get_supabase_client()
    if not supabase:
        return []
    
    try:
        query = supabase.table("workouts").select("*").eq("profile_id", profile_id)
        
        if device:
            query = query.eq("device", device)
        if is_exported is not None:
            query = query.eq("is_exported", is_exported)
        
        query = query.order("created_at", desc=True).limit(limit)
        
        result = query.execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Failed to get workouts: {e}")
        return []


def get_workout(workout_id: str, profile_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single workout by ID.
    
    Args:
        workout_id: Workout UUID
        profile_id: User profile ID (for security)
        
    Returns:
        Workout data or None if not found
    """
    supabase = get_supabase_client()
    if not supabase:
        return None
    
    try:
        result = supabase.table("workouts").select("*").eq("id", workout_id).eq("profile_id", profile_id).single().execute()
        return result.data if result.data else None
    except Exception as e:
        logger.error(f"Failed to get workout {workout_id}: {e}")
        return None


def update_workout_export_status(
    workout_id: str,
    profile_id: str,
    is_exported: bool = True,
    exported_to_device: Optional[str] = None
) -> bool:
    """
    Update workout export status.
    
    Args:
        workout_id: Workout UUID
        profile_id: User profile ID (for security)
        is_exported: Whether workout has been exported
        exported_to_device: Device ID it was exported to
        
    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase_client()
    if not supabase:
        return False
    
    try:
        from datetime import datetime, timezone
        
        update_data = {
            "is_exported": is_exported,
        }
        
        if is_exported:
            update_data["exported_at"] = datetime.now(timezone.utc).isoformat()
            if exported_to_device:
                update_data["exported_to_device"] = exported_to_device
        else:
            # Clear export info if marking as not exported
            update_data["exported_at"] = None
            update_data["exported_to_device"] = None
        
        result = supabase.table("workouts").update(update_data).eq("id", workout_id).eq("profile_id", profile_id).execute()
        return result.data is not None
    except Exception as e:
        logger.error(f"Failed to update workout export status: {e}")
        return False


def delete_workout(workout_id: str, profile_id: str) -> bool:
    """
    Delete a workout.
    
    Args:
        workout_id: Workout UUID
        profile_id: User profile ID (for security)
        
    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase_client()
    if not supabase:
        logger.error("Supabase client not available")
        return False
    
    try:
        logger.info(f"Attempting to delete workout {workout_id} for profile {profile_id}")
        result = supabase.table("workouts").delete().eq("id", workout_id).eq("profile_id", profile_id).execute()
        
        # Check if any rows were actually deleted
        # Supabase delete() returns result.data with the deleted rows
        deleted_count = len(result.data) if result.data else 0
        
        if deleted_count > 0:
            logger.info(f"Workout {workout_id} deleted successfully ({deleted_count} row(s))")
            return True
        else:
            logger.warning(f"No workout found with id {workout_id} for profile {profile_id} (0 rows deleted)")
            # Check if workout exists with different profile_id (for debugging)
            check_result = supabase.table("workouts").select("id, profile_id").eq("id", workout_id).execute()
            if check_result.data and len(check_result.data) > 0:
                logger.warning(f"Workout {workout_id} exists but belongs to different profile: {check_result.data[0].get('profile_id')}")
            return False
    except Exception as e:
        logger.error(f"Failed to delete workout {workout_id}: {e}")
        return False

