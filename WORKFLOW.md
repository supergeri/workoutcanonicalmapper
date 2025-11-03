# User Workflow: Blocks JSON to Hyrox YAML

## Complete Workflow

### Step 1: User receives JSON from image OCR
The JSON comes from image conversion with the blocks structure:
```json
{
  "title": "Imported Workout",
  "source": "image:week7.png",
  "blocks": [...]
}
```

### Step 2: Validate the workout
**Endpoint:** `POST /workflow/validate`

**IMPORTANT:** You must wrap your JSON in `blocks_json` key!

**Request:**
```json
{
  "blocks_json": {
    "title": "Imported Workout",
    "source": "image:week7.png",
    "blocks": [ ... ]
  }
}
```

**NOT just:**
```json
{
  "title": "Imported Workout",
  "blocks": [ ... ]
}
```

**Response:**
```json
{
  "total_exercises": 11,
  "validated_exercises": [
    {
      "original_name": "A1: GOODMORNINGS X10",
      "mapped_to": "Bar Good Morning",
      "confidence": 0.95,
      "status": "valid",
      ...
    }
  ],
  "needs_review": [
    {
      "original_name": "UNKNOWN EXERCISE",
      "mapped_to": null,
      "confidence": 0.0,
      "status": "needs_review",
      "suggestions": {
        "similar": [...],
        "by_type": [...],
        "category": "squat",
        "needs_user_search": true
      }
    }
  ],
  "can_proceed": false
}
```

### Step 3a: If exercises need review
**Use the SAME original blocks JSON for all steps!**

Use the suggestions API to find alternatives for specific exercises that need review:

**Endpoint:** `POST /exercise/suggest`

**Request (separate call for each exercise that needs review):**
```json
{
  "exercise_name": "SOME TYPE OF SQUAT",
  "include_similar_types": true
}
```

**Note:** This is a DIFFERENT endpoint - you're only sending the exercise name, not the full workout.

This returns:
- Best match with confidence score
- Similar exercises
- All exercises of same type (e.g., all squats)
- Flag if manual search needed

### Step 3b: User reviews suggestions
After checking suggestions, you can either:
- Accept the suggested match (the system will use it automatically)
- Note which exercise to manually fix later
- Search Garmin manually if `needs_user_search: true`

### Step 4: Process workout (after review)
**Endpoint:** `POST /workflow/process` (defaults to auto-proceed)  
**Or:** `POST /workflow/process-with-review` (requires manual review)

**IMPORTANT:** Use your **ORIGINAL blocks JSON** (same as Step 2), NOT the validation result!

**Request:**
```json
{
  "blocks_json": { 
    "title": "Imported Workout",
    "source": "image:week7.png",
    "blocks": [ ... your original blocks ... ]
  }
}
```

**Same JSON you used in Step 2!**

**Response:**
```json
{
  "validation": { ... validation results ... },
  "yaml": "settings:\n  deleteSameNameWorkout: true\n...",
  "message": "Workout converted successfully"
}
```

**Default behavior:** `auto_proceed=true` - Automatically uses best matches  
**Strict mode:** Use `/workflow/process-with-review` if you want to block unmapped exercises

### Alternative: Direct conversion (automatic - recommended)
**Endpoint:** `POST /map/auto-map`

**Request:**
```json
{
  "blocks_json": { ... your blocks JSON ... }
}
```

**Response:**
```json
{
  "yaml": "..."
}
```

**This endpoint automatically:**
- Picks the best matching exercises
- Uses your saved mappings (if any)
- Falls back to fuzzy matching
- Generates YAML immediately

**No user interaction needed** - perfect for automated workflows!

## Example Workflow (Step-by-Step)

### What JSON to use where:

**KEY POINT:** Keep your original blocks JSON handy - you'll use it multiple times!

### Step-by-Step:

1. **Prepare your JSON** → Save it as `workout.json`
   ```json
   {
     "title": "Imported Workout",
     "source": "image:week7.png",
     "blocks": [ ... ]
   }
   ```

2. **Wrap for API** → Add `blocks_json` wrapper:
   ```json
   {
     "blocks_json": {
       "title": "Imported Workout",
       "source": "image:week7.png",
       "blocks": [ ... same blocks as above ... ]
     }
   }
   ```
   Save this as `api_payload.json` (or use `test_week7_api_payload.json`)

3. **Validate (Step 2):**
   - Use: `api_payload.json` (wrapped version)
   - Endpoint: `POST /workflow/validate`
   - **Result:** Review list of exercises that need attention
   - **Action:** Look at exercises in `needs_review` or `unmapped_exercises`

4. **Get Suggestions (Step 3a) - for EACH problematic exercise:**
   - Use: Different JSON! Just the exercise name
   - Endpoint: `POST /exercise/suggest`
   - Request:
     ```json
     {
       "exercise_name": "UNKNOWN EXERCISE XYZ",
       "include_similar_types": true
     }
     ```
   - **Result:** Alternatives for that specific exercise
   - **Action:** Note which alternative to use (or mark for manual fix)

5. **Process to YAML (Step 4):**
   - Use: **SAME `api_payload.json`** from Step 2!
   - Endpoint: `POST /workflow/process`
   - Or with auto-proceed: `POST /workflow/process?auto_proceed=true`
   - **Result:** Validation + YAML output

### Quick Reference:

| Endpoint | Purpose | JSON Format | Auto-Pick? |
|----------|---------|-------------|------------|
| **`/map/auto-map`** | **Automatic conversion (recommended)** | `{"blocks_json": {...}}` | ✅ Yes - automatic |
| `/workflow/validate` | Check mapping quality | `{"blocks_json": {...}}` | No - review only |
| `/exercise/suggest` | Get alternatives | `{"exercise_name": "..."}` | No - suggestions only |
| `/workflow/process` | Validate + convert | `{"blocks_json": {...}}` | ✅ Yes - defaults to auto |
| `/workflow/process-with-review` | Strict validation | `{"blocks_json": {...}}` | ❌ No - blocks if unmapped |

**Recommended:** Just use `/map/auto-map` - it automatically picks the best matches!

## Status Codes

- **valid**: Exercise mapped with high confidence (>0.85)
- **needs_review**: Exercise mapped but low confidence or generic name
- **unmapped**: No match found, needs user intervention

## Decision Tree

```
Start with blocks JSON
    ↓
Validate workout
    ↓
All exercises valid? → YES → Generate YAML
    ↓ NO
Show suggestions for unmapped exercises
    ↓
User reviews and selects
    ↓
Re-validate or proceed with auto_proceed=true
    ↓
Generate YAML
```

