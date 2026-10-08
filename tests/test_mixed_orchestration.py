import pytest
from app.agents.intent_detector import IntentDetector
from app.models.domain import IntentType, DatasetMetadata, ColumnMetadata
from app.state.session_manager import session_manager
from app.agents.orchestrator import agent_orchestrator
from app.documents.chunker import document_chunker
from app.documents.document_store import document_store


def test_hybrid_intent_detection(populated_session):
    session_id, _ = populated_session
    session = session_manager.get_session(session_id)

    query = "Analyze my sales data and find research papers explaining the seasonal pattern"
    intent = IntentDetector.detect_intent(query, session)
    assert intent == IntentType.HYBRID


def test_hybrid_data_plus_web_execution(populated_session):
    session_id, _ = populated_session

    query = "Look at my sales dataset and find research papers explaining consumer demand trends"
    res = agent_orchestrator.process_query(session_id=session_id, query=query)

    assert res["intent"] == IntentType.HYBRID.value
    assert "answer" in res
    assert len(res["citations"]) > 0

    # Verify both dataset citations AND web citations exist
    has_dataset_citation = any(c.get("citation_type") == "dataset" for c in res["citations"])
    has_web_citation = any(c.get("citation_type") == "web" for c in res["citations"])

    assert has_dataset_citation is True
    assert has_web_citation is True
    assert len(res["sources"]) > 0


def test_smart_routing_isolation(populated_session):
    session_id, _ = populated_session

    # 1. Pure data query routes to data analysis
    q_data = "Show me the top 3 products by revenue"
    res_data = agent_orchestrator.process_query(session_id=session_id, query=q_data)
    assert res_data["intent"] == IntentType.DATA_ANALYSIS.value
    # No web sources for pure data analysis
    assert len(res_data["sources"]) == 0

    # 2. Pure research query routes to research agent
    q_research = "Find 5 papers about hybrid retrieval"
    res_research = agent_orchestrator.process_query(session_id=session_id, query=q_research)
    assert res_research["intent"] == IntentType.RESEARCH.value
    assert len(res_research["sources"]) > 0


def test_document_retrieval_routing():
    session_id = "sess_doc_routing"
    session_manager.create_session(session_id=session_id)

    # Register document chunks
    chunks = document_chunker.chunk_document(
        document_id="doc_rag",
        file_name="evaluation_paper.pdf",
        pages=[
            {"page_number": 1, "text": "Abstract: Comprehensive benchmark on RAG faithfulness."},
            {"page_number": 10, "text": "Page 10 discusses the error breakdown and latency curves."}
        ]
    )
    document_store.store_chunks(session_id=session_id, chunks=chunks)

    # Query asking about page 10
    query = "What does page 10 of the paper say?"
    res = agent_orchestrator.process_query(session_id=session_id, query=query)

    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert len(res["citations"]) > 0
    assert any(c.get("citation_type") == "pdf" and c.get("page_number") == 10 for c in res["citations"])
