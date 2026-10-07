from typing import Dict, Any, Optional
from app.tools.base import BaseTool
from app.services.storage_engine import storage_engine
from app.state.session_manager import session_manager
from app.retrieval.citation import CitationGenerator


class QuerySQLTool(BaseTool):
    name = "query_sql"
    description = "Execute a safe read-only SQL SELECT query on the dataset table."

    parameters_schema = {
        "type": "object",
        "properties": {
            "sql_query": {
                "type": "string",
                "description": "SQL SELECT query to execute on the table."
            },
            "file_id": {
                "type": "string",
                "description": "Optional file_id. Defaults to active file."
            }
        },
        "required": ["sql_query"]
    }

    output_schema = {
        "type": "object",
        "properties": {
            "row_count": {"type": "integer"},
            "results": {"type": "array"},
            "citations": {"type": "array"}
        }
    }

    usage_example = {
        "call": {
            "tool": "query_sql",
            "parameters": {
                "sql_query": "SELECT product, SUM(revenue) as total FROM {table} GROUP BY product LIMIT 5"
            }
        },
        "output": {
            "row_count": 5,
            "results": [{"product": "Laptop", "total": 12000}],
            "citations": []
        }
    }

    def execute(
        self,
        session_id: str,
        sql_query: str,
        file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        dataset = session_manager.get_active_file(session_id=session_id, file_id=file_id)
        
        # Replace template {table} with actual db_table_name if user used placeholder
        query = sql_query.replace("{table}", f'"{dataset.db_table_name}"')
        
        # If the user didn't mention the table name, check if they used 'data'
        if "from data " in query.lower() or "from data;" in query.lower():
            query = query.replace("data", f'"{dataset.db_table_name}"')

        rows = storage_engine.execute_read_query(session_id=session_id, sql=query)

        citations = []
        if rows:
            first_row = rows[0]
            row_idx = first_row.get("_row_id")
            c = CitationGenerator.create_citation(
                file_id=dataset.file_id,
                file_name=dataset.file_name,
                row_index=row_idx,
                matched_columns=list(first_row.keys()),
                data_record=first_row
            )
            citations.append(c.model_dump())

        return {
            "row_count": len(rows),
            "results": rows,
            "citations": citations
        }
