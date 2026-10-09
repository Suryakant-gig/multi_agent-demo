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
    RESEARCH = "research"
    WEB_SEARCH = "web_search"
    DOCUMENT_SEARCH = "document_search"
    DOCUMENT_EXTRACTION = "document_extraction"
    DATA_EXTRACTION = "data_extraction"
    HYBRID = "hybrid"


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


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    file_name: str
    page_number: int
    text: str
    document_order: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentMetadata(BaseModel):
    document_id: str
    file_name: str
    file_size_bytes: int
    page_count: int
    chunk_count: int
    is_scanned: bool = False
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class SourceItem(BaseModel):
    title: str
    url: str
    domain: str
    snippet: str = ""
    published_at: Optional[str] = None
    source_type: str = "website"  # "paper" | "documentation" | "article" | "website"
    relevance_score: float = 0.0


class CitationItem(BaseModel):
    file_id: str = ""
    file_name: str = ""
    row_index: Optional[int] = None
    column_names: List[str] = Field(default_factory=list)
    snippet: Optional[str] = None
    source_description: str = ""
    citation_type: str = "dataset"  # "dataset" | "pdf" | "web"
    page_number: Optional[int] = None
    url: Optional[str] = None
    title: Optional[str] = None
    domain: Optional[str] = None
    published_at: Optional[str] = None


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


class TablePayload(BaseModel):
    type: str = "table"
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    row_count: int = 0
    source: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskSource(BaseModel):
    type: str  # "spreadsheet" | "uploaded_pdf" | "web" | "database"
    file_id: Optional[str] = None
    filename: Optional[str] = None


class TaskPlan(BaseModel):
    task_type: str  # "document_extraction", "document_search", "data_extraction", "data_analysis", "research", "mixed", "direct_answer", "visualization", "schema_inspection"
    sources: List[TaskSource] = Field(default_factory=list)
    operation: str = "extract"  # "first_n", "top_n", "filter", "aggregate", "search", "extract", "search_and_synthesize", "visualize", "inspect_schema"
    requested_count: Optional[int] = None
    target_page: Optional[int] = None
    target_range: Optional[List[int]] = None  # e.g. [21, 30]
    ordering: Optional[str] = None  # "document_order", "source_order", "metric_desc", "metric_asc", "relevance"
    output_format: str = "table"  # "table", "research_list", "document_excerpts", "chart", "text"
    requires_web: bool = False
    requires_data: bool = False
    requires_document: bool = False
    metric_column: Optional[str] = None
    group_by_column: Optional[str] = None
    sort_column: Optional[str] = None
    ascending: bool = False
    filter_criteria: Optional[Dict[str, Any]] = None
    query: str = ""
    target_file_id: Optional[str] = None
    target_document_id: Optional[str] = None
    offset: int = 0
    is_follow_up: bool = False
    status: str = "valid"  # "valid", "missing_resource", "clarification_needed"
    missing_resource: Optional[str] = None  # "spreadsheet", "document"
    explanation: Optional[str] = None


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
    sources: List[SourceItem] = Field(default_factory=list)
    chart: Optional[ChartPayload] = None
    table: Optional[TablePayload] = None
    task_plan: Optional[TaskPlan] = None

