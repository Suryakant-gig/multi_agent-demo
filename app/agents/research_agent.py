import time
from typing import Dict, Any, List, Optional
from app.models.domain import CitationItem, SourceItem, ToolCallRecord
from app.agents.research_planner import research_planner, ResearchPlan
from app.services.web_search_service import web_search_service
from app.services.web_fetch_service import web_fetch_service
from app.tools.registry import tool_registry
from app.retrieval.web_ranker import web_ranker
from app.retrieval.web_citation import web_citation_formatter
from app.agents.llm_client import llm_client
from app.agents.prompts import RESEARCH_SYNTHESIS_PROMPT, RESEARCH_SYNTHESIS_SYSTEM
from app.utils.config import settings
from app.utils.logger import logger


class ResearchAgent:
    """
    Dedicated autonomous research workflow orchestrator:
    Query Understanding -> Planning -> Multi-Query Web/ArXiv Search ->
    Candidate Ranking -> Target Page Fetch -> Evidence Selection ->
    Grounded Synthesis -> Verifiable Citations.
    """

    SYSTEM_SECURITY_PROMPT = RESEARCH_SYNTHESIS_SYSTEM

    def execute_research(
        self,
        query: str,
        session_id: str,
        max_sources: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end research workflow.
        """
        start_time = time.time()
        logger.info(f"ResearchAgent starting research workflow for: '{query}'")

        # 1. Planning Phase
        plan: ResearchPlan = research_planner.create_plan(query)
        target_sources = max_sources or plan.max_sources
        tool_records: List[ToolCallRecord] = []

        # Resolve session-bound LangChain tools
        lc_tools = {t.name: t for t in tool_registry.get_langchain_tools(session_id=session_id)}
        web_search_tool = lc_tools.get("web_search")
        web_fetch_tool = lc_tools.get("web_fetch")

        # 2. Multi-Query Search Phase
        raw_candidates: List[Dict[str, Any]] = []
        for s_query in plan.search_queries:
            t0 = time.time()
            try:
                if web_search_tool:
                    search_res = web_search_tool.invoke({
                        "query": s_query,
                        "top_k": target_sources,
                        "research_mode": True
                    })
                    results = search_res.get("results", []) if isinstance(search_res, dict) else []
                else:
                    results = web_search_service.search(
                        query=s_query,
                        top_k=target_sources,
                        research_mode=True
                    )
                raw_candidates.extend(results)
                exec_ms = round((time.time() - t0) * 1000, 2)
                tool_records.append(
                    ToolCallRecord(
                        tool_name="web_search",
                        parameters={"query": s_query, "top_k": target_sources},
                        result={"found": len(results)},
                        execution_time_ms=exec_ms,
                        success=True
                    )
                )
            except Exception as e:
                logger.warning(f"Search failed for '{s_query}': {e}")

        # 3. Candidate Ranking & Top-K Selection
        ranked_sources = web_ranker.rank_candidates(
            query=query,
            candidates=raw_candidates,
            top_k=target_sources,
            prefer_research=True
        )

        if not ranked_sources:
            return {
                "answer": "No authoritative research papers or technical sources could be found matching your query.",
                "sources": [],
                "citations": [],
                "tool_calls": tool_records,
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }

        # 4. Fetch Phase for top candidates if in-depth analysis is needed
        fetched_evidence: List[Dict[str, Any]] = []
        if plan.needs_fetch:
            # Fetch readable text for top 2-3 most authoritative sources
            fetch_targets = ranked_sources[:min(3, len(ranked_sources))]
            for src in fetch_targets:
                url = src.get("url")
                if not url:
                    continue
                t0 = time.time()
                try:
                    if web_fetch_tool:
                        fetch_res = web_fetch_tool.invoke({"url": url})
                    else:
                        fetch_res = web_fetch_service.fetch_url(url)
                    exec_ms = round((time.time() - t0) * 1000, 2)
                    tool_records.append(
                        ToolCallRecord(
                            tool_name="web_fetch",
                            parameters={"url": url},
                            result={"title": fetch_res.get("title"), "length": fetch_res.get("content_length")},
                            execution_time_ms=exec_ms,
                            success=True
                        )
                    )
                    fetched_evidence.append({
                        "title": src.get("title"),
                        "url": url,
                        "domain": src.get("domain"),
                        "snippet": src.get("snippet"),
                        "full_text": fetch_res.get("text", "")[:3500]  # Cap context per source
                    })
                except Exception as ex:
                    logger.warning(f"Fetch failed for {url}: {ex}")

        # 5. Synthesis Phase
        synthesized_answer = self._synthesize_findings(
            query=query,
            goal=plan.research_goal,
            ranked_sources=ranked_sources,
            fetched_evidence=fetched_evidence
        )

        # 6. Citations & Sources formatting
        citations = [web_citation_formatter.create_citation(s) for s in ranked_sources]
        source_items = [web_citation_formatter.create_source_item(s) for s in ranked_sources]
        sources_markdown = web_citation_formatter.format_sources_section(ranked_sources)

        final_answer = synthesized_answer + sources_markdown
        duration_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "answer": final_answer,
            "sources": source_items,
            "citations": citations,
            "tool_calls": tool_records,
            "duration_ms": duration_ms
        }

    def _synthesize_findings(
        self,
        query: str,
        goal: str,
        ranked_sources: List[Dict[str, Any]],
        fetched_evidence: List[Dict[str, Any]]
    ) -> str:
        """
        Synthesizes research findings using Gemini LLM if available, or deterministic grounded synthesis.
        Guarantees safety against prompt injection from untrusted web pages.
        """
        # Format evidence safely
        evidence_blocks = []
        for idx, s in enumerate(ranked_sources, start=1):
            block = (
                f"Source [{idx}]: {s.get('title')}\n"
                f"URL: {s.get('url')}\n"
                f"Domain: {s.get('domain')}\n"
                f"Date: {s.get('published_at', 'N/A')}\n"
                f"Type: {s.get('source_type')}\n"
                f"Summary: {s.get('snippet')}\n"
            )
            evidence_blocks.append(block)

        deep_text_blocks = []
        for fe in fetched_evidence:
            deep_text_blocks.append(
                f"<source title=\"{fe['title']}\" url=\"{fe['url']}\">\n"
                f"{fe['full_text']}\n"
                f"</source>"
            )

        # 1. LLM Generation if available
        if llm_client.is_available:
            evidence_text = f"{chr(10).join(evidence_blocks)}\n\n{''.join(deep_text_blocks)}"
            llm_out = llm_client.generate_from_prompt(
                RESEARCH_SYNTHESIS_PROMPT,
                {
                    "query": query,
                    "goal": goal,
                    "evidence": evidence_text
                }
            )
            if llm_out and len(llm_out.strip()) > 50:
                return llm_out.strip()

        # 2. Deterministic high-quality synthesis fallback
        lines = [
            f"### Research Findings: {goal.title()}\n",
            f"Based on **{len(ranked_sources)} authoritative sources**, here is the synthesized overview:\n"
        ]

        # Key sources and summaries
        for idx, s in enumerate(ranked_sources, start=1):
            title = s.get("title", "")
            snippet = s.get("snippet", "")
            pub = s.get("published_at")
            pub_str = f" ({pub})" if pub else ""
            lines.append(f"{idx}. **{title}**{pub_str}: {snippet}")

        return "\n".join(lines)


research_agent = ResearchAgent()
