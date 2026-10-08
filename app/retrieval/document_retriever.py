import re
import math
from typing import List, Dict, Any, Optional
from app.models.domain import DocumentChunk, CitationItem
from app.documents.document_store import document_store
from app.utils.logger import logger


class DocumentRetriever:
    """
    Retrieves relevant PDF document chunks matching user queries or page requests.
    Calculates relevance scores using term-frequency and keyword density.
    Outputs structured citations with exact page numbers.
    """

    STOP_WORDS = {
        "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
        "and", "or", "is", "are", "was", "were", "this", "that", "it", "what", "how",
        "why", "can", "could", "tell", "me", "about", "summarize", "find", "show", "page"
    }

    def tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower())
        return [t for t in tokens if t not in self.STOP_WORDS]

    def extract_page_request(self, query: str) -> Optional[int]:
        """Detects if user is asking for a specific page, e.g., 'page 10', 'page 7'."""
        match = re.search(r"\bpage\s+(\d+)\b", query.lower())
        if match:
            return int(match.group(1))
        return None

    def search_documents(
        self,
        session_id: str,
        query: str,
        top_k: int = 4,
        document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches documents in session for relevant chunks.
        Returns list of {"chunk": DocumentChunk, "score": float, "citation": CitationItem}.
        """
        # 1. Check for specific page request
        target_page = self.extract_page_request(query)
        if target_page is not None:
            page_chunks = document_store.get_chunks_by_page(
                session_id=session_id,
                page_number=target_page,
                document_id=document_id
            )
            if page_chunks:
                results = []
                for chunk in page_chunks[:top_k]:
                    snippet = chunk.text[:220] + "..." if len(chunk.text) > 220 else chunk.text
                    citation = CitationItem(
                        file_id=chunk.document_id,
                        file_name=chunk.file_name,
                        page_number=chunk.page_number,
                        snippet=snippet,
                        source_description=f"Source: {chunk.file_name}, Page {chunk.page_number}",
                        citation_type="pdf"
                    )
                    results.append({
                        "chunk": chunk,
                        "score": 1.0,
                        "citation": citation
                    })
                return results

        # 2. General semantic keyword retrieval across all session chunks
        chunks = document_store.get_chunks(session_id=session_id, document_id=document_id)
        if not chunks:
            return []

        query_tokens = self.tokenize(query)
        if not query_tokens:
            # Fallback to first top_k chunks
            return [
                {
                    "chunk": c,
                    "score": 0.5,
                    "citation": CitationItem(
                        file_id=c.document_id,
                        file_name=c.file_name,
                        page_number=c.page_number,
                        snippet=c.text[:200] + "...",
                        source_description=f"Source: {c.file_name}, Page {c.page_number}",
                        citation_type="pdf"
                    )
                }
                for c in chunks[:top_k]
            ]

        scored_chunks = []
        for chunk in chunks:
            chunk_tokens = self.tokenize(chunk.text)
            if not chunk_tokens:
                continue

            # Calculate match score based on token frequency and coverage
            matches = sum(1 for t in query_tokens if t in chunk_tokens)
            if matches > 0:
                coverage = matches / len(query_tokens)
                density = sum(chunk_tokens.count(t) for t in query_tokens) / len(chunk_tokens)
                score = round((coverage * 0.7 + min(density * 10, 1.0) * 0.3), 3)
                scored_chunks.append((score, chunk))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored_chunks[:top_k]

        results = []
        for score, chunk in top_candidates:
            snippet = chunk.text[:220] + "..." if len(chunk.text) > 220 else chunk.text
            citation = CitationItem(
                file_id=chunk.document_id,
                file_name=chunk.file_name,
                page_number=chunk.page_number,
                snippet=snippet,
                source_description=f"Source: {chunk.file_name}, Page {chunk.page_number}",
                citation_type="pdf"
            )
            results.append({
                "chunk": chunk,
                "score": score,
                "citation": citation
            })

        return results


document_retriever = DocumentRetriever()
