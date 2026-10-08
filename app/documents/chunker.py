import uuid
from typing import List, Dict, Any
from app.models.domain import DocumentChunk
from app.utils.config import settings


class DocumentChunker:
    """
    Splits extracted PDF text into semantically coherent overlapping chunks.
    Preserves document_id, file_name, page_number, chunk_id, and text for citations.
    """

    def __init__(
        self,
        chunk_size: int = settings.PDF_CHUNK_SIZE_CHARS,
        overlap: int = settings.PDF_CHUNK_OVERLAP_CHARS
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_document(
        self,
        document_id: str,
        file_name: str,
        pages: List[Dict[str, Any]]
    ) -> List[DocumentChunk]:
        """
        Chunks pages preserving page numbers.
        """
        all_chunks: List[DocumentChunk] = []

        for page in pages:
            page_num = page["page_number"]
            page_text = page.get("text", "").strip()

            if not page_text:
                continue

            # If page fits within chunk_size, keep as a single chunk
            if len(page_text) <= self.chunk_size:
                chunk = DocumentChunk(
                    chunk_id=f"{document_id}_p{page_num}_c1",
                    document_id=document_id,
                    file_name=file_name,
                    page_number=page_num,
                    text=page_text,
                    metadata={"page": page_num, "length": len(page_text)}
                )
                all_chunks.append(chunk)
                continue

            # Break page into overlapping windows
            start = 0
            chunk_idx = 1
            text_len = len(page_text)

            while start < text_len:
                end = min(start + self.chunk_size, text_len)
                
                # Attempt to break at paragraph or newline or space
                if end < text_len:
                    break_point = page_text.rfind("\n\n", start, end)
                    if break_point == -1 or break_point < start + (self.chunk_size // 2):
                        break_point = page_text.rfind(". ", start, end)
                    if break_point == -1 or break_point < start + (self.chunk_size // 2):
                        break_point = page_text.rfind(" ", start, end)
                    
                    if break_point != -1 and break_point > start:
                        end = break_point + 1

                chunk_str = page_text[start:end].strip()
                if chunk_str:
                    chunk = DocumentChunk(
                        chunk_id=f"{document_id}_p{page_num}_c{chunk_idx}",
                        document_id=document_id,
                        file_name=file_name,
                        page_number=page_num,
                        text=chunk_str,
                        metadata={"page": page_num, "chunk_index": chunk_idx}
                    )
                    all_chunks.append(chunk)
                    chunk_idx += 1

                start += max(self.chunk_size - self.overlap, 1)

        return all_chunks


document_chunker = DocumentChunker()
