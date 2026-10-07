import io
from fastapi.testclient import TestClient


def test_upload_invalid_extension(test_client: TestClient):
    file_content = b"fake binary data"
    response = test_client.post(
        "/api/v1/upload",
        files={"file": ("virus.exe", io.BytesIO(file_content), "application/octet-stream")}
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["error"]


def test_upload_empty_file(test_client: TestClient):
    response = test_client.post(
        "/api/v1/upload",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    )
    assert response.status_code == 400
    assert "empty" in response.json()["error"].lower()


def test_search_non_existent_session(test_client: TestClient):
    response = test_client.post(
        "/api/v1/search",
        json={
            "session_id": "non-existent-session-id",
            "query": "anything"
        }
    )
    assert response.status_code == 404
    assert "not found" in response.json()["error"]


def test_chart_invalid_column(test_client: TestClient, populated_session):
    session_id, _ = populated_session
    response = test_client.post(
        "/api/v1/chart",
        json={
            "session_id": session_id,
            "chart_type": "bar",
            "x_column": "fake_column_xyz",
            "y_column": "revenue"
        }
    )
    assert response.status_code == 400
    assert "fake_column_xyz" in response.json()["error"]


def test_chat_empty_query_validation(test_client: TestClient, populated_session):
    session_id, _ = populated_session
    response = test_client.post(
        "/api/v1/chat",
        json={
            "session_id": session_id,
            "query": ""
        }
    )
    assert response.status_code == 422
