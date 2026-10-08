from typing import Dict, Any, List, Optional
from app.tools.base import BaseTool
from app.services.web_search_service import web_search_service
from app.retrieval.web_ranker import web_ranker
from app.retrieval.web_citation import web_citation_formatter
from app.utils.config import settings
from app.utils.logger import logger


class WebSearchTool(BaseTool):
    """
    Searches the public web and scholarly publications for high-authority sources.
    Prioritizes research papers, arXiv, Semantic Scholar, and official technical documentation.
    """
    name = "web_search"
    description = (
        "Search the web and scholarly databases for research papers, documentation, or technical developments. "
        "Returns top authoritative sources with titles, snippets, publication dates, and valid URLs."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Specific search query (e.g. 'hybrid RAG dense sparse retrieval paper')."
            },
            "top_k": {
                "type": "integer",
                "description": "Number of top results to return (default: 5).",
                "default": 5
            },
            "domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of domains to restrict search to (e.g. ['arxiv.org'])."
            },
            "recency_days": {
                "type": "integer",
                "description": "Optional recency filter in days for recent events or newest publications."
            },
            "research_mode": {
                "type": "boolean",
                "description": "Prioritize academic papers and technical documentation over general websites.",
                "default": True
            }
        },
        "required": ["query"]
    }
    output_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "result_count": {"type": "integer"},
            "results": {"type": "array"}
        }
    }
    usage_example = {
        "query": "hybrid RAG retrieval research papers",
        "top_k": 5,
        "research_mode": True
    }

    def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "")
        top_k = kwargs.get("top_k", settings.DEFAULT_TOP_K)
        domains = kwargs.get("domains")
        recency_days = kwargs.get("recency_days")
        research_mode = kwargs.get("research_mode", True)

        raw_results = web_search_service.search(
            query=query,
            top_k=max(top_k * 2, 6),
            domains=domains,
            recency_days=recency_days,
            research_mode=research_mode
        )

        ranked = web_ranker.rank_candidates(
            query=query,
            candidates=raw_results,
            top_k=top_k,
            prefer_research=research_mode
        )

        return {
            "query": query,
            "result_count": len(ranked),
            "results": ranked
        }
