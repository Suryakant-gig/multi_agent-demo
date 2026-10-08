import re
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from app.utils.config import settings


class ResearchPlan(BaseModel):
    research_goal: str
    search_queries: List[str]
    max_sources: int = 5
    needs_fetch: bool = True
    source_preferences: List[str] = Field(default_factory=list)


class ResearchPlanner:
    """
    Formulates a targeted research plan from user questions.
    Generates high-precision multi-angle search queries while bounding tool executions.
    """

    SCHOLARLY_KEYWORDS = ["paper", "papers", "arxiv", "survey", "benchmark", "literature", "research", "study", "studies"]

    def create_plan(self, query: str) -> ResearchPlan:
        q_lower = query.lower()

        # 1. Parse requested source count (default 5)
        max_sources = 5
        count_match = re.search(r"\b(\d+)\s*(?:papers|sources|articles|references|docs)\b", q_lower)
        if count_match:
            try:
                max_sources = min(max(int(count_match.group(1)), 1), settings.MAX_RESEARCH_SOURCES)
            except ValueError:
                max_sources = 5

        # 2. Extract research goal
        clean_goal = query
        for prefix in [
            "find recent research on", "find latest research on", "find research papers on",
            "find 5 papers about", "find papers about", "find research on",
            "research the latest methods for", "research the latest developments in",
            "what are the recent developments in", "what are the latest developments in",
            "compare these papers on", "find official documentation for", "search the internet for",
            "find papers explaining", "find", "research", "search for"
        ]:
            if q_lower.startswith(prefix):
                clean_goal = query[len(prefix):].strip()
                break

        clean_goal = clean_goal.strip("?.: ")
        if not clean_goal:
            clean_goal = query

        # 3. Determine source preferences
        is_paper_oriented = any(w in q_lower for w in self.SCHOLARLY_KEYWORDS)
        is_docs_oriented = any(w in q_lower for w in ["doc", "docs", "documentation", "api", "reference", "official"])

        source_preferences = []
        if is_paper_oriented:
            source_preferences.extend(["research paper", "arxiv", "semantic scholar"])
        if is_docs_oriented:
            source_preferences.append("official documentation")
        if not source_preferences:
            source_preferences.extend(["research paper", "official documentation", "technical article"])

        # 4. Generate targeted multi-facet search queries (2 to 3 queries max)
        queries = []
        primary_query = clean_goal
        if is_paper_oriented and "paper" not in primary_query.lower():
            primary_query += " research paper"
        queries.append(primary_query)

        # Variant 1: Academic / benchmark aspect
        if "rag" in clean_goal.lower():
            queries.append(f"{clean_goal} benchmark evaluation")
        elif "retrieval" in clean_goal.lower():
            queries.append(f"{clean_goal} dense sparse hybrid")
        else:
            queries.append(f"{clean_goal} state of the art survey")

        # Variant 2: Technical architecture / methodology
        if len(queries) < 3:
            queries.append(f"{clean_goal} methodology architecture")

        # 5. Determine whether page fetch is required
        needs_fetch = any(w in q_lower for w in ["compare", "summarize", "details", "explain", "findings", "methodology", "deep", "analyze"])
        if not needs_fetch and ("find" in q_lower or "list" in q_lower) and len(q_lower.split()) <= 7:
            needs_fetch = False  # Simple lookup

        return ResearchPlan(
            research_goal=clean_goal,
            search_queries=queries[:3],
            max_sources=max_sources,
            needs_fetch=needs_fetch,
            source_preferences=source_preferences
        )


research_planner = ResearchPlanner()
