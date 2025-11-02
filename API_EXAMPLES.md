# Exercise Suggestion API Examples

## Endpoints

### POST `/exercise/suggest`
Get comprehensive exercise suggestions including best match, similar exercises, and exercises of the same type.

**Request:**
```json
{
  "exercise_name": "SOME TYPE OF SQUAT",
  "include_similar_types": true
}
```

**Response:**
```json
{
  "input": "SOME TYPE OF SQUAT",
  "best_match": {
    "name": "Squat",
    "score": 0.95,
    "is_exact": false
  },
  "similar_exercises": [
    {"name": "Squat", "score": 0.95, "normalized": "squat"},
    {"name": "Air Squat", "score": 0.85, "normalized": "air squat"},
    ...
  ],
  "exercises_by_type": [
    {"name": "Air Squat", "score": 0.85, "normalized": "air squat", "keyword": "squat"},
    {"name": "Back Squat", "score": 0.80, "normalized": "back squat", "keyword": "squat"},
    ...
  ],
  "category": "squat",
  "needs_user_search": false
}
```

### GET `/exercise/similar/{exercise_name}`
Get similar exercises to the given name.

**Example:** `GET /exercise/similar/SOME%20TYPE%20OF%20SQUAT?limit=10`

**Response:**
```json
{
  "exercise_name": "SOME TYPE OF SQUAT",
  "similar": [
    {"name": "Squat", "score": 0.95, "normalized": "squat"},
    {"name": "Air Squat", "score": 0.85, "normalized": "air squat"},
    ...
  ]
}
```

### GET `/exercise/by-type/{exercise_name}`
Get all exercises of the same type (e.g., all squats, all push-ups).

**Example:** `GET /exercise/by-type/SOME%20TYPE%20OF%20SQUAT?limit=20`

**Response:**
```json
{
  "exercise_name": "SOME TYPE OF SQUAT",
  "category": "squat",
  "exercises": [
    {"name": "Air Squat", "score": 0.85, "normalized": "air squat", "keyword": "squat"},
    {"name": "Back Squat", "score": 0.80, "normalized": "back squat", "keyword": "squat"},
    ...
  ]
}
```

## Use Cases

1. **Exercise doesn't match exactly**: Returns best match with alternatives
2. **Exercise type is known (e.g., "squat")**: Returns all exercises of that type
3. **No match found**: Sets `needs_user_search: true` to prompt user to search Garmin database

## Response Fields

- `best_match`: Best matching Garmin exercise with confidence score
- `similar_exercises`: Exercises with similar names (fuzzy matched)
- `exercises_by_type`: All exercises of the same movement type
- `category`: Detected exercise category (squat, press, pull, etc.)
- `needs_user_search`: `true` if no good matches found and user should search manually

