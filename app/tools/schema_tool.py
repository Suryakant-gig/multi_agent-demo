from typing import Dict, Any, Optional
from app.tools.base import BaseTool
from app.state.session_manager import session_manager
from app.services.storage_engine import storage_engine


class InspectSchemaTool(BaseTool):
    name = "inspect_schema"
    description = "Inspect the schema, column types, statistics, and sample rows of the dataset."

    parameters_schema = {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Optional file_id. Defaults to active file in session."
            },
            "sample_limit": {
                "type": "integer",
                "description": "Number of sample rows to inspect. Default is 5.",
                "default": 5
            }
        }
    }

    output_schema = {
        "type": "object",
        "properties": {
            "file_name": {"type": "string"},
            "row_count": {"type": "integer"},
            "column_count": {"type": "integer"},
            "columns": {"type": "array"},
            "sample_rows": {"type": "array"}
        }
    }

    usage_example = {
        "call": {
            "tool": "inspect_schema",
            "parameters": {"sample_limit": 3}
        },
        "output": {
            "file_name": "sales.csv",
            "row_count": 100,
            "column_count": 4,
            "columns": [
                {"name": "product", "data_type": "string", "null_count": 0}
            ],
            "sample_rows": [{"product": "Laptop", "price": 999}]
        }
    }

    def execute(
        self,
        session_id: str,
        file_id: Optional[str] = None,
        sample_limit: int = 5
    ) -> Dict[str, Any]:
        dataset = session_manager.get_active_file(session_id=session_id, file_id=file_id)
        sample = storage_engine.query_paginated(
            session_id=session_id,
            table_name=dataset.db_table_name,
            limit=sample_limit
        )

        return {
            "file_id": dataset.file_id,
            "file_name": dataset.file_name,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
            "columns": [c.model_dump() for c in dataset.columns],
            "sample_rows": sample
        }
