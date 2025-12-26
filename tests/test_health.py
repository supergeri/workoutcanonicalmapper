"""Tests for health check endpoints."""

import pytest


class TestHealthEndpoints:
    """Test health check API endpoints."""

    def test_health_check(self, api_client):
        """Test health check returns 200 with status ok."""
        response = api_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_health_response_is_json(self, api_client):
        """Test health check returns valid JSON."""
        response = api_client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/json"
        # Should not raise
        response.json()


class TestApiBasics:
    """Test basic API functionality."""

    def test_root_not_found(self, api_client):
        """Test root path returns 404 (no root route defined)."""
        response = api_client.get("/")
        # FastAPI returns 404 for undefined routes
        assert response.status_code == 404

    def test_nonexistent_endpoint(self, api_client):
        """Test nonexistent endpoint returns 404."""
        response = api_client.get("/nonexistent/endpoint")
        assert response.status_code == 404

    def test_method_not_allowed(self, api_client):
        """Test wrong HTTP method returns 405."""
        # /health only accepts GET
        response = api_client.post("/health")
        assert response.status_code == 405
