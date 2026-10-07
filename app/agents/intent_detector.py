import re
from typing import Dict, Any, Tuple, Optional, List
from app.models.domain import IntentType, DatasetMetadata, ChartType
from app.state.state_models import SessionState
from app.utils.logger import logger


class IntentDetector:
    """
    Understands user intent and resolves parameters using contextual semantics,
    dataset schema analysis, and cross-turn history (coreference resolution).
    """

    CHART_KEYWORDS = {"chart", "plot", "graph", "visualize", "visualization", "histogram", "pie", "bar", "scatter"}
    ANALYSIS_KEYWORDS = {"top", "bottom", "highest", "lowest", "sum", "total", "average", "avg", "mean", "count", "maximum", "max", "minimum", "min", "aggregate"}
    SCHEMA_KEYWORDS = {"schema", "columns", "structure", "overview", "preview", "fields", "sample", "dataset"}

    @classmethod
    def detect_intent(cls, query: str, session: SessionState) -> IntentType:
        q_lower = query.lower()

        # Check for coreference chart request (e.g. "make a chart for that", "visualize this")
        if any(w in q_lower for w in cls.CHART_KEYWORDS):
            return IntentType.VISUALIZATION

        # Check for schema inspection
        if any(w in q_lower for w in ["what columns", "show columns", "list columns", "schema", "dataset structure", "data preview"]):
            return IntentType.SCHEMA_INSPECTION

        # Check for aggregation/data analysis
        if any(w in q_lower for w in cls.ANALYSIS_KEYWORDS) or re.search(r"top\s+\d+", q_lower):
            return IntentType.DATA_ANALYSIS

        # Check for search/retrieval
        if any(w in q_lower for w in ["find", "search", "show me", "get", "where", "filter", "which"]):
            return IntentType.SEARCH_RETRIEVAL

        # Default fallback
        if session.active_file_id:
            return IntentType.SEARCH_RETRIEVAL
        return IntentType.DIRECT_ANSWER

    @staticmethod
    def column_matches(col_name: str, text: str) -> bool:
        c = col_name.lower()
        t = text.lower()
        if c in t:
            return True
        # Handle plurals like category -> categories, product -> products
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

        if intent == IntentType.VISUALIZATION:
            # 1. Coreference resolution: Did user say "for that" / "of that"?
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
            if last_tool and last_tool.tool_name == "aggregate_data" and ("that" in q_lower or "this" in q_lower or "it" in q_lower or "result" in q_lower or "previous" in q_lower or len(q_lower.split()) <= 6):
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

            # Otherwise infer columns from dataset
            if dataset:
                cols = dataset.columns
                cat_cols = [c.name for c in cols if c.is_categorical or c.data_type == "string"]
                num_cols = [c.name for c in cols if c.is_numeric]
                time_cols = [c.name for c in cols if c.is_temporal]

                # Find mentions in query
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

        elif intent == IntentType.DATA_ANALYSIS:
            # Extract top_k
            top_k = 5
            match_top = re.search(r"top\s+(\d+)", q_lower)
            if match_top:
                top_k = int(match_top.group(1))

            # Aggregation func
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

            # Fallback to search
            return "search_data", {"query": query, "top_k": top_k}

        elif intent == IntentType.SCHEMA_INSPECTION:
            return "inspect_schema", {"sample_limit": 5}

        elif intent == IntentType.SEARCH_RETRIEVAL:
            top_k = 5
            match_top = re.search(r"top\s+(\d+)", q_lower)
            if match_top:
                top_k = int(match_top.group(1))
            return "search_data", {"query": query, "top_k": top_k}

        return None, {}
