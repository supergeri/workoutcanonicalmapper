# Testing the Exercise Suggestion API

## Quick Start

1. Start the FastAPI server:
```bash
source .venv/bin/activate
uvicorn backend.app:app --reload
```

2. The API will be available at: `http://localhost:8000`

3. Visit the interactive docs at: `http://localhost:8000/docs`

## Test Endpoints

### 1. Test Exercise Suggestions (POST)

```bash
curl -X POST "http://localhost:8000/exercise/suggest" \
  -H "Content-Type: application/json" \
  -d '{
    "exercise_name": "SOME TYPE OF SQUAT",
    "include_similar_types": true
  }' | python -m json.tool
```

Expected: Returns best match, similar exercises, and all squats.

### 2. Test Unknown Exercise

```bash
curl -X POST "http://localhost:8000/exercise/suggest" \
  -H "Content-Type: application/json" \
  -d '{
    "exercise_name": "UNKNOWN EXERCISE XYZ",
    "include_similar_types": true
  }' | python -m json.tool
```

Expected: `needs_user_search: true` with no matches.

### 3. Get Similar Exercises (GET)

```bash
curl "http://localhost:8000/exercise/similar/HAND%20RELEASE%20PUSH%20UPS?limit=5" | python -m json.tool
```

### 4. Get Exercises by Type (GET)

```bash
curl "http://localhost:8000/exercise/by-type/SOME%20TYPE%20OF%20SQUAT?limit=10" | python -m json.tool
```

Expected: Returns all squat variations.

## Using the Interactive Docs

1. Go to `http://localhost:8000/docs`
2. Find the `/exercise/suggest` endpoint
3. Click "Try it out"
4. Enter an exercise name like "SOME TYPE OF SQUAT"
5. Click "Execute"
6. Review the response with suggestions

## Response Structure

```json
{
  "input": "exercise name",
  "best_match": {
    "name": "Best Match Name",
    "score": 0.95,
    "is_exact": false
  },
  "similar_exercises": [
    {"name": "...", "score": 0.85},
    ...
  ],
  "exercises_by_type": [
    {"name": "...", "score": 0.80, "keyword": "squat"},
    ...
  ],
  "category": "squat",
  "needs_user_search": false
}
```

## Test Cases

- ✅ Exercise with good match: "KB SINGLE ARM SWING"
- ✅ Exercise by type: "SOME TYPE OF SQUAT" → shows all squats
- ✅ Unknown exercise: "UNKNOWN EXERCISE XYZ" → needs_user_search: true
- ✅ Partial match: "HAND RELEASE PUSH UPS" → shows push-up variants

