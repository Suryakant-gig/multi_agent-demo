from app.retrieval.ranker import RelevanceRanker
from app.retrieval.citation import CitationGenerator
from app.retrieval.search_engine import search_engine
from app.state.session_manager import session_manager


def test_relevance_ranker_scoring():
    record = {"product": "Pro Gaming Laptop", "category": "Computers", "price": 1500}
    score, matched = RelevanceRanker.calculate_score(
        record=record,
        query_tokens=["gaming", "laptop"],
        raw_query="gaming laptop"
    )
    assert score > 0
    assert "product" in matched


def test_relevance_ranker_deduplication():
    candidates = [
        {"_row_id": 1, "product": "Mouse", "price": 20},
        {"_row_id": 2, "product": "Mouse", "price": 20},  # Duplicate
        {"_row_id": 3, "product": "Keyboard", "price": 50}
    ]
    ranked = RelevanceRanker.rank_and_deduplicate(
        candidates=candidates,
        query="mouse",
        file_id="f1",
        file_name="items.csv",
        top_k=5
    )
    assert len(ranked) == 2
    assert ranked[0].data["product"] == "Mouse"


def test_search_engine_top_k(populated_session):
    session_id, meta = populated_session
    results = search_engine.search(
        session_id=session_id,
        dataset=meta,
        query="Electronics",
        top_k=3
    )
    assert len(results) <= 3
    assert all("electronics" in r.data["category"].lower() for r in results)
    assert results[0].citation.file_name == "test_sales.csv"
    assert results[0].citation.row_index is not None
