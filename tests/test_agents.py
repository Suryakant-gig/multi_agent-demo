from app.agents.orchestrator import agent_orchestrator
from app.state.session_manager import session_manager
from app.models.domain import IntentType


def test_agent_schema_intent(populated_session):
    session_id, _ = populated_session
    res = agent_orchestrator.process_query(session_id, "What columns are in this dataset?")
    assert res["intent"] == IntentType.SCHEMA_INSPECTION.value
    assert "product" in res["answer"].lower()


def test_agent_top_5_analysis(populated_session):
    session_id, _ = populated_session
    res = agent_orchestrator.process_query(session_id, "Show me the top 5 products by revenue")
    assert res["intent"] == IntentType.DATA_ANALYSIS.value
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0]["tool_name"] == "aggregate_data"
    assert "Top 5" in res["answer"]
    assert len(res["citations"]) > 0


def test_agent_coreference_chart_for_that(populated_session):
    session_id, _ = populated_session
    
    # Turn 1: Top 5 query
    res1 = agent_orchestrator.process_query(session_id, "Show me the top 5 categories by revenue")
    assert "Electronics" in res1["answer"]

    # Turn 2: "Make a chart for that"
    res2 = agent_orchestrator.process_query(session_id, "Make a chart for that")
    assert res2["intent"] == IntentType.VISUALIZATION.value
    assert len(res2["tool_calls"]) == 1
    assert res2["tool_calls"][0]["tool_name"] == "generate_chart"
    assert res2["chart"] is not None
    assert res2["chart"]["image_base64"].startswith("data:image/png;base64,")


def test_agent_search_query(populated_session):
    session_id, _ = populated_session
    res = agent_orchestrator.process_query(session_id, "Find any records about Headphones")
    assert res["intent"] == IntentType.SEARCH_RETRIEVAL.value
    assert "Headphones" in res["answer"]
    assert len(res["citations"]) > 0
