from typing import Dict, Any, Optional
from app.tools.base import BaseTool
from app.retrieval.search_engine import search_engine
from app.state.session_manager import session_manager


class SearchDataTool(BaseTool):
    name = "search_data"
    description = "Search relevant records and information from the active dataset using keyword and filter criteria."
    
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords, terms, or semantic search query."
            },
            "filters": {
                "type": "object",
                "description": "Optional column-value equality filters (e.g., {'region': 'East'}).",
                "default": {}
            },
            "top_k": {
                "type": "integer",
                "description": "Number of top results to return. Default is 5.",
                "default": 5
            },
            "file_id": {
                "type": "string",
                "description": "Optional specific file_id. Defaults to active file in session."
            }
        },
        "required": ["query"]
    }

    output_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "count": {"type": "integer"},
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "row_index": {"type": "integer"},
                        "score": {"type": "number"},
                        "data": {"type": "object"},
                        "citation": {"type": "object"}
                    }
                }
            }
        }
    }

    usage_example = {
        "call": {
            "tool": "search_data",
            "parameters": {
                "query": "laptop",
                "filters": {"category": "electronics"},
                "top_k": 5
            }
        },
        "output": {
            "query": "laptop",
            "count": 1,
            "results": [
                {
                    "row_index": 12,
                    "score": 4.5,
                    "data": {"product": "Pro Laptop 15", "category": "electronics", "price": 1200},
                    "citation": {
                        "file_name": "sales.csv",
                        "row_index": 12,
                        "source_description": "Source: sales.csv (Row 12)"
                    }
                }
            ]
        }
    }

    def execute(
        self,
        session_id: str,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        dataset = session_manager.get_active_file(session_id=session_id, file_id=file_id)
        results = search_engine.search(
            session_id=session_id,
            dataset=dataset,
            query=query,
            filters=filters,
            top_k=top_k
        )

        serialized_results = [r.model_dump() for r in results]
        return {
            "query": query,
            "count": len(serialized_results),
            "results": serialized_results
        }
