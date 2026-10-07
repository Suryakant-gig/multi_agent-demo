import pytest
from app.tools.registry import tool_registry
from app.utils.exceptions import ToolExecutionException


def test_tool_registry():
    tools = tool_registry.list_tools()
    names = [t.name for t in tools]
    assert "search_data" in names
    assert "aggregate_data" in names
    assert "generate_chart" in names
    assert "inspect_schema" in names
    assert "query_sql" in names

    defs = tool_registry.get_tool_definitions()
    assert len(defs) == 5
    assert all("parameters" in d for d in defs)


def test_search_data_tool(populated_session):
    session_id, _ = populated_session
    res = tool_registry.execute_tool(
        tool_name="search_data",
        session_id=session_id,
        query="Laptop",
        top_k=5
    )
    assert res["count"] >= 1
    assert "Laptop Pro" in str(res["results"])


def test_aggregate_data_tool(populated_session):
    session_id, _ = populated_session
    res = tool_registry.execute_tool(
        tool_name="aggregate_data",
        session_id=session_id,
        group_by_column="category",
        metric_column="revenue",
        aggregation="SUM",
        top_k=5
    )
    assert len(res["results"]) <= 5
    # Category Electronics should be top revenue (2500 + 1200 + 800 = 4500)
    top_cat = res["results"][0]
    assert top_cat["category"] == "Electronics"
    assert top_cat["metric"] == 4500.0


def test_inspect_schema_tool(populated_session):
    session_id, _ = populated_session
    res = tool_registry.execute_tool(
        tool_name="inspect_schema",
        session_id=session_id
    )
    assert res["row_count"] == 8
    assert res["column_count"] == 5


def test_sql_tool_safety(populated_session):
    session_id, meta = populated_session
    # Valid SELECT
    res = tool_registry.execute_tool(
        tool_name="query_sql",
        session_id=session_id,
        sql_query=f'SELECT product, revenue FROM "{meta.db_table_name}" WHERE revenue > 1000'
    )
    assert res["row_count"] == 2

    # Malicious non-SELECT query
    with pytest.raises(ToolExecutionException) as exc:
        tool_registry.execute_tool(
            tool_name="query_sql",
            session_id=session_id,
            sql_query=f'DROP TABLE "{meta.db_table_name}"'
        )
    assert "Only SELECT/WITH read queries are allowed" in str(exc.value)
