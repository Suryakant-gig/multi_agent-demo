from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from app.models.domain import DatasetMetadata, MessageRecord, ToolCallRecord, ChartPayload


class SessionState(BaseModel):
    session_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Files associated with session
    files: Dict[str, DatasetMetadata] = Field(default_factory=dict)
    active_file_id: Optional[str] = None
    
    # Conversation history
    messages: List[MessageRecord] = Field(default_factory=list)
    
    # Context cache for coreference resolution (e.g. "top 5 products", "that")
    last_query_result: Optional[Any] = None
    last_query_summary: Optional[str] = None
    last_tool_call: Optional[ToolCallRecord] = None
    last_chart: Optional[ChartPayload] = None
    
    def touch(self):
        self.updated_at = datetime.utcnow()
