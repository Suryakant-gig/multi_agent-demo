import re
from typing import Dict, Any, Tuple, Optional, List
from app.models.domain import IntentType, DatasetMetadata, ChartType
from app.state.state_models import SessionState
from app.agents.task_planner import task_planner
from app.utils.logger import logger


class IntentDetector:
    """
    Understands user intent and resolves parameters using contextual semantics,
    dataset schema analysis, cross-turn history (coreference resolution),
    document retrieval detection, and research intent routing.
    Leverages TaskPlanner for structured internal task plans.
    """

    CHART_KEYWORDS = {"chart", "plot", "graph", "visualize", "visualization", "histogram", "pie", "bar", "scatter"}
    ANALYSIS_KEYWORDS = {"top", "bottom", "highest", "lowest", "sum", "total", "average", "avg", "mean", "count", "maximum", "max", "minimum", "min", "aggregate"}
    SCHEMA_KEYWORDS = {"what columns", "show columns", "list columns", "schema", "dataset structure", "data preview", "overview"}
    RESEARCH_KEYWORDS = {"research paper", "research papers", "papers", "paper", "arxiv", "survey", "literature", "recent developments in", "latest developments in", "latest research", "recent research", "scientific study"}
    WEB_SEARCH_KEYWORDS = {"search the internet", "search the web", "search online", "official docs", "official documentation", "google search"}

    @classmethod
    def detect_intent(cls, query: str, session: SessionState, plan: Optional[Any] = None) -> IntentType:
        if plan is None:
            plan = task_planner.plan_task(query, session)

        if plan.task_type == "mixed":
            return IntentType.HYBRID
        elif plan.task_type == "research":
            return IntentType.RESEARCH
        elif plan.task_type == "web_search":
            return IntentType.WEB_SEARCH
        elif plan.task_type in ("document_extraction", "document_search"):
            return IntentType.DOCUMENT_SEARCH
        elif plan.task_type == "visualization":
            return IntentType.VISUALIZATION
        elif plan.task_type == "schema_inspection":
            return IntentType.SCHEMA_INSPECTION
        elif plan.task_type == "data_analysis":
            return IntentType.DATA_ANALYSIS
        elif plan.task_type == "data_extraction":
            return IntentType.SEARCH_RETRIEVAL
        elif plan.task_type == "direct_answer":
            return IntentType.DIRECT_ANSWER

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
        dataset: Optional[DatasetMetadata] = None,
        plan: Optional[Any] = None
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        q_lower = query.lower()
        if plan is None:
            plan = task_planner.plan_task(query, session)

        # Missing resources or clarification needed -> Direct explanation from plan, no tool execution
        if getattr(plan, "status", "valid") in ("missing_resource", "clarification_needed"):
            return None, {}

        # Direct Answer -> No tool execution
        if intent == IntentType.DIRECT_ANSWER or plan.task_type == "direct_answer":
            return None, {}

        # A. Hybrid Intent (Data + Research or Document + Research)
        if intent == IntentType.HYBRID or plan.task_type == "mixed":
            return "hybrid_orchestration", {
                "query": query,
                "requires_document": plan.requires_document,
                "requires_data": plan.requires_data,
                "document_id": plan.target_document_id,
                "file_id": plan.target_file_id
            }

        # B. Research Intent -> Dedicated Research Agent workflow
        elif intent == IntentType.RESEARCH or plan.task_type == "research":
            top_k = plan.requested_count or 5
            return "research_agent", {"query": query, "max_sources": top_k}

        # C. Web Search Intent
        elif intent == IntentType.WEB_SEARCH or plan.task_type == "web_search":
            return "web_search", {"query": query, "top_k": 5}

        # D. Document Search / Extraction Intent (PDF)
        elif intent in (IntentType.DOCUMENT_SEARCH, IntentType.DOCUMENT_EXTRACTION) or plan.task_type in ("document_extraction", "document_search"):
            if plan.operation == "extract" or plan.task_type == "document_extraction":
                return "search_documents", {
                    "query": query,
                    "operation": "extract",
                    "requested_count": plan.requested_count,
                    "offset": plan.offset,
                    "target_range": plan.target_range,
                    "document_id": plan.target_document_id
                }
            return "search_documents", {
                "query": query,
                "operation": "search",
                "top_k": 4,
                "document_id": plan.target_document_id
            }

        # E. Visualization
        elif intent == IntentType.VISUALIZATION or plan.task_type == "visualization":
            last_tool = session.last_tool_call
            params: Dict[str, Any] = {}

            chart_type = "bar"
            if "line" in q_lower or "trend" in q_lower or "time" in q_lower:
                chart_type = "line"
            elif "pie" in q_lower:
                chart_type = "pie"
            elif "scatter" in q_lower:
                chart_type = "scatter"
            elif "histogram" in q_lower or "distribution" in q_lower:
                chart_type = "histogram"

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

        # F. Schema Inspection
        elif intent == IntentType.SCHEMA_INSPECTION or plan.task_type == "schema_inspection":
            return "inspect_schema", {"sample_limit": 5}

        # G. Data Analysis (Aggregation)
        elif intent == IntentType.DATA_ANALYSIS or plan.task_type == "data_analysis":
            top_k = plan.requested_count or 5
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

                group_by = plan.group_by_column
                metric = plan.metric_column

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
                        "ascending": ascending,
                        "file_id": plan.target_file_id
                    }

            return "search_data", {
                "query": query,
                "operation": "first_n" if plan.operation == "first_n" else "search",
                "n": top_k,
                "file_id": plan.target_file_id
            }

        # H. Search / Extraction Retrieval (tabular)
        elif intent in (IntentType.SEARCH_RETRIEVAL, IntentType.DATA_EXTRACTION) or plan.task_type == "data_extraction":
            if plan.operation == "first_n":
                return "search_data", {
                    "operation": "first_n",
                    "n": plan.requested_count or 5,
                    "offset": plan.offset,
                    "file_id": plan.target_file_id
                }
            elif plan.operation == "filter" and plan.filter_criteria:
                return "search_data", {
                    "operation": "filter",
                    "filters": plan.filter_criteria,
                    "n": plan.requested_count or 5,
                    "file_id": plan.target_file_id
                }
            top_k = plan.requested_count or 5
            match_top = re.search(r"top\s+(\d+)", q_lower)
            if match_top:
                top_k = int(match_top.group(1))
            return "search_data", {"query": query, "top_k": top_k, "file_id": plan.target_file_id}

        return None, {}
