from typing import Dict, Any, Optional
from app.tools.base import BaseTool
from app.services.storage_engine import storage_engine
from app.state.session_manager import session_manager
from app.retrieval.citation import CitationGenerator


class AggregateDataTool(BaseTool):
    name = "aggregate_data"
    description = "Compute aggregations (SUM, AVG, COUNT, MIN, MAX) grouped by a category column and return ranked Top-K records."

    parameters_schema = {
        "type": "object",
        "properties": {
            "group_by_column": {
                "type": "string",
                "description": "Categorical column to group records by (e.g., 'product', 'category', 'region')."
            },
            "metric_column": {
                "type": "string",
                "description": "Numeric column to compute aggregation over (e.g., 'revenue', 'sales', 'quantity')."
            },
            "aggregation": {
                "type": "string",
                "enum": ["SUM", "AVG", "COUNT", "MIN", "MAX"],
                "description": "Aggregation function. Default is 'SUM'.",
                "default": "SUM"
            },
            "top_k": {
                "type": "integer",
                "description": "Top-K results count (default is 5).",
                "default": 5
            },
            "ascending": {
                "type": "boolean",
                "description": "Sort ascending (lowest first) or descending (highest first). Default false.",
                "default": False
            },
            "file_id": {
                "type": "string",
                "description": "Optional file_id. Defaults to active file."
            }
        },
        "required": ["group_by_column", "metric_column"]
    }

    output_schema = {
        "type": "object",
        "properties": {
            "group_by_column": {"type": "string"},
            "metric_column": {"type": "string"},
            "aggregation": {"type": "string"},
            "top_k": {"type": "integer"},
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "metric": {"type": "number"},
                        "row_count": {"type": "integer"}
                    }
                }
            },
            "citations": {"type": "array"}
        }
    }

    usage_example = {
        "call": {
            "tool": "aggregate_data",
            "parameters": {
                "group_by_column": "product",
                "metric_column": "revenue",
                "aggregation": "SUM",
                "top_k": 5
            }
        },
        "output": {
            "group_by_column": "product",
            "metric_column": "revenue",
            "aggregation": "SUM",
            "top_k": 5,
            "results": [
                {"category": "MacBook Pro", "metric": 54000.0, "row_count": 45},
                {"category": "Dell XPS", "metric": 38000.0, "row_count": 32}
            ],
            "citations": [
                {
                    "file_name": "sales.csv",
                    "source_description": "Source: sales.csv (Aggregated Summary over product, revenue)"
                }
            ]
        }
    }

    def execute(
        self,
        session_id: str,
        group_by_column: str,
        metric_column: str,
        aggregation: str = "SUM",
        top_k: int = 5,
        ascending: bool = False,
        file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        dataset = session_manager.get_active_file(session_id=session_id, file_id=file_id)
        
        # Validate column names exist with case-insensitive and plural/singular resolution
        def resolve_col(target: str) -> Optional[str]:
            t = target.strip().lower()
            for c in dataset.columns:
                if c.name.lower() == t:
                    return c.name
            for c in dataset.columns:
                cn = c.name.lower()
                if cn.endswith("y") and (cn[:-1] + "ies") == t:
                    return c.name
                if (cn + "s") == t or (cn + "es") == t:
                    return c.name
                if cn.rstrip("s") == t.rstrip("s"):
                    return c.name
                if t.endswith("y") and (t[:-1] + "ies") == cn:
                    return c.name
                if (t + "s") == cn or (t + "es") == cn:
                    return c.name
            for c in dataset.columns:
                if c.name.lower() in t or t in c.name.lower():
                    return c.name
            return None

        actual_group_col = resolve_col(group_by_column)
        if not actual_group_col:
            raise ValueError(f"Group column '{group_by_column}' not found. Available columns: {[c.name for c in dataset.columns]}")
        actual_metric_col = resolve_col(metric_column)
        if not actual_metric_col:
            raise ValueError(f"Metric column '{metric_column}' not found. Available columns: {[c.name for c in dataset.columns]}")

        rows = storage_engine.execute_aggregation(
            session_id=session_id,
            table_name=dataset.db_table_name,
            group_by_col=actual_group_col,
            agg_col=actual_metric_col,
            agg_func=aggregation,
            top_k=top_k,
            ascending=ascending
        )

        citation = CitationGenerator.create_citation(
            file_id=dataset.file_id,
            file_name=dataset.file_name,
            row_index=None,
            matched_columns=[actual_group_col, actual_metric_col],
            data_record={"summary": f"Top-{top_k} {actual_group_col} by {aggregation}({actual_metric_col})"}
        )

        table_rows = []
        for r in rows:
            val = r.get("metric")
            formatted_val = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
            table_rows.append([r.get("category"), formatted_val, r.get("row_count")])

        table_payload = {
            "type": "table",
            "columns": [actual_group_col, f"{aggregation.upper()}({actual_metric_col})", "Records"],
            "rows": table_rows,
            "row_count": len(table_rows),
            "source": {
                "type": "spreadsheet",
                "file_id": dataset.file_id,
                "filename": dataset.file_name
            }
        }

        return {
            "group_by_column": actual_group_col,
            "metric_column": actual_metric_col,
            "aggregation": aggregation.upper(),
            "top_k": top_k,
            "table": table_payload,
            "results": rows,
            "citations": [citation.model_dump()]
        }
