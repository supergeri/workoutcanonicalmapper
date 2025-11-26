# =====================================================================================
# FILE: mapper-api/scripts/refresh_garmin_from_collector.py
# (NEW FILE — automatically rebuilds all Garmin exercise datasets from the GitHub repo)
# =====================================================================================
import json, yaml, pathlib, requests, re


ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_YAML = ROOT / "shared/dictionaries/garmin_exercises_raw.yaml"
NAMES_TXT = ROOT / "shared/dictionaries/garmin_exercise_names.txt"
MAP_YAML = ROOT / "shared/dictionaries/garmin_map.yaml"


COLLECTOR_URL = "https://raw.githubusercontent.com/maximecharriere/GarminExercisesCollector/master/results/exercises.json"


print("Downloading GarminExercisesCollector JSON dataset…")
res = requests.get(COLLECTOR_URL)
res.raise_for_status()
collector = res.json()


print(f"Loaded {len(collector)} Garmin exercises from collector.")


raw_yaml = {}
name_map = {}
garmin_map = yaml.safe_load(MAP_YAML.read_text()) if MAP_YAML.exists() else {}


def normalize(s: str):
    return s.strip().lower()


for ex in collector:
    name = ex["name"].strip()
    cat = ex.get("category", "").strip()
    key = normalize(name)


    raw_yaml[key] = {
        "name": name,
        "category": cat
    }
    name_map[name] = True


    # build stable ids for mapping
    safe_key = re.sub(r"[^A-Za-z0-9]+", "_", name).lower()
    if safe_key not in garmin_map:
        garmin_map[safe_key] = {"name": name}


# === Write garmin_exercises_raw.yaml ===
RAW_YAML.write_text(yaml.safe_dump(raw_yaml, sort_keys=True, allow_unicode=True))
print("Updated:", RAW_YAML)


# === Write garmin_exercise_names.txt ===
NAMES_TXT.write_text("\n".join(sorted(name_map.keys())))
print("Updated:", NAMES_TXT)


# === Write garmin_map.yaml ===
MAP_YAML.write_text(yaml.safe_dump(garmin_map, sort_keys=True, allow_unicode=True))
print("Updated:", MAP_YAML)


print("\nDONE: Garmin datasets are fully refreshed from GarminExercisesCollector.")
print("You can now run your server — all categories & exercise names are exact Garmin values.")

