from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ChartType(str, Enum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"
    TIME_SERIES = "time_series"


class IntentType(str, Enum):
    DATA_ANALYSIS = "data_analysis"
    SEARCH_RETRIEVAL = "search_retrieval"
    VISUALIZATION = "visualization"
    SCHEMA_INSPECTION = "schema_inspection"
    DIRECT_ANSWER = "direct_answer"


class ColumnMetadata(BaseModel):
    name: str
    data_type: str
    null_count: int = 0
    unique_count: int = 0
    is_numeric: bool = False
    is_temporal: bool = False
    is_categorical: bool = False
    sample_values: List[Any] = Field(default_factory=list)


class DatasetMetadata(BaseModel):
    file_id: str
    file_name: str
    file_size_bytes: int
    row_count: int
    column_count: int
    columns: List[ColumnMetadata]
    db_table_name: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class CitationItem(BaseModel):
    file_id: str
    file_name: str
    row_index: Optional[int] = None
    column_names: List[str] = Field(default_factory=list)
    snippet: Optional[str] = None
    source_description: str = ""


class SearchResultItem(BaseModel):
    row_index: int
    score: float
    data: Dict[str, Any]
    citation: CitationItem


class ChartPayload(BaseModel):
    chart_type: ChartType
    title: str
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    aggregation: Optional[str] = None
    data_points: List[Dict[str, Any]] = Field(default_factory=list)
    image_base64: Optional[str] = None
    spec_json: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]
    result: Any
    execution_time_ms: float = 0.0
    success: bool = True
    error_message: Optional[str] = None


class MessageRecord(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    intent: Optional[IntentType] = None
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    citations: List[CitationItem] = Field(default_factory=list)
    chart: Optional[ChartPayload] = None
