# User Mappings - Remember Your Selections

The system can remember your exercise mapping selections for future use!

## How It Works

When you manually select a Garmin exercise from suggestions, you can save that mapping. Next time the same exercise appears, it will be automatically mapped.

## API Endpoints

### 1. Save a Mapping
**Endpoint:** `POST /mappings/add`

**Request:**
```json
{
  "exercise_name": "KB ALTERNATING PLANK DRAG X12",
  "garmin_name": "Plank Drag"
}
```

**Response:**
```json
{
  "message": "Mapping saved successfully",
  "mapping": {
    "normalized": "kb alternating plank drag x12",
    "garmin_name": "Plank Drag"
  }
}
```

### 2. View All Mappings
**Endpoint:** `GET /mappings`

**Response:**
```json
{
  "total": 3,
  "mappings": {
    "kb alternating plank drag x12": "Plank Drag",
    "some type of squat": "Front Squat",
    "unknown exercise": "Custom Exercise Name"
  }
}
```

### 3. Check if Mapping Exists
**Endpoint:** `GET /mappings/lookup/{exercise_name}`

**Example:** `GET /mappings/lookup/KB%20ALTERNATING%20PLANK%20DRAG`

**Response:**
```json
{
  "exercise_name": "KB ALTERNATING PLANK DRAG",
  "mapped_to": "Plank Drag",
  "exists": true
}
```

### 4. Remove a Mapping
**Endpoint:** `DELETE /mappings/remove/{exercise_name}`

**Example:** `DELETE /mappings/remove/UNKNOWN%20EXERCISE`

### 5. Clear All Mappings
**Endpoint:** `DELETE /mappings/clear`

## Usage Workflow

1. **Get suggestions for unmapped exercise:**
   ```
   POST /exercise/suggest
   {"exercise_name": "UNKNOWN EXERCISE"}
   ```

2. **Review suggestions and pick one:**
   - See alternatives in response
   - Choose the best match

3. **Save your selection:**
   ```
   POST /mappings/add
   {
     "exercise_name": "UNKNOWN EXERCISE",
     "garmin_name": "Selected Exercise Name"
   }
   ```

4. **Next time:** The same exercise will automatically map to your saved choice!

## Storage

Mappings are saved in: `shared/dictionaries/user_mappings.yaml`

This file is created automatically when you save your first mapping.

## Priority Order

When mapping an exercise, the system checks in this order:

1. **User mappings** (highest priority) ← Your saved selections
2. Manual mappings in code
3. Fuzzy matching against Garmin database
4. Canonical matching

So your saved mappings will always be used first!

## Example

```bash
# 1. Get suggestions
curl -X POST "http://localhost:8000/exercise/suggest" \
  -H "Content-Type: application/json" \
  -d '{"exercise_name": "MY CUSTOM EXERCISE"}'

# 2. Review suggestions, decide on "Custom Exercise Name"

# 3. Save your selection
curl -X POST "http://localhost:8000/mappings/add" \
  -H "Content-Type: application/json" \
  -d '{
    "exercise_name": "MY CUSTOM EXERCISE",
    "garmin_name": "Custom Exercise Name"
  }'

# 4. Next time you process a workout with "MY CUSTOM EXERCISE",
#    it will automatically map to "Custom Exercise Name"!
```

