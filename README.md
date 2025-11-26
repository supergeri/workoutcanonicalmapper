# Workout Canonical Mapper

A Python application that converts workout data from OCR/ingest format to canonical exercise names and exports to Garmin YAML format.

## Features

- **Exercise Normalization**: Normalizes exercise names by expanding abbreviations, removing stopwords, and converting plural forms
- **Canonical Matching**: Uses fuzzy matching to map raw exercise names to canonical names from a dictionary
- **Garmin Export**: Converts workouts to Garmin-compatible YAML format
- **FastAPI REST API**: Web API endpoint for workout conversion
- **CLI Tool**: Command-line interface for batch processing

## Prerequisites

- Python 3.8+
- pip (Python package manager)

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/supergeri/workoutcanonicalmapper.git
   cd workoutcanonicalmapper
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install fastapi uvicorn pydantic pyyaml rapidfuzz python-slugify orjson pytest pytest-cov
   ```

## Usage

### CLI Tool

Convert a workout JSON file to Garmin YAML:

```bash
python -m backend.cli sample/ocr.json -o output.yaml
```

Or output to stdout:

```bash
python -m backend.cli sample/ocr.json
```

### FastAPI Server

Start the API server:

```bash
uvicorn backend.app:app --reload
```

The server will start on `http://localhost:8000`

**API Endpoints:**

- `POST /map/final` - Convert workout from ingest JSON to Garmin YAML
  - Request body: `{"ingest_json": {...}}`
  - Response: `{"yaml": "..."}`

- `GET /docs` - Interactive API documentation (Swagger UI)

**Example API Request:**

```bash
curl -X POST "http://localhost:8000/map/final" \
  -H "Content-Type: application/json" \
  -d @test_payload.json
```

### Input Format

The ingest JSON format should look like:

```json
{
  "title": "Upper Body Push",
  "exercises": [
    {
      "name": "DB Bench Press",
      "sets": 3,
      "reps": "8-10",
      "rest": 60,
      "equipment": ["dumbbell"],
      "modifiers": ["flat"]
    }
  ]
}
```

### Output Format

The Garmin YAML output format:

```yaml
workout:
  name: Upper Body Push
  sport: strength
  steps:
    - type: exercise
      exerciseName: Dumbbell Bench Press
      sets: 3
      repetitionValue: 8-10
      rest: 60
```

## Project Structure

```
workout-mapper/
├── backend/
│   ├── adapters/          # Format converters
│   │   ├── ingest_to_cir.py
│   │   └── cir_to_garmin_yaml.py
│   ├── core/              # Core processing logic
│   │   ├── canonicalize.py
│   │   ├── catalog.py
│   │   ├── match.py
│   │   └── normalize.py
│   ├── app.py             # FastAPI application
│   └── cli.py             # Command-line interface
├── shared/
│   ├── dictionaries/      # Exercise dictionaries
│   │   ├── canonical_exercises.yaml
│   │   ├── garmin_map.yaml
│   │   └── normalization.yaml
│   └── schemas/           # Pydantic models
│       └── cir.py
└── sample/
    └── ocr.json           # Sample input file
```

## Testing

### Run tests once:

```bash
pytest
```

### Run tests with coverage:

```bash
pytest --cov=backend --cov=shared
```

### Auto-run tests on file changes (Recommended for development):

Install pytest-watch (already installed if you followed setup):
```bash
pip install pytest-watch
```

Run tests automatically whenever files change:
```bash
ptw  # or pytest-watch
```

This will watch for changes in `.py` files in `backend/`, `tests/`, and `shared/` directories and automatically rerun tests.

You can also watch specific files/directories:
```bash
ptw backend/ tests/
```

Or run with additional pytest options:
```bash
ptw -- -v --tb=short
```

### Run tests before commits (Git hook):

To automatically run tests before each commit (prevents broken code from being committed):

1. Install pre-commit:
```bash
pip install pre-commit
```

2. Install the git hook:
```bash
pre-commit install
```

Now tests will run automatically before each commit. If tests fail, the commit will be blocked.

## Configuration

### Adding Exercises

Edit `shared/dictionaries/canonical_exercises.yaml` to add new exercises:

```yaml
- canonical: exercise_name
  synonyms: ["synonym1", "synonym2"]
  category: "category_name"
  equipment: ["equipment1", "equipment2"]
  modifiers: ["modifier1"]
```

### Adding Normalization Rules

Edit `shared/dictionaries/normalization.yaml` to:
- Add abbreviation expansions
- Add plural-to-singular mappings
- Add stopwords to filter

### Adding Garmin Mappings

Edit `shared/dictionaries/garmin_map.yaml` to map canonical names to Garmin exercise names:

```yaml
canonical_name: 
  name: "Garmin Exercise Name"
  modifiers: ["Incline"]  # Optional
```

## Development

The project uses:
- **FastAPI** for the web API
- **Pydantic** for data validation
- **rapidfuzz** for fuzzy string matching
- **PyYAML** for YAML parsing/emission

## License

[Add your license here]


## Garmin Mapping & Threshold Rules

### Mapping Priority

1. **User Mappings** (highest priority) - Custom user-defined mappings
2. **Popular Mappings** - Crowd-sourced popular choices
3. **Manual Mappings** - Hard-coded mappings in `blocks_to_hyrox_yaml.py`
4. **Fuzzy Match** - Uses `exercise_name_matcher` with rapidfuzz
5. **Canonical Match** - Classification-based matching
6. **Fallback** - Generic title-case (with warning log)

### IMPORTANT: mapped_name Precedence

The `mapped_name` field from the validation step is **authoritative**. When present:
- It is used as the primary candidate for matching
- Fuzzy matching is NOT recomputed if `mapped_name` exists
- Multiple candidates (mapped_name + original names) are tried using `best_from_candidates()`

### Confidence Thresholds

- **>= 0.88 (88%)**: Status = "valid" - High confidence match
- **0.40 - 0.88 (40-88%)**: Status = "needs_review" - Medium confidence, user should review
- **< 0.40 (40%)**: Status = "unmapped" - Low confidence, requires user input

### Fallback Behavior

If final confidence < 0.40:
- A generic exercise name is used (title-case of original)
- A **warning** is logged: `GARMIN_EXPORT_FALLBACK`
- The exercise is still exported but may not match correctly in Garmin Connect

### Logging

All Garmin export steps are logged with:
- `GARMIN_EXPORT_STEP`: Logged in `map_exercise_to_garmin()` with full details
- `GARMIN_SYNC_STEP`: Logged in sync endpoint before sending to Garmin API
- `GARMIN_EXPORT_FALLBACK`: Warning when generic fallback is used

Compare `GARMIN_EXPORT_STEP` and `GARMIN_SYNC_STEP` logs to ensure mapping consistency.
