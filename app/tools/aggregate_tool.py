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
        
        # Validate column names exist
        col_names = {c.name.lower(): c.name for c in dataset.columns}
        if group_by_column.lower() not in col_names:
            raise ValueError(f"Group column '{group_by_column}' not found. Available columns: {list(col_names.values())}")
        if metric_column.lower() not in col_names:
            raise ValueError(f"Metric column '{metric_column}' not found. Available columns: {list(col_names.values())}")

        actual_group_col = col_names[group_by_column.lower()]
        actual_metric_col = col_names[metric_column.lower()]

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

        return {
            "group_by_column": actual_group_col,
            "metric_column": actual_metric_col,
            "aggregation": aggregation.upper(),
            "top_k": top_k,
            "results": rows,
            "citations": [citation.model_dump()]
        }
