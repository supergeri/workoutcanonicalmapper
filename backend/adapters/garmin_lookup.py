"""
Garmin Exercise Lookup Module

Copy this file + garmin_exercises.json to your project.

Usage:
    from garmin_lookup import GarminExerciseLookup
    
    lookup = GarminExerciseLookup("path/to/garmin_exercises.json")
    result = lookup.find("DB Bench Press")
    # Returns: {"category_id": 0, "category_name": "Bench Press", ...}
"""

import json
import re
from pathlib import Path
from difflib import SequenceMatcher


class GarminExerciseLookup:
    def __init__(self, data_path=None):
        if data_path is None:
            data_path = Path(__file__).parent / "garmin_exercises.json"
        
        with open(data_path) as f:
            data = json.load(f)
        
        self.categories = data["categories"]
        self.exercises = data["exercises"]
        self.keywords = data.get("keywords", {}).get("en", {})

        # Built-in keywords for common exercises not in the JSON
        # IMPORTANT: Only use VALID FIT SDK exercise categories!
        # Valid categories: 0=bench_press, 2=cardio, 5=core, 6=crunch, 17=lunge,
        # 19=plank, 21=pull_up, 22=push_up, 23=row, 28=squat, 29=total_body, etc.
        # Category 38 is INVALID and will cause watch to reject workout!
        # NOTE: Run uses Cardio (2) for mixed workouts - Run (32) only works with sport type 1
        self.builtin_keywords = {
            "run": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Run"},
            "running": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Run"},
            "jog": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Run"},
            "sprint": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Run"},
            "ski erg": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Ski Erg"},
            "ski mogul": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Ski Erg"},
            "ski": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Ski Erg"},
            "row erg": {"category_id": 23, "category_key": "ROW", "category_name": "Row", "display_name": "Row"},
            "rower": {"category_id": 23, "category_key": "ROW", "category_name": "Row", "display_name": "Row"},
            "indoor row": {"category_id": 23, "category_key": "ROW", "category_name": "Row", "display_name": "Indoor Row"},
            "assault bike": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Assault Bike"},
            "echo bike": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Echo Bike"},
            "air bike": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Air Bike"},
            "bike erg": {"category_id": 2, "category_key": "CARDIO", "category_name": "Cardio", "display_name": "Bike Erg"},
        }

        # Build reverse lookup: category_name -> category_id
        self.category_ids = {
            v["name"]: v["id"] for v in self.categories.values()
        }
    
    def normalize(self, name):
        """Normalize exercise name for matching."""
        name = name.lower().strip()
        # Remove trailing pipe characters that may come from canonical format parsing
        name = name.rstrip('|').strip()

        # Remove common prefixes like A1:, B2;, etc
        name = re.sub(r'^[a-z]\d+[;:\s]+', '', name, flags=re.IGNORECASE)

        # Remove equipment prefixes
        for prefix in ['db ', 'kb ', 'bb ', 'sb ', 'mb ', 'trx ', 'cable ', 'band ']:
            if name.startswith(prefix):
                name = name[len(prefix):]

        # Remove rep counts like x10, X8
        name = re.sub(r'\s*x\s*\d+.*$', '', name, flags=re.IGNORECASE)

        # Remove "each side", "per side", etc
        name = re.sub(r'\s+(each|per)\s+(side|arm|leg).*$', '', name, flags=re.IGNORECASE)

        # Remove distance at END like "200m", "1km", "1.5 km"
        name = re.sub(r'\s*[\d.]+\s*(m|km)\s*$', '', name, flags=re.IGNORECASE)

        # Remove distance at START like "1km Run", "500m Row"
        name = re.sub(r'^[\d.]+\s*(m|km)\s+', '', name, flags=re.IGNORECASE)

        return name.strip()
    
    def find(self, exercise_name, lang="en"):
        """
        Find the best matching Garmin category for an exercise name.
        
        Returns dict with:
            - category_id: FIT SDK category ID
            - category_key: Garmin category key (e.g. PUSH_UP)
            - category_name: Display name (e.g. Push Up)
            - exercise_key: Garmin exercise key if exact match found
            - display_name: Garmin display name if exact match found
            - match_type: "exact", "keyword", "fuzzy", or "default"
        """
        normalized = self.normalize(exercise_name)

        # 1. Try exact match in exercises FIRST
        # This ensures specific exercise names like "Ski Moguls" return their correct display_name
        # before builtin keywords can match via substring (e.g., "ski mogul" matching "ski moguls")
        if normalized in self.exercises:
            result = self.exercises[normalized].copy()
            result["match_type"] = "exact"
            result["input"] = exercise_name
            result["normalized"] = normalized

            # Special case: if exact match returns category 32 (Run), check if we should
            # override with builtin keyword for compatibility (Run category only works with sport type 1)
            if result.get("category_id") == 32:
                for keyword, info in self.builtin_keywords.items():
                    if keyword in normalized:
                        # Use builtin keyword's category but keep original display_name
                        result["category_id"] = info["category_id"]
                        result["category_key"] = info["category_key"]
                        result["category_name"] = info["category_name"]
                        result["match_type"] = "exact_with_category_override"
                        break

            return result

        # 2. Check builtin keywords (for generic terms like "run", "ski" that don't have exact matches)
        # This ensures "run" maps to Cardio (2) for mixed workouts, not Run (32)
        for keyword, info in self.builtin_keywords.items():
            if keyword in normalized:
                return {
                    "category_id": info["category_id"],
                    "category_key": info["category_key"],
                    "category_name": info["category_name"],
                    "exercise_key": None,
                    "display_name": info.get("display_name"),
                    "match_type": "builtin_keyword",
                    "matched_keyword": keyword,
                    "input": exercise_name,
                    "normalized": normalized
                }

        # 3. Try JSON keyword matching
        keywords = self.keywords if lang == "en" else {}
        for keyword, info in keywords.items():
            if keyword in normalized:
                return {
                    "category_id": info["category_id"],
                    "category_key": info["category_key"],
                    "category_name": info["category_name"],
                    "exercise_key": None,
                    "display_name": info.get("display_name"),
                    "match_type": "keyword",
                    "matched_keyword": keyword,
                    "input": exercise_name,
                    "normalized": normalized
                }
        
        # 3. Try fuzzy matching against exercises
        best_match = None
        best_ratio = 0.0
        
        for ex_name, ex_info in self.exercises.items():
            ratio = SequenceMatcher(None, normalized, ex_name).ratio()
            if ratio > best_ratio and ratio > 0.6:
                best_ratio = ratio
                best_match = ex_info
        
        if best_match:
            result = best_match.copy()
            result["match_type"] = "fuzzy"
            result["match_ratio"] = best_ratio
            result["input"] = exercise_name
            result["normalized"] = normalized
            return result
        
        # 4. Default fallback
        return {
            "category_id": 5,  # Core
            "category_key": "CORE",
            "category_name": "Core",
            "exercise_key": None,
            "display_name": None,
            "match_type": "default",
            "input": exercise_name,
            "normalized": normalized
        }
    
    def get_category_id(self, category_name):
        """Get category ID by name."""
        return self.category_ids.get(category_name, 5)  # Default to Core


# Quick test
if __name__ == "__main__":
    lookup = GarminExerciseLookup()
    
    tests = [
        "Push Ups",
        "DB Bench Press",
        "A1: KB Goblet Squat x10",
        "Bulgarian Split Squat",
        "TRX Rows",
        "200m Ski",
        "Plank",
        "B2: Cable Face Pulls x12 each side",
    ]
    
    print(f"{'Input':<40} {'Category':<20} {'Match Type'}")
    print("-" * 75)
    for test in tests:
        result = lookup.find(test)
        print(f"{test:<40} {result['category_name']:<20} {result['match_type']}")