# Global Mapping Popularity System

## Overview

The global mapping popularity system tracks which Garmin exercises users have chosen for each input exercise name. This creates a crowd-sourced database that improves mapping accuracy over time.

## How It Works

1. **Recording Choices**: When any user saves a mapping (via `/mappings/add`), it's automatically recorded in the global popularity database.

2. **Priority in Auto-Mapping**: Global popular mappings are checked **after** personal user mappings but **before** manual code mappings and fuzzy matching.

3. **Confidence Boost**: Popular mappings get higher confidence scores based on how many users have chosen them.

4. **Suggestions**: Popular choices are highlighted in exercise suggestions, showing how many users have selected each option.

## Priority Order

The mapping system now uses this priority order:

1. **User mappings** (personal preferences) - Highest priority
2. **Global popular mappings** (crowd-sourced) - NEW! 
3. Manual mappings in code
4. Fuzzy matching against Garmin database
5. Canonical matching
6. Fallback (title case)

## API Endpoints

### Record a Mapping Choice

**Save personal mapping** (also records globally):
```bash
POST /mappings/add
{
  "exercise_name": "RDLs",
  "garmin_name": "Romanian Deadlift"
}
```

**Record choice for popularity only** (without saving as personal):
```bash
POST /mappings/popularity/record
{
  "exercise_name": "RDLs",
  "garmin_name": "Romanian Deadlift"
}
```

### View Popularity

**Get popular mappings for an exercise**:
```bash
GET /mappings/popularity/RDLs
```

Response:
```json
{
  "exercise_name": "RDLs",
  "popular_mappings": [
    {"garmin_name": "Romanian Deadlift", "count": 5},
    {"garmin_name": "Deadlift", "count": 2}
  ]
}
```

**Get global statistics**:
```bash
GET /mappings/popularity/stats
```

Response:
```json
{
  "total_choices": 150,
  "unique_exercises": 45,
  "unique_mappings": 120,
  "most_popular": [
    {"exercise": "RDLs", "garmin_name": "Romanian Deadlift", "count": 15},
    ...
  ]
}
```

### Exercise Suggestions

**Get suggestions with popularity**:
```bash
POST /exercise/suggest
{
  "exercise_name": "RDLs",
  "include_similar_types": true
}
```

Response includes:
- `best_match.popularity` - Popularity count for best match
- `best_match.is_popular` - Whether it's a popular choice
- `popular_choices` - Top 5 popular mappings
- `similar_exercises[].popularity` - Popularity for each suggestion
- `similar_exercises[].is_popular` - Whether suggestion is popular

## Mapping Reasons in YAML

When a popular mapping is used, the description includes:
- `"chosen as popular choice by users"` (if 1 user)
- `"chosen as popular choice by 5 users"` (if multiple users)

Example:
```yaml
- 'Romanian Deadlift [category: DEADLIFT]': lap | RDLs x10 (chosen as popular choice by 5 users)
```

## Storage

Popularity data is stored in:
```
shared/dictionaries/global_mappings.yaml
```

Format:
```yaml
popular_mappings:
  "rdl":
    "Romanian Deadlift": 5
    "Deadlift": 2
  "front squat":
    "Dumbbell Front Squat": 8
```

## Benefits

1. **Crowd-sourced intelligence**: The system learns from all users' choices
2. **Better defaults**: Popular mappings become the default for new users
3. **Transparency**: Users can see what others have chosen
4. **Improves over time**: More users = better mapping accuracy

## Example Workflow

1. User A maps "RDLs" → "Romanian Deadlift" via `/mappings/add`
   - Saved as personal mapping
   - Recorded in global popularity (count: 1)

2. User B maps "RDLs" → "Romanian Deadlift" via `/mappings/add`
   - Saved as personal mapping
   - Global popularity updated (count: 2)

3. User C uses auto-map with "RDLs"
   - No personal mapping
   - System finds popular mapping: "Romanian Deadlift" (2 users)
   - Uses it automatically with confidence boost
   - Description shows: `"chosen as popular choice by 2 users"`

4. User D gets suggestions for "RDLs"
   - Sees "Romanian Deadlift" with popularity: 2
   - Can see it's a popular choice
   - Can record their own choice or use the popular one

## Notes

- Popularity is case-insensitive and normalized (e.g., "RDLs", "rdls", "RDL" all count as the same)
- Personal mappings always take priority over popular mappings
- Popular mappings are only used if they're reasonably similar to the input (validated by fuzzy matching)
- The system respects user privacy - only mapping choices are recorded, not user identities

