import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.storage.models import ResearchSourceModel
from app.storage.database import get_session_factory
from app.models.domain import SourceItem
from app.utils.logger import logger


class ResearchRepository:
    """
    Repository for persisting research agent findings and source bibliographies in PostgreSQL.
    """

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def get_session(self) -> Session:
        return self._session_factory()

    def save_sources(self, conv_id: str, sources: List[SourceItem]) -> None:
        if not sources:
            return
        with self.get_session() as db:
            for s in sources:
                src_id = f"src_{uuid.uuid4().hex[:12]}"
                rec = ResearchSourceModel(
                    id=src_id,
                    conversation_id=conv_id,
                    title=s.title,
                    url=s.url,
                    domain=s.domain,
                    source_type=s.source_type,
                    published_at=s.published_at,
                    relevance_score=s.relevance_score,
                    metadata_={"snippet": s.snippet}
                )
                db.add(rec)
            db.commit()
            logger.info(f"Saved {len(sources)} research sources in PostgreSQL for conversation {conv_id}")

    def get_sources(self, conv_id: str) -> List[SourceItem]:
        with self.get_session() as db:
            records = (
                db.query(ResearchSourceModel)
                .filter(ResearchSourceModel.conversation_id == conv_id)
                .all()
            )
            return [
                SourceItem(
                    title=r.title,
                    url=r.url,
                    domain=r.domain,
                    snippet=(r.metadata_ or {}).get("snippet", ""),
                    published_at=r.published_at,
                    source_type=r.source_type,
                    relevance_score=r.relevance_score or 0.0
                )
                for r in records
            ]


research_repository = ResearchRepository()
