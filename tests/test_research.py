import pytest
from app.agents.intent_detector import IntentDetector
from app.models.domain import IntentType
from app.state.session_manager import session_manager
from app.tools.registry import tool_registry
from app.services.web_search_service import web_search_service
from app.services.web_fetch_service import web_fetch_service
from app.retrieval.web_ranker import web_ranker
from app.agents.research_planner import research_planner
from app.agents.research_agent import research_agent


def test_research_intent_detection():
    session = session_manager.create_session(session_id="test_intent_sess")

    # Research intent queries
    q1 = "Find 5 papers about hybrid retrieval"
    assert IntentDetector.detect_intent(q1, session) == IntentType.RESEARCH

    q2 = "What are the recent developments in agentic RAG?"
    assert IntentDetector.detect_intent(q2, session) == IntentType.RESEARCH

    q3 = "Research the latest methods for entity resolution"
    assert IntentDetector.detect_intent(q3, session) == IntentType.RESEARCH

    # Web search queries
    q4 = "Search the internet for SQLite PRAGMA commands"
    assert IntentDetector.detect_intent(q4, session) == IntentType.WEB_SEARCH


def test_web_search_tool_schema():
    tool = tool_registry.get_tool("web_search")
    assert tool.name == "web_search"
    schema = tool.parameters_schema
    assert "query" in schema["properties"]
    assert "top_k" in schema["properties"]
    assert "query" in schema["required"]


def test_web_search_top_k_enforcement():
    # Test top-k defaults and bounds
    results = web_search_service.search("hybrid RAG retrieval", top_k=5)
    assert len(results) <= 5
    assert len(results) > 0
    for item in results:
        assert "title" in item
        assert "url" in item
        assert "domain" in item
        assert "source_type" in item
        assert item["url"].startswith("http://") or item["url"].startswith("https://")


def test_web_ranker_scholarly_authority_boost():
    candidates = [
        {
            "title": "Random Blog Post on RAG",
            "url": "https://randomblog.com/post-1",
            "domain": "randomblog.com",
            "snippet": "Just my opinion on RAG.",
            "source_type": "article",
            "relevance_score": 0.70
        },
        {
            "title": "Hybrid Retrieval for Augmented Generation",
            "url": "https://arxiv.org/abs/2310.03743",
            "domain": "arxiv.org",
            "snippet": "Empirical analysis of sparse and dense representations.",
            "source_type": "paper",
            "relevance_score": 0.75
        }
    ]

    ranked = web_ranker.rank_candidates("hybrid RAG retrieval paper", candidates, top_k=2)
    assert len(ranked) == 2
    # arXiv paper must be ranked #1 due to scholarly authority and paper boost
    assert ranked[0]["domain"] == "arxiv.org"
    assert ranked[0]["source_type"] == "paper"


def test_research_planner_planning_flow():
    query = "Find 5 papers about hybrid RAG retrieval and summarize them"
    plan = research_planner.create_plan(query)
    assert plan.max_sources == 5
    assert len(plan.search_queries) >= 2
    assert plan.needs_fetch is True
    assert any("hybrid" in q.lower() for q in plan.search_queries)


def test_research_agent_grounded_workflow():
    session_id = "test_agent_research_sess"
    session_manager.create_session(session_id=session_id)

    res = research_agent.execute_research(
        query="Find papers about hybrid RAG retrieval",
        session_id=session_id,
        max_sources=3
    )

    assert "answer" in res
    assert len(res["sources"]) > 0
    assert len(res["sources"]) <= 3
    assert len(res["citations"]) > 0

    # Verify no fabricated URLs: every source has a valid real URL
    for src in res["sources"]:
        assert src.url.startswith("http://") or src.url.startswith("https://")
        assert len(src.domain) > 0
        assert len(src.title) > 0

    # Verify clickable links rendered in answer Sources section
    assert "### Sources" in res["answer"]
    assert "http" in res["answer"]
