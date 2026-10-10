import io
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.domain import IntentType

client = TestClient(app)


def test_e2e_health_check():
    """Verifies the health check endpoint."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "database" in data


def test_e2e_full_workflow():
    """
    Exercises complete end-to-end API lifecycle:
    1. Upload CSV dataset -> returns 201 Created
    2. Inspect schema via /api/v1/chat -> returns 200 OK
    3. Aggregate data via /api/v1/chat -> returns 200 OK with citations
    4. Generate chart via /api/v1/chart -> returns 200 OK with base64 image
    5. Conversational greeting -> returns 200 OK
    6. Verify conversation history via /api/v1/conversations
    """
    # 1. Upload CSV dataset
    csv_content = b"Product,Region,Revenue,Quantity\nLaptop,North,1200,5\nMouse,South,40,10\nKeyboard,East,90,8\nMonitor,West,450,4\n"
    files = {"file": ("e2e_sales.csv", io.BytesIO(csv_content), "text/csv")}
    
    upload_resp = client.post("/api/v1/upload", files=files)
    assert upload_resp.status_code == 201
    up_data = upload_resp.json()
    assert up_data["success"] is True
    session_id = up_data["session_id"]
    assert session_id is not None
    assert up_data["row_count"] == 4

    # 2. Schema inspection via /api/v1/chat
    chat_resp = client.post("/api/v1/chat", json={
        "session_id": session_id,
        "query": "What columns are in this dataset?"
    })
    assert chat_resp.status_code == 200
    c_data = chat_resp.json()
    assert c_data["intent"] == IntentType.SCHEMA_INSPECTION.value
    assert "product" in c_data["answer"].lower()
    assert len(c_data["tool_calls"]) == 1

    # 3. Aggregation via /api/v1/chat
    agg_resp = client.post("/api/v1/chat", json={
        "session_id": session_id,
        "query": "Show me the top 3 products by revenue"
    })
    assert agg_resp.status_code == 200
    a_data = agg_resp.json()
    assert a_data["intent"] == IntentType.DATA_ANALYSIS.value
    assert "Top 3" in a_data["answer"]
    assert len(a_data["citations"]) > 0

    # 4. Chart generation via /api/v1/chart
    chart_resp = client.post("/api/v1/chart", json={
        "session_id": session_id,
        "chart_type": "bar",
        "x_column": "Product",
        "y_column": "Revenue"
    })
    assert chart_resp.status_code == 200
    ch_data = chart_resp.json()
    assert ch_data["image_base64"].startswith("data:image/png;base64,")

    # 5. Conversational greeting
    hello_resp = client.post("/api/v1/chat", json={
        "session_id": session_id,
        "query": "Hello"
    })
    assert hello_resp.status_code == 200
    h_data = hello_resp.json()
    assert len(h_data["answer"]) > 0

    # 6. Verify conversations endpoint
    conv_resp = client.get(f"/api/v1/conversations/{session_id}")
    assert conv_resp.status_code == 200
    conv_data = conv_resp.json()
    assert conv_data["session_id"] == session_id
    assert len(conv_data["messages"]) >= 6


def test_e2e_sql_security_enforcement():
    """Verifies that arbitrary or destructive SQL queries are blocked via the API."""
    csv_content = b"Item,Cost\nA,10\nB,20\n"
    files = {"file": ("test_sql.csv", io.BytesIO(csv_content), "text/csv")}
    upload_resp = client.post("/api/v1/upload", files=files)
    assert upload_resp.status_code == 201
    session_id = upload_resp.json()["session_id"]

    from app.agents.orchestrator import agent_orchestrator
    with pytest.raises(Exception) as exc_info:
        agent_orchestrator._execute_tool(
            tool_name="query_sql",
            session_id=session_id,
            parameters={"sql_query": "DELETE FROM test_sql"}
        )
    assert "Only SELECT/WITH read queries are allowed" in str(exc_info.value)
