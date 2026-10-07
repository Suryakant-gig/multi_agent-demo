from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict
from app.models.domain import ChartType


class ChartRequest(BaseModel):
    session_id: str = Field(..., description="Active session ID containing the file.")
    chart_type: ChartType = Field(..., description="Chart type: bar, line, pie, scatter, histogram, or time_series.")
    x_column: str = Field(..., description="Column name for X axis or categories.")
    y_column: Optional[str] = Field(None, description="Optional column name for Y axis or metrics.")
    aggregation: Optional[str] = Field("SUM", description="Aggregation function (SUM, AVG, COUNT, MIN, MAX).")
    title: Optional[str] = Field(None, description="Custom title for chart.")
    top_k: int = Field(10, ge=1, le=100, description="Max categories to plot.")
    file_id: Optional[str] = Field(None, description="Target specific file if multiple uploaded.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "sess-12345",
                "chart_type": "bar",
                "x_column": "product",
                "y_column": "revenue",
                "aggregation": "SUM",
                "title": "Revenue by Product",
                "top_k": 5
            }
        }
    )


class ChartResponse(BaseModel):
    chart_type: str
    title: str
    x_column: str
    y_column: Optional[str] = None
    aggregation: Optional[str] = None
    image_base64: str
    spec_json: Optional[Dict[str, Any]] = None
    data_points: List[Dict[str, Any]]
    metadata: Dict[str, Any]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "chart_type": "bar",
                "title": "Revenue by Product",
                "x_column": "product",
                "y_column": "revenue",
                "aggregation": "SUM",
                "image_base64": "data:image/png;base64,iVBORw0KGgoAAA...",
                "spec_json": {"type": "bar"},
                "data_points": [{"product": "Laptop", "revenue": 1000}],
                "metadata": {"points_rendered": 1}
            }
        }
    )
