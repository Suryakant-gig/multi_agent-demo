import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.storage.models import ConversationModel, MessageModel, UploadedFileModel
from app.storage.database import get_session_factory
from app.utils.logger import logger


class ConversationRepository:
    """
    CRUD repository for conversation records in PostgreSQL / central storage.
    """

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def get_session(self) -> Session:
        return self._session_factory()

    def create(self, conv_id: str, title: str = "New Chat") -> Dict[str, Any]:
        with self.get_session() as db:
            now = datetime.datetime.utcnow()
            conv = ConversationModel(
                id=conv_id,
                title=title or "New Chat",
                created_at=now,
                updated_at=now
            )
            db.merge(conv)
            db.commit()
            return {
                "id": conv_id,
                "title": title or "New Chat",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat()
            }

    def get(self, conv_id: str) -> Optional[Dict[str, Any]]:
        with self.get_session() as db:
            conv = db.query(ConversationModel).filter(ConversationModel.id == conv_id).first()
            if not conv:
                return None
            return {
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat()
            }

    def list_all(self) -> List[Dict[str, Any]]:
        with self.get_session() as db:
            convs = db.query(ConversationModel).order_by(ConversationModel.updated_at.desc()).all()
            result = []
            for c in convs:
                msg_count = db.query(MessageModel).filter(MessageModel.conversation_id == c.id).count()
                file_count = db.query(UploadedFileModel).filter(UploadedFileModel.conversation_id == c.id).count()
                result.append({
                    "conversation_id": c.id,
                    "session_id": c.id,
                    "title": c.title,
                    "message_count": msg_count,
                    "file_count": file_count,
                    "created_at": c.created_at.isoformat(),
                    "updated_at": c.updated_at.isoformat()
                })
            return result

    def update_title(self, conv_id: str, title: str) -> bool:
        with self.get_session() as db:
            conv = db.query(ConversationModel).filter(ConversationModel.id == conv_id).first()
            if conv:
                conv.title = title
                conv.updated_at = datetime.datetime.utcnow()
                db.commit()
                return True
            return False

    def touch(self, conv_id: str) -> None:
        with self.get_session() as db:
            conv = db.query(ConversationModel).filter(ConversationModel.id == conv_id).first()
            if conv:
                conv.updated_at = datetime.datetime.utcnow()
                db.commit()

    def delete(self, conv_id: str) -> bool:
        with self.get_session() as db:
            conv = db.query(ConversationModel).filter(ConversationModel.id == conv_id).first()
            if conv:
                db.delete(conv)
                db.commit()
                logger.info(f"Deleted conversation {conv_id} and all associated records from database.")
                return True
            return False


conversation_repository = ConversationRepository()
