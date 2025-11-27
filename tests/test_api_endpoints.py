BASE_HEADERS = {}  # placeholder if you later need auth headers


def test_health_endpoint(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    if isinstance(data, dict) and "status" in data:
        assert data["status"] == "ok"


def test_get_workouts_missing_all_params_returns_422(api_client):
    """
    /workouts requires at least profile_id – calling it bare should 422.
    """
    resp = api_client.get("/workouts")
    assert resp.status_code == 422


def test_get_workouts_with_profile_id_does_not_return_422(api_client):
    """
    With profile_id provided, we should at least pass FastAPI validation.
    We don't assert 200 here to avoid coupling to DB/state.
    """
    resp = api_client.get("/workouts", params={"profile_id": "test-user"})
    assert resp.status_code != 422


def test_validate_workflow_missing_body_returns_422(api_client):
    """
    POST /workflow/validate expects a BlocksPayload body.
    Sending {} should fail validation.
    """
    resp = api_client.post("/workflow/validate", json={})
    assert resp.status_code == 422


def test_map_final_missing_body_returns_422(api_client):
    """
    POST /map/final expects an IngestPayload body.
    """
    resp = api_client.post("/map/final", json={})
    assert resp.status_code == 422


def test_exercise_suggest_missing_body_returns_422(api_client):
    """
    POST /exercise/suggest expects an ExerciseSuggestionRequest body.
    """
    resp = api_client.post("/exercise/suggest", json={})
    assert resp.status_code == 422


def test_exercise_similar_basic_call_not_422(api_client):
    """
    Simple smoke test for GET /exercise/similar/{exercise_name}.
    We only assert that validation passes (not 422).
    """
    resp = api_client.get("/exercise/similar/squat")
    assert resp.status_code != 422


def test_list_mappings_not_422(api_client):
    """
    GET /mappings has no required params – should at least pass validation.
    """
    resp = api_client.get("/mappings")
    assert resp.status_code != 422