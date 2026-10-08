import datetime
from sqlalchemy import Column, String, Integer, BigInteger, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.storage.database import Base


class ConversationModel(Base):
    __tablename__ = "conversations"

    id = Column(String(64), primary_key=True, index=True)
    title = Column(String(255), nullable=False, default="New Chat")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    messages = relationship("MessageModel", back_populates="conversation", cascade="all, delete-orphan", order_by="MessageModel.created_at")
    files = relationship("UploadedFileModel", back_populates="conversation", cascade="all, delete-orphan")
    research_sources = relationship("ResearchSourceModel", back_populates="conversation", cascade="all, delete-orphan")
    tool_calls = relationship("ToolCallModel", back_populates="conversation", cascade="all, delete-orphan")
    citations = relationship("CitationModel", back_populates="conversation", cascade="all, delete-orphan")


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(String(64), primary_key=True, index=True)
    conversation_id = Column(String(64), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False)  # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)

    conversation = relationship("ConversationModel", back_populates="messages")


class UploadedFileModel(Base):
    __tablename__ = "uploaded_files"

    id = Column(String(64), primary_key=True, index=True)
    conversation_id = Column(String(64), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(32), nullable=False)  # "csv", "xlsx", "xls", "pdf"
    file_size = Column(BigInteger, default=0)
    storage_path = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    conversation = relationship("ConversationModel", back_populates="files")
    dataset = relationship("DatasetModel", back_populates="file", uselist=False, cascade="all, delete-orphan")
    document = relationship("DocumentModel", back_populates="file", uselist=False, cascade="all, delete-orphan")


class DatasetModel(Base):
    __tablename__ = "datasets"

    id = Column(String(64), primary_key=True, index=True)
    file_id = Column(String(64), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False, index=True)
    table_name = Column(String(128), nullable=False)
    row_count = Column(Integer, default=0)
    column_count = Column(Integer, default=0)
    schema_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    file = relationship("UploadedFileModel", back_populates="dataset")


class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True, index=True)
    file_id = Column(String(64), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False, index=True)
    page_count = Column(Integer, default=0)
    is_scanned = Column(Boolean, default=False)
    metadata_ = Column("metadata", JSON, default=dict)

    file = relationship("UploadedFileModel", back_populates="document")


class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"

    id = Column(String(64), primary_key=True, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    chunk_id = Column(String(64), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)


class ResearchSourceModel(Base):
    __tablename__ = "research_sources"

    id = Column(String(64), primary_key=True, index=True)
    conversation_id = Column(String(64), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    url = Column(Text, nullable=False)
    domain = Column(String(255), nullable=False)
    source_type = Column(String(64), default="website")
    published_at = Column(String(64), nullable=True)
    relevance_score = Column(Float, default=0.0)
    metadata_ = Column("metadata", JSON, default=dict)

    conversation = relationship("ConversationModel", back_populates="research_sources")


class ToolCallModel(Base):
    __tablename__ = "tool_calls"

    id = Column(String(64), primary_key=True, index=True)
    conversation_id = Column(String(64), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(64), nullable=False)
    parameters = Column(JSON, default=dict)
    result_metadata = Column(JSON, default=dict)
    execution_time_ms = Column(Float, default=0.0)
    success = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    conversation = relationship("ConversationModel", back_populates="tool_calls")


class CitationModel(Base):
    __tablename__ = "citations"

    id = Column(String(64), primary_key=True, index=True)
    conversation_id = Column(String(64), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(64), nullable=True, index=True)
    citation_type = Column(String(32), nullable=False)  # "dataset" | "pdf" | "web"
    file_id = Column(String(64), nullable=True)
    page_number = Column(Integer, nullable=True)
    row_index = Column(Integer, nullable=True)
    url = Column(Text, nullable=True)
    title = Column(String(512), nullable=True)
    domain = Column(String(255), nullable=True)
    snippet = Column(Text, nullable=True)

    conversation = relationship("ConversationModel", back_populates="citations")
