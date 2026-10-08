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
