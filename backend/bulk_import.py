"""
Bulk Import Service
AMA-100: Bulk Import Controller & State Management

Handles the 5-step bulk import workflow:
1. Detect - Parse sources and detect workout items
2. Map - Apply column mappings (for files)
3. Match - Match exercises to Garmin database
4. Preview - Generate preview of workouts
5. Import - Execute the import

This module provides:
- Pydantic models for API requests/responses
- BulkImportService class for orchestrating the workflow
- Database operations for job tracking
"""

import uuid
import base64
import asyncio
import logging
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from backend.parsers import (
    FileParserFactory,
    FileInfo,
    ParseResult,
    ParsedWorkout,
    URLParser,
    fetch_url_metadata_batch,
    ImageParser,
    parse_images_batch,
    is_supported_image,
)
from backend.core.garmin_matcher import find_garmin_exercise, get_garmin_suggestions

logger = logging.getLogger(__name__)

# ============================================================================
# Exercise Matching Constants
# ============================================================================

# Confidence thresholds for exercise matching
MATCH_AUTO_THRESHOLD = 0.90      # 90%+ = auto-match
MATCH_REVIEW_THRESHOLD = 0.70    # 70-90% = needs review
MATCH_UNMAPPED_THRESHOLD = 0.50  # <50% = unmapped/new

# ============================================================================
# Pydantic Models
# ============================================================================

class DetectedItem(BaseModel):
    """Detected item from file/URL/image parsing"""
    id: str
    source_index: int
    source_type: str
    source_ref: str
    raw_data: Dict[str, Any]
    parsed_title: Optional[str] = None
    parsed_exercise_count: Optional[int] = None
    parsed_block_count: Optional[int] = None
    confidence: float = 0
    errors: Optional[List[str]] = None
    warnings: Optional[List[str]] = None


class ColumnMapping(BaseModel):
    """Column mapping for file imports"""
    source_column: str
    source_column_index: int
    target_field: str
    confidence: float = 0
    user_override: bool = False
    sample_values: List[str] = []


class DetectedPattern(BaseModel):
    """Detected pattern in the data"""
    pattern_type: str
    regex: Optional[str] = None
    confidence: float = 0
    examples: List[str] = []
    count: int = 0


class ExerciseMatch(BaseModel):
    """Exercise matching result"""
    id: str
    original_name: str
    matched_garmin_name: Optional[str] = None
    confidence: float = 0
    suggestions: List[Dict[str, Any]] = []
    status: Literal["matched", "needs_review", "unmapped", "new"] = "unmapped"
    user_selection: Optional[str] = None
    source_workout_ids: List[str] = []
    occurrence_count: int = 1


class ValidationIssue(BaseModel):
    """Validation issue found during preview"""
    id: str
    severity: Literal["error", "warning", "info"]
    field: str
    message: str
    workout_id: Optional[str] = None
    exercise_name: Optional[str] = None
    suggestion: Optional[str] = None
    auto_fixable: bool = False


class PreviewWorkout(BaseModel):
    """Preview workout before import"""
    id: str
    detected_item_id: str
    title: str
    description: Optional[str] = None
    exercise_count: int = 0
    block_count: int = 0
    estimated_duration: Optional[int] = None
    validation_issues: List[ValidationIssue] = []
    workout: Dict[str, Any] = {}
    selected: bool = True
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None


class ImportStats(BaseModel):
    """Import statistics for preview"""
    total_detected: int = 0
    total_selected: int = 0
    total_skipped: int = 0
    exercises_matched: int = 0
    exercises_needing_review: int = 0
    exercises_unmapped: int = 0
    new_exercises_to_create: int = 0
    estimated_duration: int = 0
    duplicates_found: int = 0
    validation_errors: int = 0
    validation_warnings: int = 0


class ImportResult(BaseModel):
    """Import result for a single workout"""
    workout_id: str
    title: str
    status: Literal["success", "failed", "skipped"]
    error: Optional[str] = None
    saved_workout_id: Optional[str] = None
    export_formats: Optional[List[str]] = None


# API Request/Response Models

class BulkDetectRequest(BaseModel):
    """Request to detect workout items from sources"""
    profile_id: str
    source_type: Literal["file", "urls", "images"]
    sources: List[str]  # URLs, file content (base64), or image data


class BulkDetectResponse(BaseModel):
    """Response from detect endpoint"""
    success: bool
    job_id: str
    items: List[DetectedItem]
    metadata: Dict[str, Any] = {}
    total: int
    success_count: int
    error_count: int


class BulkMapRequest(BaseModel):
    """Request to apply column mappings"""
    job_id: str
    profile_id: str
    column_mappings: List[ColumnMapping]


class BulkMapResponse(BaseModel):
    """Response from map endpoint"""
    success: bool
    job_id: str
    mapped_count: int
    patterns: List[DetectedPattern] = []


class BulkMatchRequest(BaseModel):
    """Request to match exercises"""
    job_id: str
    profile_id: str
    user_mappings: Optional[Dict[str, str]] = None  # original_name -> selected_garmin_name


class BulkMatchResponse(BaseModel):
    """Response from match endpoint"""
    success: bool
    job_id: str
    exercises: List[ExerciseMatch]
    total_exercises: int
    matched: int
    needs_review: int
    unmapped: int


class BulkPreviewRequest(BaseModel):
    """Request to generate preview"""
    job_id: str
    profile_id: str
    selected_ids: List[str]


class BulkPreviewResponse(BaseModel):
    """Response from preview endpoint"""
    success: bool
    job_id: str
    workouts: List[PreviewWorkout]
    stats: ImportStats


class BulkExecuteRequest(BaseModel):
    """Request to execute import"""
    job_id: str
    profile_id: str
    workout_ids: List[str]
    device: str
    async_mode: bool = True


class BulkExecuteResponse(BaseModel):
    """Response from execute endpoint"""
    success: bool
    job_id: str
    status: str
    message: str


class BulkStatusResponse(BaseModel):
    """Response from status endpoint"""
    success: bool
    job_id: str
    status: str
    progress: int
    current_item: Optional[str] = None
    results: List[ImportResult] = []
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================================================
# Bulk Import Service
# ============================================================================

class BulkImportService:
    """
    Service for orchestrating the 5-step bulk import workflow.

    This service manages:
    - Job creation and tracking
    - Source detection and parsing
    - Column mapping (for file imports)
    - Exercise matching
    - Preview generation
    - Import execution with progress tracking
    """

    def __init__(self):
        self.supabase = self._get_supabase_client()

    def _get_supabase_client(self):
        """Get Supabase client from database module"""
        try:
            from backend.database import get_supabase_client
            return get_supabase_client()
        except Exception as e:
            logger.warning(f"Could not get Supabase client: {e}")
            return None

    def _patterns_to_list(self, patterns) -> List[Dict[str, Any]]:
        """Convert DetectedPatterns object to a list of pattern dicts"""
        result = []
        if patterns:
            if patterns.supersets:
                result.append({"type": "supersets", **patterns.supersets.model_dump()})
            if patterns.complex_movements:
                result.append({"type": "complex_movements", **patterns.complex_movements.model_dump()})
            if patterns.duration_exercises:
                result.append({"type": "duration_exercises", **patterns.duration_exercises.model_dump()})
            if patterns.percentage_weights:
                result.append({"type": "percentage_weights", **patterns.percentage_weights.model_dump()})
            if patterns.warmup_sets:
                result.append({"type": "warmup_sets", **patterns.warmup_sets.model_dump()})
        return result

    # ========================================================================
    # Job Management
    # ========================================================================

    def _create_job(
        self,
        profile_id: str,
        input_type: str,
        total_items: int = 0
    ) -> str:
        """Create a new bulk import job"""
        job_id = str(uuid.uuid4())

        if self.supabase:
            try:
                self.supabase.table("bulk_import_jobs").insert({
                    "id": job_id,
                    "profile_id": profile_id,
                    "input_type": input_type,
                    "status": "pending",
                    "total_items": total_items,
                    "processed_items": 0,
                    "results": [],
                }).execute()
            except Exception as e:
                logger.error(f"Failed to create job in database: {e}")

        return job_id

    def _update_job_status(
        self,
        job_id: str,
        profile_id: str,
        status: str,
        **kwargs
    ) -> bool:
        """Update job status and optional fields"""
        if not self.supabase:
            return False

        try:
            update_data = {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            update_data.update(kwargs)

            if status in ("complete", "failed", "cancelled"):
                update_data["completed_at"] = datetime.now(timezone.utc).isoformat()

            self.supabase.table("bulk_import_jobs").update(update_data)\
                .eq("id", job_id)\
                .eq("profile_id", profile_id)\
                .execute()

            return True
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
            return False

    def _update_job_progress(
        self,
        job_id: str,
        profile_id: str,
        processed_items: int,
        current_item: Optional[str] = None
    ) -> bool:
        """Update job progress"""
        if not self.supabase:
            return False

        try:
            self.supabase.table("bulk_import_jobs").update({
                "processed_items": processed_items,
                "current_item": current_item,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", job_id).eq("profile_id", profile_id).execute()

            return True
        except Exception as e:
            logger.error(f"Failed to update job progress: {e}")
            return False

    def _get_job(self, job_id: str, profile_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID"""
        if not self.supabase:
            return None

        try:
            result = self.supabase.table("bulk_import_jobs")\
                .select("*")\
                .eq("id", job_id)\
                .eq("profile_id", profile_id)\
                .single()\
                .execute()

            return result.data if result.data else None
        except Exception as e:
            logger.error(f"Failed to get job: {e}")
            return None

    # ========================================================================
    # Detected Items Management
    # ========================================================================

    def _store_detected_items(
        self,
        job_id: str,
        profile_id: str,
        items: List[Dict[str, Any]]
    ) -> bool:
        """Store detected items in database"""
        if not self.supabase or not items:
            return False

        try:
            records = [
                {
                    "id": item.get("id", str(uuid.uuid4())),
                    "job_id": job_id,
                    "profile_id": profile_id,
                    "source_index": item.get("source_index", idx),
                    "source_type": item.get("source_type", "file"),
                    "source_ref": item.get("source_ref", ""),
                    "raw_data": item.get("raw_data", {}),
                    "parsed_workout": item.get("parsed_workout"),
                    "confidence": item.get("confidence", 0),
                    "errors": item.get("errors", []),
                    "warnings": item.get("warnings", []),
                }
                for idx, item in enumerate(items)
            ]

            self.supabase.table("bulk_import_detected_items").insert(records).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to store detected items: {e}")
            return False

    def _get_detected_items(
        self,
        job_id: str,
        profile_id: str,
        selected_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Get detected items for a job"""
        if not self.supabase:
            return []

        try:
            query = self.supabase.table("bulk_import_detected_items")\
                .select("*")\
                .eq("job_id", job_id)\
                .eq("profile_id", profile_id)\
                .order("source_index")

            if selected_only:
                query = query.eq("selected", True)

            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to get detected items: {e}")
            return []

    def _update_detected_item(
        self,
        item_id: str,
        profile_id: str,
        **kwargs
    ) -> bool:
        """Update a detected item"""
        if not self.supabase:
            return False

        try:
            self.supabase.table("bulk_import_detected_items").update({
                **kwargs,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", item_id).eq("profile_id", profile_id).execute()

            return True
        except Exception as e:
            logger.error(f"Failed to update detected item: {e}")
            return False

    # ========================================================================
    # Step 1: Detection
    # ========================================================================

    async def detect_items(
        self,
        profile_id: str,
        source_type: str,
        sources: List[str]
    ) -> BulkDetectResponse:
        """
        Detect and parse workout items from sources.

        For files: Parse Excel/CSV/JSON/Text content
        For URLs: Fetch metadata and queue for processing (batched, max 5 concurrent)
        For images: Run OCR and extract workout data
        """
        job_id = self._create_job(profile_id, source_type, len(sources))

        detected_items = []
        success_count = 0
        error_count = 0

        # Use optimized batch processing for URLs and images
        if source_type == "urls":
            detected_items, success_count, error_count = await self._detect_urls_batch(
                sources, max_concurrent=5
            )
        elif source_type == "images":
            # Images are passed as list of (base64_data, filename) or just base64_data
            # If just base64 strings, convert to tuples
            images = []
            for idx, source in enumerate(sources):
                if isinstance(source, tuple):
                    images.append(source)
                elif isinstance(source, dict):
                    images.append((source.get("data", ""), source.get("filename", f"image_{idx}.jpg")))
                else:
                    images.append((source, f"image_{idx}.jpg"))
            detected_items, success_count, error_count = await self._detect_images_batch(
                images, max_concurrent=3
            )
        else:
            # Process files sequentially
            for idx, source in enumerate(sources):
                try:
                    item = await self._detect_single_source(
                        source_type=source_type,
                        source=source,
                        index=idx
                    )
                    detected_items.append(item)

                    if item.get("errors"):
                        error_count += 1
                    else:
                        success_count += 1

                except Exception as e:
                    logger.error(f"Error detecting source {idx}: {e}")
                    detected_items.append({
                        "id": str(uuid.uuid4()),
                        "source_index": idx,
                        "source_type": source_type,
                        "source_ref": source[:100] if source else "",
                        "raw_data": {},
                        "confidence": 0,
                        "errors": [str(e)],
                    })
                    error_count += 1

        # Store in database
        self._store_detected_items(job_id, profile_id, detected_items)

        # Update job with total items
        self._update_job_status(
            job_id, profile_id, "pending",
            total_items=len(detected_items)
        )

        return BulkDetectResponse(
            success=True,
            job_id=job_id,
            items=[DetectedItem(**item) for item in detected_items],
            metadata={},
            total=len(detected_items),
            success_count=success_count,
            error_count=error_count,
        )

    async def _detect_urls_batch(
        self,
        urls: List[str],
        max_concurrent: int = 5
    ) -> tuple:
        """
        Batch process URLs with concurrency limit.

        Uses optimized batch fetching from URL parser.

        Returns:
            Tuple of (detected_items, success_count, error_count)
        """
        detected_items = []
        success_count = 0
        error_count = 0

        # Fetch metadata for all URLs in batch (with concurrency limit)
        metadata_list = await fetch_url_metadata_batch(urls, max_concurrent)

        for idx, metadata in enumerate(metadata_list):
            item_id = str(uuid.uuid4())

            if metadata.error:
                detected_items.append({
                    "id": item_id,
                    "source_index": idx,
                    "source_type": "urls",
                    "source_ref": metadata.url,
                    "raw_data": {
                        "url": metadata.url,
                        "platform": metadata.platform,
                        "video_id": metadata.video_id,
                    },
                    "parsed_title": f"{metadata.platform.title()} Video",
                    "parsed_exercise_count": 0,
                    "parsed_block_count": 0,
                    "confidence": 30,
                    "errors": [metadata.error],
                })
                error_count += 1
            else:
                # Build title
                title = metadata.title
                if not title:
                    title = f"{metadata.platform.title()} Video"
                    if metadata.video_id:
                        title += f" ({metadata.video_id[:8]}...)"

                detected_items.append({
                    "id": item_id,
                    "source_index": idx,
                    "source_type": "urls",
                    "source_ref": metadata.url,
                    "raw_data": {
                        "url": metadata.url,
                        "platform": metadata.platform,
                        "video_id": metadata.video_id,
                        "title": metadata.title,
                        "author": metadata.author,
                        "thumbnail_url": metadata.thumbnail_url,
                        "duration_seconds": metadata.duration_seconds,
                    },
                    "parsed_title": title,
                    "parsed_exercise_count": 0,
                    "parsed_block_count": 0,
                    "confidence": 70,
                    "thumbnail_url": metadata.thumbnail_url,
                    "author": metadata.author,
                    "platform": metadata.platform,
                })
                success_count += 1

        return detected_items, success_count, error_count

    async def _detect_images_batch(
        self,
        images: List[tuple],  # List of (base64_data, filename)
        max_concurrent: int = 3
    ) -> tuple:
        """
        Batch process images with concurrency limit.

        Uses Vision AI for workout extraction.

        Args:
            images: List of (base64_data, filename) tuples
            max_concurrent: Max concurrent requests (lower than URLs due to cost)

        Returns:
            Tuple of (detected_items, success_count, error_count)
        """
        detected_items = []
        success_count = 0
        error_count = 0

        # Decode base64 images and prepare for batch processing
        decoded_images = []
        decode_errors = []

        for idx, (b64_data, filename) in enumerate(images):
            try:
                image_data = base64.b64decode(b64_data)
                decoded_images.append((image_data, filename or f"image_{idx}.jpg", idx))
            except Exception as e:
                decode_errors.append((idx, filename, str(e)))

        # Add decode error items
        for idx, filename, error in decode_errors:
            detected_items.append({
                "id": str(uuid.uuid4()),
                "source_index": idx,
                "source_type": "images",
                "source_ref": filename or f"image_{idx}",
                "raw_data": {},
                "parsed_title": f"Image Workout {idx + 1}",
                "parsed_exercise_count": 0,
                "confidence": 0,
                "errors": [f"Invalid base64 image data: {error}"],
            })
            error_count += 1

        # Process decoded images in batch
        if decoded_images:
            batch_input = [(data, fname) for data, fname, _ in decoded_images]
            results = await parse_images_batch(
                batch_input,
                mode="vision",
                max_concurrent=max_concurrent,
            )

            for (_, filename, idx), result in zip(decoded_images, results):
                item_id = str(uuid.uuid4())

                if not result.success:
                    detected_items.append({
                        "id": item_id,
                        "source_index": idx,
                        "source_type": "images",
                        "source_ref": filename,
                        "raw_data": {
                            "extraction_method": result.extraction_method,
                        },
                        "parsed_title": f"Image Workout {idx + 1}",
                        "parsed_exercise_count": 0,
                        "confidence": result.confidence,
                        "errors": [result.error] if result.error else ["Failed to extract workout"],
                    })
                    error_count += 1
                else:
                    title = result.title or f"Image Workout {idx + 1}"
                    exercise_count = len(result.exercises)
                    block_count = len(result.blocks)

                    detected_items.append({
                        "id": item_id,
                        "source_index": idx,
                        "source_type": "images",
                        "source_ref": filename,
                        "raw_data": {
                            "extraction_method": result.extraction_method,
                            "model_used": result.model_used,
                            "exercises": result.exercises,
                            "blocks": result.blocks,
                        },
                        "parsed_title": title,
                        "parsed_exercise_count": exercise_count,
                        "parsed_block_count": block_count,
                        "parsed_workout": result.raw_workout,
                        "confidence": result.confidence,
                        "flagged_items": result.flagged_items if result.flagged_items else None,
                    })
                    success_count += 1

        # Sort by source_index to maintain order
        detected_items.sort(key=lambda x: x["source_index"])

        return detected_items, success_count, error_count

    async def _detect_single_source(
        self,
        source_type: str,
        source: str,
        index: int
    ) -> Dict[str, Any]:
        """Detect workout from a single source"""
        item_id = str(uuid.uuid4())

        if source_type == "file":
            return await self._detect_from_file(item_id, source, index)
        elif source_type == "urls":
            return await self._detect_from_url(item_id, source, index)
        elif source_type == "images":
            return await self._detect_from_image(item_id, source, index)
        else:
            return {
                "id": item_id,
                "source_index": index,
                "source_type": source_type,
                "source_ref": source[:100] if source else "",
                "raw_data": {},
                "confidence": 0,
                "errors": [f"Unknown source type: {source_type}"],
            }

    async def _detect_from_file(
        self,
        item_id: str,
        source: str,
        index: int,
        filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Detect workout from file content (base64 encoded).

        Args:
            item_id: Unique ID for this detected item
            source: Base64 encoded file content (optionally prefixed with "filename:")
            index: Source index in the batch
            filename: Optional filename (if not embedded in source)
        """
        try:
            # Parse source format: can be "filename:base64content" or just "base64content"
            if filename is None and ":" in source and not source.startswith("data:"):
                # Check if it looks like "filename.ext:base64..."
                parts = source.split(":", 1)
                if "." in parts[0] and len(parts[0]) < 256:
                    filename = parts[0]
                    source = parts[1]

            # Default filename if none provided
            if not filename:
                filename = f"file_{index}.txt"

            # Use the parser factory
            parse_result = await FileParserFactory.parse_base64(source, filename)

            if not parse_result.success:
                return {
                    "id": item_id,
                    "source_index": index,
                    "source_type": "file",
                    "source_ref": filename,
                    "raw_data": {"filename": filename},
                    "parsed_title": None,
                    "parsed_exercise_count": 0,
                    "parsed_block_count": 0,
                    "confidence": 0,
                    "errors": parse_result.errors,
                    "warnings": parse_result.warnings,
                }

            # Convert workouts to detected items format
            # For multi-workout files (e.g., multi-sheet Excel), we'll create multiple items
            # But since this method returns a single item, we'll aggregate
            total_exercises = 0
            total_blocks = 0
            workout_titles = []
            parsed_workouts = []

            for workout in parse_result.workouts:
                workout_titles.append(workout.name or f"Workout {len(workout_titles) + 1}")
                exercise_count = len(workout.exercises)
                total_exercises += exercise_count
                total_blocks += 1  # Each workout is considered one block

                # Convert ParsedWorkout to dict for storage
                parsed_workouts.append(workout.model_dump())

            # Generate title
            if len(workout_titles) == 1:
                title = workout_titles[0]
            elif len(workout_titles) > 1:
                title = f"{workout_titles[0]} (+{len(workout_titles) - 1} more)"
            else:
                title = filename

            return {
                "id": item_id,
                "source_index": index,
                "source_type": "file",
                "source_ref": filename,
                "raw_data": {
                    "filename": filename,
                    "detected_format": parse_result.detected_format,
                    "column_info": [c.model_dump() for c in (parse_result.columns or [])],
                },
                "parsed_title": title,
                "parsed_exercise_count": total_exercises,
                "parsed_block_count": total_blocks,
                "parsed_workout": parsed_workouts[0] if len(parsed_workouts) == 1 else {
                    "workouts": parsed_workouts
                },
                "confidence": parse_result.confidence,
                "errors": parse_result.errors if parse_result.errors else None,
                "warnings": parse_result.warnings if parse_result.warnings else None,
                "patterns": self._patterns_to_list(parse_result.patterns) if parse_result.patterns else [],
            }

        except Exception as e:
            logger.exception(f"Error parsing file: {e}")
            return {
                "id": item_id,
                "source_index": index,
                "source_type": "file",
                "source_ref": filename or f"file_{index}",
                "raw_data": {},
                "confidence": 0,
                "errors": [f"Failed to parse file: {str(e)}"],
            }

    async def _detect_from_url(
        self,
        item_id: str,
        source: str,
        index: int
    ) -> Dict[str, Any]:
        """
        Detect workout from URL (YouTube, Instagram, TikTok).

        Fetches metadata using oEmbed APIs for quick preview.
        Full workout extraction is done during the import step.
        """
        try:
            # Fetch metadata using URL parser
            metadata = await URLParser.fetch_metadata(source)

            if metadata.error:
                return {
                    "id": item_id,
                    "source_index": index,
                    "source_type": "urls",
                    "source_ref": source,
                    "raw_data": {
                        "url": source,
                        "platform": metadata.platform,
                        "video_id": metadata.video_id,
                    },
                    "parsed_title": f"{metadata.platform.title()} Video",
                    "parsed_exercise_count": 0,
                    "parsed_block_count": 0,
                    "confidence": 30,
                    "errors": [metadata.error],
                }

            # Build title
            title = metadata.title
            if not title:
                title = f"{metadata.platform.title()} Video"
                if metadata.video_id:
                    title += f" ({metadata.video_id[:8]}...)"

            return {
                "id": item_id,
                "source_index": index,
                "source_type": "urls",
                "source_ref": source,
                "raw_data": {
                    "url": source,
                    "platform": metadata.platform,
                    "video_id": metadata.video_id,
                    "title": metadata.title,
                    "author": metadata.author,
                    "thumbnail_url": metadata.thumbnail_url,
                    "duration_seconds": metadata.duration_seconds,
                },
                "parsed_title": title,
                "parsed_exercise_count": 0,  # Will be populated after ingestion
                "parsed_block_count": 0,
                "confidence": 70,  # Metadata fetched successfully
                "thumbnail_url": metadata.thumbnail_url,
                "author": metadata.author,
                "platform": metadata.platform,
            }

        except Exception as e:
            logger.exception(f"Error detecting URL: {e}")
            return {
                "id": item_id,
                "source_index": index,
                "source_type": "urls",
                "source_ref": source,
                "raw_data": {"url": source},
                "parsed_title": f"Video Workout {index + 1}",
                "parsed_exercise_count": 0,
                "confidence": 20,
                "errors": [f"Failed to fetch URL metadata: {str(e)}"],
            }

    async def _detect_from_image(
        self,
        item_id: str,
        source: str,
        index: int,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Detect workout from image (base64 encoded).

        Uses Vision AI via workout-ingestor-api to extract workout data.
        """
        try:
            # Decode base64 image
            try:
                image_data = base64.b64decode(source)
            except Exception as e:
                return {
                    "id": item_id,
                    "source_index": index,
                    "source_type": "images",
                    "source_ref": filename or f"image_{index}",
                    "raw_data": {},
                    "parsed_title": f"Image Workout {index + 1}",
                    "parsed_exercise_count": 0,
                    "confidence": 0,
                    "errors": [f"Invalid base64 image data: {str(e)}"],
                }

            # Use filename or generate one
            fname = filename or f"image_{index}.jpg"

            # Parse using ImageParser
            result = await ImageParser.parse_image(
                image_data=image_data,
                filename=fname,
                mode="vision",
                vision_model="gpt-4o-mini",
            )

            if not result.success:
                return {
                    "id": item_id,
                    "source_index": index,
                    "source_type": "images",
                    "source_ref": fname,
                    "raw_data": {
                        "extraction_method": result.extraction_method,
                    },
                    "parsed_title": f"Image Workout {index + 1}",
                    "parsed_exercise_count": 0,
                    "confidence": result.confidence,
                    "errors": [result.error] if result.error else ["Failed to extract workout from image"],
                }

            # Build title
            title = result.title
            if not title:
                title = f"Image Workout {index + 1}"

            # Count exercises
            exercise_count = len(result.exercises)
            block_count = len(result.blocks)

            return {
                "id": item_id,
                "source_index": index,
                "source_type": "images",
                "source_ref": fname,
                "raw_data": {
                    "extraction_method": result.extraction_method,
                    "model_used": result.model_used,
                    "exercises": result.exercises,
                    "blocks": result.blocks,
                },
                "parsed_title": title,
                "parsed_exercise_count": exercise_count,
                "parsed_block_count": block_count,
                "parsed_workout": result.raw_workout,
                "confidence": result.confidence,
                "flagged_items": result.flagged_items if result.flagged_items else None,
            }

        except Exception as e:
            logger.exception(f"Error detecting image: {e}")
            return {
                "id": item_id,
                "source_index": index,
                "source_type": "images",
                "source_ref": filename or f"image_{index}",
                "raw_data": {},
                "parsed_title": f"Image Workout {index + 1}",
                "parsed_exercise_count": 0,
                "confidence": 0,
                "errors": [f"Failed to process image: {str(e)}"],
            }

    # ========================================================================
    # Step 2: Column Mapping (for files)
    # ========================================================================

    async def apply_column_mappings(
        self,
        job_id: str,
        profile_id: str,
        column_mappings: List[ColumnMapping]
    ) -> BulkMapResponse:
        """
        Apply column mappings to detected file data.
        Transforms raw CSV/Excel data into structured workout data.
        """
        # Get detected items
        detected = self._get_detected_items(job_id, profile_id)

        # TODO: Implement column mapping logic
        # This will be fully implemented in AMA-101

        # Store mappings in job
        if self.supabase:
            self.supabase.table("bulk_import_jobs").update({
                "column_mappings": [m.dict() for m in column_mappings],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", job_id).eq("profile_id", profile_id).execute()

        return BulkMapResponse(
            success=True,
            job_id=job_id,
            mapped_count=len(detected),
            patterns=[],
        )

    # ========================================================================
    # Step 3: Exercise Matching
    # ========================================================================

    async def match_exercises(
        self,
        job_id: str,
        profile_id: str,
        user_mappings: Optional[Dict[str, str]] = None
    ) -> BulkMatchResponse:
        """
        Match exercises to Garmin exercise database.

        Uses fuzzy matching with rapidfuzz to find best matches.

        Confidence thresholds:
        - 90%+ = "matched" (auto-accept)
        - 70-90% = "needs_review" (show with option to change)
        - 50-70% = "needs_review" with lower confidence
        - <50% = "unmapped" (new exercise or needs manual mapping)

        Args:
            job_id: Import job ID
            profile_id: User profile ID
            user_mappings: Optional dict of {original_name: garmin_name} overrides
        """
        detected = self._get_detected_items(job_id, profile_id, selected_only=True)

        # Collect all unique exercises with their sources
        exercise_names = set()
        exercise_sources: Dict[str, List[str]] = {}

        for item in detected:
            workout = item.get("parsed_workout") or {}
            for block in workout.get("blocks") or []:
                # Direct exercises
                for exercise in block.get("exercises", []):
                    name = exercise.get("name", "")
                    if name:
                        exercise_names.add(name)
                        if name not in exercise_sources:
                            exercise_sources[name] = []
                        exercise_sources[name].append(item["id"])

                # Superset exercises
                for superset in block.get("supersets", []):
                    for exercise in superset.get("exercises", []):
                        name = exercise.get("name", "")
                        if name:
                            exercise_names.add(name)
                            if name not in exercise_sources:
                                exercise_sources[name] = []
                            exercise_sources[name].append(item["id"])

        # Match each unique exercise
        exercises = []
        for name in sorted(exercise_names):
            # Check if user has provided a mapping override
            if user_mappings and name in user_mappings:
                user_choice = user_mappings[name]
                exercises.append(ExerciseMatch(
                    id=str(uuid.uuid4()),
                    original_name=name,
                    matched_garmin_name=user_choice,
                    confidence=1.0,  # User confirmed
                    suggestions=[],
                    status="matched",
                    user_selection=user_choice,
                    source_workout_ids=exercise_sources.get(name, []),
                    occurrence_count=len(exercise_sources.get(name, [])),
                ))
                continue

            # Use Garmin matcher for fuzzy matching
            matched_name, confidence = find_garmin_exercise(name, threshold=30)

            # Get suggestions for alternatives
            suggestions_list = get_garmin_suggestions(name, limit=5, score_cutoff=0.3)
            suggestions = [
                {"name": sugg_name, "confidence": round(sugg_conf, 2)}
                for sugg_name, sugg_conf in suggestions_list
            ]

            # Determine status based on confidence thresholds
            if matched_name and confidence >= MATCH_AUTO_THRESHOLD:
                status = "matched"
            elif matched_name and confidence >= MATCH_UNMAPPED_THRESHOLD:
                status = "needs_review"
            else:
                status = "unmapped"
                # For unmapped, still include top suggestion as potential match
                if suggestions and not matched_name:
                    matched_name = suggestions[0]["name"]
                    confidence = suggestions[0]["confidence"]

            exercises.append(ExerciseMatch(
                id=str(uuid.uuid4()),
                original_name=name,
                matched_garmin_name=matched_name,
                confidence=round(confidence, 2) if confidence else 0,
                suggestions=suggestions,
                status=status,
                source_workout_ids=exercise_sources.get(name, []),
                occurrence_count=len(exercise_sources.get(name, [])),
            ))

        # Store matches in job
        if self.supabase:
            self.supabase.table("bulk_import_jobs").update({
                "exercise_matches": [e.dict() for e in exercises],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", job_id).eq("profile_id", profile_id).execute()

        # Calculate statistics
        matched = len([e for e in exercises if e.status == "matched"])
        needs_review = len([e for e in exercises if e.status == "needs_review"])
        unmapped = len([e for e in exercises if e.status == "unmapped"])

        return BulkMatchResponse(
            success=True,
            job_id=job_id,
            exercises=exercises,
            total_exercises=len(exercises),
            matched=matched,
            needs_review=needs_review,
            unmapped=unmapped,
        )

    # ========================================================================
    # Step 4: Preview
    # ========================================================================

    async def generate_preview(
        self,
        job_id: str,
        profile_id: str,
        selected_ids: List[str]
    ) -> BulkPreviewResponse:
        """Generate preview of workouts to be imported."""
        detected = self._get_detected_items(job_id, profile_id)

        previews = []
        stats = ImportStats()

        for item in detected:
            is_selected = item["id"] in selected_ids

            if is_selected:
                stats.total_selected += 1
            else:
                stats.total_skipped += 1

            workout_data = item.get("parsed_workout", {})

            preview = PreviewWorkout(
                id=str(uuid.uuid4()),
                detected_item_id=item["id"],
                title=item.get("parsed_title", f"Workout {item['source_index'] + 1}"),
                description=workout_data.get("description"),
                exercise_count=item.get("parsed_exercise_count", 0),
                block_count=item.get("parsed_block_count", 0),
                validation_issues=[],
                workout=workout_data,
                selected=is_selected,
                is_duplicate=item.get("is_duplicate", False),
                duplicate_of=item.get("duplicate_of"),
            )

            previews.append(preview)

        stats.total_detected = len(detected)

        return BulkPreviewResponse(
            success=True,
            job_id=job_id,
            workouts=previews,
            stats=stats,
        )

    # ========================================================================
    # Step 5: Import Execution
    # ========================================================================

    async def execute_import(
        self,
        job_id: str,
        profile_id: str,
        workout_ids: List[str],
        device: str,
        async_mode: bool = True
    ) -> BulkExecuteResponse:
        """
        Execute the actual import of workouts.

        In async mode, creates a background job and returns immediately.
        In sync mode, processes all workouts before returning.
        """
        # Create import job entry
        import_job_id = str(uuid.uuid4())

        self._update_job_status(
            job_id, profile_id, "running",
            target_device=device
        )

        if async_mode:
            # Start background task
            asyncio.create_task(
                self._process_import_async(
                    job_id, profile_id, workout_ids, device
                )
            )

            return BulkExecuteResponse(
                success=True,
                job_id=job_id,
                status="running",
                message="Import started in background",
            )
        else:
            # Synchronous import
            results = await self._process_import_sync(
                job_id, profile_id, workout_ids, device
            )

            return BulkExecuteResponse(
                success=True,
                job_id=job_id,
                status="complete",
                message=f"Imported {len([r for r in results if r.status == 'success'])} workouts",
            )

    async def _process_import_async(
        self,
        job_id: str,
        profile_id: str,
        workout_ids: List[str],
        device: str
    ):
        """Background task for processing imports"""
        try:
            results = await self._process_import_sync(
                job_id, profile_id, workout_ids, device
            )

            self._update_job_status(
                job_id, profile_id, "complete",
                results=[r.dict() for r in results]
            )

        except Exception as e:
            logger.error(f"Import job {job_id} failed: {e}")
            self._update_job_status(
                job_id, profile_id, "failed",
                error=str(e)
            )

    async def _process_import_sync(
        self,
        job_id: str,
        profile_id: str,
        workout_ids: List[str],
        device: str
    ) -> List[ImportResult]:
        """Synchronous import processing"""
        detected = self._get_detected_items(job_id, profile_id)
        results = []

        total = len(workout_ids)

        for idx, workout_id in enumerate(workout_ids):
            # Check for cancellation
            job = self._get_job(job_id, profile_id)
            if job and job.get("status") == "cancelled":
                break

            # Update progress
            self._update_job_progress(job_id, profile_id, idx + 1, workout_id)

            # Find the detected item
            item = next(
                (d for d in detected if d["id"] == workout_id),
                None
            )

            if not item:
                results.append(ImportResult(
                    workout_id=workout_id,
                    title="Unknown",
                    status="failed",
                    error="Workout not found",
                ))
                continue

            try:
                # TODO: Implement actual workout saving
                # This will use database.save_workout()
                result = await self._import_single_workout(
                    item, profile_id, device
                )
                results.append(result)

            except Exception as e:
                logger.error(f"Failed to import workout {workout_id}: {e}")
                results.append(ImportResult(
                    workout_id=workout_id,
                    title=item.get("parsed_title", "Unknown"),
                    status="failed",
                    error=str(e),
                ))

        return results

    async def _import_single_workout(
        self,
        item: Dict[str, Any],
        profile_id: str,
        device: str
    ) -> ImportResult:
        """Import a single workout"""
        # TODO: Implement using database.save_workout()
        # This will be integrated with existing workout saving

        return ImportResult(
            workout_id=item["id"],
            title=item.get("parsed_title", "Unknown"),
            status="success",
            saved_workout_id=str(uuid.uuid4()),  # Placeholder
        )

    # ========================================================================
    # Status & Control
    # ========================================================================

    async def get_import_status(
        self,
        job_id: str,
        profile_id: str
    ) -> BulkStatusResponse:
        """Get status of an import job"""
        job = self._get_job(job_id, profile_id)

        if not job:
            return BulkStatusResponse(
                success=False,
                job_id=job_id,
                status="not_found",
                progress=0,
                error="Job not found",
            )

        total = job.get("total_items", 0)
        processed = job.get("processed_items", 0)
        progress = int((processed / total * 100) if total > 0 else 0)

        return BulkStatusResponse(
            success=True,
            job_id=job_id,
            status=job.get("status", "unknown"),
            progress=progress,
            current_item=job.get("current_item"),
            results=[ImportResult(**r) for r in job.get("results", [])],
            error=job.get("error"),
            created_at=job.get("created_at"),
            updated_at=job.get("updated_at"),
        )

    async def cancel_import(
        self,
        job_id: str,
        profile_id: str
    ) -> bool:
        """Cancel a running import job"""
        job = self._get_job(job_id, profile_id)

        if not job or job.get("status") != "running":
            return False

        return self._update_job_status(job_id, profile_id, "cancelled")


# ============================================================================
# Global Service Instance
# ============================================================================

bulk_import_service = BulkImportService()
