from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from app.models.domain import ToolCallRecord, CitationItem, ChartPayload


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User's natural language question or command.")
    session_id: Optional[str] = Field(None, description="Existing session identifier. Created if omitted.")
    file_id: Optional[str] = Field(None, description="Target specific file, or defaults to session active file.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Show me the top 5 products by revenue",
                "session_id": "sess-12345"
            }
        }
    )


class ChatResponse(BaseModel):
    session_id: str
    query: str
    intent: str
    answer: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    chart: Optional[Dict[str, Any]] = None
    duration_ms: float

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "sess-12345",
                "query": "Show me the top 5 products by revenue",
                "intent": "data_analysis",
                "answer": "Here are the Top 5 products by SUM(revenue):\n1. **MacBook Pro**: 54,000.00\n2. **Dell XPS**: 38,000.00",
                "tool_calls": [
                    {
                        "tool_name": "aggregate_data",
                        "parameters": {"group_by_column": "product", "metric_column": "revenue", "top_k": 5},
                        "execution_time_ms": 12.5,
                        "success": True
                    }
                ],
                "citations": [
                    {
                        "file_id": "f8a910",
                        "file_name": "sales.csv",
                        "source_description": "Source: sales.csv (Aggregated Summary over product, revenue)"
                    }
                ],
                "chart": None,
                "duration_ms": 28.4
            }
        }
    )
