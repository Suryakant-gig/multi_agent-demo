from typing import Dict, Any, Optional, List
from app.tools.base import BaseTool
from app.retrieval.search_engine import search_engine
from app.services.storage_engine import storage_engine
from app.state.session_manager import session_manager
from app.models.domain import CitationItem


class SearchDataTool(BaseTool):
    name = "search_data"
    description = (
        "Extract, filter, sort, or search records from the active tabular dataset (CSV/Excel). "
        "Supports deterministic operations: 'first_n' (first N rows in source order), "
        "'top_n' (top records sorted by a metric column), 'filter' (exact/matching criteria), "
        "and 'search' (keyword relevance search). Always outputs structured table data and citations."
    )
    
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords, terms, or search prompt (optional for first_n / top_n).",
                "default": ""
            },
            "operation": {
                "type": "string",
                "enum": ["first_n", "top_n", "filter", "sort", "search"],
                "description": "Explicit operation: 'first_n' for source order rows, 'top_n' or 'sort' for ranked records, 'filter' for conditions, 'search' for keyword matches.",
                "default": "search"
            },
            "n": {
                "type": "integer",
                "description": "Number of rows to retrieve (default: 5).",
                "default": 5
            },
            "offset": {
                "type": "integer",
                "description": "Row offset for pagination or follow-up 'next N' queries (default: 0).",
                "default": 0
            },
            "sort_column": {
                "type": "string",
                "description": "Column name to sort by for top_n or sort operations."
            },
            "ascending": {
                "type": "boolean",
                "description": "Sort ascending if true, descending if false (default: false).",
                "default": False
            },
            "filters": {
                "type": "object",
                "description": "Optional column-value equality filters (e.g., {'region': 'East'}).",
                "default": {}
            },
            "top_k": {
                "type": "integer",
                "description": "Alias for n. Number of top results to return.",
                "default": 5
            },
            "file_id": {
                "type": "string",
                "description": "Optional specific file_id. Defaults to active file in session."
            }
        }
    }

    output_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "operation": {"type": "string"},
            "count": {"type": "integer"},
            "table": {"type": "object"},
            "results": {"type": "array"},
            "citations": {"type": "array"}
        }
    }

    usage_example = {
        "call": {
            "tool": "search_data",
            "parameters": {
                "operation": "first_n",
                "n": 5
            }
        },
        "output": {
            "query": "",
            "operation": "first_n",
            "count": 5,
            "table": {
                "type": "table",
                "columns": ["Product", "Region", "Revenue"],
                "rows": [["Laptop", "East", 1200]],
                "row_count": 1
            }
        }
    }

    def execute(
        self,
        session_id: str,
        query: str = "",
        operation: str = "search",
        n: Optional[int] = None,
        offset: int = 0,
        sort_column: Optional[str] = None,
        ascending: bool = False,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        dataset = session_manager.get_active_file(session_id=session_id, file_id=file_id)
        limit = n if n is not None else top_k

        # Case-insensitive column resolution
        col_map = {c.name.lower(): c.name for c in dataset.columns}

        raw_rows: List[Dict[str, Any]] = []
        serialized_results: List[Dict[str, Any]] = []
        citations: List[Dict[str, Any]] = []

        if operation == "first_n":
            raw_rows = storage_engine.get_first_n(
                session_id=session_id,
                table_name=dataset.db_table_name,
                n=limit,
                offset=offset
            )
        elif operation in ("top_n", "sort") and sort_column:
            actual_sort_col = col_map.get(sort_column.lower(), sort_column)
            raw_rows = storage_engine.get_top_n(
                session_id=session_id,
                table_name=dataset.db_table_name,
                sort_column=actual_sort_col,
                n=limit,
                ascending=ascending,
                offset=offset
            )
        elif operation == "filter" and filters:
            norm_filters = {col_map.get(k.lower(), k): v for k, v in filters.items()}
            raw_rows = storage_engine.filter_records(
                session_id=session_id,
                table_name=dataset.db_table_name,
                filters=norm_filters,
                limit=limit,
                offset=offset
            )
        else:
            # Semantic / keyword search fallback
            results = search_engine.search(
                session_id=session_id,
                dataset=dataset,
                query=query or "",
                filters=filters,
                top_k=limit
            )
            for r in results:
                serialized_results.append(r.model_dump())
                raw_rows.append(r.data)
                citations.append(r.citation.model_dump())

        # Build citations for direct database rows if not already populated
        if not citations and raw_rows:
            for row in raw_rows:
                r_id = row.get("_row_id")
                clean_data = {k: v for k, v in row.items() if k != "_row_id"}
                snippet_str = ", ".join([f"{k}: {v}" for k, v in list(clean_data.items())[:3]])
                c_item = CitationItem(
                    file_id=dataset.file_id,
                    file_name=dataset.file_name,
                    row_index=r_id,
                    snippet=snippet_str,
                    source_description=f"Source: {dataset.file_name} (Row {r_id})" if r_id else f"Source: {dataset.file_name}",
                    citation_type="dataset"
                )
                citations.append(c_item.model_dump())
                serialized_results.append({
                    "row_index": r_id or 0,
                    "score": 1.0,
                    "data": clean_data,
                    "citation": c_item.model_dump()
                })

        # Build clean structured table
        display_columns = [c.name for c in dataset.columns if c.name != "_row_id"]
        table_rows = []
        for r in raw_rows:
            row_vals = [r.get(col, "") for col in display_columns]
            table_rows.append(row_vals)

        table_payload = {
            "type": "table",
            "columns": display_columns,
            "rows": table_rows,
            "row_count": len(table_rows),
            "offset": offset,
            "source": {
                "type": "spreadsheet",
                "file_id": dataset.file_id,
                "filename": dataset.file_name
            }
        }

        return {
            "query": query,
            "operation": operation,
            "count": len(raw_rows),
            "offset": offset,
            "table": table_payload,
            "results": serialized_results,
            "citations": citations
        }
