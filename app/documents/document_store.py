import threading
from typing import List, Optional
from app.models.domain import DocumentChunk
from app.storage.repositories.document_repository import document_repository
from app.utils.logger import logger


class DocumentStore:
    """
    Store for document chunks indexed per session/conversation in PostgreSQL / central storage.
    Ensures complete isolation so documents from one conversation cannot be accessed by another.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DocumentStore, cls).__new__(cls)
        return cls._instance

    def store_chunks(self, session_id: str, chunks: List[DocumentChunk]) -> None:
        """
        Stores extracted document chunks in PostgreSQL associated with the conversation session.
        """
        if not chunks:
            return
        document_repository.save_chunks(chunks, session_id=session_id)
        logger.info(f"Stored {len(chunks)} document chunks in PostgreSQL for session '{session_id}'")

        try:
            from app.state.session_manager import session_manager
            from app.models.domain import DocumentMetadata
            session = session_manager.get_session(session_id)
            for c in chunks:
                if c.document_id not in session.documents:
                    doc_meta = DocumentMetadata(
                        document_id=c.document_id,
                        file_name=c.file_name,
                        file_size_bytes=sum(len(chk.text.encode('utf-8')) for chk in chunks if chk.document_id == c.document_id),
                        page_count=max(chk.page_number for chk in chunks if chk.document_id == c.document_id),
                        chunk_count=sum(1 for chk in chunks if chk.document_id == c.document_id)
                    )
                    session.documents[c.document_id] = doc_meta
                    if not session.active_document_id:
                        session.active_document_id = c.document_id
        except Exception as e:
            logger.debug(f"Could not auto-register document in session: {e}")

    def get_chunks(self, session_id: str, document_id: Optional[str] = None) -> List[DocumentChunk]:
        """
        Retrieves document chunks for a session, optionally filtered by document_id.
        """
        return document_repository.get_chunks(session_id=session_id, document_id=document_id)

    def get_chunks_by_page(self, session_id: str, page_number: int, document_id: Optional[str] = None) -> List[DocumentChunk]:
        """
        Retrieves document chunks for a session by specific page number.
        """
        return document_repository.get_chunks_by_page(session_id=session_id, page_number=page_number, document_id=document_id)


document_store = DocumentStore()
