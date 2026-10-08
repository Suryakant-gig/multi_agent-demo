import re
from typing import Dict, Any, Tuple, Optional, List
from app.models.domain import IntentType, DatasetMetadata, ChartType
from app.state.state_models import SessionState
from app.utils.logger import logger


class IntentDetector:
    """
    Understands user intent and resolves parameters using contextual semantics,
    dataset schema analysis, cross-turn history (coreference resolution),
    document retrieval detection, and research intent routing.
    """

    CHART_KEYWORDS = {"chart", "plot", "graph", "visualize", "visualization", "histogram", "pie", "bar", "scatter"}
    ANALYSIS_KEYWORDS = {"top", "bottom", "highest", "lowest", "sum", "total", "average", "avg", "mean", "count", "maximum", "max", "minimum", "min", "aggregate"}
    SCHEMA_KEYWORDS = {"what columns", "show columns", "list columns", "schema", "dataset structure", "data preview", "overview"}
    RESEARCH_KEYWORDS = {"research paper", "research papers", "papers", "paper", "arxiv", "survey", "literature", "recent developments in", "latest developments in", "latest research", "recent research", "scientific study"}
    WEB_SEARCH_KEYWORDS = {"search the internet", "search the web", "search online", "official docs", "official documentation", "google search"}

    @classmethod
    def detect_intent(cls, query: str, session: SessionState) -> IntentType:
        q_lower = query.lower()

        has_active_dataset = bool(session.active_file_id and session.active_file_id in session.files)
        has_active_documents = bool(session.documents)

        # 1. Check for Hybrid (Mixed Data + Research)
        has_data_mention = any(w in q_lower for w in ["dataset", "sales", "data", "excel", "csv", "table", "my trend", "my pattern", "uploaded data"])
        has_research_mention = any(w in q_lower for w in ["research", "paper", "papers", "literature", "consumer demand", "explain using research", "consistent with research"])
        if (has_data_mention or has_active_dataset) and has_research_mention and any(w in q_lower for w in ["explain", "consistent", "theory", "literature", "why", "pattern", "trend"]):
            return IntentType.HYBRID

        # 2. Check for PDF Document Search
        if (has_active_documents or "pdf" in q_lower or re.search(r"\bpage\s+\d+\b", q_lower)) and not has_data_mention:
            if re.search(r"\bpage\s+\d+\b", q_lower) or any(w in q_lower for w in ["in this paper", "in the pdf", "in the document", "methodology", "section", "abstract"]):
                return IntentType.DOCUMENT_SEARCH

        # 3. Check for Research Agent Request
        if any(w in q_lower for w in cls.RESEARCH_KEYWORDS) or re.search(r"\b\d+\s+papers\b", q_lower) or q_lower.startswith("research "):
            # Ensure it's not a dataset column search (e.g. if dataset has a column called "paper")
            return IntentType.RESEARCH

        # 4. Check for Web Search
        if any(w in q_lower for w in cls.WEB_SEARCH_KEYWORDS) or q_lower.startswith("search for ") or "what happened recently with" in q_lower:
            return IntentType.WEB_SEARCH

        # 5. Coreference chart request (e.g. "make a chart for that", "visualize this")
        if any(w in q_lower for w in cls.CHART_KEYWORDS):
            return IntentType.VISUALIZATION

        # 6. Schema inspection
        if any(w in q_lower for w in cls.SCHEMA_KEYWORDS):
            return IntentType.SCHEMA_INSPECTION

        # 7. Aggregation / data analysis (Top-K, SUM, AVG)
        if any(w in q_lower for w in cls.ANALYSIS_KEYWORDS) or re.search(r"top\s+\d+", q_lower):
            return IntentType.DATA_ANALYSIS

        # 8. Search / retrieval in dataset
        if any(w in q_lower for w in ["find", "search", "show me", "get", "where", "filter", "which"]):
            if has_active_dataset:
                return IntentType.SEARCH_RETRIEVAL
            if has_active_documents:
                return IntentType.DOCUMENT_SEARCH
            return IntentType.WEB_SEARCH

        # 9. Fallback based on session state
        if has_active_dataset:
            return IntentType.SEARCH_RETRIEVAL
        if has_active_documents:
            return IntentType.DOCUMENT_SEARCH

        return IntentType.DIRECT_ANSWER

    @staticmethod
    def column_matches(col_name: str, text: str) -> bool:
        c = col_name.lower()
        t = text.lower()
        if c in t:
            return True
        if c.endswith("y") and (c[:-1] + "ies") in t:
            return True
        if (c + "s") in t or (c + "es") in t:
            return True
        if c.rstrip("s") in t:
            return True
        return False

    @classmethod
    def resolve_tool_and_params(
        cls,
        intent: IntentType,
        query: str,
        session: SessionState,
        dataset: Optional[DatasetMetadata]
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        q_lower = query.lower()

        # A. Research Intent -> Dedicated Research Agent workflow
        if intent == IntentType.RESEARCH:
            # Parse desired number of papers if specified
            top_k = 5
            count_match = re.search(r"\b(\d+)\s*papers\b", q_lower)
            if count_match:
                top_k = int(count_match.group(1))
            return "research_agent", {"query": query, "max_sources": top_k}

        # B. Web Search Intent
        elif intent == IntentType.WEB_SEARCH:
            return "web_search", {"query": query, "top_k": 5}

        # C. Document Search Intent (PDF)
        elif intent == IntentType.DOCUMENT_SEARCH:
            return "search_documents", {"query": query, "top_k": 4}

        # D. Hybrid Intent (Data + Research)
        elif intent == IntentType.HYBRID:
            return "hybrid_orchestration", {"query": query}

        # E. Visualization
        elif intent == IntentType.VISUALIZATION:
            last_tool = session.last_tool_call
            params: Dict[str, Any] = {}

            # Detect chart type
            chart_type = "bar"
            if "line" in q_lower or "trend" in q_lower or "time" in q_lower:
                chart_type = "line"
            elif "pie" in q_lower:
                chart_type = "pie"
            elif "scatter" in q_lower:
                chart_type = "scatter"
            elif "histogram" in q_lower or "distribution" in q_lower:
                chart_type = "histogram"

            # Check if referring to last aggregation result
            if last_tool and last_tool.tool_name == "aggregate_data" and (
                "that" in q_lower or "this" in q_lower or "it" in q_lower or "result" in q_lower or "previous" in q_lower or len(q_lower.split()) <= 6
            ):
                prev_params = last_tool.parameters
                params = {
                    "chart_type": chart_type,
                    "x_column": prev_params.get("group_by_column"),
                    "y_column": prev_params.get("metric_column"),
                    "aggregation": prev_params.get("aggregation", "SUM"),
                    "title": f"{chart_type.capitalize()} of {prev_params.get('metric_column')} by {prev_params.get('group_by_column')}",
                    "top_k": prev_params.get("top_k", 10)
                }
                return "generate_chart", params

            # Inferred columns from dataset
            if dataset:
                cols = dataset.columns
                cat_cols = [c.name for c in cols if c.is_categorical or c.data_type == "string"]
                num_cols = [c.name for c in cols if c.is_numeric]
                time_cols = [c.name for c in cols if c.is_temporal]

                x_col = None
                y_col = None
                for c in cols:
                    if cls.column_matches(c.name, q_lower):
                        if c.is_numeric and not y_col:
                            y_col = c.name
                        elif not x_col:
                            x_col = c.name

                if not x_col:
                    x_col = (time_cols[0] if (chart_type == "line" and time_cols) else None) or (cat_cols[0] if cat_cols else cols[0].name)
                if not y_col and num_cols:
                    y_col = num_cols[0]

                params = {
                    "chart_type": chart_type,
                    "x_column": x_col,
                    "y_column": y_col,
                    "title": f"{chart_type.capitalize()} Chart"
                }
                return "generate_chart", params

        # F. Data Analysis (Aggregation)
        elif intent == IntentType.DATA_ANALYSIS:
            top_k = 5
            match_top = re.search(r"top\s+(\d+)", q_lower)
            if match_top:
                top_k = int(match_top.group(1))

            agg = "SUM"
            if "average" in q_lower or "avg" in q_lower or "mean" in q_lower:
                agg = "AVG"
            elif "count" in q_lower:
                agg = "COUNT"
            elif "highest" in q_lower or "max" in q_lower:
                agg = "MAX"
            elif "lowest" in q_lower or "min" in q_lower:
                agg = "MIN"

            ascending = "lowest" in q_lower or "bottom" in q_lower or "min" in q_lower

            if dataset:
                cols = dataset.columns
                cat_cols = [c.name for c in cols if c.is_categorical or c.data_type == "string"]
                num_cols = [c.name for c in cols if c.is_numeric]

                group_by = None
                metric = None

                for c in cols:
                    if cls.column_matches(c.name, q_lower):
                        if c.is_numeric and not metric:
                            metric = c.name
                        elif not group_by and not c.is_numeric:
                            group_by = c.name

                if not group_by and cat_cols:
                    group_by = cat_cols[0]
                if not metric and num_cols:
                    metric = num_cols[0]

                if group_by and metric:
                    return "aggregate_data", {
                        "group_by_column": group_by,
                        "metric_column": metric,
                        "aggregation": agg,
                        "top_k": top_k,
                        "ascending": ascending
                    }

            return "search_data", {"query": query, "top_k": top_k}

        # G. Schema Inspection
        elif intent == IntentType.SCHEMA_INSPECTION:
            return "inspect_schema", {"sample_limit": 5}

        # H. Search Retrieval (tabular)
        elif intent == IntentType.SEARCH_RETRIEVAL:
            top_k = 5
            match_top = re.search(r"top\s+(\d+)", q_lower)
            if match_top:
                top_k = int(match_top.group(1))
            return "search_data", {"query": query, "top_k": top_k}

        return None, {}
