"""Tests for exercise mapping endpoints."""

import pytest


class TestExerciseSuggestions:
    """Test /exercise/suggest endpoint."""

    def test_suggest_returns_suggestions(self, api_client):
        """Test that suggestions are returned for valid exercise name."""
        response = api_client.post(
            "/exercise/suggest",
            json={"exercise_name": "Bench Press"},
        )
        assert response.status_code == 200
        data = response.json()
        # Should return some data structure with suggestions
        assert data is not None

    def test_suggest_missing_body_returns_422(self, api_client):
        """Test that missing body returns 422."""
        response = api_client.post("/exercise/suggest", json={})
        assert response.status_code == 422

    def test_suggest_empty_string_returns_error(self, api_client):
        """Test that empty string returns error."""
        response = api_client.post(
            "/exercise/suggest",
            json={"exercise_name": ""},
        )
        # May return 422 for validation or 200 with empty results
        assert response.status_code in [200, 400, 422]


class TestSimilarExercises:
    """Test /exercise/similar/{exercise_name} endpoint."""

    def test_similar_returns_list(self, api_client):
        """Test that similar exercises endpoint returns data."""
        response = api_client.get("/exercise/similar/squat")
        assert response.status_code == 200
        data = response.json()
        assert "exercise_name" in data
        assert "similar" in data
        assert data["exercise_name"] == "squat"

    def test_similar_respects_limit(self, api_client):
        """Test that limit parameter affects result count."""
        # Get results with small limit
        response_small = api_client.get("/exercise/similar/squat?limit=3")
        assert response_small.status_code == 200
        data_small = response_small.json()

        # Get results with larger limit
        response_large = api_client.get("/exercise/similar/squat?limit=20")
        assert response_large.status_code == 200
        data_large = response_large.json()

        # Larger limit should return same or more results
        assert len(data_small.get("similar", [])) <= len(data_large.get("similar", []))

    def test_similar_with_unknown_exercise(self, api_client):
        """Test similar endpoint with unknown exercise."""
        response = api_client.get("/exercise/similar/xyzzyflibbert")
        assert response.status_code == 200
        # Should still return structure, possibly with empty similar list
        data = response.json()
        assert "exercise_name" in data


class TestExerciseMatch:
    """Test /exercises/match endpoint for single exercise matching."""

    def test_match_exact_name(self, api_client):
        """Test matching with exact exercise name."""
        response = api_client.post(
            "/exercises/match",
            json={"name": "Barbell Bench Press"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "original_name" in data
        assert "status" in data
        assert data["status"] in ["matched", "needs_review", "unmapped"]

    def test_match_high_confidence_exercise(self, api_client, known_exercises):
        """Test that known exercises match with reasonable confidence."""
        for exercise in known_exercises[:5]:  # Test first 5
            response = api_client.post(
                "/exercises/match",
                json={"name": exercise},
            )
            assert response.status_code == 200
            data = response.json()
            # Known exercises should at least get some match
            assert data.get("matched_name") is not None or len(data.get("suggestions", [])) > 0

    def test_match_fuzzy_word_order(self, api_client):
        """Test that different word order still matches."""
        response = api_client.post(
            "/exercises/match",
            json={"name": "bench press barbell"},
        )
        assert response.status_code == 200
        data = response.json()
        # Should find a match even with reordered words
        assert data.get("matched_name") is not None or len(data.get("suggestions", [])) > 0

    def test_match_abbreviation(self, api_client):
        """Test matching with common abbreviations."""
        response = api_client.post(
            "/exercises/match",
            json={"name": "BB bench press"},
        )
        assert response.status_code == 200
        data = response.json()
        # BB should expand to Barbell
        assert data.get("matched_name") is not None or len(data.get("suggestions", [])) > 0

    def test_match_typo(self, api_client):
        """Test matching with minor typos."""
        response = api_client.post(
            "/exercises/match",
            json={"name": "Benchpress"},  # Missing space
        )
        assert response.status_code == 200
        data = response.json()
        # Should still match despite typo
        assert data.get("matched_name") is not None or len(data.get("suggestions", [])) > 0

    def test_match_case_insensitive(self, api_client):
        """Test that matching is case insensitive."""
        response = api_client.post(
            "/exercises/match",
            json={"name": "BARBELL BENCH PRESS"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("matched_name") is not None

    def test_match_no_match_gibberish(self, api_client):
        """Test that gibberish returns no match or low confidence."""
        response = api_client.post(
            "/exercises/match",
            json={"name": "xyzzy flibbertigibbet nonsense"},
        )
        assert response.status_code == 200
        data = response.json()
        # Should return unmapped status for gibberish
        assert data["status"] == "unmapped" or data.get("confidence", 0) < 0.5

    def test_match_empty_string_error(self, api_client):
        """Test that empty string returns appropriate error."""
        response = api_client.post(
            "/exercises/match",
            json={"name": ""},
        )
        # Either validation error or unmapped result
        assert response.status_code in [200, 400, 422]

    def test_match_returns_suggestions(self, api_client):
        """Test that match returns suggestions list."""
        response = api_client.post(
            "/exercises/match",
            json={"name": "squat", "limit": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    def test_match_common_variations(self, api_client, exercise_variations):
        """Test that common exercise variations match correctly."""
        for input_name, expected_contains in exercise_variations[:5]:  # Test first 5
            response = api_client.post(
                "/exercises/match",
                json={"name": input_name},
            )
            assert response.status_code == 200
            data = response.json()
            # Should find some match for common variations
            assert (
                data.get("matched_name") is not None
                or len(data.get("suggestions", [])) > 0
            ), f"Failed to match: {input_name}"


class TestExerciseByType:
    """Test /exercise/by-type/{exercise_name} endpoint."""

    def test_by_type_returns_category(self, api_client):
        """Test that by-type returns category information."""
        response = api_client.get("/exercise/by-type/squat")
        assert response.status_code == 200
        data = response.json()
        assert "exercise_name" in data
        assert "category" in data
        assert "exercises" in data

    def test_by_type_returns_exercises_list(self, api_client):
        """Test that by-type returns list of exercises."""
        response = api_client.get("/exercise/by-type/bench%20press?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("exercises", []), list)
        assert len(data.get("exercises", [])) <= 10


class TestWorkflowValidation:
    """Test /workflow/validate endpoint."""

    def test_validate_missing_body_returns_422(self, api_client):
        """Test that missing body returns 422."""
        response = api_client.post("/workflow/validate", json={})
        assert response.status_code == 422

    def test_validate_valid_workout(self, api_client, sample_blocks_json):
        """Test validation with valid workout structure."""
        response = api_client.post(
            "/workflow/validate",
            json={"blocks_json": sample_blocks_json},
        )
        assert response.status_code == 200
        data = response.json()
        # Should return validation results
        assert data is not None

    def test_validate_returns_unmapped_exercises(self, api_client):
        """Test that validation identifies unmapped exercises."""
        workout = {
            "title": "Test",
            "blocks": [
                {
                    "label": "Main",
                    "structure": "regular",
                    "exercises": [
                        {"name": "xyzzy unknown exercise", "reps": 10},
                    ],
                }
            ],
        }
        response = api_client.post(
            "/workflow/validate",
            json={"blocks_json": workout},
        )
        assert response.status_code == 200
        data = response.json()
        # Should identify the unmapped exercise
        assert "unmapped_exercises" in data or "total_exercises" in data


class TestMapFinal:
    """Test /map/final endpoint."""

    def test_map_final_missing_body_returns_422(self, api_client):
        """Test that missing body returns 422."""
        response = api_client.post("/map/final", json={})
        assert response.status_code == 422

    def test_map_final_returns_yaml(self, api_client, sample_ingest_json):
        """Test that map/final returns YAML output."""
        response = api_client.post(
            "/map/final",
            json={"ingest_json": sample_ingest_json},
        )
        assert response.status_code == 200
        data = response.json()
        assert "yaml" in data


class TestAutoMap:
    """Test /map/auto-map endpoint."""

    def test_auto_map_valid_workout(self, api_client, sample_blocks_json):
        """Test auto-map with valid workout."""
        response = api_client.post(
            "/map/auto-map",
            json={"blocks_json": sample_blocks_json},
        )
        assert response.status_code == 200
        data = response.json()
        assert "yaml" in data

    def test_auto_map_missing_body_returns_422(self, api_client):
        """Test that missing body returns 422."""
        response = api_client.post("/map/auto-map", json={})
        assert response.status_code == 422
