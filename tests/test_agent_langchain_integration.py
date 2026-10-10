import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from app.agents.orchestrator import agent_orchestrator
from app.agents.research_agent import research_agent
from app.models.domain import IntentType, ToolCallRecord
from app.state.session_manager import session_manager
from app.tools.registry import tool_registry
from app.agents.llm_client import llm_client
from app.utils.exceptions import ToolExecutionException


def test_deterministic_routing_preserved(populated_session):
    """Verifies that IntentDetector and TaskPlanner remain authoritative."""
    session_id, _ = populated_session

    res = agent_orchestrator.process_query(session_id, "Show me the top 3 products by revenue")
    assert res["intent"] == IntentType.DATA_ANALYSIS.value
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0]["tool_name"] == "aggregate_data"
    assert "Top 3" in res["answer"]


def test_orchestrator_executes_tool_via_langchain(populated_session):
    """Verifies that AgentOrchestrator delegates tool execution through LangChain tool adapter."""
    session_id, _ = populated_session

    with patch.object(agent_orchestrator, "_execute_tool", wraps=agent_orchestrator._execute_tool) as mock_exec:
        res = agent_orchestrator.process_query(session_id, "What columns are in this dataset?")
        assert res["intent"] == IntentType.SCHEMA_INSPECTION.value
        mock_exec.assert_called_once()
        assert mock_exec.call_args[1]["tool_name"] == "inspect_schema"
        assert mock_exec.call_args[1]["session_id"] == session_id


def test_orchestrator_handles_tool_failure(populated_session):
    """Verifies that tool execution errors are safely captured in tool records without crashing."""
    session_id, _ = populated_session

    res = agent_orchestrator.process_query(session_id, "Show me the top 3 nonexistent_column by revenue")
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0]["success"] is False
    assert "not found" in res["tool_calls"][0]["error_message"].lower()
    assert "issue executing tool" in res["answer"]


def test_research_agent_uses_langchain_tools():
    """Verifies that ResearchAgent utilizes LangChain web_search and web_fetch tools."""
    session_id = "test_research_lc_sess"
    session_manager.create_session(session_id)

    res = research_agent.execute_research(
        query="Research hybrid RAG papers",
        session_id=session_id,
        max_sources=2
    )

    assert "answer" in res
    assert len(res["sources"]) > 0
    assert len(res["sources"]) <= 2
    assert len(res["citations"]) > 0

    tool_names = [tc.tool_name for tc in res["tool_calls"]]
    assert "web_search" in tool_names


def test_hybrid_workflow_uses_langchain_tools(populated_session):
    """Verifies that the hybrid workflow dispatches data extraction through LangChain tools."""
    session_id, _ = populated_session

    with patch.object(agent_orchestrator, "_execute_tool", wraps=agent_orchestrator._execute_tool) as mock_exec:
        res = agent_orchestrator.process_query(
            session_id=session_id,
            query="Analyze my sales dataset and find research papers on consumer trends"
        )
        assert res["intent"] == IntentType.HYBRID.value
        # Verify _execute_tool was called for the tabular portion
        tool_names = [call[1]["tool_name"] for call in mock_exec.call_args_list]
        assert "aggregate_data" in tool_names
        assert len(res["citations"]) > 0


def test_bounded_tool_loop_fallback_when_llm_unavailable():
    """Verifies that execute_with_langchain_tools falls back to deterministic execution when LLM is unavailable."""
    session_id = "test_bounded_fallback_sess"
    session_manager.create_session(session_id)

    with patch.object(llm_client, "_chat_model", None):
        res = agent_orchestrator.execute_with_langchain_tools(
            session_id=session_id,
            query="Hello"
        )
        assert "answer" in res
        assert res["intent"] == IntentType.DIRECT_ANSWER.value


def test_bounded_tool_loop_repeated_call_protection(populated_session):
    """Verifies loop protection against repeated identical tool calls."""
    session_id, _ = populated_session

    mock_chat_model = MagicMock()
    # Mock AI response requesting the exact same tool call twice
    tool_call_item = {
        "name": "inspect_schema",
        "args": {"sample_limit": 5},
        "id": "call_123"
    }
    ai_with_tool_call = AIMessage(content="", tool_calls=[tool_call_item])
    ai_final = AIMessage(content="Here is the schema.")
    # On first and second invocation, returns identical tool call, then final
    mock_chat_model.bind_tools.return_value.invoke.side_effect = [
        ai_with_tool_call,
        ai_with_tool_call,
        ai_final
    ]

    with patch.object(llm_client, "_chat_model", mock_chat_model):
        res = agent_orchestrator.execute_with_langchain_tools(
            session_id=session_id,
            query="Inspect the schema",
            max_iterations=3
        )
        assert "answer" in res
        assert res["intent"] == IntentType.DIRECT_ANSWER.value
        # Loop protection prevented infinite cycles and stopped repeat calls
        assert len(res["tool_calls"]) <= 2


def test_orchestrator_sql_security_enforcement(populated_session):
    """Verifies read-only SQL restrictions remain enforced through the LangChain tool interface in the orchestrator."""
    session_id, _ = populated_session

    with pytest.raises(ToolExecutionException) as exc_info:
        agent_orchestrator._execute_tool(
            tool_name="query_sql",
            session_id=session_id,
            parameters={"sql_query": "DROP TABLE sales"}
        )
    assert "Only SELECT/WITH read queries are allowed" in str(exc_info.value)
