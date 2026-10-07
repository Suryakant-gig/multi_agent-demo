from typing import List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from app.models.domain import ColumnMetadata


class UploadResponse(BaseModel):
    success: bool = True
    session_id: str
    file_id: str
    file_name: str
    file_size_bytes: int
    row_count: int
    column_count: int
    columns: List[ColumnMetadata]
    message: str = "File uploaded and processed successfully."

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "session_id": "sess-12345",
                "file_id": "f8a910",
                "file_name": "sales_q4.csv",
                "file_size_bytes": 102400,
                "row_count": 1500,
                "column_count": 5,
                "columns": [
                    {
                        "name": "product",
                        "data_type": "string",
                        "null_count": 0,
                        "unique_count": 12,
                        "is_numeric": False,
                        "is_temporal": False,
                        "is_categorical": True,
                        "sample_values": ["Laptop", "Mouse"]
                    }
                ],
                "message": "File uploaded and processed successfully."
            }
        }
    )
