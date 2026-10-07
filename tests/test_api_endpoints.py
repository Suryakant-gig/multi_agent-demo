import os
from fastapi.testclient import TestClient


def test_api_health(test_client: TestClient):
    response = test_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_api_upload_csv(test_client: TestClient, sample_csv_path):
    with open(sample_csv_path, "rb") as f:
        response = test_client.post(
            "/api/v1/upload",
            files={"file": ("sales.csv", f, "text/csv")},
            data={"session_id": "api-sess-1"}
        )
    assert response.status_code == 201
    data = response.json()
    assert data["session_id"] == "api-sess-1"
    assert data["row_count"] == 8
    assert len(data["columns"]) == 5


def test_api_upload_excel(test_client: TestClient, sample_excel_path):
    with open(sample_excel_path, "rb") as f:
        response = test_client.post(
            "/api/v1/upload",
            files={"file": ("inventory.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"session_id": "api-sess-excel"}
        )
    assert response.status_code == 201
    data = response.json()
    assert data["row_count"] == 3


def test_api_search(test_client: TestClient, populated_session):
    session_id, _ = populated_session
    response = test_client.post(
        "/api/v1/search",
        json={
            "session_id": session_id,
            "query": "Electronics",
            "top_k": 3
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] <= 3
    assert len(data["results"]) > 0
    assert "citation" in data["results"][0]


def test_api_chart(test_client: TestClient, populated_session):
    session_id, _ = populated_session
    response = test_client.post(
        "/api/v1/chart",
        json={
            "session_id": session_id,
            "chart_type": "bar",
            "x_column": "category",
            "y_column": "revenue",
            "aggregation": "SUM",
            "title": "Revenue by Category"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["chart_type"] == "bar"
    assert data["image_base64"].startswith("data:image/png;base64,")
    assert "spec_json" in data


def test_api_chat_flow(test_client: TestClient, populated_session):
    session_id, _ = populated_session
    
    # Query 1
    resp1 = test_client.post(
        "/api/v1/chat",
        json={
            "session_id": session_id,
            "query": "Show me the top 5 products by revenue"
        }
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "Laptop Pro" in data1["answer"]
    assert len(data1["citations"]) > 0

    # Query 2: Coreference chart
    resp2 = test_client.post(
        "/api/v1/chat",
        json={
            "session_id": session_id,
            "query": "Make a chart for that"
        }
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["chart"] is not None
    assert data2["chart"]["image_base64"].startswith("data:image/png;base64,")
