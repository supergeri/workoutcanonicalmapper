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

Run tests with pytest:

```bash
pytest
```

With coverage:

```bash
pytest --cov=backend --cov=shared
```

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

