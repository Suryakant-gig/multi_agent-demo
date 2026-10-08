from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from app.models.domain import (
    DatasetMetadata,
    DocumentMetadata,
    MessageRecord,
    ToolCallRecord,
    ChartPayload
)


class ConversationState(BaseModel):
    session_id: str
    conversation_id: str
    title: str = "New Chat"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Tabular files associated with session
    files: Dict[str, DatasetMetadata] = Field(default_factory=dict)
    active_file_id: Optional[str] = None

    # PDF and text documents associated with session
    documents: Dict[str, DocumentMetadata] = Field(default_factory=dict)
    active_document_id: Optional[str] = None

    # Conversation history & tool trace
    messages: List[MessageRecord] = Field(default_factory=list)
    tool_history: List[ToolCallRecord] = Field(default_factory=list)

    # Context cache for cross-turn coreference resolution
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    last_query_result: Optional[Any] = None
    last_query_summary: Optional[str] = None
    last_tool_call: Optional[ToolCallRecord] = None
    last_chart: Optional[ChartPayload] = None

    def __init__(self, **data):
        if "conversation_id" not in data and "session_id" in data:
            data["conversation_id"] = data["session_id"]
        elif "session_id" not in data and "conversation_id" in data:
            data["session_id"] = data["conversation_id"]
        super().__init__(**data)

    def touch(self):
        self.updated_at = datetime.utcnow()

    @property
    def active_dataset(self) -> Optional[DatasetMetadata]:
        if self.active_file_id and self.active_file_id in self.files:
            return self.files[self.active_file_id]
        return None

    @property
    def active_documents(self) -> List[DocumentMetadata]:
        return list(self.documents.values())

    @property
    def uploaded_files(self) -> List[Dict[str, Any]]:
        file_list = []
        for f in self.files.values():
            file_list.append({
                "file_id": f.file_id,
                "file_name": f.file_name,
                "file_type": "tabular",
                "row_count": f.row_count,
                "size_bytes": f.file_size_bytes
            })
        for d in self.documents.values():
            file_list.append({
                "file_id": d.document_id,
                "file_name": d.file_name,
                "file_type": "pdf",
                "page_count": d.page_count,
                "size_bytes": d.file_size_bytes,
                "is_scanned": d.is_scanned
            })
        return file_list

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": len(self.messages),
            "file_count": len(self.files) + len(self.documents),
            "has_dataset": bool(self.files),
            "has_documents": bool(self.documents)
        }

    def to_detail_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [m.model_dump() for m in self.messages],
            "uploaded_files": self.uploaded_files,
            "active_dataset": self.active_dataset.model_dump() if self.active_dataset else None,
            "active_documents": [d.model_dump() for d in self.active_documents],
            "tool_history": [t.model_dump() for t in self.tool_history],
            "context": self.context,
            "metadata": self.metadata
        }


# Backwards compatibility alias
SessionState = ConversationState
