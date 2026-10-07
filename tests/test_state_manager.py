import pytest
from app.state.session_manager import session_manager
from app.models.domain import DatasetMetadata, MessageRecord, ToolCallRecord
from app.utils.exceptions import SessionNotFoundException, FileNotFoundException


def test_session_lifecycle():
    sess = session_manager.create_session("sess-1")
    assert sess.session_id == "sess-1"
    assert session_manager.session_exists("sess-1")

    # Fetching existing session returns the same object
    fetched = session_manager.get_session("sess-1")
    assert fetched.session_id == sess.session_id

    # Non-existent session
    with pytest.raises(SessionNotFoundException):
        session_manager.get_session("non-existent-sess")


def test_session_file_tracking():
    sess = session_manager.create_session("sess-files")
    meta = DatasetMetadata(
        file_id="f1",
        file_name="test.csv",
        file_size_bytes=100,
        row_count=10,
        column_count=2,
        columns=[],
        db_table_name="data_f1"
    )
    session_manager.register_file("sess-files", meta)
    active = session_manager.get_active_file("sess-files")
    assert active.file_id == "f1"
    assert active.file_name == "test.csv"


def test_session_context_update():
    sess = session_manager.create_session("sess-ctx")
    record = ToolCallRecord(
        tool_name="aggregate_data",
        parameters={"group_by": "product"},
        result={"data": []}
    )
    session_manager.update_context("sess-ctx", query_summary="Summary 1", tool_call=record)
    
    updated = session_manager.get_session("sess-ctx")
    assert updated.last_query_summary == "Summary 1"
    assert updated.last_tool_call.tool_name == "aggregate_data"
