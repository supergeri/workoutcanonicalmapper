# Simple Workflow Guide

## Quick Start (Recommended)

**Just use this one endpoint:**
- **Endpoint:** `POST /map/auto-map`
- **Use:** Your wrapped blocks JSON
- **Result:** YAML output automatically generated

**That's it!** The system automatically picks the best exercise matches.

## Detailed Workflow (If You Want Review)

**Keep your original blocks JSON - you'll use it multiple times!**

## Step-by-Step:

### 📄 Your Original JSON (from OCR)
```json
{
  "title": "Imported Workout",
  "source": "image:week7.png",
  "blocks": [ ... ]
}
```

### 1️⃣ Wrap It for the API
Add `blocks_json` wrapper:
```json
{
  "blocks_json": {
    "title": "Imported Workout",
    "source": "image:week7.png",
    "blocks": [ ... same blocks ... ]
  }
}
```
**Save this - you'll use it in Steps 2 and 4!**

### 2️⃣ Validate
- **Endpoint:** `POST /workflow/validate`
- **Use:** Your wrapped JSON (from Step 1)
- **Result:** Shows which exercises need review
- **What to do:** Look for exercises in `needs_review` or `unmapped_exercises`

### 3️⃣ Get Suggestions (if needed)
- **Endpoint:** `POST /exercise/suggest`
- **Use:** **DIFFERENT JSON** - just the exercise name:
  ```json
  {
    "exercise_name": "UNKNOWN EXERCISE XYZ",
    "include_similar_types": true
  }
  ```
- **Result:** Alternatives for that exercise
- **What to do:** Review suggestions, note alternatives

### 4️⃣ Process to YAML
- **Endpoint:** `POST /workflow/process`
- **Use:** **SAME wrapped JSON** from Step 1!
- **Result:** Validation + YAML output

## Quick Summary:

✅ **Step 2 (Validate) and Step 4 (Process) use the SAME JSON**  
✅ **Step 3 (Suggest) uses a DIFFERENT, smaller JSON** (just exercise name)

## Example Files:

- `test_week7_full.json` - Your original blocks JSON
- `test_week7_api_payload.json` - Already wrapped correctly (use for Steps 2 & 4)

