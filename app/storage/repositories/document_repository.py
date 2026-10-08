import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.storage.models import DocumentModel, DocumentChunkModel, UploadedFileModel
from app.storage.database import get_session_factory
from app.models.domain import DocumentMetadata, DocumentChunk
from app.utils.logger import logger


class DocumentRepository:
    """
    Repository for documents and document chunks in PostgreSQL.
    """

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def get_session(self) -> Session:
        return self._session_factory()

    def save_document_metadata(
        self,
        doc_meta: DocumentMetadata,
        conv_id: str,
        storage_path: str = ""
    ) -> None:
        with self.get_session() as db:
            # 1. Uploaded file record
            file_rec = db.query(UploadedFileModel).filter(UploadedFileModel.id == doc_meta.document_id).first()
            if not file_rec:
                file_rec = UploadedFileModel(
                    id=doc_meta.document_id,
                    conversation_id=conv_id,
                    file_name=doc_meta.file_name,
                    file_type="pdf",
                    file_size=doc_meta.file_size_bytes,
                    storage_path=storage_path,
                    created_at=doc_meta.uploaded_at or datetime.datetime.utcnow()
                )
                db.merge(file_rec)
                db.flush()

            # 2. Document record
            doc_rec = DocumentModel(
                id=doc_meta.document_id,
                file_id=doc_meta.document_id,
                page_count=doc_meta.page_count,
                is_scanned=doc_meta.is_scanned,
                metadata_={
                    "chunk_count": doc_meta.chunk_count,
                    "file_name": doc_meta.file_name
                }
            )
            db.merge(doc_rec)
            db.commit()
            logger.info(f"Persisted PDF document metadata for {doc_meta.file_name} in PostgreSQL.")

    def save_chunks(self, chunks: List[DocumentChunk], session_id: str) -> None:
        if not chunks:
            return
        with self.get_session() as db:
            for c in chunks:
                chunk_rec = DocumentChunkModel(
                    id=f"{session_id}_{c.chunk_id}",
                    document_id=c.document_id,
                    chunk_id=c.chunk_id,
                    page_number=c.page_number,
                    content=c.text,
                    metadata_={
                        "session_id": session_id,
                        "file_name": c.file_name,
                        **(c.metadata or {})
                    }
                )
                db.merge(chunk_rec)
            db.commit()
            logger.info(f"Stored {len(chunks)} document chunks in PostgreSQL for conversation {session_id}")

    def get_chunks(self, session_id: str, document_id: Optional[str] = None) -> List[DocumentChunk]:
        with self.get_session() as db:
            query = db.query(DocumentChunkModel)
            if document_id:
                query = query.filter(DocumentChunkModel.document_id == document_id)
            records = query.order_by(DocumentChunkModel.page_number.asc(), DocumentChunkModel.chunk_id.asc()).all()
            
            # Filter by session_id in metadata if present
            results = []
            for r in records:
                meta = r.metadata_ or {}
                if meta.get("session_id") and meta.get("session_id") != session_id:
                    continue
                results.append(
                    DocumentChunk(
                        chunk_id=r.chunk_id,
                        document_id=r.document_id,
                        file_name=meta.get("file_name", "Document"),
                        page_number=r.page_number,
                        text=r.content,
                        metadata=meta
                    )
                )
            return results

    def get_chunks_by_page(self, session_id: str, page_number: int, document_id: Optional[str] = None) -> List[DocumentChunk]:
        with self.get_session() as db:
            query = db.query(DocumentChunkModel).filter(DocumentChunkModel.page_number == page_number)
            if document_id:
                query = query.filter(DocumentChunkModel.document_id == document_id)
            records = query.order_by(DocumentChunkModel.chunk_id.asc()).all()

            results = []
            for r in records:
                meta = r.metadata_ or {}
                if meta.get("session_id") and meta.get("session_id") != session_id:
                    continue
                results.append(
                    DocumentChunk(
                        chunk_id=r.chunk_id,
                        document_id=r.document_id,
                        file_name=meta.get("file_name", "Document"),
                        page_number=r.page_number,
                        text=r.content,
                        metadata=meta
                    )
                )
            return results

    def get_documents_for_conversation(self, conv_id: str) -> Dict[str, DocumentMetadata]:
        with self.get_session() as db:
            results = (
                db.query(DocumentModel, UploadedFileModel)
                .join(UploadedFileModel, DocumentModel.file_id == UploadedFileModel.id)
                .filter(UploadedFileModel.conversation_id == conv_id)
                .all()
            )
            docs = {}
            for doc, f in results:
                meta = doc.metadata_ or {}
                docs[f.id] = DocumentMetadata(
                    document_id=f.id,
                    file_name=f.file_name,
                    file_size_bytes=f.file_size or 0,
                    page_count=doc.page_count or 0,
                    chunk_count=meta.get("chunk_count", 0),
                    is_scanned=doc.is_scanned or False,
                    uploaded_at=f.created_at
                )
            return docs


document_repository = DocumentRepository()
