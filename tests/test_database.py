import pytest
from app.storage.database import check_connection, init_db, get_engine
from app.storage.repositories import (
    conversation_repository,
    message_repository,
    file_repository,
    document_repository,
    tool_repository,
    research_repository,
    citation_repository
)
from app.models.domain import (
    MessageRecord,
    IntentType,
    ToolCallRecord,
    CitationItem,
    SourceItem,
    DatasetMetadata,
    ColumnMetadata,
    DocumentMetadata,
    DocumentChunk
)


def test_database_initialization_and_health():
    init_db()
    health = check_connection()
    assert health["status"] == "connected"
    assert health["database"] == "connected"


def test_conversation_repository_crud():
    conv_id = "test_conv_repo_1"
    # Create
    created = conversation_repository.create(conv_id, title="Initial Title")
    assert created["id"] == conv_id
    assert created["title"] == "Initial Title"

    # Get
    fetched = conversation_repository.get(conv_id)
    assert fetched is not None
    assert fetched["title"] == "Initial Title"

    # Update Title
    conversation_repository.update_title(conv_id, "Renamed Title")
    assert conversation_repository.get(conv_id)["title"] == "Renamed Title"

    # List
    conv_list = conversation_repository.list_all()
    assert any(c["conversation_id"] == conv_id for c in conv_list)

    # Delete
    assert conversation_repository.delete(conv_id) is True
    assert conversation_repository.get(conv_id) is None


def test_message_and_audit_persistence():
    conv_id = "test_conv_repo_msg"
    conversation_repository.create(conv_id, title="Audit Test")

    user_msg = MessageRecord(role="user", content="Top 5 items by cost")
    msg_id_1 = message_repository.add_message(conv_id, user_msg)
    assert msg_id_1.startswith("msg_")

    tool_record = ToolCallRecord(
        tool_name="aggregate_data",
        parameters={"group_by": "category", "metric": "cost"},
        result={"summary": "Electronics is highest"},
        execution_time_ms=12.5,
        success=True
    )

    cite = CitationItem(
        file_id="f_audit",
        file_name="sales.csv",
        row_index=1,
        citation_type="dataset",
        snippet="category: Electronics | cost: 500"
    )

    source = SourceItem(
        title="RAG Systems Paper",
        url="https://arxiv.org/abs/2005.11401",
        domain="arxiv.org",
        snippet="Retrieval-Augmented Generation methodology",
        relevance_score=0.92
    )

    asst_msg = MessageRecord(
        role="assistant",
        content="Electronics generated highest cost.",
        intent=IntentType.DATA_ANALYSIS,
        tool_calls=[tool_record],
        citations=[cite],
        sources=[source]
    )
    msg_id_2 = message_repository.add_message(conv_id, asst_msg)
    assert msg_id_2.startswith("msg_")

    # Persist tool history, sources, citations
    tool_repository.record_tool_call(conv_id, tool_record)
    research_repository.save_sources(conv_id, [source])
    citation_repository.save_citations(conv_id, msg_id_2, [cite])

    # Verify retrieval
    msgs = message_repository.get_messages(conv_id)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].role == "assistant"
    assert msgs[1].intent == IntentType.DATA_ANALYSIS
    assert len(msgs[1].tool_calls) == 1
    assert msgs[1].tool_calls[0].tool_name == "aggregate_data"

    tools_logged = tool_repository.get_history(conv_id)
    assert any(t["tool_name"] == "aggregate_data" for t in tools_logged)

    sources_logged = research_repository.get_sources(conv_id)
    assert any(s.title == "RAG Systems Paper" for s in sources_logged)

    citations_logged = citation_repository.get_citations(conv_id)
    assert any(c.file_name == "sales.csv" or c.snippet == "category: Electronics | cost: 500" for c in citations_logged)

    # Clean up
    conversation_repository.delete(conv_id)


def test_file_and_dataset_repository():
    conv_id = "test_conv_files"
    conversation_repository.create(conv_id, title="Files Test")

    meta = DatasetMetadata(
        file_id="fid_123",
        file_name="q3_data.csv",
        file_size_bytes=1024,
        row_count=100,
        column_count=2,
        columns=[
            ColumnMetadata(name="item", data_type="string"),
            ColumnMetadata(name="cost", data_type="numeric")
        ],
        db_table_name="data_fid_123"
    )

    file_repository.save_dataset_metadata(meta, conv_id, storage_path="data/uploads/q3_data.csv")

    datasets = file_repository.get_datasets_for_conversation(conv_id)
    assert "fid_123" in datasets
    assert datasets["fid_123"].file_name == "q3_data.csv"
    assert datasets["fid_123"].row_count == 100
    assert len(datasets["fid_123"].columns) == 2

    # Clean up
    conversation_repository.delete(conv_id)


def test_document_and_chunk_repository():
    conv_id = "test_conv_docs"
    conversation_repository.create(conv_id, title="Docs Test")

    doc_meta = DocumentMetadata(
        document_id="doc_789",
        file_name="paper.pdf",
        file_size_bytes=2048,
        page_count=10,
        chunk_count=2
    )

    chunks = [
        DocumentChunk(
            chunk_id="chk_1",
            document_id="doc_789",
            file_name="paper.pdf",
            page_number=1,
            text="Introduction to Hybrid RAG systems and multi-agent coordination."
        ),
        DocumentChunk(
            chunk_id="chk_2",
            document_id="doc_789",
            file_name="paper.pdf",
            page_number=7,
            text="Experimental benchmarks show a 42% accuracy gain over baseline RAG."
        )
    ]

    document_repository.save_document_metadata(doc_meta, conv_id, storage_path="data/uploads/paper.pdf")
    document_repository.save_chunks(chunks, session_id=conv_id)

    docs = document_repository.get_documents_for_conversation(conv_id)
    assert "doc_789" in docs
    assert docs["doc_789"].page_count == 10

    retrieved_chunks = document_repository.get_chunks(session_id=conv_id, document_id="doc_789")
    assert len(retrieved_chunks) == 2

    page_7_chunks = document_repository.get_chunks_by_page(session_id=conv_id, page_number=7, document_id="doc_789")
    assert len(page_7_chunks) == 1
    assert "42% accuracy gain" in page_7_chunks[0].text

    # Clean up
    conversation_repository.delete(conv_id)


def test_frontend_root_served_at_slash(test_client):
    """
    Verifies single-origin frontend mounting:
    GET / must return InfinityGPT index.html with status 200.
    """
    res = test_client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "InfinityGPT" in res.text


def test_health_endpoint_checks_database(test_client):
    """
    Verifies /api/v1/health returns status and database status.
    """
    res = test_client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert data["database"] in ("connected", "disconnected")
