from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from app.models.domain import SearchResultItem


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Keywords or text to search for.")
    session_id: str = Field(..., description="Active session ID containing uploaded file.")
    file_id: Optional[str] = Field(None, description="Optional target file ID.")
    filters: Optional[Dict[str, Any]] = Field(None, description="Key-value filters for specific columns.")
    top_k: int = Field(5, ge=1, le=50, description="Number of ranked items to retrieve.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "laptop",
                "session_id": "sess-12345",
                "filters": {"category": "electronics"},
                "top_k": 5
            }
        }
    )


class SearchResponse(BaseModel):
    session_id: str
    query: str
    count: int
    top_k: int
    results: List[Dict[str, Any]]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "sess-12345",
                "query": "laptop",
                "count": 2,
                "top_k": 5,
                "results": [
                    {
                        "row_index": 4,
                        "score": 4.5,
                        "data": {"product": "Gaming Laptop", "price": 1499},
                        "citation": {
                            "file_name": "inventory.csv",
                            "row_index": 4,
                            "source_description": "Source: inventory.csv (Row 4)"
                        }
                    }
                ]
            }
        }
    )
