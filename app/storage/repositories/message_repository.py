import uuid
import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.storage.models import MessageModel
from app.storage.database import get_session_factory
from app.models.domain import MessageRecord, IntentType, ToolCallRecord, CitationItem, SourceItem, ChartPayload
from app.utils.logger import logger


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively converts non-serializable objects (e.g. Decimal) to JSON-compatible primitives.
    """
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(x) for x in obj]
    return obj


class MessageRepository:
    """
    Repository for persisting and querying conversation messages in PostgreSQL.
    """

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def get_session(self) -> Session:
        return self._session_factory()

    def add_message(self, conv_id: str, message: MessageRecord) -> str:
        with self.get_session() as db:
            msg_id = f"msg_{uuid.uuid4().hex[:12]}"
            
            # Serialize metadata (intent, tool_calls, citations, sources, chart)
            meta = {
                "intent": message.intent.value if message.intent else None,
                "tool_calls": [tc.model_dump() for tc in message.tool_calls],
                "citations": [c.model_dump() for c in message.citations],
                "sources": [s.model_dump() for s in message.sources],
                "chart": message.chart.model_dump() if message.chart else None
            }
            clean_meta = sanitize_for_json(meta)

            model = MessageModel(
                id=msg_id,
                conversation_id=conv_id,
                role=message.role,
                content=message.content,
                created_at=message.timestamp or datetime.datetime.utcnow(),
                metadata_=clean_meta
            )
            db.add(model)
            db.commit()
            return msg_id

    def get_messages(self, conv_id: str) -> List[MessageRecord]:
        with self.get_session() as db:
            records = (
                db.query(MessageModel)
                .filter(MessageModel.conversation_id == conv_id)
                .order_by(MessageModel.created_at.asc())
                .all()
            )
            result = []
            for r in records:
                meta = r.metadata_ or {}
                intent = None
                if meta.get("intent"):
                    try:
                        intent = IntentType(meta["intent"])
                    except Exception:
                        intent = None

                tool_calls = [ToolCallRecord(**tc) for tc in meta.get("tool_calls", [])]
                citations = [CitationItem(**c) for c in meta.get("citations", [])]
                sources = [SourceItem(**s) for s in meta.get("sources", [])]
                chart = ChartPayload(**meta["chart"]) if meta.get("chart") else None

                msg = MessageRecord(
                    role=r.role,
                    content=r.content,
                    timestamp=r.created_at,
                    intent=intent,
                    tool_calls=tool_calls,
                    citations=citations,
                    sources=sources,
                    chart=chart
                )
                result.append(msg)
            return result

    def count(self, conv_id: str) -> int:
        with self.get_session() as db:
            return db.query(MessageModel).filter(MessageModel.conversation_id == conv_id).count()


message_repository = MessageRepository()
