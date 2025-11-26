# =====================================================================================
# FILE: mapper-api/backend/core/exercise_categories.py
# (REPLACE ENTIRE FILE WITH THIS VERSION)
# =====================================================================================
from __future__ import annotations


import json
import logging
import pathlib
from typing import Optional, Dict


import yaml


logger = logging.getLogger(__name__)


ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW_FILE = ROOT / "shared" / "dictionaries" / "garmin_exercises_raw.yaml"


# ---------------------------------------------------------------------------
# Manual category overrides for known problematic names
# ---------------------------------------------------------------------------
# These are used *before* looking into the GarminExercisesCollector dataset.
# They let us fix cases where names differ slightly or Garmin doesn't expose
# a category as expected.
MANUAL_CATEGORY_OVERRIDES: Dict[str, str] = {
    # Chest / fly variations
    "Chest Fly": "FLYE",


    # Shoulders
    "Alternating Lateral Raise With Static Hold": "LATERAL_RAISE",


    # Arms
    "Cable Overhead Triceps Extension": "TRICEPS_EXTENSION",
    "Alternating Dumbbell Biceps Curl": "CURL",
}




def _load_raw() -> Dict[str, dict]:
    """Load GarminExercisesCollector-derived YAML with official categories."""
    try:
        if not RAW_FILE.exists():
            logger.error("garmin_exercises_raw.yaml missing at %s", RAW_FILE)
            return {}
        data = yaml.safe_load(RAW_FILE.read_text()) or {}
        if not isinstance(data, dict):
            logger.error(
                "garmin_exercises_raw.yaml has unexpected format (expected dict, got %s)",
                type(data),
            )
            return {}
        return {str(k).lower(): v for k, v in data.items()}
    except Exception as e:
        logger.error("Failed to load raw Garmin dataset: %s", e)
        return {}




RAW: Dict[str, dict] = _load_raw()




def _official_category(name: str) -> Optional[str]:
    """
    Lookup category from GarminExercisesCollector data.


    RAW entries look like:
        key (lowercased name): { "name": "Barbell Bench Press",
                                  "category": "BENCH_PRESS" }
    """
    if not name:
        return None


    key = name.strip().lower()
    ex = RAW.get(key)
    if not ex:
        return None


    cat = ex.get("category")
    if not cat:
        return None


    # Most collector categories are already in enum form (e.g. BENCH_PRESS),
    # but we normalize anyway.
    return str(cat).strip().upper().replace(" ", "_") or None




def add_category_to_exercise_name(garmin_name: str) -> str:
    """
    Append Garmin category to an exercise name.


    Priority:
      1) MANUAL_CATEGORY_OVERRIDES (for tricky / mismatched names)
      2) GarminExercisesCollector dataset (garmin_exercises_raw.yaml)
      3) If both fail, leave name unchanged.


    Output example:
        "Barbell Bench Press [category: BENCH_PRESS]"
    """
    if not garmin_name:
        return garmin_name


    # 1) Manual overrides first
    category = MANUAL_CATEGORY_OVERRIDES.get(garmin_name)


    # 2) If no manual override, use official dataset
    if not category:
        category = _official_category(garmin_name)


    # 3) No category at all → return name unchanged but log
    if not category:
        print("=== GARMIN_CATEGORY_ASSIGN ===")
        print(
            json.dumps(
                {
                    "garmin_name_before": garmin_name,
                    "assigned_category": None,
                    "garmin_name_after": garmin_name,
                },
                indent=2,
            )
        )
        return garmin_name


    name_with_category = f"{garmin_name} [category: {category}]"


    # Debug logging (keeps your existing log format)
    print("=== GARMIN_CATEGORY_ASSIGN ===")
    print(
        json.dumps(
            {
                "garmin_name_before": garmin_name,
                "assigned_category": category,
                "garmin_name_after": name_with_category,
            },
            indent=2,
        )
    )


    return name_with_category




def detect_exercise_category(name: str) -> Optional[str]:
    """
    Legacy function kept for compatibility.


    We now rely entirely on:
      - MANUAL_CATEGORY_OVERRIDES
      - GarminExercisesCollector data via _official_category()
    """
    return None
