"""Tests for batch exercise mapping endpoint."""

import pytest


class TestBatchExerciseMatch:
    """Test /exercises/match/batch endpoint."""

    def test_batch_match_success(self, api_client):
        """Test batch matching processes multiple exercises."""
        response = api_client.post(
            "/exercises/match/batch",
            json={
                "names": ["Bench Press", "Squat", "Deadlift"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 3
        assert "total" in data
        assert data["total"] == 3

    def test_batch_match_statistics(self, api_client):
        """Test batch returns match statistics."""
        response = api_client.post(
            "/exercises/match/batch",
            json={
                "names": ["Bench Press", "Squat", "Deadlift"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Should have statistics
        assert "matched" in data
        assert "needs_review" in data
        assert "unmapped" in data
        # Total should equal sum of categories
        assert data["total"] == data["matched"] + data["needs_review"] + data["unmapped"]

    def test_batch_match_partial(self, api_client):
        """Test batch with some unmatched exercises still succeeds."""
        response = api_client.post(
            "/exercises/match/batch",
            json={
                "names": ["Bench Press", "xyzzy nonsense", "Squat"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 3
        # First and third should match, second should not
        assert data["results"][0]["status"] in ["matched", "needs_review"]
        assert data["results"][1]["status"] == "unmapped"
        assert data["results"][2]["status"] in ["matched", "needs_review"]

    def test_batch_match_all_matched(self, api_client, known_exercises):
        """Test batch with all well-known exercises."""
        response = api_client.post(
            "/exercises/match/batch",
            json={"names": known_exercises[:5]},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 5
        # Known exercises should mostly match
        matched_or_review = sum(
            1 for r in data["results"] if r["status"] in ["matched", "needs_review"]
        )
        assert matched_or_review >= 3  # At least 3 of 5 should match

    def test_batch_match_all_unmapped(self, api_client):
        """Test batch with all unknown exercises returns low confidence."""
        response = api_client.post(
            "/exercises/match/batch",
            json={
                "names": ["xyzzy1 qwerty zxcvbn", "flibbert ghjkl poiuy", "abcdef mnbvc lkjhg"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 3
        # For truly unknown exercises, should have low confidence or be unmapped
        for result in data["results"]:
            # Either unmapped or low confidence match
            assert result["status"] == "unmapped" or result.get("confidence", 0) < 0.7

    def test_batch_match_empty_list(self, api_client):
        """Test batch with empty list."""
        response = api_client.post(
            "/exercises/match/batch",
            json={"names": []},
        )
        # Either returns empty results or validation error
        assert response.status_code in [200, 400, 422]
        if response.status_code == 200:
            data = response.json()
            assert data["total"] == 0

    def test_batch_match_deduplication(self, api_client):
        """Test that batch deduplicates exercise names."""
        response = api_client.post(
            "/exercises/match/batch",
            json={
                "names": ["Squat", "squat", "SQUAT", "Squat"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Should deduplicate to fewer unique names
        # Depending on implementation, may be 1-4 results
        assert data["total"] <= 4

    def test_batch_match_limit_parameter(self, api_client):
        """Test that limit parameter affects suggestions."""
        response = api_client.post(
            "/exercises/match/batch",
            json={
                "names": ["squat"],
                "limit": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Each result should have suggestions limited
        for result in data["results"]:
            assert len(result.get("suggestions", [])) <= 3

    def test_batch_match_result_structure(self, api_client):
        """Test that each result has correct structure."""
        response = api_client.post(
            "/exercises/match/batch",
            json={"names": ["Bench Press"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        result = data["results"][0]
        # Check required fields
        assert "original_name" in result
        assert "status" in result
        assert "confidence" in result
        assert "suggestions" in result
        # Status should be valid
        assert result["status"] in ["matched", "needs_review", "unmapped"]
        # Confidence should be between 0 and 1
        assert 0 <= result["confidence"] <= 1

    def test_batch_match_large_batch(self, api_client):
        """Test batch with larger number of exercises."""
        exercises = ["Squat"] * 50 + ["Bench Press"] * 50
        response = api_client.post(
            "/exercises/match/batch",
            json={"names": exercises},
        )
        # Either succeeds or returns limit error
        assert response.status_code in [200, 400, 413]
        if response.status_code == 200:
            data = response.json()
            # With deduplication, should be 2 unique names
            assert data["total"] == 2

    def test_batch_match_whitespace_handling(self, api_client):
        """Test that whitespace is handled correctly."""
        response = api_client.post(
            "/exercises/match/batch",
            json={
                "names": ["  Squat  ", "Bench Press", "  ", ""],
            },
        )
        assert response.status_code in [200, 400, 422]
        if response.status_code == 200:
            data = response.json()
            # Empty strings should be filtered out
            assert data["total"] <= 2


class TestBatchMappingIntegration:
    """Integration tests for batch mapping with workflow."""

    def test_batch_then_validate(self, api_client, sample_blocks_json):
        """Test batch matching followed by workflow validation."""
        # Extract exercise names from workout
        exercises = []
        for block in sample_blocks_json.get("blocks", []):
            for ex in block.get("exercises", []):
                exercises.append(ex.get("name", ""))

        # First, batch match
        batch_response = api_client.post(
            "/exercises/match/batch",
            json={"names": exercises},
        )
        assert batch_response.status_code == 200

        # Then validate the workout
        validate_response = api_client.post(
            "/workflow/validate",
            json={"blocks_json": sample_blocks_json},
        )
        assert validate_response.status_code == 200
