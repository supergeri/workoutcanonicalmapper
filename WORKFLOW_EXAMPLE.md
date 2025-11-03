# Complete Workflow Example

## Step-by-Step User Journey

### 1. User has JSON from Image OCR

The user receives this JSON:
```json
{
  "title": "Imported Workout",
  "source": "image:week7.png",
  "blocks": [...]
}
```

### 2. Direct Conversion (Recommended First Step)

**Endpoint:** `POST /map/auto-map`

**Request body:**
```json
{
  "blocks_json": {
    "title": "Imported Workout",
    "blocks": [...]
  }
}
```

**Response:**
```json
{
  "yaml": "settings:\n  deleteSameNameWorkout: true\n..."
}
```

**Use this for:** Quick conversion - automatically picks best matches. No user interaction needed!

### 3. Validation Workflow (When You Want to Review First)

**Step 3a: Validate the workout**
**Endpoint:** `POST /workflow/validate`

**Request:**
```json
{
  "blocks_json": { ... your full JSON ... }
}
```

**Response shows:**
- ✅ Validated exercises (good matches)
- ⚠️ Exercises needing review (low confidence or generic names)
- ❌ Unmapped exercises (no match found)

**Step 3b: Get suggestions for problematic exercises**

For each exercise in `needs_review` or `unmapped_exercises`:

**Endpoint:** `POST /exercise/suggest`

**Request:**
```json
{
  "exercise_name": "UNKNOWN EXERCISE XYZ",
  "include_similar_types": true
}
```

**Response provides:**
- Best match with confidence
- Similar exercises
- All exercises of same type (e.g., all squats)
- Flag if manual Garmin search needed

**Step 3c: Process after review**

**Endpoint:** `POST /workflow/process`

**Request:**
```json
{
  "blocks_json": { ... your full JSON ... }
}
```

**Query parameter:** `?auto_proceed=true` to proceed even with unmapped exercises

## Quick Start Commands

### Test the conversion:
```bash
   curl -X POST "http://localhost:8000/map/auto-map" \
  -H "Content-Type: application/json" \
  -d '{"blocks_json": {...your JSON...}}'
```

### Validate first:
```bash
curl -X POST "http://localhost:8000/workflow/validate" \
  -H "Content-Type: application/json" \
  -d '{"blocks_json": {...your JSON...}}'
```

### Get suggestions for specific exercise:
```bash
curl -X POST "http://localhost:8000/exercise/suggest" \
  -H "Content-Type: application/json" \
  -d '{"exercise_name": "SOME TYPE OF SQUAT", "include_similar_types": true}'
```

## Using the Interactive Docs

1. Start server: `uvicorn backend.app:app --reload`
2. Visit: `http://localhost:8000/docs`
3. Use these endpoints:
   - `/map/auto-map` - Automatic conversion (recommended)
   - `/workflow/validate` - Check mapping quality
   - `/workflow/process` - Validate + convert
   - `/exercise/suggest` - Get alternatives for specific exercise

