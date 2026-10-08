import os
import pytest
from fastapi.testclient import TestClient
from app.state.session_manager import session_manager
from app.models.domain import DatasetMetadata, ColumnMetadata, MessageRecord


def test_create_new_conversation():
    session = session_manager.create_session(title="Financial Q3")
    assert session.conversation_id is not None
    assert session.session_id == session.conversation_id
    assert session.title == "Financial Q3"
    assert session.messages == []
    assert session.files == {}


def test_conversation_isolation():
    # Create conversation 1 with a dataset
    conv1 = session_manager.create_session(session_id="conv_iso_1", title="Conv 1")
    meta1 = DatasetMetadata(
        file_id="f1",
        file_name="sales_2023.csv",
        file_size_bytes=5000,
        row_count=50,
        column_count=2,
        columns=[ColumnMetadata(name="revenue", data_type="numeric")],
        db_table_name="data_f1"
    )
    session_manager.register_file(conv1.session_id, meta1)

    # Create conversation 2 without dataset
    conv2 = session_manager.create_session(session_id="conv_iso_2", title="Conv 2")

    # Verify complete isolation: conv2 must NOT have conv1's files or active dataset
    s1 = session_manager.get_session("conv_iso_1")
    s2 = session_manager.get_session("conv_iso_2")

    assert "f1" in s1.files
    assert s1.active_dataset is not None
    assert s1.active_dataset.file_name == "sales_2023.csv"

    assert "f1" not in s2.files
    assert s2.active_dataset is None


def test_conversation_persistence():
    conv_id = "conv_persist_test"
    session = session_manager.create_session(session_id=conv_id, title="Persist Chat")
    session_manager.append_message(
        conv_id,
        MessageRecord(role="user", content="Hello InfinityGPT")
    )

    # Verify conversation is persisted in database
    from app.storage.repositories.conversation_repository import conversation_repository
    from app.storage.repositories.message_repository import message_repository
    db_conv = conversation_repository.get(conv_id)
    assert db_conv is not None
    assert db_conv["title"] == "Persist Chat"

    msgs = message_repository.get_messages(conv_id)
    assert len(msgs) >= 1
    assert msgs[0].content == "Hello InfinityGPT"

    # Evict from memory to verify cold hydration from database
    if conv_id in session_manager._sessions:
        del session_manager._sessions[conv_id]

    # Retrieve session fresh from database
    reloaded = session_manager.get_session(conv_id)
    assert reloaded.title == "Persist Chat"
    assert len(reloaded.messages) >= 1
    assert reloaded.messages[0].content == "Hello InfinityGPT"


def test_conversation_rename_and_delete():
    conv_id = "conv_rename_del"
    session_manager.create_session(session_id=conv_id, title="Original Title")

    renamed = session_manager.rename_conversation(conv_id, "Updated Title")
    assert renamed.title == "Updated Title"

    # Delete conversation
    success = session_manager.delete_conversation(conv_id)
    assert success is True
    assert not session_manager.session_exists(conv_id)


def test_conversation_api_endpoints(test_client: TestClient):
    # 1. Create via API
    res = test_client.post("/api/v1/conversations", json={"title": "API Created Chat"})
    assert res.status_code == 201
    data = res.json()
    conv_id = data["conversation_id"]
    assert data["title"] == "API Created Chat"

    # 2. List conversations
    res_list = test_client.get("/api/v1/conversations")
    assert res_list.status_code == 200
    convs = res_list.json()
    assert any(c["conversation_id"] == conv_id for c in convs)

    # 3. Get detail
    res_get = test_client.get(f"/api/v1/conversations/{conv_id}")
    assert res_get.status_code == 200
    assert res_get.json()["title"] == "API Created Chat"

    # 4. Rename via PATCH
    res_patch = test_client.patch(f"/api/v1/conversations/{conv_id}", json={"title": "Renamed API Chat"})
    assert res_patch.status_code == 200
    assert res_patch.json()["title"] == "Renamed API Chat"

    # 5. Delete via DELETE
    res_del = test_client.delete(f"/api/v1/conversations/{conv_id}")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True
