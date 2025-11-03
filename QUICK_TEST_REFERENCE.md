# Quick Test Reference for FastAPI

## Server URL
http://localhost:8000

## Interactive Docs
http://localhost:8000/docs

## Endpoints to Test (in order)

### 1. Automatic Conversion (Fastest - Recommended)
**Endpoint:** `POST /map/auto-map`

**Automatically picks best exercise matches - no user choices needed!**

**In FastAPI docs:**
1. Go to http://localhost:8000/docs
2. Find `POST /map/auto-map`
3. Click "Try it out"
4. Use this request body structure:
```json
{
  "blocks_json": {
    "title": "Imported Workout",
    "source": "image:week7.png",
    "blocks": [
      {
        "label": "Primer",
        "structure": "3 rounds",
        "exercises": [],
        "supersets": [
          {
            "exercises": [
              {
                "name": "A1: GOODMORNINGS X10",
                "sets": 3,
                "reps": 10,
                "type": "strength"
              }
            ]
          }
        ]
      }
    ]
  }
}
```

**Or paste your full JSON from `test_week7_full.json` wrapped like:**
```json
{
  "blocks_json": { ... paste your full JSON here ... }
}
```

### 2. Validate Workout First (Recommended)
**Endpoint:** `POST /workflow/validate`

Use same request body format as above.

This will show:
- ✅ Validated exercises (good matches)
- ⚠️ Exercises needing review
- ❌ Unmapped exercises

### 3. Get Suggestions for Specific Exercise
**Endpoint:** `POST /exercise/suggest`

**Request body:**
```json
{
  "exercise_name": "DUAL KB FRONT SQUAT",
  "include_similar_types": true
}
```

Returns:
- Best match with confidence
- Similar exercises
- Exercises of same type
- Flag if manual search needed

### 4. Process with Validation
**Endpoint:** `POST /workflow/process`

**Request body:**
```json
{
  "blocks_json": { ... your JSON ... }
}
```

**Query parameter:** `auto_proceed=true` to proceed even with unmapped exercises

## Test Your Week 7 JSON

1. Open http://localhost:8000/docs
2. Use `POST /map/auto-map`
3. Copy your JSON from `test_week7_full.json`
4. Wrap it: `{"blocks_json": <your JSON>}`
5. Execute!

Expected: You should get YAML output with all exercises mapped correctly.

