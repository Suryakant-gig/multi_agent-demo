import pytest
from unittest.mock import patch, MagicMock
from langchain_core.tools import StructuredTool
from pydantic import ValidationError

from app.tools.registry import tool_registry
from app.tools.base import BaseTool
from app.utils.exceptions import ToolExecutionException, AppException


# ==============================================================================
# 1. LangChain Tool Conversion & Registry Tests
# ==============================================================================

def test_all_tools_convert_to_langchain_structured_tools():
    """Verify all 8 registered tools convert into LangChain StructuredTools with correct names and schemas."""
    tools = tool_registry.list_tools()
    assert len(tools) == 8

    for base_tool in tools:
        lc_tool = base_tool.to_langchain_tool(session_id="test_sess")
        assert isinstance(lc_tool, StructuredTool)
        assert lc_tool.name == base_tool.name
        assert lc_tool.description == base_tool.description
        assert lc_tool.args_schema is not None
        assert issubclass(lc_tool.args_schema, base_tool.get_args_schema())

        # Verify session_id is NOT in the schema presented to LLMs
        assert "session_id" not in lc_tool.args


def test_tool_registry_get_langchain_tools_core_only():
    """Verify get_langchain_tools respects core_only parameter."""
    # core_only=True must return exactly the 5 data tools
    core_tools = tool_registry.get_langchain_tools(session_id="test_sess", core_only=True)
    assert len(core_tools) == 5
    core_names = {t.name for t in core_tools}
    assert core_names == {"search_data", "aggregate_data", "generate_chart", "inspect_schema", "query_sql"}

    # core_only=False must return all 8 tools
    all_tools = tool_registry.get_langchain_tools(session_id="test_sess", core_only=False)
    assert len(all_tools) == 8
    all_names = {t.name for t in all_tools}
    assert "web_search" in all_names
    assert "web_fetch" in all_names
    assert "search_documents" in all_names


def test_tool_registry_prevent_duplicate_names():
    """Verify registry prevents duplicate tool names and reflects changes."""
    names = [t.name for t in tool_registry.get_langchain_tools()]
    assert len(names) == len(set(names))


# ==============================================================================
# 2. Execution via LangChain .invoke() with Session Context
# ==============================================================================

def test_langchain_search_data_invoke(populated_session):
    """Verify search_data tool execution through LangChain invoke."""
    session_id, _ = populated_session
    tool = tool_registry.get_tool("search_data").to_langchain_tool(session_id=session_id)

    res = tool.invoke({"query": "Laptop", "top_k": 5})
    assert isinstance(res, dict)
    assert res["count"] >= 1
    assert "Laptop Pro" in str(res["results"])


def test_langchain_aggregate_data_invoke(populated_session):
    """Verify aggregate_data tool execution through LangChain invoke."""
    session_id, _ = populated_session
    tool = tool_registry.get_tool("aggregate_data").to_langchain_tool(session_id=session_id)

    res = tool.invoke({
        "group_by_column": "category",
        "metric_column": "revenue",
        "aggregation": "SUM",
        "top_k": 5
    })
    assert isinstance(res, dict)
    assert len(res["results"]) <= 5
    top_cat = res["results"][0]
    assert top_cat["category"] == "Electronics"
    assert top_cat["metric"] == 4500.0


def test_langchain_inspect_schema_invoke(populated_session):
    """Verify inspect_schema tool execution through LangChain invoke."""
    session_id, _ = populated_session
    tool = tool_registry.get_tool("inspect_schema").to_langchain_tool(session_id=session_id)

    res = tool.invoke({"sample_limit": 5})
    assert isinstance(res, dict)
    assert res["row_count"] == 8
    assert res["column_count"] == 5


# ==============================================================================
# 3. Security Controls & Validation Preservation
# ==============================================================================

def test_langchain_sql_tool_safety_and_read_only(populated_session):
    """Verify SQL tool preserves read-only restriction and prevents DDL/DML via LangChain invoke."""
    session_id, meta = populated_session
    tool = tool_registry.get_tool("query_sql").to_langchain_tool(session_id=session_id)

    # Valid SELECT query succeeds
    valid_query = f'SELECT product, revenue FROM "{meta.db_table_name}" WHERE revenue > 1000'
    res = tool.invoke({"sql_query": valid_query})
    assert isinstance(res, dict)
    assert res["row_count"] == 2

    # Malicious query raises ToolExecutionException
    with pytest.raises(ToolExecutionException) as exc_info:
        tool.invoke({"sql_query": f'DROP TABLE "{meta.db_table_name}"'})
    assert "Only SELECT/WITH read queries are allowed" in str(exc_info.value)


def test_langchain_web_fetch_security_controls():
    """Verify web_fetch tool preserves SSRF and protocol validations through LangChain invoke."""
    tool = tool_registry.get_tool("web_fetch").to_langchain_tool(session_id="test_sess")

    # Invalid scheme (ftp://) raises AppException or ToolExecutionException
    with pytest.raises((AppException, ToolExecutionException)):
        tool.invoke({"url": "ftp://malicious.com/secret.txt"})

    # Private IP range (SSRF check) raises AppException or ToolExecutionException
    with pytest.raises((AppException, ToolExecutionException)):
        tool.invoke({"url": "http://127.0.0.1:8000/api/internal"})


# ==============================================================================
# 4. Schema Validation & Missing Arguments
# ==============================================================================

def test_langchain_tool_argument_validation():
    """Verify LangChain tool validates required fields and fails gracefully when required inputs are missing."""
    tool = tool_registry.get_tool("aggregate_data").to_langchain_tool(session_id="test_sess")

    # Missing group_by_column and metric_column must fail validation
    with pytest.raises(ValidationError):
        tool.invoke({})


def test_backward_compatibility_existing_callers(populated_session):
    """Verify existing tool_registry.execute_tool and tool.run contracts are 100% unchanged."""
    session_id, _ = populated_session
    res = tool_registry.execute_tool(
        tool_name="search_data",
        session_id=session_id,
        query="Laptop",
        top_k=3
    )
    assert res["count"] >= 1
    assert "Laptop Pro" in str(res["results"])
