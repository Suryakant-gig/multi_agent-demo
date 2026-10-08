import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.storage.models import CitationModel
from app.storage.database import get_session_factory
from app.models.domain import CitationItem
from app.utils.logger import logger


class CitationRepository:
    """
    Repository for persisting citations in PostgreSQL.
    """

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def get_session(self) -> Session:
        return self._session_factory()

    def save_citations(self, conv_id: str, message_id: Optional[str], citations: List[CitationItem]) -> None:
        if not citations:
            return
        with self.get_session() as db:
            for c in citations:
                cite_id = f"cite_{uuid.uuid4().hex[:12]}"
                rec = CitationModel(
                    id=cite_id,
                    conversation_id=conv_id,
                    message_id=message_id,
                    citation_type=c.citation_type,
                    file_id=c.file_id,
                    page_number=c.page_number,
                    row_index=c.row_index,
                    url=c.url,
                    title=c.title,
                    domain=c.domain,
                    snippet=c.snippet
                )
                db.add(rec)
            db.commit()
            logger.info(f"Saved {len(citations)} citations in PostgreSQL for conversation {conv_id}")

    def get_citations(self, conv_id: str) -> List[CitationItem]:
        with self.get_session() as db:
            records = (
                db.query(CitationModel)
                .filter(CitationModel.conversation_id == conv_id)
                .all()
            )
            return [
                CitationItem(
                    file_id=r.file_id or "",
                    file_name=r.title or "",
                    row_index=r.row_index,
                    column_names=[],
                    snippet=r.snippet,
                    source_description=f"{r.title or ''} {r.domain or ''}".strip(),
                    citation_type=r.citation_type or "dataset",
                    page_number=r.page_number,
                    url=r.url,
                    title=r.title,
                    domain=r.domain
                )
                for r in records
            ]


citation_repository = CitationRepository()
